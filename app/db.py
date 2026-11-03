"""SQLite-Persistenz für Gassi-Planung und eingefrorene Wochenpläne."""
from __future__ import annotations

import json
import sqlite3
from datetime import date as dt_date
from datetime import datetime, timedelta, timezone
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
    password_hash TEXT NOT NULL,
    is_admin INTEGER NOT NULL DEFAULT 0,
    auth_version INTEGER NOT NULL DEFAULT 1
)
"""

ACTIVITY_DDL = """
CREATE TABLE IF NOT EXISTS activity_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_username TEXT NOT NULL,
    action TEXT NOT NULL,
    subject_username TEXT NOT NULL,
    details_json TEXT NOT NULL DEFAULT '{}',
    occurred_at TEXT NOT NULL
)
"""

WEEKLY_PLANS_DDL = """
CREATE TABLE IF NOT EXISTS weekly_plans (
    year INTEGER NOT NULL,
    week INTEGER NOT NULL,
    plan_json TEXT NOT NULL,
    PRIMARY KEY (year, week)
)
"""

WALK_COMPLETIONS_DDL = """
CREATE TABLE IF NOT EXISTS walk_completions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    walk_date TEXT NOT NULL,
    slot TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('plan', 'manual')),
    created_at TEXT NOT NULL,
    UNIQUE (person_id, walk_date, slot)
)
"""

WALK_COMPLETIONS_INDEX_DDL = """
CREATE INDEX IF NOT EXISTS idx_walk_completions_person_date
ON walk_completions (person_id, walk_date)
"""

ACTIVE_WALKS_DDL = """
CREATE TABLE IF NOT EXISTS active_walks (
    person_id INTEGER PRIMARY KEY REFERENCES persons(id) ON DELETE CASCADE,
    walk_date TEXT NOT NULL,
    slot TEXT NOT NULL,
    started_at TEXT NOT NULL
)
"""

BADGE_CATEGORIES_DDL = """
CREATE TABLE IF NOT EXISTS badge_categories (
    id TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    sort_order INTEGER NOT NULL UNIQUE
)
"""

BADGE_DEFINITIONS_DDL = """
CREATE TABLE IF NOT EXISTS badge_definitions (
    id TEXT PRIMARY KEY,
    category_id TEXT NOT NULL REFERENCES badge_categories(id),
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    condition_type TEXT NOT NULL,
    condition_json TEXT NOT NULL DEFAULT '{}',
    target_value INTEGER,
    season TEXT,
    event_year INTEGER,
    starts_at TEXT,
    ends_at TEXT,
    retention TEXT NOT NULL CHECK (retention IN ('current-count', 'historical')),
    active INTEGER NOT NULL DEFAULT 1,
    icon TEXT NOT NULL DEFAULT '',
    art_key TEXT NOT NULL DEFAULT 'seal'
)
"""

PERSON_BADGES_DDL = """
CREATE TABLE IF NOT EXISTS person_badges (
    person_id INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    badge_id TEXT NOT NULL REFERENCES badge_definitions(id) ON DELETE CASCADE,
    awarded_at TEXT NOT NULL,
    PRIMARY KEY (person_id, badge_id)
)
"""

LEVEL_DEFINITIONS_DDL = """
CREATE TABLE IF NOT EXISTS level_definitions (
    level INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    threshold_points INTEGER NOT NULL,
    locale TEXT NOT NULL DEFAULT 'de'
)
"""

LEVEL_SEEDS = [
    (1, "Gassi-Starter", 0, "de"),
    (2, "Runden-Profi", 10, "de"),
    (3, "Pfoten-Champion", 25, "de"),
    (4, "Spaziergangs-Legende", 45, "de"),
]

BADGE_CATEGORIES = [
    ("start-discovery", "Start & Entdecken", 1),
    ("walk-milestones", "Runden-Meilensteine", 2),
    ("streaks-habits", "Serien & Gewohnheiten", 3),
    ("loyalty-long-term", "Treue & Langzeit", 4),
    ("season-events", "Saison & Ereignisse", 5),
    ("community-sharing", "Community & Teilen", 6),
]

BADGE_SEEDS = [
    ("first-walk", "start-discovery", "Erste Runde", "Erledige deine erste Gassirunde.", "completion-count", '{"source":"any"}', 1, None, None, "current-count", "seed"),
    ("ten-walks", "walk-milestones", "10 Runden", "Erledige zehn Gassirunden.", "completion-count", '{"source":"any"}', 10, None, None, "current-count", "bronze-medal"),
    ("fifty-walks", "walk-milestones", "50 Runden", "Erledige fünfzig Gassirunden.", "completion-count", '{"source":"any"}', 50, None, None, "current-count", "gold-medal"),
    ("full-week", "streaks-habits", "Volle Woche", "Erledige mindestens eine Runde an jedem Tag einer ISO-Kalenderwoche.", "full-iso-week", '{}', 7, None, None, "historical", "seven-paws"),
]

SEASONAL_EVENT_SEEDS = [
    ("new-year-walk", "Neujahr", "Neujahrsrunde", "Starte das Jahr mit einer Gassirunde.", 1, 1, "fireworks"),
    ("valentines-walk", "Valentinstag", "Valentinstagsrunde", "Teile am Valentinstag eine Runde mit deinem Lieblingsmenschen.", 2, 14, "heart-paws"),
    ("spring-walk", "Frühlingsanfang", "Frühlingspfoten", "Begrüße den Frühling mit einer Gassirunde.", 3, 20, "bloom"),
    ("earth-day-walk", "Earth Day", "Grüne Pfoten", "Feiere den Earth Day mit einem Spaziergang draußen.", 4, 22, "paw-globe"),
    ("summer-solstice-walk", "Sommersonnenwende", "Sonnenpfoten", "Geh zur Sommersonnenwende eine Runde.", 6, 21, "sun-path"),
    ("autumn-walk", "Herbstanfang", "Goldene Pfoten", "Entdecke den Herbst bei einer Gassirunde.", 9, 22, "leaf-trail"),
    ("animal-day-walk", "Welttierschutztag", "Fürsorgliche Pfoten", "Geh am Welttierschutztag eine Runde.", 10, 4, "paw-shield"),
    ("halloween-walk", "Halloween", "Mondscheinrunde", "Geh an Halloween eine Gassirunde.", 10, 31, "moon-trail"),
    ("st-nicholas-walk", "Nikolaustag", "Nikolauspfoten", "Geh am Nikolaustag eine Gassirunde.", 12, 6, "gift-paw"),
    ("winter-solstice-walk", "Wintersonnenwende", "Winterpfoten", "Geh zur Wintersonnenwende eine Runde.", 12, 21, "snow-paw"),
]
# ponytail: fünf Jahre saisonale Definitionen vorbereiten; beim jährlichen Content-Update den Horizont erweitern.
SEASONAL_BADGE_SEEDS = [
    (
        f"{slug}-{year}", season, year, f"{year:04d}-{month:02d}-{day:02d}",
        title, description, icon,
    )
    for year in range(2026, 2031)
    for slug, season, title, description, month, day, icon in SEASONAL_EVENT_SEEDS
]

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
            person_additions = {
                "calendar_token_version": "INTEGER NOT NULL DEFAULT 1",
                "avatar_data": "BLOB",
                "avatar_mime_type": "TEXT",
                "avatar_updated_at": "TEXT",
                "badge_visibility": "INTEGER NOT NULL DEFAULT 0",
                "push_enabled": "INTEGER NOT NULL DEFAULT 0",
                "reminders_enabled": "INTEGER NOT NULL DEFAULT 0",
            }
            for column, definition in person_additions.items():
                if column not in person_cols:
                    con.execute(f"ALTER TABLE persons ADD COLUMN {column} {definition}")
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
                account_cols = {r[1] for r in con.execute("PRAGMA table_info(accounts)")}
                if "is_admin" not in account_cols:
                    con.execute("ALTER TABLE accounts ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0")
                if "auth_version" not in account_cols:
                    con.execute("ALTER TABLE accounts ADD COLUMN auth_version INTEGER NOT NULL DEFAULT 1")
            con.execute(ACTIVITY_DDL)
            con.execute(WEEKLY_PLANS_DDL)
            con.execute(WALK_COMPLETIONS_DDL)
            con.execute(WALK_COMPLETIONS_INDEX_DDL)
            con.execute(ACTIVE_WALKS_DDL)
            con.execute(BADGE_CATEGORIES_DDL)
            con.execute(BADGE_DEFINITIONS_DDL)
            badge_cols = {row[1] for row in con.execute("PRAGMA table_info(badge_definitions)")}
            if "icon" not in badge_cols:
                con.execute(
                    "ALTER TABLE badge_definitions ADD COLUMN icon TEXT NOT NULL DEFAULT ''"
                )
            else:
                con.execute("UPDATE badge_definitions SET icon = '' WHERE icon != ''")
            if "art_key" not in badge_cols:
                con.execute(
                    "ALTER TABLE badge_definitions ADD COLUMN art_key TEXT NOT NULL DEFAULT 'seal'"
                )
            con.execute(LEVEL_DEFINITIONS_DDL)
            level_cols = {row[1] for row in con.execute("PRAGMA table_info(level_definitions)")}
            if "threshold_points" not in level_cols:
                con.execute(
                    "ALTER TABLE level_definitions ADD COLUMN threshold_points INTEGER NOT NULL DEFAULT 0"
                )
            con.executemany(
                "INSERT OR IGNORE INTO badge_categories (id, label, sort_order) VALUES (?, ?, ?)",
                BADGE_CATEGORIES,
            )
            con.executemany(
                """
                INSERT OR IGNORE INTO badge_definitions
                    (id, category_id, title, description, condition_type,
                     condition_json, target_value, season, event_year, retention, art_key)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                BADGE_SEEDS,
            )
            con.executemany(
                "UPDATE badge_definitions SET art_key = ? WHERE id = ?",
                [(art_key, badge_id) for badge_id, _, _, _, _, _, _, _, _, _, art_key in BADGE_SEEDS],
            )
            con.executemany(
                """
                INSERT OR IGNORE INTO badge_definitions
                    (id, category_id, title, description, condition_type,
                     condition_json, target_value, season, event_year, starts_at,
                     ends_at, retention, art_key)
                VALUES (?, 'season-events', ?, ?, 'date-completion', ?, 1, ?, ?, ?, ?, 'historical', ?)
                """,
                [
                    (
                        badge_id,
                        f"{event_title} {year}",
                        description,
                        json.dumps({"date": event_date}),
                        season,
                        year,
                        event_date,
                        event_date,
                        icon,
                    )
                    for badge_id, season, year, event_date, event_title, description, icon in SEASONAL_BADGE_SEEDS
                ],
            )
            con.executemany(
                "UPDATE badge_definitions SET title = ?, description = ?, art_key = ? WHERE id = ?",
                [
                    (f"{title} {year}", description, icon, badge_id)
                    for badge_id, _, year, _, title, description, icon in SEASONAL_BADGE_SEEDS
                ],
            )
            con.executemany(
                """
                INSERT OR IGNORE INTO level_definitions (level, name, threshold_points, locale)
                VALUES (?, ?, ?, ?)
                """,
                LEVEL_SEEDS,
            )
            if con.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'person_badges'"
            ).fetchone():
                badge_fks = con.execute("PRAGMA foreign_key_list(person_badges)").fetchall()
                if not any(
                    row["table"] == "badge_definitions" and row["from"] == "badge_id"
                    for row in badge_fks
                ):
                    existing_badges = con.execute(
                        "SELECT person_id, badge_id, awarded_at FROM person_badges"
                    ).fetchall()
                    known_ids = {
                        row[0] for row in con.execute("SELECT id FROM badge_definitions")
                    }
                    for badge_id in {row["badge_id"] for row in existing_badges} - known_ids:
                        con.execute(
                            """
                            INSERT INTO badge_definitions
                                (id, category_id, title, description, condition_type,
                                 condition_json, retention)
                            VALUES (?, 'start-discovery', ?, ?, 'legacy', '{}', 'historical')
                            """,
                            (badge_id, badge_id, "Historischer Badge-Eintrag"),
                        )
                    con.execute("ALTER TABLE person_badges RENAME TO person_badges_old")
                    con.execute(PERSON_BADGES_DDL)
                    con.executemany(
                        """
                        INSERT INTO person_badges (person_id, badge_id, awarded_at)
                        VALUES (?, ?, ?)
                        """,
                        [tuple(row) for row in existing_badges],
                    )
                    con.execute("DROP TABLE person_badges_old")
            else:
                con.execute(PERSON_BADGES_DDL)
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

    def profile(self, person_id: int) -> dict | None:
        with self._connect() as con:
            row = con.execute(
                """
                SELECT p.id, p.name, p.color, p.avatar_mime_type, p.avatar_updated_at,
                       p.badge_visibility, p.push_enabled, p.reminders_enabled,
                       (SELECT MAX(l.occurred_at) FROM activity_log l
                        JOIN accounts a ON a.username = l.actor_username
                        WHERE a.person_id = p.id) AS last_activity
                FROM persons p JOIN accounts a ON a.person_id = p.id
                WHERE p.id = ? AND p.active = 1
                """,
                (person_id,),
            ).fetchone()
        if row is None:
            return None
        result = dict(row)
        for key in ("badge_visibility", "push_enabled", "reminders_enabled"):
            result[key] = bool(result[key])
        avatar_mime_type = result.pop("avatar_mime_type")
        result["avatar_url"] = (
            f"/api/profile/avatar?v={result['avatar_updated_at']}"
            if avatar_mime_type else None
        )
        result.pop("avatar_updated_at")
        return result

    def save_avatar(self, person_id: int, data: bytes, mime_type: str) -> bool:
        updated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._connect() as con:
            cur = con.execute(
                """
                UPDATE persons
                SET avatar_data = ?, avatar_mime_type = ?, avatar_updated_at = ?
                WHERE id = ? AND active = 1
                """,
                (data, mime_type, updated_at, person_id),
            )
        return cur.rowcount > 0

    def avatar(self, person_id: int) -> tuple[bytes, str] | None:
        with self._connect() as con:
            row = con.execute(
                """
                SELECT avatar_data, avatar_mime_type FROM persons
                WHERE id = ? AND active = 1
                """,
                (person_id,),
            ).fetchone()
        if not row or row["avatar_data"] is None or row["avatar_mime_type"] is None:
            return None
        return bytes(row["avatar_data"]), row["avatar_mime_type"]

    def remove_avatar(self, person_id: int) -> bool:
        with self._connect() as con:
            cur = con.execute(
                """
                UPDATE persons
                SET avatar_data = NULL, avatar_mime_type = NULL, avatar_updated_at = NULL
                WHERE id = ? AND active = 1
                """,
                (person_id,),
            )
        return cur.rowcount > 0

    def update_profile_preferences(
        self,
        person_id: int,
        *,
        badge_visibility: bool | None = None,
        push_enabled: bool | None = None,
        reminders_enabled: bool | None = None,
    ) -> bool:
        columns = {
            "badge_visibility": badge_visibility,
            "push_enabled": push_enabled,
            "reminders_enabled": reminders_enabled,
        }
        updates = [(column, int(value)) for column, value in columns.items() if value is not None]
        if not updates:
            return self.person_exists(person_id)
        assignments = ", ".join(f"{column} = ?" for column, _ in updates)
        with self._connect() as con:
            cur = con.execute(
                f"UPDATE persons SET {assignments} WHERE id = ? AND active = 1",
                (*(value for _, value in updates), person_id),
            )
        return cur.rowcount > 0

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
                SELECT p.id, p.name, p.color, p.active, a.password_hash,
                       a.is_admin, a.auth_version
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
                SELECT p.id, p.name, p.color, p.active, a.is_admin, a.auth_version
                FROM accounts a JOIN persons p ON p.id = a.person_id
                WHERE p.id = ? AND p.active = 1
                """,
                (person_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_admin_users(self) -> list[dict]:
        with self._connect() as con:
            rows = con.execute(
                """
                SELECT p.id, p.name, p.color, a.username, a.is_admin,
                       (SELECT MAX(occurred_at) FROM activity_log l
                        WHERE l.action = 'login' AND l.actor_username = a.username) AS last_login
                FROM accounts a JOIN persons p ON p.id = a.person_id
                WHERE p.active = 1 ORDER BY p.name COLLATE NOCASE
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def set_account_password(self, person_id: int, password_hash: str) -> int | None:
        with self._connect() as con:
            cur = con.execute(
                """
                UPDATE accounts SET password_hash = ?, auth_version = auth_version + 1
                WHERE person_id = ?
                """,
                (password_hash, person_id),
            )
            if not cur.rowcount:
                return None
            row = con.execute(
                "SELECT auth_version FROM accounts WHERE person_id = ?", (person_id,)
            ).fetchone()
        return row["auth_version"]

    def set_admin(self, username: str, enabled: bool) -> bool:
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute(
                "SELECT person_id, is_admin FROM accounts WHERE username = ?",
                (username.strip(),),
            ).fetchone()
            if not row:
                return False
            if bool(row["is_admin"]) == enabled:
                return True
            if not enabled:
                total = con.execute(
                    "SELECT count(*) FROM accounts WHERE is_admin = 1"
                ).fetchone()[0]
                if total <= 1:
                    raise ValueError("Der letzte Admin kann nicht herabgestuft werden")
            con.execute(
                "UPDATE accounts SET is_admin = ? WHERE person_id = ?",
                (int(enabled), row["person_id"]),
            )
        return True

    def record_activity(
        self,
        actor_username: str,
        action: str,
        subject_username: str,
        details: dict | None = None,
    ) -> None:
        now = datetime.now(timezone.utc)
        cutoff = (now - timedelta(days=90)).isoformat(timespec="seconds")
        with self._connect() as con:
            con.execute("DELETE FROM activity_log WHERE occurred_at < ?", (cutoff,))
            con.execute(
                """
                INSERT INTO activity_log
                    (actor_username, action, subject_username, details_json, occurred_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    actor_username,
                    action,
                    subject_username,
                    json.dumps(details or {}, ensure_ascii=False),
                    now.isoformat(timespec="seconds"),
                ),
            )

    def recent_activity(self) -> list[dict]:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat(timespec="seconds")
        with self._connect() as con:
            con.execute("DELETE FROM activity_log WHERE occurred_at < ?", (cutoff,))
            rows = con.execute(
                """
                SELECT actor_username, action, subject_username, details_json, occurred_at
                FROM activity_log WHERE occurred_at >= ?
                ORDER BY occurred_at DESC
                """,
                (cutoff,),
            ).fetchall()
        return [
            {
                "actor": row["actor_username"],
                "action": row["action"],
                "subject": row["subject_username"],
                "details": json.loads(row["details_json"]),
                "occurred_at": row["occurred_at"],
            }
            for row in rows
        ]

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

    def level_definition(self, level: int, locale: str = "de") -> dict:
        with self._connect() as con:
            row = con.execute(
                "SELECT level, name, threshold_points, locale FROM level_definitions "
                "WHERE level = ? AND locale = ?",
                (level, locale),
            ).fetchone()
        return dict(row) if row else {
            "level": level,
            "name": f"Level {level}",
            "threshold_points": None,
            "locale": locale,
        }

    # --- Erledigte Gassirunden ----------------------------------------------

    def add_walk_completion(
        self, person_id: int, walk_date: str, slot: str, source: str
    ) -> bool:
        created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._connect() as con:
            cur = con.execute(
                """
                INSERT OR IGNORE INTO walk_completions
                    (person_id, walk_date, slot, source, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (person_id, walk_date, slot, source, created_at),
            )
        return cur.rowcount > 0

    def remove_walk_completion(self, person_id: int, walk_date: str, slot: str) -> bool:
        with self._connect() as con:
            cur = con.execute(
                """
                DELETE FROM walk_completions
                WHERE person_id = ? AND walk_date = ? AND slot = ?
                """,
                (person_id, walk_date, slot),
            )
        return cur.rowcount > 0

    def list_walk_completions(self, person_id: int | None = None) -> list[dict]:
        query = """
            SELECT person_id, walk_date AS date, slot, source, created_at
            FROM walk_completions
        """
        params: tuple[int, ...] = ()
        if person_id is not None:
            query += " WHERE person_id = ?"
            params = (person_id,)
        query += " ORDER BY walk_date, slot, person_id"
        with self._connect() as con:
            rows = con.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def active_walk(self, person_id: int) -> dict | None:
        with self._connect() as con:
            row = con.execute(
                """
                SELECT person_id, walk_date AS date, slot, started_at
                FROM active_walks WHERE person_id = ?
                """,
                (person_id,),
            ).fetchone()
        return dict(row) if row else None

    def start_walk(self, person_id: int, walk_date: str, slot: str, started_at: str) -> dict:
        with self._connect() as con:
            con.execute(
                """
                INSERT OR IGNORE INTO active_walks (person_id, walk_date, slot, started_at)
                VALUES (?, ?, ?, ?)
                """,
                (person_id, walk_date, slot, started_at),
            )
            row = con.execute(
                """
                SELECT person_id, walk_date AS date, slot, started_at
                FROM active_walks WHERE person_id = ?
                """,
                (person_id,),
            ).fetchone()
        assert row is not None
        return dict(row)

    def finish_walk(self, person_id: int, ended_at: str) -> dict | None:
        with self._connect() as con:
            row = con.execute(
                """
                SELECT person_id, walk_date AS date, slot
                FROM active_walks WHERE person_id = ?
                """,
                (person_id,),
            ).fetchone()
            if row is None:
                return None
            cur = con.execute(
                """
                INSERT OR IGNORE INTO walk_completions
                    (person_id, walk_date, slot, source, created_at)
                VALUES (?, ?, ?, 'manual', ?)
                """,
                (row["person_id"], row["date"], row["slot"], ended_at),
            )
            con.execute("DELETE FROM active_walks WHERE person_id = ?", (person_id,))
        return {
            "person_id": row["person_id"],
            "date": row["date"],
            "slot": row["slot"],
            "source": "manual",
            "created": cur.rowcount > 0,
        }

    def award_badges(self, person_id: int, badge_ids: list[str]) -> None:
        if not badge_ids:
            return
        awarded_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._connect() as con:
            con.executemany(
                """
                INSERT OR IGNORE INTO person_badges (person_id, badge_id, awarded_at)
                VALUES (?, ?, ?)
                """,
                [(person_id, badge_id, awarded_at) for badge_id in badge_ids],
            )

    def list_person_badges(self, person_id: int | None = None) -> list[dict]:
        query = "SELECT person_id, badge_id, awarded_at FROM person_badges"
        params: tuple[int, ...] = ()
        if person_id is not None:
            query += " WHERE person_id = ?"
            params = (person_id,)
        query += " ORDER BY person_id, awarded_at, badge_id"
        with self._connect() as con:
            rows = con.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def badge_categories(self) -> list[dict]:
        with self._connect() as con:
            rows = con.execute(
                "SELECT id, label, sort_order FROM badge_categories ORDER BY sort_order"
            ).fetchall()
        return [dict(row) for row in rows]

    def badge_definitions(self) -> list[dict]:
        with self._connect() as con:
            rows = con.execute(
                """
                SELECT d.*, c.label AS category_label, c.sort_order
                FROM badge_definitions d
                JOIN badge_categories c ON c.id = d.category_id
                WHERE d.active = 1
                ORDER BY c.sort_order, d.event_year, d.title
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def badge_definition(self, badge_id: str) -> dict | None:
        with self._connect() as con:
            row = con.execute(
                """
                SELECT d.*, c.label AS category_label, c.sort_order
                FROM badge_definitions d
                JOIN badge_categories c ON c.id = d.category_id
                WHERE d.id = ? AND d.active = 1
                """,
                (badge_id,),
            ).fetchone()
        return dict(row) if row else None

    def badge_participants(self, badge_id: str) -> list[dict]:
        with self._connect() as con:
            rows = con.execute(
                """
                SELECT p.id, p.name, p.color, b.awarded_at,
                       CASE WHEN p.avatar_mime_type IS NOT NULL
                            THEN '/api/badges/' || ? || '/participants/' || p.id || '/avatar'
                            ELSE NULL END AS avatar_url
                FROM person_badges b
                JOIN persons p ON p.id = b.person_id
                WHERE b.badge_id = ? AND p.active = 1 AND p.badge_visibility = 1
                ORDER BY b.awarded_at, p.name COLLATE NOCASE
                """,
                (badge_id, badge_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def badge_participant_avatar(self, badge_id: str, person_id: int) -> tuple[bytes, str] | None:
        with self._connect() as con:
            row = con.execute(
                """
                SELECT p.avatar_data, p.avatar_mime_type
                FROM person_badges b
                JOIN persons p ON p.id = b.person_id
                WHERE b.badge_id = ? AND p.id = ? AND p.active = 1
                  AND p.badge_visibility = 1
                """,
                (badge_id, person_id),
            ).fetchone()
        if row is None or row["avatar_data"] is None or row["avatar_mime_type"] is None:
            return None
        return bytes(row["avatar_data"]), row["avatar_mime_type"]

    def remove_badges(self, person_id: int, badge_ids: list[str]) -> None:
        if not badge_ids:
            return
        placeholders = ", ".join("?" for _ in badge_ids)
        with self._connect() as con:
            con.execute(
                f"DELETE FROM person_badges WHERE person_id = ? AND badge_id IN ({placeholders})",
                (person_id, *badge_ids),
            )

    # --- Prioritäten (allgemeingültig pro Wochentag) ------------------------

    def set_pref(
        self,
        person_id: int,
        weekday: int,
        slot: str,
        value: int | None,
        *,
        freeze_week: tuple[int, int] | None = None,
        frozen_plan: dict | None = None,
        actor_username: str | None = None,
    ) -> bool:
        """Setzt eine Wochentagspriorität und friert optional den aktiven Plan ein."""
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute(
                "SELECT value FROM prefs WHERE person_id = ? AND weekday = ? AND slot = ?",
                (person_id, weekday, slot),
            ).fetchone()
            if (row["value"] if row else None) == value:
                return False
            if freeze_week and frozen_plan is not None:
                con.execute(
                    """
                    INSERT OR IGNORE INTO weekly_plans (year, week, plan_json)
                    VALUES (?, ?, ?)
                    """,
                    (*freeze_week, json.dumps(frozen_plan, ensure_ascii=False)),
                )
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
            if actor_username:
                subject = con.execute(
                    "SELECT username FROM accounts WHERE person_id = ?", (person_id,)
                ).fetchone()
                now = datetime.now(timezone.utc)
                cutoff = (now - timedelta(days=90)).isoformat(timespec="seconds")
                con.execute("DELETE FROM activity_log WHERE occurred_at < ?", (cutoff,))
                con.execute(
                    """
                    INSERT INTO activity_log
                        (actor_username, action, subject_username, details_json, occurred_at)
                    VALUES (?, 'preference_change', ?, ?, ?)
                    """,
                    (
                        actor_username,
                        subject["username"] if subject else str(person_id),
                        json.dumps({
                            "weekday": weekday,
                            "slot": slot,
                            "old_value": row["value"] if row else None,
                            "new_value": value,
                        }),
                        now.isoformat(timespec="seconds"),
                    ),
                )
            return True

    def frozen_plan(self, year: int, week: int) -> dict | None:
        with self._connect() as con:
            row = con.execute(
                "SELECT plan_json FROM weekly_plans WHERE year = ? AND week = ?",
                (year, week),
            ).fetchone()
        return json.loads(row["plan_json"]) if row else None

    def prefs_all(self) -> dict[tuple[int, str, int], int]:
        """Liefert {(weekday, slot, person_id): value} aller Prioritäten."""
        with self._connect() as con:
            rows = con.execute(
                "SELECT person_id, weekday, slot, value FROM prefs"
            ).fetchall()
        return {(r["weekday"], r["slot"], r["person_id"]): r["value"] for r in rows}
