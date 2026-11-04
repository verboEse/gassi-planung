from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from cryptography.hazmat.primitives import serialization
from fastapi.testclient import TestClient
from py_vapid import Vapid
from itsdangerous import TimestampSigner

from app import main as main_module
from app.auth import hash_password, verify_password
from app.db import Database
from app.main import avatar_mime_type, create_app


def configure_test_vapid(monkeypatch):
    vapid = Vapid()
    vapid.generate_keys()
    public_key = base64.urlsafe_b64encode(
        vapid.public_key.public_bytes(
            serialization.Encoding.X962,
            serialization.PublicFormat.UncompressedPoint,
        )
    ).rstrip(b"=").decode()
    private_key = base64.b64encode(vapid.private_pem()).decode()
    monkeypatch.setenv("GASSI_VAPID_PUBLIC_KEY", public_key)
    monkeypatch.setenv("GASSI_VAPID_PRIVATE_KEY_B64", private_key)
    monkeypatch.setenv("GASSI_VAPID_SUBJECT", "mailto:admin@example.test")
    return public_key


def test_password_hash_uses_scrypt_and_verifies():
    encoded = hash_password("a long family password")
    assert encoded.startswith("scrypt$")
    assert verify_password("a long family password", encoded)
    assert not verify_password("wrong password", encoded)


def test_auth_ownership_and_calendar_token_rotation(tmp_path, monkeypatch):
    monkeypatch.setattr(main_module, "current_iso_week", lambda: (2026, 42))
    secret = "test-session-secret-that-is-long-enough"
    monkeypatch.setenv("GASSI_SESSION_SECRET", secret)
    monkeypatch.setenv("GASSI_BASE_URL", "https://gassiplan.example")

    db_path = tmp_path / "auth.sqlite3"
    db = Database(db_path)
    owner = db.add_account("Jan", hash_password("jan family password"))
    other = db.add_account("Laura", hash_password("laura family password"))
    db.set_pref(owner["id"], 1, "morning", 3)
    db.set_pref(other["id"], 1, "morning", 1)

    app = create_app(str(db_path))
    with TestClient(app) as client:
        assert client.get("/api/week").status_code == 401
        session = base64.b64encode(json.dumps({
            "person_id": owner["id"], "auth_version": 1,
        }).encode())
        client.cookies.set("session", TimestampSigner(secret).sign(session).decode())

        week_response = client.get("/api/week")
        assert week_response.status_code == 200, week_response.text
        week = week_response.json()
        assert list(week["prefs"]) == [str(owner["id"])]
        assert client.put("/api/prefs", json={
            "person_id": owner["id"], "weekday": 7, "slot": "evening", "value": 3,
        }).status_code == 200
        frozen_week = client.get("/api/week?year=2026&week=42").json()
        assert frozen_week["plan"] == week["plan"]
        assert frozen_week["prefs"][str(owner["id"])]["7"]["evening"] == 3
        assert all(
            "pref" not in slot or slot["pref"] is None
            for day in frozen_week["plan"]["days"]
            for slot in day["slots"].values()
            if slot.get("person_id") == other["id"]
        )
        other_slots = [
            slot
            for day in week["plan"]["days"]
            for slot in day["slots"].values()
            if slot.get("person_id") == other["id"]
        ]
        assert other_slots and all(slot["pref"] is None for slot in other_slots)
        assert client.put("/api/prefs", json={
            "person_id": other["id"], "weekday": 1, "slot": "noon", "value": 3,
        }).status_code == 403

        old_url = client.get("/api/me").json()["calendar_url"]
        feed_path = urlsplit(old_url).path
        feed = client.get(feed_path)
        assert feed.status_code == 200
        head = client.head(feed_path)
        assert head.status_code == 200
        assert head.headers["content-type"].startswith("text/calendar")
        assert head.headers["content-length"] == feed.headers["content-length"]
        new_url = client.post("/api/me/calendar-token").json()["calendar_url"]
        assert client.get(urlsplit(old_url).path).status_code == 404
        assert client.get(urlsplit(new_url).path).status_code == 200


def test_takeover_endpoints_require_authenticated_identity(tmp_path, monkeypatch):
    monkeypatch.setattr(main_module, "current_iso_week", lambda: (2026, 1))
    monkeypatch.setattr(
        main_module,
        "berlin_now",
        lambda: datetime(2026, 1, 1, 6, 30, tzinfo=ZoneInfo("Europe/Berlin")),
    )
    secret = "test-session-secret-that-is-long-enough"
    monkeypatch.setenv("GASSI_SESSION_SECRET", secret)
    db_path = tmp_path / "takeover-auth.sqlite3"
    db = Database(db_path)
    jan = db.add_account("Jan", hash_password("jan family password"))
    laura = db.add_account("Laura", hash_password("laura family password"))
    app = create_app(str(db_path))

    with TestClient(app, base_url="https://testserver") as client:
        body = {"date": "2026-01-01", "slot": "morning"}
        assert client.get("/api/walk-takeovers").status_code == 401
        assert client.post("/api/walk-takeovers", json=body).status_code == 401
        assert client.post("/auth/login", json={
            "display_name": "Jan", "password": "jan family password",
        }).status_code == 200
        day = next(
            item for item in client.get("/api/plan?year=2026&week=1").json()["days"]
            if item["date"] == "2026-01-01"
        )
        assignee_id = day["slots"]["morning"]["person_id"]
        requester = laura if assignee_id == jan["id"] else jan
        assignee = jan if assignee_id == jan["id"] else laura
        assert client.post("/auth/logout").status_code == 204
        assert client.post("/auth/login", json={
            "display_name": requester["name"],
            "password": f"{requester['name'].lower()} family password",
        }).status_code == 200
        assert client.post("/api/walk-takeovers", json={
            **body, "person_id": assignee["id"],
        }).status_code == 403
        requested = client.post("/api/walk-takeovers", json=body)
        assert requested.status_code == 201, requested.text
        request_id = requested.json()["request"]["id"]
        assert client.put(f"/api/walk-takeovers/{request_id}", json={
            "approved": True,
        }).status_code == 404

        assert client.post("/auth/logout").status_code == 204
        assert client.post("/auth/login", json={
            "display_name": assignee["name"],
            "password": f"{assignee['name'].lower()} family password",
        }).status_code == 200
        assert client.put(f"/api/walk-takeovers/{request_id}", json={
            "person_id": requester["id"], "approved": True,
        }).status_code == 403
        assert client.put(f"/api/walk-takeovers/{request_id}", json={
            "approved": True,
        }).status_code == 200


def test_push_subscription_endpoints_are_authenticated_and_owned(tmp_path, monkeypatch):
    secret = "test-session-secret-that-is-long-enough"
    monkeypatch.setenv("GASSI_SESSION_SECRET", secret)
    monkeypatch.setenv("GASSI_BASE_URL", "https://gassiplan.example")
    public_key = configure_test_vapid(monkeypatch)
    db_path = tmp_path / "push-subscriptions.sqlite3"
    db = Database(db_path)
    owner = db.add_account("Jan", hash_password("jan family password"))
    other = db.add_account("Laura", hash_password("laura family password"))
    app = create_app(str(db_path))
    payload = {
        "endpoint": "https://fcm.googleapis.com/fcm/send/test-token",
        "keys": {
            "p256dh": base64.urlsafe_b64encode(b"\x04" + b"p" * 64).rstrip(b"=").decode(),
            "auth": base64.urlsafe_b64encode(b"a" * 16).rstrip(b"=").decode(),
        },
    }

    with TestClient(app, base_url="https://testserver") as client:
        assert client.get("/api/push/public-key").status_code == 401
        assert client.post("/api/push/subscriptions", json=payload).status_code == 401
        assert client.post("/auth/login", json={
            "display_name": "Jan", "password": "jan family password",
        }).status_code == 200
        assert client.get("/api/push/public-key").json() == {
            "public_key": public_key,
        }
        assert client.post("/api/push/subscriptions", json=payload).status_code == 201
        assert client.post("/api/push/subscriptions", json={
            **payload, "endpoint": "https://example.com/push",
        }).status_code == 422
        assert client.post("/api/push/subscriptions", json={
            **payload, "keys": {**payload["keys"], "p256dh": "invalid"},
        }).status_code == 422

        client.post("/auth/logout")
        assert client.post("/auth/login", json={
            "display_name": "Laura", "password": "laura family password",
        }).status_code == 200
        assert client.request(
            "DELETE", "/api/push/subscriptions", json={"endpoint": payload["endpoint"]}
        ).status_code == 404
        assert len(db.list_push_subscriptions(owner["id"])) == 1

        client.post("/auth/logout")
        assert client.post("/auth/login", json={
            "display_name": "Jan", "password": "jan family password",
        }).status_code == 200
        assert client.request(
            "DELETE", "/api/push/subscriptions", json={"endpoint": payload["endpoint"]}
        ).status_code == 204
        assert db.list_push_subscriptions(owner["id"]) == []


def test_service_worker_is_root_scoped(tmp_path):
    app = create_app(str(tmp_path / "service-worker.sqlite3"), auth_enabled=False)
    with TestClient(app) as client:
        response = client.get("/service-worker.js")
    assert response.status_code == 200
    assert response.headers["service-worker-allowed"] == "/"
    assert 'addEventListener("push"' in response.text


def test_gamification_requires_auth_and_own_completion(tmp_path, monkeypatch):
    monkeypatch.setenv("GASSI_SESSION_SECRET", "test-session-secret-that-is-long-enough")
    monkeypatch.setattr(
        main_module,
        "berlin_now",
        lambda: datetime(2026, 10, 12, 6, 30, tzinfo=ZoneInfo("Europe/Berlin")),
    )
    db_path = tmp_path / "gamification-auth.sqlite3"
    db = Database(db_path)
    owner = db.add_account("Jan", hash_password("jan family password"))
    other = db.add_account("Laura", hash_password("laura family password"))
    app = create_app(str(db_path))

    with TestClient(app) as client:
        assert client.get("/api/gamification").status_code == 401
        assert client.post("/auth/login", json={
            "display_name": "Jan", "password": "jan family password",
        }).status_code == 200
        foreign = client.post(f"/api/walks/start?person_id={other['id']}")
        assert foreign.status_code == 403
        own = client.post("/api/walks/start")
        assert own.status_code == 200
        monkeypatch.setattr(
            main_module,
            "berlin_now",
            lambda: datetime(2026, 10, 12, 7, 0, tzinfo=ZoneInfo("Europe/Berlin")),
        )
        assert client.post("/api/walks/end").status_code == 200
        assert db.add_walk_completion(other["id"], "2026-10-12", "noon", "manual")
        progress = client.get("/api/gamification").json()
        assert {person["name"] for person in progress["persons"]} == {"Jan", "Laura"}
        assert {(row["person_id"], row["slot"]) for row in progress["completions"]} == {
            (owner["id"], "morning"),
            (other["id"], "noon"),
        }
        assert client.delete(
            f"/api/completions/2026-10-12/morning?person_id={other['id']}"
        ).status_code == 403


def test_avatar_format_detection_accepts_only_bounded_image_headers():
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
    jpeg = bytes.fromhex(
        "ffd8 ffc0 0011 08 0001 0001 03 011100 021100 031100 ffd9"
    )
    webp = (
        b"RIFF" + (22).to_bytes(4, "little") + b"WEBPVP8X"
        + (10).to_bytes(4, "little") + bytes(10)
    )
    oversized_png = bytearray(png)
    oversized_png[16:20] = (5000).to_bytes(4, "big")
    assert avatar_mime_type(png) == "image/png"
    assert avatar_mime_type(jpeg) == "image/jpeg"
    assert avatar_mime_type(webp) == "image/webp"
    assert avatar_mime_type(bytes(oversized_png)) is None
    assert avatar_mime_type(b"<svg/>") is None


def test_profile_avatar_upload_is_validated_and_account_scoped(tmp_path, monkeypatch):
    monkeypatch.setenv("GASSI_SESSION_SECRET", "test-session-secret-that-is-long-enough")
    db_path = tmp_path / "avatar-api.sqlite3"
    db = Database(db_path)
    jan = db.add_account("Jan", hash_password("jan family password"))
    laura = db.add_account("Laura", hash_password("laura family password"))
    app = create_app(str(db_path))
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )

    with TestClient(app) as client:
        assert client.put("/api/profile/avatar", content=png).status_code == 401
        assert client.post("/auth/login", json={
            "display_name": "Jan", "password": "jan family password",
        }).status_code == 200
        uploaded = client.put(
            "/api/profile/avatar", content=png, headers={"Content-Type": "image/png"}
        )
        assert uploaded.status_code == 200, uploaded.text
        assert uploaded.json()["avatar_url"]
        image = client.get("/api/profile/avatar")
        assert image.status_code == 200
        assert image.headers["content-type"] == "image/png"
        assert image.headers["x-content-type-options"] == "nosniff"
        assert image.content == png
        assert client.put(
            "/api/profile/avatar", content=b"<svg/>", headers={"Content-Type": "image/svg+xml"}
        ).status_code == 415
        assert client.put(
            "/api/profile/avatar", content=png, headers={"Content-Type": "image/jpeg"}
        ).status_code == 422
        too_large = client.put(
            "/api/profile/avatar",
            content=png + b"0" * (2 * 1024 * 1024),
            headers={"Content-Type": "image/png"},
        )
        assert too_large.status_code == 413
        assert client.delete("/api/profile/avatar").status_code == 204
        assert client.get("/api/profile/avatar").status_code == 404
        with db._connect() as con:
            assert con.execute(
                "SELECT avatar_data FROM persons WHERE id = ?", (laura["id"],)
            ).fetchone()[0] is None
        assert jan["id"] != laura["id"]


def test_profile_api_and_preferences_are_account_scoped(tmp_path, monkeypatch):
    monkeypatch.setenv("GASSI_SESSION_SECRET", "test-session-secret-that-is-long-enough")
    db_path = tmp_path / "profile-api.sqlite3"
    db = Database(db_path)
    jan = db.add_account("Jan", hash_password("jan family password"))
    laura = db.add_account("Laura", hash_password("laura family password"))
    app = create_app(str(db_path))

    with TestClient(app) as client:
        assert client.get("/api/profile").status_code == 401
        assert client.post("/auth/login", json={
            "display_name": "Jan", "password": "jan family password",
        }).status_code == 200
        profile = client.get("/api/profile")
        assert profile.status_code == 200
        assert profile.json()["id"] == jan["id"]
        assert profile.json()["level_name"] == "Gassi-Starter"
        updated = client.patch("/api/profile/preferences", json={
            "badge_visibility": True, "push_enabled": True,
        })
        assert updated.status_code == 200
        assert updated.json()["badge_visibility"] is True
        assert updated.json()["push_enabled"] is True
        updated = client.patch("/api/profile/preferences", json={"reminders_enabled": True})
        assert updated.status_code == 200
        assert updated.json()["reminders_enabled"] is True
        with db._connect() as con:
            values = con.execute(
                "SELECT badge_visibility, push_enabled, reminders_enabled "
                "FROM persons WHERE id = ?", (laura["id"],)
            ).fetchone()
        assert tuple(values) == (0, 0, 0)


def test_badge_catalog_seasons_and_opt_in_participants(tmp_path, monkeypatch):
    monkeypatch.setenv("GASSI_SESSION_SECRET", "test-session-secret-that-is-long-enough")
    monkeypatch.setattr(
        main_module,
        "berlin_now",
        lambda: datetime(2026, 11, 3, 12, 0, tzinfo=ZoneInfo("Europe/Berlin")),
    )
    db_path = tmp_path / "badge-catalog.sqlite3"
    db = Database(db_path)
    jan = db.add_account("Jan", hash_password("jan family password"))
    laura = db.add_account("Laura", hash_password("laura family password"))
    db.award_badges(laura["id"], ["first-walk"])
    avatar_png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
    assert db.save_avatar(laura["id"], avatar_png, "image/png")
    assert db.add_walk_completion(jan["id"], "2026-02-14", "morning", "manual")
    app = create_app(str(db_path))

    with TestClient(app) as client:
        assert client.post("/auth/login", json={
            "display_name": "Jan", "password": "jan family password",
        }).status_code == 200
        current = client.get("/api/badges").json()
        assert current["progress"]["available"] == 15
        current_ids = {badge["id"] for badge in current["badges"]}
        assert {
            "first-shared-walk", "ten-shared-walks", "fifty-shared-walks",
            "three-person-walk", "four-plus-walk",
            "st-nicholas-walk-2026", "winter-solstice-walk-2026",
            "new-year-walk-2027", "valentines-walk-2027",
            "spring-walk-2027", "earth-day-walk-2027",
        } <= current_ids
        assert "summer-solstice-walk-2027" not in current_ids
        assert "valentines-walk-2026" not in current_ids
        one_off_badge = next(
            badge for badge in current["badges"] if badge["id"] == "valentines-walk-2027"
        )
        assert one_off_badge["show_progress"] is False
        assert one_off_badge["art_key"] == "heart-paws"
        category_ids = {category["id"] for category in current["categories"]}
        assert "loyalty-long-term" not in category_ids
        assert "community-sharing" in category_ids
        history = client.get("/api/badges?history=true").json()
        assert len(history["badges"]) == 8
        valentines = next(
            badge for badge in history["badges"] if badge["id"] == "valentines-walk-2026"
        )
        assert valentines["earned"] is True
        assert valentines["show_progress"] is False
        assert valentines["progress"] == 1
        detail = client.get("/api/badges/first-walk").json()
        assert detail["participants"] == []
        assert db.update_profile_preferences(laura["id"], badge_visibility=True)
        detail = client.get("/api/badges/first-walk").json()
        assert [person["name"] for person in detail["participants"]] == ["Laura"]
        avatar_url = detail["participants"][0]["avatar_url"]
        assert avatar_url
        avatar = client.get(avatar_url)
        assert avatar.status_code == 200
        assert avatar.headers["content-type"] == "image/png"
        assert avatar.content == avatar_png
        assert db.update_profile_preferences(laura["id"], badge_visibility=False)
        detail = client.get("/api/badges/first-walk").json()
        assert detail["participants"] == []
        assert client.get(avatar_url).status_code == 404
        assert client.get("/api/badges/missing").status_code == 404


def test_admin_console_role_and_admin_api(tmp_path, monkeypatch):
    monkeypatch.setattr(main_module, "current_iso_week", lambda: (2026, 42))
    monkeypatch.setenv("GASSI_SESSION_SECRET", "test-session-secret-that-is-long-enough")
    db_path = tmp_path / "admin.sqlite3"
    db = Database(db_path)
    admin = db.add_account("Jan", hash_password("jan family password"))
    participant = db.add_account("Laura", hash_password("laura family password"))
    assert db.set_admin("Jan", True)
    app = create_app(str(db_path))

    with TestClient(app) as admin_client, TestClient(app) as user_client:
        assert admin_client.post("/auth/login", json={
            "display_name": "Jan", "password": "jan family password",
        }).status_code == 200
        assert user_client.post("/auth/login", json={
            "display_name": "Laura", "password": "laura family password",
        }).status_code == 200
        assert admin_client.get("/api/me").json()["person"]["is_admin"] == 1
        assert user_client.get("/api/admin/users").status_code == 403
        assert admin_client.post(
            f"/api/admin/users/{admin['id']}/password",
            json={"new_password": "another Jan password"},
        ).status_code == 422

        users = admin_client.get("/api/admin/users").json()
        assert {user["username"] for user in users["users"]} == {"Jan", "Laura"}
        override = admin_client.put("/api/admin/prefs", json={
            "person_id": participant["id"], "weekday": 2, "slot": "evening", "value": -1,
        })
        assert override.status_code == 200 and override.json()["changed"]
        events = admin_client.get("/api/admin/activity").json()["events"]
        assert any(event["action"] == "login" and event["actor"] == "Laura" for event in events)
        pref_event = next(event for event in events if event["action"] == "preference_change")
        assert pref_event["actor"] == "Jan" and pref_event["subject"] == "Laura"

        reset = admin_client.post(
            f"/api/admin/users/{participant['id']}/password",
            json={"new_password": "laura reset password"},
        )
        assert reset.status_code == 200
        assert user_client.get("/api/me").status_code == 401
        assert user_client.post("/auth/login", json={
            "display_name": "Laura", "password": "laura family password",
        }).status_code == 401
        assert user_client.post("/auth/login", json={
            "display_name": "Laura", "password": "laura reset password",
        }).status_code == 200

    assert db.set_admin("Laura", True)
    assert db.set_admin("Jan", False)
    try:
        db.set_admin("Laura", False)
    except ValueError as exc:
        assert "letzte Admin" in str(exc)
    else:
        raise AssertionError("must retain at least one admin")


def test_activity_history_expires_after_90_days(tmp_path):
    db = Database(tmp_path / "activity.sqlite3")
    db.record_activity("Jan", "login", "Jan")
    cutoff_event = (datetime.now(timezone.utc) - timedelta(days=91)).isoformat(timespec="seconds")
    with db._connect() as con:
        con.execute(
            """
            INSERT INTO activity_log (actor_username, action, subject_username, details_json, occurred_at)
            VALUES ('Laura', 'login', 'Laura', '{}', ?)
            """,
            (cutoff_event,),
        )

    events = db.recent_activity()
    assert len(events) == 1
    assert events[0]["actor"] == "Jan"


def test_registration_login_and_password_change(tmp_path, monkeypatch):
    monkeypatch.setenv("GASSI_SESSION_SECRET", "test-session-secret-that-is-long-enough")
    invite_code = "family-invite-code-12345678901234567890"
    monkeypatch.setenv("GASSI_INVITE_CODE", invite_code)
    app = create_app(str(tmp_path / "accounts.sqlite3"))
    with TestClient(app) as client:
        payload = {
            "display_name": "Jan",
            "password": "a long family password",
            "invite_code": "wrong-code",
        }
        assert client.post("/auth/register", json=payload).status_code == 403
        payload["invite_code"] = invite_code
        assert client.post("/auth/register", json=payload).status_code == 201
        assert client.get("/api/me").json()["person"]["name"] == "Jan"

        client.post("/auth/logout")
        assert client.post("/auth/login", json={
            "display_name": "Jan", "password": "wrong password",
        }).status_code == 401
        assert client.post("/auth/login", json={
            "display_name": "Jan", "password": "a long family password",
        }).status_code == 200

        assert client.post("/api/me/password", json={
            "current_password": "wrong password", "new_password": "another good password",
        }).status_code == 403
        assert client.post("/api/me/password", json={
            "current_password": "a long family password",
            "new_password": "another good password",
        }).status_code == 200
        client.post("/auth/logout")
        assert client.post("/auth/login", json={
            "display_name": "Jan", "password": "a long family password",
        }).status_code == 401
        assert client.post("/auth/login", json={
            "display_name": "Jan", "password": "another good password",
        }).status_code == 200
