import asyncio
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from pywebpush import WebPushException

from app import main as main_module
from app.db import Database
from app.main import create_app
from app.reminders import (
    dispatch_due_active_walk_reminders,
    dispatch_due_reminders,
    reminder_jobs,
    send_event_push,
)


def test_reminders_follow_slot_time_in_berlin_across_dst():
    plans = [{
        "days": [
            {"date": "2026-07-06", "slots": {
                "morning": {"person_id": 7},
                "noon": {"person_id": 8},
                "evening": {"unassigned": True},
            }},
            {"date": "2026-01-05", "slots": {
                "morning": {"person_id": 7},
            }},
        ],
    }]

    assert reminder_jobs(plans, {7}) == [
        (7, "2026-01-05", "morning", "2026-01-05T04:45:00+00:00"),
        (7, "2026-07-06", "morning", "2026-07-06T03:45:00+00:00"),
    ]


def make_delivery_case(tmp_path, filename="dispatcher.sqlite3"):
    db = Database(tmp_path / filename)
    person = db.add_person("Jan")
    db.update_profile_preferences(person["id"], reminders_enabled=True)
    db.save_push_subscription(
        person["id"],
        endpoint="https://fcm.googleapis.com/fcm/send/test",
        p256dh="key",
        auth="auth",
    )
    jobs = reminder_jobs([{
        "days": [{"date": "2026-07-06", "slots": {
            "morning": {"person_id": person["id"]},
        }}],
    }], {person["id"]})
    return db, person, jobs


def test_event_push_uses_push_preference_and_removes_expired_subscription(tmp_path):
    db = Database(tmp_path / "event-push.sqlite3")
    person = db.add_person("Jan")
    db.save_push_subscription(
        person["id"], endpoint="https://fcm.googleapis.com/fcm/send/event",
        p256dh="key", auth="auth",
    )
    config = (None, "mailto:admin@example.test", "public")
    sent = []
    sender = lambda *args: sent.append(args)

    assert not send_event_push(db, person["id"], {"title": "Test"}, config, sender)
    assert sent == []

    db.update_profile_preferences(
        person["id"], push_enabled=True, reminders_enabled=False
    )
    assert send_event_push(db, person["id"], {"title": "Test"}, config, sender)
    assert sent[0][1]["title"] == "Test"

    class Response:
        status_code = 410
        headers = {}

    def expired(*_args):
        raise WebPushException("expired", response=Response())

    assert not send_event_push(db, person["id"], {"title": "Test"}, config, expired)
    assert db.list_push_subscriptions(person["id"]) == []


def read_outbox(db):
    with db._connect() as con:
        return con.execute(
            "SELECT status, attempts, next_attempt_at FROM reminder_outbox"
        ).fetchone()


def make_active_walk_case(tmp_path, filename, walk_type="planned"):
    db = Database(tmp_path / filename)
    person = db.add_person("Jan")
    db.update_profile_preferences(person["id"], reminders_enabled=True)
    db.save_push_subscription(
        person["id"],
        endpoint=f"https://fcm.googleapis.com/fcm/send/{person['id']}",
        p256dh="key",
        auth="auth",
    )
    started_at = datetime(2026, 7, 6, 3, 45, tzinfo=timezone.utc)
    db.start_walk(
        person["id"],
        "2026-07-06",
        "morning" if walk_type == "planned" else None,
        started_at.isoformat(timespec="seconds"),
        walk_type=walk_type,
    )
    return db, person, started_at


def read_active_walk_reminder(db, person_id):
    with db._connect() as con:
        return con.execute(
            """
            SELECT reminder_status, reminder_attempts, reminder_next_attempt_at
            FROM active_walks WHERE person_id = ?
            """,
            (person_id,),
        ).fetchone()


def test_active_walk_reminder_is_sent_once_after_two_hours(tmp_path):
    for walk_type in ("planned", "extra"):
        db, person, started_at = make_active_walk_case(
            tmp_path, f"{walk_type}.sqlite3", walk_type
        )
        sent = []
        sender = lambda _subscription, payload, *_args: sent.append(payload)
        due_at = started_at + timedelta(hours=2)

        asyncio.run(dispatch_due_active_walk_reminders(
            db, {person["id"]}, due_at - timedelta(seconds=1), None,
            "mailto:admin@example.test", sender,
        ))
        assert sent == []

        asyncio.run(dispatch_due_active_walk_reminders(
            db, {person["id"]}, due_at, None,
            "mailto:admin@example.test", sender,
        ))
        assert len(sent) == 1
        assert sent[0]["title"] == "Gassirunde noch aktiv"
        assert sent[0]["tag"].startswith(f"gassi-active-walk-{person['id']}-")
        assert read_active_walk_reminder(db, person["id"])["reminder_status"] == "sent"
        assert db.active_walk(person["id"]) is not None

        asyncio.run(dispatch_due_active_walk_reminders(
            db, {person["id"]}, due_at + timedelta(seconds=30), None,
            "mailto:admin@example.test", sender,
        ))
        assert len(sent) == 1


def test_active_walk_reminder_is_skipped_when_ended_or_disabled(tmp_path):
    ended_db, ended_person, ended_at = make_active_walk_case(
        tmp_path, "ended.sqlite3"
    )
    ended_db.finish_walk(
        ended_person["id"],
        (ended_at + timedelta(hours=1)).isoformat(timespec="seconds"),
    )
    disabled_db, disabled_person, _disabled_at = make_active_walk_case(
        tmp_path, "disabled.sqlite3"
    )
    disabled_db.update_profile_preferences(
        disabled_person["id"], reminders_enabled=False
    )
    sent = []
    sender = lambda *args: sent.append(args)
    due_at = ended_at + timedelta(hours=2)

    for db in (
        ended_db,
        disabled_db,
    ):
        asyncio.run(dispatch_due_active_walk_reminders(
            db, db.enabled_reminder_person_ids(), due_at, None,
            "mailto:admin@example.test", sender,
        ))

    assert sent == []
    assert disabled_db.active_walk(disabled_person["id"]) is not None
    assert read_active_walk_reminder(
        disabled_db, disabled_person["id"]
    )["reminder_status"] == "cancelled"


def test_active_walk_reminder_retries_temporary_push_failure(tmp_path):
    db, person, started_at = make_active_walk_case(tmp_path, "retry-active.sqlite3")
    due_at = started_at + timedelta(hours=2)

    class Response:
        status_code = 503
        headers = {}

    def failing_sender(*_args):
        raise WebPushException("temporary", response=Response())

    asyncio.run(dispatch_due_active_walk_reminders(
        db, {person["id"]}, due_at, None, "mailto:admin@example.test",
        failing_sender,
    ))
    row = read_active_walk_reminder(db, person["id"])
    assert tuple(row) == (
        "pending", 1, (due_at + timedelta(seconds=30)).isoformat(timespec="seconds")
    )

    sent = []
    asyncio.run(dispatch_due_active_walk_reminders(
        db, {person["id"]}, due_at + timedelta(seconds=30), None,
        "mailto:admin@example.test",
        lambda _subscription, payload, *_args: sent.append(payload),
    ))
    assert len(sent) == 1
    assert read_active_walk_reminder(db, person["id"])["reminder_status"] == "sent"


def test_dispatch_sends_due_reminder_and_marks_it_sent(tmp_path):
    db, person, jobs = make_delivery_case(tmp_path)
    sent = []

    def sender(subscription, payload, vapid, subject):
        sent.append((subscription["endpoint"], payload))

    asyncio.run(dispatch_due_reminders(
        db, jobs, {person["id"]}, datetime(2026, 7, 6, 3, 45, tzinfo=timezone.utc),
        None, "mailto:admin@example.test", sender,
    ))

    row = read_outbox(db)
    assert row["status"] == "sent"
    assert sent[0][0] == "https://fcm.googleapis.com/fcm/send/test"
    assert sent[0][1]["tag"] == f"gassi-{person['id']}-2026-07-06-morning"


def test_dispatch_cancels_after_reminder_is_disabled(tmp_path):
    db, person, jobs = make_delivery_case(tmp_path)
    db.reconcile_reminder_outbox(jobs, datetime(2026, 7, 6, 3, 45, tzinfo=timezone.utc))
    db.update_profile_preferences(person["id"], reminders_enabled=False)
    sent = []

    asyncio.run(dispatch_due_reminders(
        db, jobs, {person["id"]}, datetime(2026, 7, 6, 3, 45, tzinfo=timezone.utc),
        None, "mailto:admin@example.test", lambda *args: sent.append(args),
    ))

    assert read_outbox(db)["status"] == "cancelled"
    assert sent == []


def test_dispatch_retries_temporary_failures_with_backoff(tmp_path):
    db, person, jobs = make_delivery_case(tmp_path)

    class Response:
        status_code = 503
        headers = {}

    def sender(*_args):
        raise WebPushException("temporary", response=Response())

    asyncio.run(dispatch_due_reminders(
        db, jobs, {person["id"]}, datetime(2026, 7, 6, 3, 45, tzinfo=timezone.utc),
        None, "mailto:admin@example.test", sender,
    ))

    row = read_outbox(db)
    assert row["status"] == "pending"
    assert row["attempts"] == 1
    assert row["next_attempt_at"] == "2026-07-06T03:45:30+00:00"


def test_dispatch_removes_expired_subscriptions_and_skips_late_reminders(tmp_path):
    db, person, jobs = make_delivery_case(tmp_path)

    class Response:
        status_code = 410
        headers = {}

    def sender(*_args):
        raise WebPushException("expired", response=Response())

    asyncio.run(dispatch_due_reminders(
        db, jobs, {person["id"]}, datetime(2026, 7, 6, 3, 45, tzinfo=timezone.utc),
        None, "mailto:admin@example.test", sender,
    ))
    assert db.list_push_subscriptions(person["id"]) == []
    assert read_outbox(db)["status"] == "cancelled"

    db2, person2, jobs2 = make_delivery_case(tmp_path, "late.sqlite3")
    sent = []
    asyncio.run(dispatch_due_reminders(
        db2, jobs2, {person2["id"]}, datetime(2026, 7, 6, 4, 0, 1, tzinfo=timezone.utc),
        None, "mailto:admin@example.test", lambda *args: sent.append(args),
    ))
    assert read_outbox(db2)["status"] == "expired"
    assert sent == []


def test_reminder_preference_controls_ical_and_browser_push_together(tmp_path, monkeypatch):
    monkeypatch.setattr(main_module, "current_iso_week", lambda: (2026, 46))
    db_path = tmp_path / "combined-reminders.sqlite3"
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
        plan = client.get("/api/week?year=2026&week=46").json()["plan"]
        jobs = reminder_jobs([plan], {person["id"]})
        assert jobs
        sent_job = min(jobs, key=lambda job: job[3])
        due_now = datetime.fromisoformat(sent_job[3])
        db.save_push_subscription(
            person["id"], endpoint="https://fcm.googleapis.com/fcm/send/test",
            p256dh="key", auth="auth",
        )
        sent = []
        asyncio.run(dispatch_due_reminders(
            db, jobs, {person["id"]}, due_now, None,
            "mailto:admin@example.test", lambda sub, payload, *_: sent.append(payload),
        ))
        assert len(sent) == 1
        with db._connect() as con:
            sent_row = con.execute(
                """
                SELECT status FROM reminder_outbox
                WHERE person_id = ? AND walk_date = ? AND slot = ?
                """,
                (sent_job[0], sent_job[1], sent_job[2]),
            ).fetchone()
        assert sent_row["status"] == "sent"

        db.update_profile_preferences(person["id"], reminders_enabled=False)
        feed = client.get(f"/api/calendar/{person['id']}.ics").text
        assert "BEGIN:VALARM" not in feed
        asyncio.run(dispatch_due_reminders(
            db, [], set(), due_now + timedelta(seconds=30), None,
            "mailto:admin@example.test", lambda *args: sent.append(args),
        ))
        assert len(sent) == 1
        with db._connect() as con:
            statuses = {row[0] for row in con.execute(
                "SELECT status FROM reminder_outbox"
            )}
        assert statuses <= {"sent", "cancelled"}
