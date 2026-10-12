"""API-Tests mit FastAPI TestClient gegen eine temporäre SQLite-DB."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app, week_dates


@pytest.fixture()
def client(tmp_path):
    app = create_app(str(tmp_path / "test.sqlite3"))
    with TestClient(app) as c:
        yield c


def add_person(client, name, color=None):
    payload = {"name": name}
    if color:
        payload["color"] = color
    res = client.post("/api/persons", json=payload)
    assert res.status_code == 201, res.text
    return res.json()


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
