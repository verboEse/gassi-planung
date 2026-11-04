"""Tests für den iCal-Export (RFC 5545) und den Kalender-Endpoint."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import main as main_module
from app.db import Database
from app.ical import build_ics, escape_text, fold_line
from app.main import create_app
from app.scheduler import Assignment


class TestEscape:
    def test_special_chars(self):
        assert escape_text('a,b;c\\d\ne') == 'a\\,b\\;c\\\\d\\ne'

    def test_plain_text_unchanged(self):
        assert escape_text("Gassi Morgens") == "Gassi Morgens"


class TestFold:
    def test_short_line_untouched(self):
        assert fold_line("BEGIN:VCALENDAR") == "BEGIN:VCALENDAR"

    def test_long_line_folds_with_space_continuation(self):
        line = "DESCRIPTION:" + "x" * 200
        folded = fold_line(line)
        physical = folded.split("\r\n ")
        assert all(len(p.encode()) <= 75 for p in physical)
        # Entfaltet muss wieder das Original ergeben
        assert folded.replace("\r\n ", "") == line

    def test_utf8_not_split_mid_character(self):
        line = "SUMMARY:" + "🐕" * 40  # 4 Bytes pro Zeichen
        folded = fold_line(line)
        for physical in folded.split("\r\n "):
            assert len(physical.encode()) <= 75
        assert folded.replace("\r\n ", "") == line


def make_assignment(date, slot, person_id=1, pref=2):
    return Assignment(date=date, slot=slot, person_id=person_id, pref=pref)


class TestBuildIcs:
    def test_structure_and_crlf(self):
        ics = build_ics(1, "Jan", [make_assignment("2026-10-12", "morning")])
        assert ics.startswith("BEGIN:VCALENDAR\r\n")
        assert ics.endswith("END:VCALENDAR\r\n")
        assert "\n" not in ics.replace("\r\n", "")  # nur CRLF
        assert ics.count("BEGIN:VEVENT") == 1
        assert "VERSION:2.0" in ics
        assert "X-WR-CALNAME:Gassi – Jan" in ics

    def test_stable_uid_contains_weekday_and_slot(self):
        # 2026-10-12 ist ein Montag (ISO-Wochentag 1)
        ics = build_ics(7, "Jan", [make_assignment("2026-10-12", "noon")])
        assert "UID:gassi-wd1-noon-7@gassi-planung" in ics

    def test_recurring_weekly_without_end_date(self):
        ics = build_ics(1, "Jan", [make_assignment("2026-10-12", "morning")])
        assert "RRULE:FREQ=WEEKLY" in ics
        assert "UNTIL" not in ics
        assert "COUNT" not in ics
        assert "wöchentlich" in ics

    def test_reminder_alarm_is_optional_for_single_and_recurring_events(self):
        assignment = make_assignment("2026-10-12", "morning")
        assert "BEGIN:VALARM" not in build_ics(1, "Jan", [assignment])

        for feed in (
            build_ics(1, "Jan", [assignment], recurring=False, reminders_enabled=True),
            build_ics(1, "Jan", [assignment], reminders_enabled=True),
        ):
            assert "BEGIN:VALARM" in feed
            assert "ACTION:DISPLAY" in feed
            assert "TRIGGER:-PT15M" in feed
            assert feed.count("BEGIN:VALARM") == feed.count("BEGIN:VEVENT")

    def test_non_recurring_mode_uses_date_uid(self):
        ics = build_ics(7, "Jan", [make_assignment("2026-10-12", "noon")], recurring=False)
        assert "UID:gassi-2026-10-12-noon-7@gassi-planung" in ics
        assert "RRULE" not in ics

    def test_event_urls_target_the_calendar_walk(self):
        ics = build_ics(
            7,
            "Jan",
            [make_assignment("2026-10-12", "morning")],
            recurring=False,
            future_assignments=[make_assignment("2026-10-19", "noon")],
            base_url="https://gassi.example/",
        )

        assert "URL:https://gassi.example/#walk/date/2026-10-12/morning/7" in ics
        assert "URL:https://gassi.example/#walk/weekday/1/noon/7" in ics

    def test_multiple_events_sorted(self):
        assignments = [
            make_assignment("2026-10-13", "evening"),
            make_assignment("2026-10-12", "morning"),
        ]
        ics = build_ics(1, "Jan", assignments)
        assert ics.count("BEGIN:VEVENT") == 2
        assert ics.index("DTSTART:20261012") < ics.index("DTSTART:20261013")

    def test_summer_time_utc_offset(self):
        # Juli = MESZ (UTC+2): 06:00 lokal -> 04:00 UTC
        ics = build_ics(1, "Jan", [make_assignment("2026-07-06", "morning")])
        assert "DTSTART:20260706T040000Z" in ics
        assert "DTEND:20260706T060000Z" in ics

    def test_winter_time_utc_offset(self):
        # Januar = MEZ (UTC+1): 06:00 lokal -> 05:00 UTC
        ics = build_ics(1, "Jan", [make_assignment("2026-01-05", "morning")])
        assert "DTSTART:20260105T050000Z" in ics

    def test_slot_time_windows(self):
        noon = build_ics(1, "Jan", [make_assignment("2026-01-05", "noon")])
        assert "DTSTART:20260105T123000Z" in noon  # 13:30 MEZ
        assert "DTEND:20260105T143000Z" in noon    # 15:30 MEZ

        evening = build_ics(1, "Jan", [make_assignment("2026-01-05", "evening")])
        assert "DTSTART:20260105T190000Z" in evening  # 20:00 MEZ
        assert "DTEND:20260105T210000Z" in evening    # 22:00 MEZ


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main_module, "current_iso_week", lambda: (2026, 42))
    app = create_app(str(tmp_path / "test.sqlite3"), auth_enabled=False)
    with TestClient(app) as c:
        yield c


def add_person(client, name):
    res = client.post("/api/persons", json={"name": name})
    assert res.status_code == 201
    return res.json()


class TestCalendarEndpoint:
    def test_feed_contains_only_own_slots(self, client):
        p1 = add_person(client, "Jan")
        add_person(client, "Laura")
        add_person(client, "Till")
        res = client.get(f"/api/calendar/{p1['id']}.ics")
        assert res.status_code == 200
        assert res.headers["content-type"].startswith("text/calendar")
        body = res.text
        assert "X-WR-CALNAME:Gassi – Jan" in body
        # Aktuelle Woche einmalig, Folgewochen als wiederkehrende Termine.
        assert body.count("BEGIN:VEVENT") == 14
        assert body.count("RRULE:FREQ=WEEKLY") == 7
        assert "UNTIL" not in body
        assert "COUNT" not in body
        assert "-1@gassi-planung" in body
        assert "-2@gassi-planung" not in body
        assert "-3@gassi-planung" not in body

    def test_feed_events_link_to_configured_app(self, tmp_path, monkeypatch):
        monkeypatch.setattr(main_module, "current_iso_week", lambda: (2026, 42))
        monkeypatch.setenv("GASSI_BASE_URL", "https://gassi.example/")
        app = create_app(str(tmp_path / "calendar-links.sqlite3"), auth_enabled=False)

        with TestClient(app) as client:
            person = add_person(client, "Jan")
            body = client.get(f"/api/calendar/{person['id']}.ics").text

        assert body.count("URL:https://gassi.example/#walk/") == body.count("BEGIN:VEVENT")

    def test_feed_alarms_follow_person_reminder_preference(self, tmp_path, monkeypatch):
        monkeypatch.setattr(main_module, "current_iso_week", lambda: (2026, 42))
        db_path = tmp_path / "reminders.sqlite3"
        db = Database(db_path)
        person = db.add_person("Jan")
        db.add_person("Laura")
        db.add_person("Till")
        app = create_app(str(db_path), auth_enabled=False)

        with TestClient(app) as client:
            feed = client.get(f"/api/calendar/{person['id']}.ics").text
            assert "BEGIN:VEVENT" in feed
            assert "BEGIN:VALARM" not in feed

            db.update_profile_preferences(person["id"], reminders_enabled=True)
            feed = client.get(f"/api/calendar/{person['id']}.ics").text
            assert feed.count("BEGIN:VALARM") == feed.count("BEGIN:VEVENT")
            assert "TRIGGER:-PT15M" in feed

    def test_unknown_person_404(self, client):
        assert client.get("/api/calendar/999.ics").status_code == 404

    def test_blocked_slots_apply_to_calendar_from_next_week(self, client):
        p1 = add_person(client, "Jan")
        p2 = add_person(client, "Laura")
        baseline = client.get("/api/week?year=2026&week=42").json()["plan"]
        for wd in range(1, 8):
            for slot in ("morning", "noon", "evening"):
                client.put("/api/prefs", json={
                    "person_id": p1["id"], "weekday": wd, "slot": slot, "value": -1,
                })

        jan_now = sum(
            cell.get("person_id") == p1["id"]
            for day in baseline["days"]
            for cell in day["slots"].values()
        )
        jan_feed = client.get(f"/api/calendar/{p1['id']}.ics").text
        assert jan_feed.count("BEGIN:VEVENT") == jan_now
        assert "RRULE:FREQ=WEEKLY" not in jan_feed

        laura_now = sum(
            cell.get("person_id") == p2["id"]
            for day in baseline["days"]
            for cell in day["slots"].values()
        )
        laura_feed = client.get(f"/api/calendar/{p2['id']}.ics").text
        assert laura_feed.count("BEGIN:VEVENT") == laura_now + 21
        assert laura_feed.count("RRULE:FREQ=WEEKLY") == 21
