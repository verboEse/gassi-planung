"""API-Tests mit FastAPI TestClient gegen eine temporäre SQLite-DB."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app import main as main_module
from app.main import create_app, week_dates


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main_module, "current_iso_week", lambda: (2026, 1))
    app = create_app(str(tmp_path / "test.sqlite3"), auth_enabled=False)
    with TestClient(app) as c:
        yield c


def add_person(client, name, color=None):
    payload = {"name": name}
    if color:
        payload["color"] = color
    res = client.post("/api/persons", json=payload)
    assert res.status_code == 201, res.text
    return res.json()


def test_profile_and_badge_endpoints_are_in_openapi(tmp_path):
    schema = create_app(str(tmp_path / "openapi.sqlite3")).openapi()
    paths = schema["paths"]
    assert {"get"} <= paths["/api/profile"].keys()
    assert {"get"} <= paths["/api/badges"].keys()
    assert {"get"} <= paths["/api/badges/{badge_id}"].keys()
    assert {"get"} <= paths["/api/badges/{badge_id}/participants/{person_id}/avatar"].keys()
    assert {"put", "get", "delete"} <= paths["/api/profile/avatar"].keys()
    assert {"patch"} <= paths["/api/profile/preferences"].keys()


class TestPersons:
    def test_create_and_list(self, client):
        p = add_person(client, "Jan")
        assert p["id"] > 0
        assert p["color"].startswith("#")
        res = client.get("/api/persons")
        assert [x["name"] for x in res.json()["persons"]] == ["Jan"]

    def test_duplicate_name_rejected(self, client):
        add_person(client, "Jan")
        res = client.post("/api/persons", json={"name": "Jan"})
        assert res.status_code == 409

    def test_empty_name_rejected(self, client):
        res = client.post("/api/persons", json={"name": "   "})
        assert res.status_code == 422

    def test_delete(self, client):
        p = add_person(client, "Jan")
        assert client.delete(f"/api/persons/{p['id']}").status_code == 204
        assert client.get("/api/persons").json()["persons"] == []
        assert client.delete(f"/api/persons/{p['id']}").status_code == 404


class TestGamification:
    def test_planned_duplicate_and_remove(self, client, monkeypatch):
        monkeypatch.setattr(
            main_module,
            "berlin_now",
            lambda: datetime(2026, 1, 1, 6, 30, tzinfo=ZoneInfo("Europe/Berlin")),
        )
        person = add_person(client, "Jan")
        payload = {
            "person_id": person["id"],
            "date": "2026-01-01",
            "slot": "morning",
            "source": "plan",
        }
        first = client.put("/api/completions", json=payload)
        assert first.status_code == 200 and first.json()["created"]
        assert not client.put("/api/completions", json=payload).json()["created"]

        progress = client.get("/api/gamification")
        assert progress.status_code == 200
        jan = progress.json()["persons"][0]
        assert jan["points"] == 1
        assert jan["level"] == 1
        assert jan["level_name"] == "Gassi-Starter"
        assert {badge["id"] for badge in jan["badges"]} == {"first-walk"}

        removed = client.delete(
            f"/api/completions/{payload['date']}/{payload['slot']}?person_id={person['id']}"
        )
        assert removed.status_code == 200
        assert client.get("/api/gamification").json()["persons"][0]["points"] == 0

    def test_count_badge_is_removed_after_completion_correction(self, client, monkeypatch):
        monkeypatch.setattr(
            main_module,
            "berlin_now",
            lambda: datetime(2026, 1, 1, 6, 30, tzinfo=ZoneInfo("Europe/Berlin")),
        )
        person = add_person(client, "Jan")
        payload = {
            "person_id": person["id"],
            "date": "2026-01-01",
            "slot": "morning",
            "source": "plan",
        }
        assert client.put("/api/completions", json=payload).status_code == 200
        badges = client.get("/api/gamification").json()["persons"][0]["badges"]
        assert {badge["id"] for badge in badges} == {"first-walk"}
        assert client.delete(
            f"/api/completions/2026-01-01/morning?person_id={person['id']}"
        ).status_code == 200
        badges = client.get("/api/gamification").json()["persons"][0]["badges"]
        assert badges == []

    def test_full_week_badge_remains_after_correction(self, client, monkeypatch):
        person = add_person(client, "Jan")
        for day in range(5, 12):
            monkeypatch.setattr(
                main_module,
                "berlin_now",
                lambda day=day: datetime(
                    2026, 1, day, 6, 30, tzinfo=ZoneInfo("Europe/Berlin")
                ),
            )
            assert client.post(f"/api/walks/start?person_id={person['id']}").status_code == 200
            monkeypatch.setattr(
                main_module,
                "berlin_now",
                lambda day=day: datetime(
                    2026, 1, day, 7, 0, tzinfo=ZoneInfo("Europe/Berlin")
                ),
            )
            assert client.post(f"/api/walks/end?person_id={person['id']}").status_code == 200
        badges = client.get("/api/gamification").json()["persons"][0]["badges"]
        assert "full-week" in {badge["id"] for badge in badges}
        assert client.delete(
            f"/api/completions/2026-01-11/morning?person_id={person['id']}"
        ).status_code == 200
        badges = client.get("/api/gamification").json()["persons"][0]["badges"]
        assert "full-week" in {badge["id"] for badge in badges}

    def test_walk_session_start_end_and_reload(self, client, monkeypatch):
        person = add_person(client, "Jan")
        set_time = lambda hour, minute: monkeypatch.setattr(
            main_module,
            "berlin_now",
            lambda: datetime(2026, 1, 1, hour, minute, tzinfo=ZoneInfo("Europe/Berlin")),
        )
        set_time(5, 29)
        assert client.post(f"/api/walks/start?person_id={person['id']}").status_code == 422
        set_time(5, 30)
        started = client.post(f"/api/walks/start?person_id={person['id']}")
        assert started.status_code == 200
        assert started.json()["active"]["slot"] == "morning"
        assert client.get(
            f"/api/gamification?person_id={person['id']}"
        ).json()["walk_status"]["active"]
        set_time(9, 0)
        ended = client.post(f"/api/walks/end?person_id={person['id']}")
        assert ended.status_code == 200 and ended.json()["created"]
        assert client.post(f"/api/walks/end?person_id={person['id']}").status_code == 404
        assert client.get("/api/gamification").json()["persons"][0]["points"] == 1

    def test_calendar_link_start_requires_matching_walk(self, client, monkeypatch):
        person = add_person(client, "Jan")
        monkeypatch.setattr(
            main_module,
            "berlin_now",
            lambda: datetime(2026, 1, 1, 6, 30, tzinfo=ZoneInfo("Europe/Berlin")),
        )
        start_url = f"/api/walks/start?person_id={person['id']}"

        assert client.post(f"{start_url}&date=2026-01-01&slot=noon").status_code == 422
        assert client.post(f"{start_url}&weekday=5&slot=morning").status_code == 422
        started = client.post(f"{start_url}&weekday=4&slot=morning")
        assert started.status_code == 200
        assert started.json()["active"]["date"] == "2026-01-01"
        assert client.post(f"{start_url}&weekday=4&slot=morning").json()["created"] is False
        assert client.post(f"{start_url}&weekday=4&slot=noon").status_code == 409

    def test_walk_session_requires_takeover_approval(self, client, monkeypatch):
        monkeypatch.setattr(
            main_module,
            "berlin_now",
            lambda: datetime(2026, 1, 1, 6, 30, tzinfo=ZoneInfo("Europe/Berlin")),
        )
        monkeypatch.setattr(main_module, "send_event_push", lambda *args: None)
        monkeypatch.setattr(
            main_module, "load_vapid_configuration", lambda: (None, "mailto:test", "public")
        )
        jan = add_person(client, "Jan")
        laura = add_person(client, "Laura")
        day = next(
            day for day in client.get("/api/plan?year=2026&week=1").json()["days"]
            if day["date"] == "2026-01-01"
        )
        assignee_id = day["slots"]["morning"]["person_id"]
        requester = laura if assignee_id == jan["id"] else jan
        assignee = jan if assignee_id == jan["id"] else laura
        start_url = f"/api/walks/start?person_id={requester['id']}"
        status = client.get(
            f"/api/gamification?person_id={requester['id']}"
        ).json()["walk_status"]

        assert status["assignee_id"] == assignee_id
        assert client.post(start_url).status_code == 403
        response = client.post("/api/walk-takeovers", json={
            "person_id": requester["id"],
            "date": "2026-01-01",
            "slot": "morning",
        })
        assert response.status_code == 201
        request_id = response.json()["request"]["id"]
        assert client.post(start_url).status_code == 403
        assert client.put(
            f"/api/walk-takeovers/{request_id}",
            json={"person_id": assignee["id"], "approved": True},
        ).status_code == 200
        assert client.post(start_url).status_code == 200

    def test_invalid_completion_rejected(self, client, monkeypatch):
        person = add_person(client, "Jan")
        base = {"person_id": person["id"], "date": "2026-01-01", "source": "plan"}
        assert client.put("/api/completions", json={**base, "slot": "nachts"}).status_code == 422
        assert client.put(
            "/api/completions", json={**base, "slot": "morning", "source": "manual"}
        ).status_code == 422
        monkeypatch.setattr(
            main_module,
            "berlin_now",
            lambda: datetime(2026, 1, 1, 10, 0, tzinfo=ZoneInfo("Europe/Berlin")),
        )
        assert client.put(
            "/api/completions", json={**base, "slot": "morning"}
        ).status_code == 422

    def test_planned_completion_requires_assignment(self, client, monkeypatch):
        monkeypatch.setattr(
            main_module,
            "berlin_now",
            lambda: datetime(2026, 1, 1, 6, 30, tzinfo=ZoneInfo("Europe/Berlin")),
        )
        jan = add_person(client, "Jan")
        laura = add_person(client, "Laura")
        plan = client.get("/api/plan?year=2026&week=1").json()
        assigned = next(day for day in plan["days"] if day["date"] == "2026-01-01")
        assigned_id = assigned["slots"]["morning"]["person_id"]
        wrong_person = laura if assigned_id == jan["id"] else jan
        response = client.put("/api/completions", json={
            "person_id": wrong_person["id"],
            "date": "2026-01-01",
            "slot": "morning",
            "source": "plan",
        })
        assert response.status_code == 403

    def test_takeover_requires_assignee_approval(self, client, monkeypatch):
        monkeypatch.setattr(
            main_module,
            "berlin_now",
            lambda: datetime(2026, 1, 1, 6, 30, tzinfo=ZoneInfo("Europe/Berlin")),
        )
        pushes = []
        monkeypatch.setattr(main_module, "send_event_push", lambda *args: pushes.append(args))
        monkeypatch.setattr(
            main_module, "load_vapid_configuration", lambda: (None, "mailto:test", "public")
        )
        jan = add_person(client, "Jan")
        laura = add_person(client, "Laura")
        plan_before = client.get("/api/plan?year=2026&week=1").json()
        day = next(day for day in plan_before["days"] if day["date"] == "2026-01-01")
        assignee_id = day["slots"]["morning"]["person_id"]
        requester = laura if assignee_id == jan["id"] else jan
        assignee = jan if assignee_id == jan["id"] else laura
        payload = {
            "person_id": requester["id"],
            "date": "2026-01-01",
            "slot": "morning",
        }

        requested = client.post("/api/walk-takeovers", json=payload)
        assert requested.status_code == 201, requested.text
        request = requested.json()["request"]
        assert pushes[-1][1] == assignee_id
        assert "übernehmen" in pushes[-1][2]["title"]
        assert client.get(
            f"/api/walk-takeovers?person_id={assignee['id']}"
        ).json()["requests"][0]["id"] == request["id"]
        completion = {
            **payload,
            "source": "plan",
        }
        assert client.put("/api/completions", json=completion).status_code == 403
        assert client.put(
            f"/api/walk-takeovers/{request['id']}",
            json={"person_id": requester["id"], "approved": True},
        ).status_code == 404
        approved = client.put(
            f"/api/walk-takeovers/{request['id']}",
            json={"person_id": assignee["id"], "approved": True},
        )
        assert approved.status_code == 200
        assert approved.json()["request"]["status"] == "approved"
        assert pushes[-1][1] == requester["id"]
        assert "freigegeben" in pushes[-1][2]["title"]
        assert client.put("/api/completions", json={
            **completion, "person_id": assignee["id"],
        }).status_code == 403
        assert client.put("/api/completions", json=completion).status_code == 200
        assert client.get("/api/plan?year=2026&week=1").json() == plan_before
        points = {
            person["id"]: person["points"]
            for person in client.get("/api/gamification").json()["persons"]
        }
        assert points[requester["id"]] == 1

    def test_group_takeover_records_shared_completion(self, client, monkeypatch):
        monkeypatch.setattr(
            main_module,
            "berlin_now",
            lambda: datetime(2026, 1, 1, 6, 30, tzinfo=ZoneInfo("Europe/Berlin")),
        )
        pushes = []
        monkeypatch.setattr(main_module, "send_event_push", lambda *args: pushes.append(args))
        monkeypatch.setattr(
            main_module, "load_vapid_configuration", lambda: (None, "mailto:test", "public")
        )
        jan = add_person(client, "Jan")
        laura = add_person(client, "Laura")
        day = next(
            day for day in client.get("/api/plan?year=2026&week=1").json()["days"]
            if day["date"] == "2026-01-01"
        )
        assignee_id = day["slots"]["morning"]["person_id"]
        requester = laura if assignee_id == jan["id"] else jan
        assignee = jan if assignee_id == jan["id"] else laura
        requested = client.post("/api/walk-takeovers", json={
            "person_id": requester["id"],
            "date": "2026-01-01",
            "slot": "morning",
        })
        request_id = requested.json()["request"]["id"]

        confirmed = client.post(
            f"/api/walk-takeovers/{request_id}/group",
            json={"person_id": assignee["id"]},
        )

        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["request"]["status"] == "shared"
        assert {row["person_id"] for row in confirmed.json()["completions"]} == {
            requester["id"], assignee["id"],
        }
        assert len({row["shared_walk_id"] for row in confirmed.json()["completions"]}) == 1
        assert pushes[-1][1] == requester["id"]
        assert pushes[-1][2]["title"] == "Gemeinsame Gassirunde bestätigt"
        assert client.post(
            f"/api/walk-takeovers/{request_id}/group",
            json={"person_id": assignee["id"]},
        ).status_code == 404

    def test_declined_takeover_cannot_be_completed(self, client, monkeypatch):
        monkeypatch.setattr(
            main_module,
            "berlin_now",
            lambda: datetime(2026, 1, 1, 6, 30, tzinfo=ZoneInfo("Europe/Berlin")),
        )
        pushes = []
        monkeypatch.setattr(main_module, "send_event_push", lambda *args: pushes.append(args))
        monkeypatch.setattr(
            main_module, "load_vapid_configuration", lambda: (None, "mailto:test", "public")
        )
        jan = add_person(client, "Jan")
        laura = add_person(client, "Laura")
        day = next(
            day for day in client.get("/api/plan?year=2026&week=1").json()["days"]
            if day["date"] == "2026-01-01"
        )
        assignee_id = day["slots"]["morning"]["person_id"]
        requester = laura if assignee_id == jan["id"] else jan
        assignee = jan if assignee_id == jan["id"] else laura
        response = client.post("/api/walk-takeovers", json={
            "person_id": requester["id"], "date": "2026-01-01", "slot": "morning",
        })
        request = response.json()["request"]
        declined = client.put(f"/api/walk-takeovers/{request['id']}", json={
            "person_id": assignee["id"], "approved": False,
        })
        assert declined.status_code == 200
        assert declined.json()["request"]["status"] == "declined"
        assert pushes[-1][1] == requester["id"]
        assert "wahrgenommen" in pushes[-1][2]["body"]
        assert client.put("/api/completions", json={
            "person_id": requester["id"], "date": "2026-01-01",
            "slot": "morning", "source": "plan",
        }).status_code == 403

    def test_shared_walk_awards_both_and_retries_idempotently(self, client, monkeypatch):
        monkeypatch.setattr(
            main_module,
            "berlin_now",
            lambda: datetime(2026, 1, 1, 6, 30, tzinfo=ZoneInfo("Europe/Berlin")),
        )
        jan = add_person(client, "Jan")
        laura = add_person(client, "Laura")
        people = {jan["id"], laura["id"]}
        day = next(
            day for day in client.get("/api/plan?year=2026&week=1").json()["days"]
            if day["date"] == "2026-01-01"
        )
        owner_id = day["slots"]["morning"]["person_id"]
        co_walker_id = next(person_id for person_id in people if person_id != owner_id)
        payload = {
            "person_id": owner_id,
            "date": "2026-01-01",
            "slot": "morning",
            "source": "plan",
            "co_walker_ids": [co_walker_id],
        }

        solo_payload = {
            key: value for key, value in payload.items() if key != "co_walker_ids"
        }
        assert client.put("/api/completions", json=solo_payload).json()["created"]
        first = client.put("/api/completions", json=payload)
        assert first.status_code == 200 and first.json()["created"]
        retry = client.put("/api/completions", json=payload)
        assert retry.status_code == 200 and not retry.json()["created"]
        progress = client.get("/api/gamification").json()
        assert {row["person_id"] for row in progress["completions"]} == people
        assert {row["shared_group_size"] for row in progress["completions"]} == {2}
        assert {person["points"] for person in progress["persons"]} == {1}

    def test_shared_walk_corrections_update_group_size(self, client, monkeypatch):
        monkeypatch.setattr(
            main_module,
            "berlin_now",
            lambda: datetime(2026, 1, 1, 6, 30, tzinfo=ZoneInfo("Europe/Berlin")),
        )
        people = [add_person(client, name) for name in ("Jan", "Laura", "Max", "Eva")]
        day = next(
            day for day in client.get("/api/plan?year=2026&week=1").json()["days"]
            if day["date"] == "2026-01-01"
        )
        owner_id = day["slots"]["morning"]["person_id"]
        co_walker_ids = [person["id"] for person in people if person["id"] != owner_id]
        payload = {
            "person_id": owner_id,
            "date": "2026-01-01",
            "slot": "morning",
            "source": "plan",
            "co_walker_ids": co_walker_ids,
        }
        assert client.put("/api/completions", json=payload).status_code == 200
        initial = client.get("/api/gamification").json()
        assert {row["shared_group_size"] for row in initial["completions"]} == {4}
        for participant in initial["persons"]:
            assert {badge["id"] for badge in participant["badges"]} >= {
                "first-shared-walk", "four-plus-walk",
            }

        for index, (person_id, expected_size) in enumerate(
            zip(co_walker_ids, (3, 2, 0))
        ):
            removed = client.delete(
                f"/api/completions/2026-01-01/morning?person_id={person_id}"
            )
            assert removed.status_code == 200
            progress = client.get("/api/gamification").json()
            assert {row["shared_group_size"] for row in progress["completions"]} == {
                expected_size
            }
            badges = [
                {badge["id"] for badge in participant["badges"]}
                for participant in progress["persons"]
            ]
            if expected_size == 3:
                assert all("three-person-walk" in ids for ids in badges if ids)
                assert all("four-plus-walk" not in ids for ids in badges)
            elif expected_size == 2:
                assert all(
                    "three-person-walk" not in ids and "four-plus-walk" not in ids
                    for ids in badges
                )
            else:
                owner_badges = next(
                    badge_ids for person, badge_ids in zip(people, badges)
                    if person["id"] == owner_id
                )
                assert "first-shared-walk" not in owner_badges


class TestPrefs:
    def test_set_and_read_back(self, client):
        p = add_person(client, "Jan")
        res = client.put("/api/prefs", json={
            "person_id": p["id"], "weekday": 1, "slot": "morning", "value": 3,
        })
        assert res.status_code == 200
        week = client.get("/api/week?year=2026&week=42").json()
        assert week["prefs"][str(p["id"])]["1"]["morning"] == 3

    def test_pref_applies_to_every_week(self, client):
        """Allgemeingültigkeit: derselbe Wochentags-Eintrag gilt in jeder KW."""
        p = add_person(client, "Jan")
        client.put("/api/prefs", json={
            "person_id": p["id"], "weekday": 3, "slot": "evening", "value": -1,
        })
        for kw in (42, 43, 44):
            week = client.get(f"/api/week?year=2026&week={kw}").json()
            assert week["prefs"][str(p["id"])]["3"]["evening"] == -1
            wed = next(d for d in week["plan"]["days"] if d["weekday"] == "Mi")
            assert wed["slots"]["evening"].get("person_id") != p["id"]

    def test_plan_freezes_for_current_week_and_calendar_uses_next_week_prefs(
        self, client, monkeypatch
    ):
        monkeypatch.setattr(main_module, "current_iso_week", lambda: (2026, 42))
        jan = add_person(client, "Jan")
        laura = add_person(client, "Laura")
        before = client.get("/api/week?year=2026&week=42").json()["plan"]

        changed = client.put("/api/prefs", json={
            "person_id": jan["id"], "weekday": 2, "slot": "evening", "value": -1,
        })
        assert changed.status_code == 200
        assert changed.json() == {
            "ok": True, "changed": True, "effective_year": 2026, "effective_week": 43,
        }
        this_week = client.get("/api/week?year=2026&week=42").json()
        next_week = client.get("/api/week?year=2026&week=43").json()
        assert this_week["plan"] == before
        assert this_week["prefs"][str(jan["id"])]["2"]["evening"] == -1
        tue_next_week = next(d for d in next_week["plan"]["days"] if d["weekday"] == "Di")
        assert tue_next_week["slots"]["evening"]["person_id"] == laura["id"]
        assert client.put("/api/prefs", json={
            "person_id": laura["id"], "weekday": 3, "slot": "morning", "value": -1,
        }).status_code == 200
        assert client.get("/api/week?year=2026&week=42").json()["plan"] == before
        next_week = client.get("/api/week?year=2026&week=43").json()
        wed_next_week = next(d for d in next_week["plan"]["days"] if d["weekday"] == "Mi")
        assert wed_next_week["slots"]["morning"]["person_id"] == jan["id"]

        feed = client.get(f"/api/calendar/{jan['id']}.ics").text
        jan_this_week = sum(
            cell.get("person_id") == jan["id"]
            for day in before["days"]
            for cell in day["slots"].values()
        )
        jan_next_week = sum(
            cell.get("person_id") == jan["id"]
            for day in next_week["plan"]["days"]
            for cell in day["slots"].values()
        )
        assert feed.count("BEGIN:VEVENT") == jan_this_week + jan_next_week
        assert feed.count("RRULE:FREQ=WEEKLY") == jan_next_week
        assert "UID:gassi-2026-10-" in feed
        recurring_events = [
            event for event in feed.split("BEGIN:VEVENT\r\n")[1:]
            if "RRULE:FREQ=WEEKLY" in event
        ]
        future_dates = {date.replace("-", "") for date in week_dates(2026, 43)}
        assert all(
            event.split("DTSTART:", 1)[1][:8] in future_dates
            for event in recurring_events
        )

    def test_clear_with_null(self, client):
        p = add_person(client, "Jan")
        client.put("/api/prefs", json={
            "person_id": p["id"], "weekday": 1, "slot": "morning", "value": -1,
        })
        client.put("/api/prefs", json={
            "person_id": p["id"], "weekday": 1, "slot": "morning", "value": None,
        })
        week = client.get("/api/week?year=2026&week=42").json()
        assert str(p["id"]) not in week["prefs"]

    def test_invalid_value_rejected(self, client):
        p = add_person(client, "Jan")
        for bad in (0, 4, 99, -2):
            res = client.put("/api/prefs", json={
                "person_id": p["id"], "weekday": 1, "slot": "morning", "value": bad,
            })
            assert res.status_code == 422, bad

    def test_invalid_slot_rejected(self, client):
        p = add_person(client, "Jan")
        res = client.put("/api/prefs", json={
            "person_id": p["id"], "weekday": 1, "slot": "nachts", "value": 2,
        })
        assert res.status_code == 422

    def test_invalid_weekday_rejected(self, client):
        p = add_person(client, "Jan")
        for bad in (0, 8, -1):
            res = client.put("/api/prefs", json={
                "person_id": p["id"], "weekday": bad, "slot": "morning", "value": 2,
            })
            assert res.status_code == 422, bad

    def test_unknown_person_rejected(self, client):
        res = client.put("/api/prefs", json={
            "person_id": 999, "weekday": 1, "slot": "morning", "value": 2,
        })
        assert res.status_code == 404


class TestWeekAndPlan:
    def test_week_dates(self):
        dates = week_dates(2026, 42)
        assert dates[0] == "2026-10-12"  # Montag
        assert dates[-1] == "2026-10-18"  # Sonntag
        assert len(dates) == 7

    def test_week_defaults_to_current(self, client):
        res = client.get("/api/week")
        assert res.status_code == 200
        body = res.json()
        assert body["year"] and body["week"]
        assert len(body["dates"]) == 7

    def test_invalid_week_rejected(self, client):
        assert client.get("/api/week?year=2026&week=54").status_code == 422

    def test_plan_shape_and_full_coverage(self, client):
        for name in ("Jan", "Laura", "Till"):
            add_person(client, name)
        plan = client.get("/api/plan?year=2026&week=42").json()
        assert len(plan["days"]) == 7
        assigned = 0
        for day in plan["days"]:
            assert set(day["slots"].keys()) == {"morning", "noon", "evening"}
            for slot in day["slots"].values():
                assert not slot["unassigned"]
                assigned += 1
        assert assigned == 21
        assert sum(c["count"] for c in plan["counts"]) == 21

    def test_plan_respects_block(self, client):
        p1 = add_person(client, "Jan")
        p2 = add_person(client, "Laura")
        client.put("/api/prefs", json={
            "person_id": p1["id"], "weekday": 2, "slot": "evening", "value": -1,
        })
        plan = client.get("/api/plan?year=2026&week=42").json()
        tue = next(d for d in plan["days"] if d["date"] == "2026-10-13")
        assert tue["slots"]["evening"]["person_id"] == p2["id"]

    def test_plan_unassigned_when_all_blocked(self, client):
        p = add_person(client, "Jan")
        client.put("/api/prefs", json={
            "person_id": p["id"], "weekday": 3, "slot": "noon", "value": -1,
        })
        plan = client.get("/api/plan?year=2026&week=42").json()
        wed = next(d for d in plan["days"] if d["date"] == "2026-10-14")
        assert wed["slots"]["noon"]["unassigned"] is True
        assert {"date": "2026-10-14", "slot": "noon"} in plan["unassigned"]

    def test_index_served(self, client):
        res = client.get("/")
        assert res.status_code == 200
        assert "Gassi" in res.text
        assert "https://github.com/verboEse/gassi-planung/issues/new" in res.text
        assert "Verbesserung vorschlagen" in res.text
        assert 'class="app-tabs"' not in res.text
        assert 'id="planView"' in res.text
        assert 'id="profileView" hidden' in res.text
        assert 'id="badgesView" hidden' in res.text
        assert 'id="planHomeButton"' in res.text
        assert 'id="changeAvatarButton"' in res.text

    def test_news_bootstrap_is_not_blocked_by_page_loads(self, client):
        script = client.get("/static/app.js").text
        initialize = script.split("async function initialize() {", 1)[1].split(
            "\n}\n\nsetAuthMode(", 1
        )[0]
        session_restore = initialize.index('state.me = await api("/api/me");')
        news_load = initialize.index("loadNews();")
        plan_load = initialize.index("loadWeek()")
        assert session_restore < news_load < plan_load
        assert "if (state.me) loadNews();" in initialize

    def test_news_loader_does_not_skip_admin_accounts(self, client):
        script = client.get("/static/app.js").text
        news_loader = script.split("async function loadNews() {", 1)[1].split(
            "\n}\n\nasync function initialize()", 1
        )[0]
        assert "if (!state.me) return;" in news_loader
        assert "state.me.person.is_admin" not in news_loader
