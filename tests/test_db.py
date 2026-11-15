"""Tests für die DB-Schicht: Migration und wochentagsbasierte Prioritäten."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import pytest

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

    def test_distance_column_migration_preserves_existing_walks(self, tmp_path):
        db_file = tmp_path / "distance-migration.sqlite3"
        db = Database(db_file)
        person = db.add_person("Jan")
        db.add_walk_completion(person["id"], "2026-10-12", "morning", "plan")

        with sqlite3.connect(db_file) as con:
            con.execute("ALTER TABLE walk_completions DROP COLUMN distance_meters")

        migrated = Database(db_file)
        completion = migrated.list_walk_completions(person["id"])[0]
        assert completion["distance_meters"] is None
        assert migrated.max_distance_meters(person["id"]) is None

    def test_dog_care_schema_migrates_without_changing_walks_or_plans(self, tmp_path):
        db_file = tmp_path / "dog-care-migration.sqlite3"
        db = Database(db_file)
        jan = db.add_person("Jan")
        db.add_walk_completion(jan["id"], "2026-10-12", "morning", "plan")
        with db._connect() as con:
            con.execute(
                "INSERT INTO weekly_plans (year, week, plan_json) VALUES (?, ?, ?)",
                (2026, 42, '{"jan":["morning"]}'),
            )
            con.execute("DROP TABLE IF EXISTS walk_completion_dogs")
            con.execute("DROP TABLE IF EXISTS dog_compatibility")
            con.execute("DROP TABLE IF EXISTS dog_care_share")
            con.execute("DROP TABLE IF EXISTS dogs")

        migrated = Database(db_file)

        completions = migrated.list_walk_completions(jan["id"])
        assert [(row["date"], row["slot"]) for row in completions] == [
            ("2026-10-12", "morning")
        ]
        with migrated._connect() as con:
            tables = {
                row[0]
                for row in con.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            assert {
                "dogs",
                "dog_compatibility",
                "dog_care_share",
                "walk_completion_dogs",
            } <= tables
            plan = con.execute(
                "SELECT plan_json FROM weekly_plans WHERE year = 2026 AND week = 42"
            ).fetchone()[0]
            share = con.execute(
                "SELECT enabled, token_version FROM dog_care_share WHERE id = 1"
            ).fetchone()
        assert plan == '{"jan":["morning"]}'
        assert tuple(share) == (0, 1)

    def test_walk_type_migration_preserves_links_and_supports_multiple_extras(self, tmp_path):
        db_file = tmp_path / "walk-type-migration.sqlite3"
        with sqlite3.connect(db_file) as con:
            con.executescript("""
                PRAGMA foreign_keys = ON;
                CREATE TABLE persons (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    color TEXT NOT NULL DEFAULT '#4a90d9',
                    active INTEGER NOT NULL DEFAULT 1
                );
                INSERT INTO persons (id, name) VALUES (1, 'Jan');
                CREATE TABLE shared_walks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    walk_date TEXT NOT NULL,
                    slot TEXT NOT NULL,
                    created_by INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
                    created_at TEXT NOT NULL,
                    UNIQUE (walk_date, slot)
                );
                INSERT INTO shared_walks
                    (id, walk_date, slot, created_by, created_at)
                VALUES (7, '2026-10-12', 'morning', 1, '2026-10-12T06:00:00Z');
                CREATE TABLE dogs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    feeding_instructions TEXT NOT NULL DEFAULT '',
                    medication_notes TEXT NOT NULL DEFAULT '',
                    allergies TEXT NOT NULL DEFAULT '',
                    veterinary_contact TEXT NOT NULL DEFAULT '',
                    walk_notes TEXT NOT NULL DEFAULT ''
                );
                INSERT INTO dogs (id, name) VALUES (9, 'Rex');
                CREATE TABLE walk_completions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    person_id INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
                    walk_date TEXT NOT NULL,
                    slot TEXT NOT NULL,
                    source TEXT NOT NULL CHECK (source IN ('plan', 'manual')),
                    off_plan INTEGER NOT NULL DEFAULT 0 CHECK (off_plan IN (0, 1)),
                    created_at TEXT NOT NULL,
                    shared_walk_id INTEGER REFERENCES shared_walks(id) ON DELETE SET NULL,
                    UNIQUE (person_id, walk_date, slot)
                );
                INSERT INTO walk_completions
                    (id, person_id, walk_date, slot, source, created_at, shared_walk_id)
                VALUES (42, 1, '2026-10-12', 'morning', 'manual',
                        '2026-10-12T06:00:00Z', 7);
                CREATE TABLE walk_completion_dogs (
                    completion_id INTEGER NOT NULL
                        REFERENCES walk_completions(id) ON DELETE CASCADE,
                    dog_id INTEGER NOT NULL REFERENCES dogs(id) ON DELETE CASCADE,
                    PRIMARY KEY (completion_id, dog_id)
                );
                INSERT INTO walk_completion_dogs VALUES (42, 9);
                CREATE TABLE active_walks (
                    person_id INTEGER PRIMARY KEY REFERENCES persons(id) ON DELETE CASCADE,
                    walk_date TEXT NOT NULL,
                    slot TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    off_plan INTEGER NOT NULL DEFAULT 0 CHECK (off_plan IN (0, 1))
                );
                INSERT INTO active_walks
                    (person_id, walk_date, slot, started_at)
                VALUES (1, '2026-10-13', 'noon', '2026-10-13T12:00:00Z');
            """)

        db = Database(db_file)

        with db._connect() as con:
            completion = con.execute(
                "SELECT id, walk_type, slot, shared_walk_id, off_plan "
                "FROM walk_completions WHERE id = 42"
            ).fetchone()
            assert tuple(completion) == (42, "planned", "morning", 7, 0)
            assert con.execute(
                "SELECT completion_id, dog_id FROM walk_completion_dogs"
            ).fetchall()[0][:] == (42, 9)
            active = con.execute(
                "SELECT walk_type, slot FROM active_walks WHERE person_id = 1"
            ).fetchone()
            assert tuple(active) == ("planned", "noon")

            for created_at in ("2026-10-12T08:00:00Z", "2026-10-12T10:00:00Z"):
                con.execute(
                    """INSERT INTO walk_completions
                       (person_id, walk_date, slot, walk_type, source, off_plan, created_at)
                       VALUES (1, '2026-10-12', NULL, 'extra', 'manual', 0, ?)""",
                    (created_at,),
                )
            assert con.execute(
                "SELECT count(*) FROM walk_completions "
                "WHERE walk_date = '2026-10-12' AND walk_type = 'extra'"
            ).fetchone()[0] == 2
            assert con.execute("PRAGMA foreign_key_check").fetchall() == []

    def test_takeover_status_migration_preserves_requests(self, tmp_path):
        db_file = tmp_path / "takeovers.sqlite3"
        db = Database(db_file)
        jan = db.add_person("Jan")
        laura = db.add_person("Laura")
        with sqlite3.connect(db_file) as con:
            con.execute("DROP INDEX IF EXISTS idx_active_walk_takeover_slot")
            con.execute("DROP TABLE walk_takeover_requests")
            con.execute("""
                CREATE TABLE walk_takeover_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    walk_date TEXT NOT NULL,
                    slot TEXT NOT NULL CHECK (slot IN ('morning', 'noon', 'evening')),
                    requester_id INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
                    assignee_id INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
                    status TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'approved', 'declined')),
                    created_at TEXT NOT NULL,
                    decided_at TEXT,
                    CHECK (requester_id != assignee_id)
                )
            """)
            con.execute(
                """INSERT INTO walk_takeover_requests
                   (walk_date, slot, requester_id, assignee_id, status, created_at)
                   VALUES ('2026-10-12', 'morning', ?, ?, 'pending', '2026-10-12T06:00:00Z')""",
                (laura["id"], jan["id"]),
            )

        db = Database(db_file)

        assert db.list_walk_takeover_requests(jan["id"])[0]["status"] == "pending"
        with sqlite3.connect(db_file) as con:
            schema = con.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'table' "
                "AND name = 'walk_takeover_requests'"
            ).fetchone()[0]
        assert "'shared'" in schema


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
        assert {
            "first-walk", "ten-walks", "fifty-walks", "full-week",
            "first-shared-walk", "ten-shared-walks", "fifty-shared-walks",
            "three-person-walk", "four-plus-walk",
        } <= definition_ids
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


class TestWalkCoordination:
    def test_existing_completions_gain_nullable_shared_reference(self, tmp_path):
        path = tmp_path / "shared-walk-migration.sqlite3"
        con = sqlite3.connect(path)
        con.executescript(
            """
            CREATE TABLE persons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                color TEXT NOT NULL DEFAULT '#4a90d9',
                active INTEGER NOT NULL DEFAULT 1
            );
            INSERT INTO persons (id, name) VALUES (1, 'Jan');
            CREATE TABLE walk_completions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                person_id INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
                walk_date TEXT NOT NULL,
                slot TEXT NOT NULL,
                source TEXT NOT NULL CHECK (source IN ('plan', 'manual')),
                created_at TEXT NOT NULL,
                UNIQUE (person_id, walk_date, slot)
            );
            INSERT INTO walk_completions
                (person_id, walk_date, slot, source, created_at)
            VALUES (1, '2026-10-12', 'morning', 'plan', '2026-10-12T06:00:00+00:00');
            CREATE TABLE active_walks (
                person_id INTEGER PRIMARY KEY REFERENCES persons(id) ON DELETE CASCADE,
                walk_date TEXT NOT NULL,
                slot TEXT NOT NULL,
                started_at TEXT NOT NULL
            );
            INSERT INTO active_walks
                (person_id, walk_date, slot, started_at)
            VALUES (1, '2026-10-13', 'noon', '2026-10-13T12:00:00+00:00');
            """
        )
        con.commit()
        con.close()

        db = Database(path)
        completion = db.list_walk_completions(1)[0]
        assert completion["date"] == "2026-10-12"
        assert completion["shared_walk_id"] is None
        assert completion["shared_group_size"] == 0
        assert completion["off_plan"] == 0
        result = db.finish_walk(1, "2026-10-13T14:00:00+00:00")
        assert result and result["off_plan"] is False
        migrated_completion = next(
            row for row in db.list_walk_completions(1) if row["date"] == "2026-10-13"
        )
        assert migrated_completion["off_plan"] == 0

    def test_takeovers_allow_one_active_request_per_slot(self, tmp_path):
        db = Database(tmp_path / "takeovers.sqlite3")
        jan = db.add_person("Jan")
        laura = db.add_person("Laura")
        max_person = db.add_person("Max")
        created_at = "2026-10-12T06:00:00+00:00"

        request = db.create_walk_takeover_request(
            "2026-10-12", "morning", laura["id"], jan["id"], created_at
        )
        with pytest.raises(sqlite3.IntegrityError):
            db.create_walk_takeover_request(
                "2026-10-12", "morning", max_person["id"], jan["id"], created_at
            )
        declined = db.decide_walk_takeover_request(
            request["id"], jan["id"], False, created_at
        )
        assert declined and declined["status"] == "declined"
        assert not db.approved_walk_takeover(laura["id"], "2026-10-12", "morning")

        request = db.create_walk_takeover_request(
            "2026-10-12", "morning", max_person["id"], jan["id"], created_at
        )
        approved = db.decide_walk_takeover_request(
            request["id"], jan["id"], True, created_at
        )
        assert approved and approved["status"] == "approved"
        assert db.approved_walk_takeover(max_person["id"], "2026-10-12", "morning")
        assert db.decide_walk_takeover_request(
            request["id"], jan["id"], False, created_at
        ) is None

    def test_shared_walk_creates_one_completion_per_participant(self, tmp_path):
        db = Database(tmp_path / "shared-walks.sqlite3")
        people = [db.add_person(name) for name in ("Jan", "Laura", "Max")]
        shared_walk = db.add_shared_walk_completions(
            people[0]["id"], "2026-10-12", "morning", [p["id"] for p in people[1:]]
        )
        completions = shared_walk["completions"]

        assert shared_walk["created"]
        assert {row["person_id"] for row in completions} == {p["id"] for p in people}
        assert len({row["shared_walk_id"] for row in completions}) == 1
        assert all(row["shared_group_size"] == 3 for row in db.list_walk_completions())
        duplicate = db.add_shared_walk_completions(
            people[0]["id"], "2026-10-12", "morning", [p["id"] for p in people[1:]]
        )
        assert not duplicate["created"]
        assert len(duplicate["completions"]) == 3
        assert len(db.list_walk_completions()) == 3


class TestWalkCompletions:
    def test_completion_listing_includes_only_recorded_dogs(self, tmp_path):
        db = Database(tmp_path / "completion-dogs.sqlite3")
        jan = db.add_person("Jan")
        rex = db.add_dog("Rex")
        bella = db.add_dog("Bella")
        db.add_walk_completion(
            jan["id"], "2026-10-12", "morning", "manual", dog_ids=[bella["id"], rex["id"]]
        )
        db.add_walk_completion(jan["id"], "2026-10-13", "morning", "manual")

        completions = db.list_walk_completions(jan["id"])

        assert completions[0]["dog_ids"] == [rex["id"], bella["id"]]
        assert completions[0]["dog_names"] == ["Rex", "Bella"]
        assert completions[1]["dog_ids"] == []
        assert completions[1]["dog_names"] == []
        db.delete_dog(rex["id"])
        assert db.list_walk_completions(jan["id"])[0]["dog_names"] == ["Bella"]

    def test_unique_and_remove(self, tmp_path):
        db = Database(tmp_path / "walks.sqlite3")
        jan = db.add_person("Jan")
        laura = db.add_person("Laura")

        assert db.add_walk_completion(jan["id"], "2026-10-12", "morning", "plan")
        assert not db.add_walk_completion(jan["id"], "2026-10-12", "morning", "manual")
        assert db.add_walk_completion(
            jan["id"], "2026-10-12", "noon", "manual", off_plan=True
        )
        rows = db.list_walk_completions(jan["id"])
        assert [(row["date"], row["slot"], row["source"]) for row in rows] == [
            ("2026-10-12", "morning", "plan"),
            ("2026-10-12", "noon", "manual"),
        ]
        assert all(row["created_at"] for row in rows)
        assert [row["off_plan"] for row in rows] == [0, 1]
        assert db.list_walk_completions(laura["id"]) == []
        assert db.remove_walk_completion(jan["id"], "2026-10-12", "morning")
        assert not db.remove_walk_completion(jan["id"], "2026-10-12", "morning")
        assert [row["slot"] for row in db.list_walk_completions(jan["id"])] == ["noon"]

    def test_session_start_and_finish(self, tmp_path):
        db = Database(tmp_path / "walks.sqlite3")
        jan = db.add_person("Jan")
        active = db.start_walk(
            jan["id"], "2026-10-12", "morning", "2026-10-12T04:30:00+00:00",
            off_plan=True,
        )
        assert active["slot"] == "morning"
        assert active["off_plan"] == 1
        assert db.active_walk(jan["id"])["date"] == "2026-10-12"
        result = db.finish_walk(jan["id"], "2026-10-12T07:00:00+00:00")
        assert result and result["created"]
        assert db.active_walk(jan["id"]) is None
        assert db.list_walk_completions(jan["id"])[0]["source"] == "manual"
        assert db.list_walk_completions(jan["id"])[0]["off_plan"] == 1
        assert db.finish_walk(jan["id"], "2026-10-12T07:01:00+00:00") is None

    def test_extra_sessions_are_distinct_and_removable_by_completion_id(self, tmp_path):
        db = Database(tmp_path / "extra-walks.sqlite3")
        jan = db.add_person("Jan")

        completion_ids = []
        for started_at, ended_at in (
            ("2026-10-12T08:00:00+00:00", "2026-10-12T08:30:00+00:00"),
            ("2026-10-12T10:00:00+00:00", "2026-10-12T10:30:00+00:00"),
        ):
            active = db.start_walk(
                jan["id"], "2026-10-12", None, started_at, walk_type="extra"
            )
            assert active["walk_type"] == "extra"
            result = db.finish_walk(jan["id"], ended_at)
            assert result and result["walk_type"] == "extra" and result["created"]
            completion_ids.append(result["completion_id"])

        completions = db.list_walk_completions(jan["id"])
        assert [row["completion_id"] for row in completions] == completion_ids
        assert all(row["slot"] is None and row["walk_type"] == "extra" for row in completions)
        assert [row["created_at"] for row in completions] == [
            "2026-10-12T08:30:00+00:00",
            "2026-10-12T10:30:00+00:00",
        ]
        assert db.remove_extra_walk_completion(jan["id"], completion_ids[0])
        assert [row["completion_id"] for row in db.list_walk_completions(jan["id"])] == [
            completion_ids[1]
        ]
        assert not db.remove_extra_walk_completion(jan["id"], completion_ids[0])

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


class TestDogProfiles:
    def test_profile_crud_compatibility_and_delete_cleanup(self, tmp_path):
        db = Database(tmp_path / "dogs.sqlite3")
        jan = db.add_person("Jan")
        first = db.add_dog("  Bello  ", feeding_instructions="Morgens füttern")
        second = db.add_dog("Mila")
        db.add_walk_completion(jan["id"], "2026-10-12", "morning", "manual")
        with db._connect() as con:
            completion_id = con.execute(
                "SELECT id FROM walk_completions WHERE person_id = ?",
                (jan["id"],),
            ).fetchone()[0]

        updated = db.update_dog(
            first["id"], name="Bello", allergies="Nüsse", walk_notes="An der Leine"
        )
        assert updated["feeding_instructions"] == "Morgens füttern"
        assert updated["allergies"] == "Nüsse"
        assert db.set_dog_compatibility(first["id"], [second["id"], first["id"]])
        assert db.are_dogs_compatible(first["id"], second["id"])
        assert db.are_dogs_compatible(second["id"], first["id"])
        assert db.are_dogs_compatible(first["id"], first["id"])
        assert db.list_dogs()[0]["compatible_dog_ids"] == [second["id"]]
        with db._connect() as con:
            con.execute(
                "INSERT INTO walk_completion_dogs (completion_id, dog_id) VALUES (?, ?)",
                (completion_id, first["id"]),
            )

        assert db.delete_dog(first["id"])
        assert not db.delete_dog(first["id"])
        assert not db.are_dogs_compatible(first["id"], second["id"])
        assert db.get_dog(second["id"])["compatible_dog_ids"] == []
        assert db.list_walk_completions(jan["id"])[0]["date"] == "2026-10-12"
        with db._connect() as con:
            assert con.execute("SELECT count(*) FROM walk_completion_dogs").fetchone()[0] == 0

    def test_completion_assignments_and_share_state(self, tmp_path):
        db = Database(tmp_path / "dog-assignments.sqlite3")
        jan = db.add_person("Jan")
        dog = db.add_dog("Bello")
        db.add_walk_completion(jan["id"], "2026-10-12", "morning", "manual")

        assert db.set_completion_dogs(
            jan["id"], "2026-10-12", "morning", [dog["id"], dog["id"]]
        )
        assert db.completion_dog_ids(jan["id"], "2026-10-12", "morning") == [dog["id"]]
        assert not db.set_completion_dogs(jan["id"], "2026-10-13", "morning", [])
        assert db.dog_care_share_state() == {"enabled": 0, "token_version": 1}
        assert db.enable_dog_care_share() == 1
        assert db.dog_care_share_is_valid(1)
        assert db.revoke_dog_care_share() == 2
        assert not db.dog_care_share_is_valid(1)
        assert db.dog_care_share_state() == {"enabled": 0, "token_version": 2}

    def test_shared_completion_dog_assignments_are_atomic(self, tmp_path):
        db = Database(tmp_path / "shared-dog-assignments.sqlite3")
        jan = db.add_person("Jan")
        laura = db.add_person("Laura")
        bello = db.add_dog("Bello")
        mila = db.add_dog("Mila")

        shared = db.add_shared_walk_completions(
            jan["id"],
            "2026-10-12",
            "morning",
            [laura["id"]],
            dog_ids_by_person={jan["id"]: [bello["id"]], laura["id"]: [mila["id"]]},
        )
        assert shared["created"]
        assert db.completion_dog_ids(jan["id"], "2026-10-12", "morning") == [bello["id"]]
        assert db.completion_dog_ids(laura["id"], "2026-10-12", "morning") == [mila["id"]]

        with pytest.raises(sqlite3.IntegrityError):
            db.add_shared_walk_completions(
                jan["id"],
                "2026-10-13",
                "morning",
                [laura["id"]],
                dog_ids_by_person={jan["id"]: [bello["id"]], laura["id"]: [999]},
            )
        assert not db.walk_completion_exists("2026-10-13", "morning")
