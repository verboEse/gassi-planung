"""SQLite-Persistenz für die Gassi-Planung (Stdlib sqlite3, ohne ORM)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS persons (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    name   TEXT NOT NULL UNIQUE,
    color  TEXT NOT NULL DEFAULT '#4a90d9',
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS prefs (
    person_id INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    date      TEXT NOT NULL,
    slot      TEXT NOT NULL,
    value     INTEGER NOT NULL,
    PRIMARY KEY (person_id, date, slot)
);
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
        with self._connect() as con:
            con.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")
        return con

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

    # --- Prioritäten --------------------------------------------------------

    def set_pref(
        self, person_id: int, date: str, slot: str, value: int | None
    ) -> None:
        """Setzt eine Priorität; value=None löscht den Eintrag (zurück zu neutral)."""
        with self._connect() as con:
            if value is None:
                con.execute(
                    "DELETE FROM prefs WHERE person_id = ? AND date = ? AND slot = ?",
                    (person_id, date, slot),
                )
            else:
                con.execute(
                    """
                    INSERT INTO prefs (person_id, date, slot, value)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT (person_id, date, slot)
                    DO UPDATE SET value = excluded.value
                    """,
                    (person_id, date, slot, value),
                )

    def prefs_for_dates(self, dates: list[str]) -> dict[tuple[str, str, int], int]:
        """Liefert {(date, slot, person_id): value} für die gegebenen Tage."""
        if not dates:
            return {}
        placeholders = ",".join("?" for _ in dates)
        with self._connect() as con:
            rows = con.execute(
                f"SELECT person_id, date, slot, value FROM prefs WHERE date IN ({placeholders})",
                dates,
            ).fetchall()
        return {(r["date"], r["slot"], r["person_id"]): r["value"] for r in rows}
