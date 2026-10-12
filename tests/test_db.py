"""Tests für die DB-Schicht: Migration und wochentagsbasierte Prioritäten."""
from __future__ import annotations

import sqlite3

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
        con.close()

    def test_migration_is_idempotent(self, tmp_path):
        db_file = tmp_path / "old.sqlite3"
        create_old_db(db_file)
        Database(db_file)
        db = Database(db_file)  # zweiter Start: keine Doppel-Migration
        assert db.prefs_all()[(1, "morning", 1)] == 1


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
