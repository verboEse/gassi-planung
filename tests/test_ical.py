"""Tests für den iCal-Export (RFC 5545) und den Kalender-Endpoint."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

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

    def test_non_recurring_mode_uses_date_uid(self):
        ics = build_ics(7, "Jan", [make_assignment("2026-10-12", "noon")], recurring=False)
        assert "UID:gassi-2026-10-12-noon-7@gassi-planung" in ics
        assert "RRULE" not in ics

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
        ics = build_ics(1, "Jan", [make_assignment("2026-01-05", "evening")])
        assert "DTSTART:20260105T170000Z" in ics  # 18:00 MEZ
        assert "DTEND:20260105T190000Z" in ics    # 20:00 MEZ


@pytest.fixture()
def client(tmp_path):
    app = create_app(str(tmp_path / "test.sqlite3"))
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
        # Eine Referenzwoche, fair verteilt auf 3 Personen: 7 eigene Slots,
        # jeweils als wöchentlich wiederkehrendes Event ohne Enddatum
        assert body.count("BEGIN:VEVENT") == 7
        assert body.count("RRULE:FREQ=WEEKLY") == 7
        assert "UNTIL" not in body
        assert "COUNT" not in body
        assert "-1@gassi-planung" in body
        assert "-2@gassi-planung" not in body
        assert "-3@gassi-planung" not in body

    def test_unknown_person_404(self, client):
        assert client.get("/api/calendar/999.ics").status_code == 404

    def test_blocked_slots_not_in_feed(self, client):
        p1 = add_person(client, "Jan")
        p2 = add_person(client, "Laura")
        # Jan blockiert alles (alle Wochentage) -> sein Feed hat 0 Events, Lauras alle
        for wd in range(1, 8):
            for slot in ("morning", "noon", "evening"):
                client.put("/api/prefs", json={
                    "person_id": p1["id"], "weekday": wd, "slot": slot, "value": -1,
                })
        res = client.get(f"/api/calendar/{p1['id']}.ics?weeks=1")
        assert res.text.count("BEGIN:VEVENT") == 0
        res2 = client.get(f"/api/calendar/{p2['id']}.ics?weeks=1")
        assert res2.text.count("BEGIN:VEVENT") == 21  # ganze Woche, je 1 Recurring-Event pro Slot
