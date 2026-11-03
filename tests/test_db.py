"""Tests für die DB-Schicht: Migration und wochentagsbasierte Prioritäten."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from app.db import Database

OLD_SCHEMA = """
CREATE TABLE persons (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    name   TEXT NOT NULL UNIQUE,
    color  TEXT NOT NULL DEFAULT '#4a90d9',
    active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE prefs (
    person_id INTEGER NOT NULL,
    date      TEXT NOT NULL,
    slot      TEXT NOT NULL,
    value     INTEGER NOT NULL,
    PRIMARY KEY (person_id, date, slot)
);
"""


def create_old_db(path):
    con = sqlite3.connect(path)
    con.executescript(OLD_SCHEMA)
    con.execute("INSERT INTO persons (name) VALUES ('Jan')")
    # Zwei verschiedene Montage mit unterschiedlichen Werten:
    # das spätere Datum muss bei der Migration gewinnen.
    con.execute("INSERT INTO prefs VALUES (1, '2026-10-05', 'morning', 3)")
    con.execute("INSERT INTO prefs VALUES (1, '2026-10-12', 'morning', 1)")
    con.execute("INSERT INTO prefs VALUES (1, '2026-10-13', 'noon', -1)")
    con.commit()
    con.close()


class TestMigration:
    def test_date_based_table_is_migrated(self, tmp_path):
        db_file = tmp_path / "old.sqlite3"
        create_old_db(db_file)

        db = Database(db_file)
        prefs = db.prefs_all()

        assert prefs[(1, "morning", 1)] == 1   # späterer Montag gewinnt
        assert prefs[(2, "noon", 1)] == -1     # Dienstag übernommen
        assert len(prefs) == 2

        # Alte Tabelle ist weg, neue Spalten vorhanden
        con = sqlite3.connect(db_file)
        cols = {r[1] for r in con.execute("PRAGMA table_info(prefs)")}
        assert cols == {"person_id", "weekday", "slot", "value"}
        tables = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert "prefs_old" not in tables
        assert "walk_completions" in tables
        assert "active_walks" in tables
        assert "person_badges" in tables
        assert "badge_categories" in tables
        assert "badge_definitions" in tables
        con.close()

    def test_migration_is_idempotent(self, tmp_path):
        db_file = tmp_path / "old.sqlite3"
        create_old_db(db_file)
        Database(db_file)
        db = Database(db_file)  # zweiter Start: keine Doppel-Migration
        assert db.prefs_all()[(1, "morning", 1)] == 1


class TestProfileSchema:
    def test_profile_fields_and_badge_seeds_on_existing_database(self, tmp_path):
        path = tmp_path / "profile-migration.sqlite3"
        create_old_db(path)
        con = sqlite3.connect(path)
        con.execute(
            "CREATE TABLE person_badges (person_id INTEGER NOT NULL, badge_id TEXT NOT NULL, "
            "awarded_at TEXT NOT NULL, PRIMARY KEY (person_id, badge_id))"
        )
        con.execute(
            "INSERT INTO person_badges VALUES (1, 'first-walk', '2026-10-12T00:00:00+00:00')"
        )
        con.commit()
        con.close()
        db = Database(path)
        with db._connect() as con:
            person_cols = {row[1] for row in con.execute("PRAGMA table_info(persons)")}
            categories = con.execute(
                "SELECT id FROM badge_categories ORDER BY sort_order"
            ).fetchall()
            definitions = con.execute(
                "SELECT id, category_id, retention, icon, art_key FROM badge_definitions ORDER BY id"
            ).fetchall()
        assert {
            "avatar_data", "avatar_mime_type", "badge_visibility",
            "push_enabled", "reminders_enabled",
        } <= person_cols
        assert len(categories) == 6
        definition_ids = {row[0] for row in definitions}
        assert {"first-walk", "ten-walks", "fifty-walks", "full-week"} <= definition_ids
        seasonal_ids = {
            badge_id for badge_id in definition_ids if badge_id.endswith(tuple(map(str, range(2026, 2031))))
        }
        assert len(seasonal_ids) == 50
        assert all(row[3] == "" for row in definitions)
        assert all(row[4] and row[4] != "seal" for row in definitions if row[0] in seasonal_ids)
        assert next(row for row in definitions if row[0] == "first-walk")[4] == "seed"
        assert next(row for row in definitions if row[0] == "valentines-walk-2027")[4] == "heart-paws"
        assert [db.level_definition(level)["name"] for level in range(1, 5)] == [
            "Gassi-Starter", "Runden-Profi", "Pfoten-Champion", "Spaziergangs-Legende"
        ]
        assert [db.level_definition(level)["threshold_points"] for level in range(1, 5)] == [
            0, 10, 25, 45
        ]
        assert db.person_exists(1)
        assert db.list_person_badges(1)[0]["badge_id"] == "first-walk"
        with db._connect() as con:
            badge_fks = con.execute("PRAGMA foreign_key_list(person_badges)").fetchall()
        assert any(row["table"] == "badge_definitions" for row in badge_fks)


    def test_badge_definition_icons_are_added_to_existing_database(self, tmp_path):
        path = tmp_path / "badge-icon-migration.sqlite3"
        db = Database(path)
        with db._connect() as con:
            con.execute("ALTER TABLE badge_definitions DROP COLUMN icon")
        migrated = Database(path)
        with migrated._connect() as con:
            columns = {row[1] for row in con.execute("PRAGMA table_info(badge_definitions)")}
        assert "art_key" in columns
        assert migrated.badge_definition("first-walk")["art_key"] == "seed"


class TestPushSubscriptions:
    def test_subscription_schema_is_added_to_existing_database(self, tmp_path):
        path = tmp_path / "subscriptions-migration.sqlite3"
        create_old_db(path)
        Database(path)

        con = sqlite3.connect(path)
        tables = {row[0] for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        con.close()
        assert "push_subscriptions" in tables

    def test_subscriptions_are_owned_unique_and_cascade_on_person_delete(self, tmp_path):
        db = Database(tmp_path / "subscriptions.sqlite3")
        jan = db.add_person("Jan")
        laura = db.add_person("Laura")
        first = {"endpoint": "https://push.example/1", "p256dh": "key1", "auth": "auth1"}
        second = {"endpoint": "https://push.example/2", "p256dh": "key2", "auth": "auth2"}

        db.save_push_subscription(jan["id"], **first)
        db.save_push_subscription(jan["id"], **second)
        assert {row["endpoint"] for row in db.list_push_subscriptions(jan["id"])} == {
            first["endpoint"], second["endpoint"],
        }

        db.save_push_subscription(laura["id"], **first)
        assert [row["endpoint"] for row in db.list_push_subscriptions(jan["id"])] == [
            second["endpoint"],
        ]
        assert [row["endpoint"] for row in db.list_push_subscriptions(laura["id"])] == [
            first["endpoint"],
        ]
        assert not db.delete_push_subscription(jan["id"], first["endpoint"])
        assert db.delete_push_subscription(laura["id"], first["endpoint"])

        db.delete_person(jan["id"])
        assert db.list_push_subscriptions(jan["id"]) == []


class TestReminderOutbox:
    def test_outbox_schema_is_added_to_existing_database(self, tmp_path):
        path = tmp_path / "reminder-outbox-migration.sqlite3"
        create_old_db(path)
        Database(path)

        con = sqlite3.connect(path)
        tables = {row[0] for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        con.close()
        assert "reminder_outbox" in tables

    def test_reconciliation_is_idempotent_and_cancels_changed_assignments(self, tmp_path):
        db = Database(tmp_path / "reminder-outbox.sqlite3")
        jan = db.add_person("Jan")
        laura = db.add_person("Laura")
        due_at = "2026-07-10T03:45:00+00:00"
        now = datetime(2026, 7, 1, tzinfo=timezone.utc)
        jan_job = (jan["id"], "2026-07-10", "morning", due_at)
        laura_job = (laura["id"], "2026-07-10", "morning", due_at)

        db.reconcile_reminder_outbox([jan_job], now)
        db.reconcile_reminder_outbox([jan_job], now)
        with db._connect() as con:
            rows = con.execute(
                "SELECT person_id, status, attempts FROM reminder_outbox"
            ).fetchall()
        assert [(row["person_id"], row["status"], row["attempts"]) for row in rows] == [
            (jan["id"], "pending", 0),
        ]

        db.reconcile_reminder_outbox([laura_job], now)
        with db._connect() as con:
            rows = con.execute(
                "SELECT person_id, status FROM reminder_outbox ORDER BY person_id"
            ).fetchall()
        assert [(row["person_id"], row["status"]) for row in rows] == [
            (jan["id"], "cancelled"),
            (laura["id"], "pending"),
        ]


class TestWalkCompletions:
    def test_unique_and_remove(self, tmp_path):
        db = Database(tmp_path / "walks.sqlite3")
        jan = db.add_person("Jan")
        laura = db.add_person("Laura")

        assert db.add_walk_completion(jan["id"], "2026-10-12", "morning", "plan")
        assert not db.add_walk_completion(jan["id"], "2026-10-12", "morning", "manual")
        assert db.add_walk_completion(jan["id"], "2026-10-12", "noon", "manual")
        rows = db.list_walk_completions(jan["id"])
        assert [(row["date"], row["slot"], row["source"]) for row in rows] == [
            ("2026-10-12", "morning", "plan"),
            ("2026-10-12", "noon", "manual"),
        ]
        assert all(row["created_at"] for row in rows)
        assert db.list_walk_completions(laura["id"]) == []
        assert db.remove_walk_completion(jan["id"], "2026-10-12", "morning")
        assert not db.remove_walk_completion(jan["id"], "2026-10-12", "morning")
        assert [row["slot"] for row in db.list_walk_completions(jan["id"])] == ["noon"]

    def test_session_start_and_finish(self, tmp_path):
        db = Database(tmp_path / "walks.sqlite3")
        jan = db.add_person("Jan")
        active = db.start_walk(jan["id"], "2026-10-12", "morning", "2026-10-12T04:30:00+00:00")
        assert active["slot"] == "morning"
        assert db.active_walk(jan["id"])["date"] == "2026-10-12"
        result = db.finish_walk(jan["id"], "2026-10-12T07:00:00+00:00")
        assert result and result["created"]
        assert db.active_walk(jan["id"]) is None
        assert db.list_walk_completions(jan["id"])[0]["source"] == "manual"
        assert db.finish_walk(jan["id"], "2026-10-12T07:01:00+00:00") is None

    def test_badges_can_be_removed(self, tmp_path):
        db = Database(tmp_path / "badges.sqlite3")
        jan = db.add_person("Jan")
        db.award_badges(jan["id"], ["first-walk"])
        db.award_badges(jan["id"], ["first-walk"])
        assert db.list_person_badges(jan["id"])[0]["badge_id"] == "first-walk"
        db.remove_badges(jan["id"], ["first-walk"])
        assert db.list_person_badges(jan["id"]) == []

    def test_delete_person_cascades(self, tmp_path):
        db = Database(tmp_path / "walks.sqlite3")
        jan = db.add_person("Jan")
        db.add_walk_completion(jan["id"], "2026-10-12", "morning", "manual")
        db.start_walk(jan["id"], "2026-10-12", "noon", "2026-10-12T12:30:00+00:00")
        db.delete_person(jan["id"])
        assert db.list_walk_completions() == []
        assert db.active_walk(jan["id"]) is None


class TestWeekdayPrefs:
    def test_set_update_clear(self, tmp_path):
        db = Database(tmp_path / "t.sqlite3")
        p = db.add_person("Jan")
        db.set_pref(p["id"], 5, "evening", 3)
        assert db.prefs_all() == {(5, "evening", p["id"]): 3}
        db.set_pref(p["id"], 5, "evening", 1)  # Update
        assert db.prefs_all()[(5, "evening", p["id"])] == 1
        db.set_pref(p["id"], 5, "evening", None)  # Löschen
        assert db.prefs_all() == {}

    def test_delete_person_cascades(self, tmp_path):
        db = Database(tmp_path / "t.sqlite3")
        p = db.add_person("Jan")
        db.set_pref(p["id"], 1, "morning", 2)
        db.delete_person(p["id"])
        assert db.prefs_all() == {}
