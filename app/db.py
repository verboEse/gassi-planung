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

ACCOUNTS_DDL = """
CREATE TABLE IF NOT EXISTS accounts (
    person_id INTEGER PRIMARY KEY REFERENCES persons(id) ON DELETE CASCADE,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL
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
            person_cols = {r[1] for r in con.execute("PRAGMA table_info(persons)")}
            if "calendar_token_version" not in person_cols:
                con.execute(
                    "ALTER TABLE persons ADD COLUMN calendar_token_version INTEGER NOT NULL DEFAULT 1"
                )
            account_cols = {r[1] for r in con.execute("PRAGMA table_info(accounts)")}
            if "apple_sub" in account_cols:
                linked = con.execute(
                    """
                    SELECT a.person_id, p.name
                    FROM accounts a JOIN persons p ON p.id = a.person_id
                    """
                ).fetchall()
                con.execute("DROP TABLE accounts")
                con.execute(ACCOUNTS_DDL)
                con.executemany(
                    "INSERT INTO accounts (person_id, username, password_hash) VALUES (?, ?, '')",
                    [(row["person_id"], row["name"]) for row in linked],
                )
            else:
                con.execute(ACCOUNTS_DDL)
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

    def list_registered_persons(self) -> list[dict]:
        with self._connect() as con:
            rows = con.execute(
                """
                SELECT p.id, p.name, p.color, p.active
                FROM persons p JOIN accounts a ON a.person_id = p.id
                WHERE p.active = 1 ORDER BY p.id
                """
            ).fetchall()
        return [dict(r) for r in rows]

    def add_account(self, display_name: str, password_hash: str) -> dict:
        display_name = display_name.strip()
        if not display_name:
            raise ValueError("Name darf nicht leer sein")
        with self._connect() as con:
            color = DEFAULT_COLORS[con.execute(
                "SELECT count(*) FROM accounts"
            ).fetchone()[0] % len(DEFAULT_COLORS)]
            cur = con.execute(
                "INSERT INTO persons (name, color) VALUES (?, ?)",
                (display_name, color),
            )
            person_id = cur.lastrowid
            con.execute(
                """
                INSERT INTO accounts (person_id, username, password_hash)
                VALUES (?, ?, ?)
                """,
                (person_id, display_name, password_hash),
            )
        return {"id": person_id, "name": display_name, "color": color, "active": 1}

    def account_for_username(self, username: str) -> dict | None:
        with self._connect() as con:
            row = con.execute(
                """
                SELECT p.id, p.name, p.color, p.active, a.password_hash
                FROM accounts a JOIN persons p ON p.id = a.person_id
                WHERE a.username = ? AND p.active = 1
                """,
                (username.strip(),),
            ).fetchone()
        return dict(row) if row else None

    def account_for_person(self, person_id: int) -> dict | None:
        with self._connect() as con:
            row = con.execute(
                """
                SELECT p.id, p.name, p.color, p.active
                FROM accounts a JOIN persons p ON p.id = a.person_id
                WHERE p.id = ? AND p.active = 1
                """,
                (person_id,),
            ).fetchone()
        return dict(row) if row else None

    def set_account_password(self, person_id: int, password_hash: str) -> bool:
        with self._connect() as con:
            cur = con.execute(
                "UPDATE accounts SET password_hash = ? WHERE person_id = ?",
                (password_hash, person_id),
            )
        return cur.rowcount > 0

    def calendar_person_version(self, person_id: int) -> int:
        with self._connect() as con:
            row = con.execute(
                "SELECT calendar_token_version FROM persons WHERE id = ?", (person_id,)
            ).fetchone()
        return row[0] if row else 0

    def calendar_person(self, person_id: int, token_version: int) -> dict | None:
        with self._connect() as con:
            row = con.execute(
                """
                SELECT p.id, p.name, p.color, p.active
                FROM accounts a JOIN persons p ON p.id = a.person_id
                WHERE p.id = ? AND p.active = 1 AND p.calendar_token_version = ?
                """,
                (person_id, token_version),
            ).fetchone()
        return dict(row) if row else None

    def rotate_calendar_token(self, person_id: int) -> int:
        with self._connect() as con:
            con.execute(
                "UPDATE persons SET calendar_token_version = calendar_token_version + 1 WHERE id = ?",
                (person_id,),
            )
            row = con.execute(
                "SELECT calendar_token_version FROM persons WHERE id = ?", (person_id,)
            ).fetchone()
        return row[0]

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
