from __future__ import annotations

import base64
import json
from urllib.parse import urlsplit

from fastapi.testclient import TestClient
from itsdangerous import TimestampSigner

from app import main as main_module
from app.auth import hash_password, verify_password
from app.db import Database
from app.main import create_app


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
        session = base64.b64encode(json.dumps({"person_id": owner["id"]}).encode())
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
