"""SQLite-Persistenz für die Gassi-Planung (Stdlib sqlite3, ohne ORM).

Prioritäten sind **allgemeingültig pro Wochentag** (ISO: 1=Montag … 7=Sonntag)
und gelten damit für jede Kalenderwoche gleichermaßen.
"""
from __future__ import annotations

import sqlite3
from datetime import date as dt_date
from pathlib import Path

PERSONS_DDL = """
CREATE TABLE IF NOT EXISTS persons (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    name   TEXT NOT NULL UNIQUE,
    color  TEXT NOT NULL DEFAULT '#4a90d9',
    active INTEGER NOT NULL DEFAULT 1
)
"""

PREFS_DDL = """
CREATE TABLE IF NOT EXISTS prefs (
    person_id INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    weekday   INTEGER NOT NULL CHECK (weekday BETWEEN 1 AND 7),
    slot      TEXT NOT NULL,
    value     INTEGER NOT NULL,
    PRIMARY KEY (person_id, weekday, slot)
)
"""

DEFAULT_COLORS = [
    "#4a90d9",
    "#e67e22",
    "#27ae60",
    "#8e44ad",
    "#c0392b",
    "#16a085",
    "#d35400",
    "#2c3e50",
]


class Database:
    def __init__(self, path: str | Path):
        self.path = str(path)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")
        return con

    def _init_schema(self) -> None:
        with self._connect() as con:
            con.execute(PERSONS_DDL)
            cols = {r[1] for r in con.execute("PRAGMA table_info(prefs)")}
            if cols and "date" in cols:
                # Migration: alte datumsbasierte Tabelle (person_id, date, slot, value)
                # -> wochentagsbasiert. Bei mehreren Daten desselben Wochentags
                # gewinnt das jeweils späteste Datum.
                con.execute("ALTER TABLE prefs RENAME TO prefs_old")
                con.execute(PREFS_DDL)
                rows = con.execute(
                    "SELECT person_id, date, slot, value FROM prefs_old ORDER BY date ASC"
                ).fetchall()
                for r in rows:
                    wd = dt_date.fromisoformat(r["date"]).isoweekday()
                    con.execute(
                        "INSERT OR REPLACE INTO prefs (person_id, weekday, slot, value)"
                        " VALUES (?, ?, ?, ?)",
                        (r["person_id"], wd, r["slot"], r["value"]),
                    )
                con.execute("DROP TABLE prefs_old")
            else:
                con.execute(PREFS_DDL)

    # --- Personen ---------------------------------------------------------

    def list_persons(self) -> list[dict]:
        with self._connect() as con:
            rows = con.execute(
                "SELECT id, name, color, active FROM persons WHERE active = 1 ORDER BY id"
            ).fetchall()
        return [dict(r) for r in rows]

    def add_person(self, name: str, color: str | None = None) -> dict:
        name = name.strip()
        if not name:
            raise ValueError("Name darf nicht leer sein")
        if color is None:
            color = DEFAULT_COLORS[len(self.list_persons()) % len(DEFAULT_COLORS)]
        with self._connect() as con:
            cur = con.execute(
                "INSERT INTO persons (name, color) VALUES (?, ?)", (name, color)
            )
            pid = cur.lastrowid
        return {"id": pid, "name": name, "color": color, "active": 1}

    def delete_person(self, person_id: int) -> bool:
        with self._connect() as con:
            cur = con.execute("DELETE FROM persons WHERE id = ?", (person_id,))
            return cur.rowcount > 0

    def person_exists(self, person_id: int) -> bool:
        with self._connect() as con:
            row = con.execute(
                "SELECT 1 FROM persons WHERE id = ?", (person_id,)
            ).fetchone()
        return row is not None

    def get_person(self, person_id: int) -> dict | None:
        with self._connect() as con:
            row = con.execute(
                "SELECT id, name, color, active FROM persons WHERE id = ? AND active = 1",
                (person_id,),
            ).fetchone()
        return dict(row) if row else None

    # --- Prioritäten (allgemeingültig pro Wochentag) ------------------------

    def set_pref(
        self, person_id: int, weekday: int, slot: str, value: int | None
    ) -> None:
        """Setzt eine Priorität für einen Wochentag (1=Mo … 7=So).

        value=None löscht den Eintrag (zurück zu neutral).
        """
        with self._connect() as con:
            if value is None:
                con.execute(
                    "DELETE FROM prefs WHERE person_id = ? AND weekday = ? AND slot = ?",
                    (person_id, weekday, slot),
                )
            else:
                con.execute(
                    """
                    INSERT INTO prefs (person_id, weekday, slot, value)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT (person_id, weekday, slot)
                    DO UPDATE SET value = excluded.value
                    """,
                    (person_id, weekday, slot, value),
                )

    def prefs_all(self) -> dict[tuple[int, str, int], int]:
        """Liefert {(weekday, slot, person_id): value} aller Prioritäten."""
        with self._connect() as con:
            rows = con.execute(
                "SELECT person_id, weekday, slot, value FROM prefs"
            ).fetchall()
        return {(r["weekday"], r["slot"], r["person_id"]): r["value"] for r in rows}
