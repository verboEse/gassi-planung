"""FastAPI-Backend der Gassi-Planung.

Start: uvicorn app.main:app --host 0.0.0.0 --port 8000
DB-Pfad per Umgebungsvariable GASSI_DB überschreibbar (Default: ./gassi.sqlite3).
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import calendar
import logging
import hmac
import json
import os
import secrets
import sqlite3
from datetime import date as dt_date
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware
from itsdangerous import BadSignature, URLSafeSerializer

from .auth import DUMMY_PASSWORD_HASH, hash_password, verify_password
from .db import Database
from .gamification import badge_progress, group_progress, summarize_completions
from .ical import SLOT_TIMES, WALK_WINDOW_TOLERANCE, build_ics
from .reminders import (
    dispatch_due_reminders,
    load_vapid_configuration,
    reminder_jobs,
    send_event_push,
)
from .scheduler import (
    Assignment,
    SLOT_LABELS,
    SLOTS,
    VALID_PREF_VALUES,
    WEEKDAYS,
    compute_plan,
)

STATIC_DIR = Path(__file__).parent / "static"
BERLIN = ZoneInfo("Europe/Berlin")
MAX_AVATAR_BYTES = 2 * 1024 * 1024
MAX_AVATAR_DIMENSION = 4096
logger = logging.getLogger(__name__)
PUSH_SERVICE_HOSTS = {
    "fcm.googleapis.com",
    "push.services.mozilla.com",
    "updates.push.services.mozilla.com",
    "web.push.apple.com",
}
RELEASE_NEWS = (
    {
        "id": "0.3.0-secret-badges",
        "version": "0.3.0",
        "title": "Neue geheime Abzeichen und Serien-Erfolge",
        "body": (
            "Neue geheime Abzeichen belohnen Tages- und Rundenserien sowie Runden "
            "außerhalb des Plans. Bei Serien siehst du deine aktuelle Serie und deinen "
            "Bestwert. Eine natürliche Unterbrechung nimmt einen bereits erreichten "
            "Erfolg nicht zurück."
        ),
    },
    {
        "id": "0.2.0-navigation-feedback",
        "version": "0.2.0",
        "title": "Mehr Übersicht und Feedback direkt in der App",
        "body": (
            "Der Plan ist jetzt deine Startansicht. Über dein Profilbild kommst du zu "
            "Profil und Einstellungen; über deinen Level zu Abzeichen, Fortschritt und "
            "Gassirunden. Verbesserungsvorschläge kannst du direkt aus der App einreichen. "
            "Ungelesene Neuigkeiten werden auch nach dem Neuladen angezeigt."
        ),
    },
)


def _decode_web_push_key(value: str) -> bytes | None:
    try:
        return base64.b64decode(
            value + "=" * (-len(value) % 4), altchars=b"-_", validate=True
        )
    except (binascii.Error, ValueError):
        return None


def valid_push_subscription(endpoint: str, p256dh: str, auth: str) -> bool:
    try:
        parsed = urlsplit(endpoint)
        port = parsed.port
    except ValueError:
        return False
    public_key = _decode_web_push_key(p256dh)
    auth_secret = _decode_web_push_key(auth)
    return (
        parsed.scheme == "https"
        and parsed.hostname in PUSH_SERVICE_HOSTS
        and parsed.username is None
        and parsed.password is None
        and port in (None, 443)
        and bool(parsed.path)
        and not parsed.fragment
        and public_key is not None
        and len(public_key) == 65
        and public_key[0] == 4
        and auth_secret is not None
        and len(auth_secret) == 16
    )


def avatar_mime_type(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 45:
        if data[12:16] != b"IHDR" or data[8:12] != b"\x00\x00\x00\r":
            return None
        width = int.from_bytes(data[16:20], "big")
        height = int.from_bytes(data[20:24], "big")
        if (
            0 < width <= MAX_AVATAR_DIMENSION
            and 0 < height <= MAX_AVATAR_DIMENSION
            and data.endswith(b"\x00\x00\x00\x00IEND\xaeB`\x82")
        ):
            return "image/png"
        return None

    if data.startswith(b"\xff\xd8") and data.endswith(b"\xff\xd9"):
        offset = 2
        while offset + 4 <= len(data) and data[offset] == 0xFF:
            while offset < len(data) and data[offset] == 0xFF:
                offset += 1
            if offset >= len(data):
                break
            marker = data[offset]
            offset += 1
            if marker in (0xD8, 0xD9, 0x01) or 0xD0 <= marker <= 0xD7:
                continue
            segment_length = int.from_bytes(data[offset:offset + 2], "big")
            if segment_length < 2 or offset + segment_length > len(data):
                return None
            if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
                if segment_length < 8:
                    return None
                component_count = data[offset + 7]
                if component_count == 0 or segment_length != 8 + 3 * component_count:
                    return None
                height = int.from_bytes(data[offset + 3:offset + 5], "big")
                width = int.from_bytes(data[offset + 5:offset + 7], "big")
                if 0 < width <= MAX_AVATAR_DIMENSION and 0 < height <= MAX_AVATAR_DIMENSION:
                    return "image/jpeg"
                return None
            offset += segment_length
        return None

    if len(data) >= 30 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        if int.from_bytes(data[4:8], "little") != len(data) - 8:
            return None
        chunk = data[12:16]
        if chunk == b"VP8X":
            width = 1 + int.from_bytes(data[24:27], "little")
            height = 1 + int.from_bytes(data[27:30], "little")
        elif chunk == b"VP8L" and data[20] == 0x2F:
            width = 1 + data[21] + ((data[22] & 0x3F) << 8)
            height = 1 + ((data[22] >> 6) & 0x03) + (data[23] << 2) + ((data[24] & 0x0F) << 10)
        elif chunk == b"VP8 " and data[23:26] == b"\x9d\x01\x2a":
            width = int.from_bytes(data[26:28], "little") & 0x3FFF
            height = int.from_bytes(data[28:30], "little") & 0x3FFF
        else:
            return None
        if 0 < width <= MAX_AVATAR_DIMENSION and 0 < height <= MAX_AVATAR_DIMENSION:
            return "image/webp"
    return None


def berlin_now() -> datetime:
    return datetime.now(BERLIN)


def current_iso_week() -> tuple[int, int]:
    iso = berlin_now().date().isocalendar()
    return iso.year, iso.week


def current_walk_window(now: datetime | None = None) -> dict | None:
    local = (now or berlin_now()).astimezone(BERLIN)
    for slot, ((start_hour, start_minute), (end_hour, end_minute)) in SLOT_TIMES.items():
        start = local.replace(
            hour=start_hour, minute=start_minute, second=0, microsecond=0
        )
        end = local.replace(hour=end_hour, minute=end_minute, second=0, microsecond=0)
        if start - WALK_WINDOW_TOLERANCE <= local <= end + WALK_WINDOW_TOLERANCE:
            return {"date": local.date().isoformat(), "slot": slot}
    return None


class PersonIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")


class PrefIn(BaseModel):
    person_id: int
    weekday: int = Field(ge=1, le=7)  # ISO-Wochentag: 1=Montag … 7=Sonntag
    slot: str
    value: int | None = None  # None = Eintrag löschen (zurück zu neutral)


class RegistrationIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=12, max_length=256)
    invite_code: str = Field(min_length=1, max_length=200)


class LoginIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=256)


class PasswordChangeIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)


class AdminPasswordResetIn(BaseModel):
    new_password: str = Field(min_length=12, max_length=256)


class AdminCompletionIn(BaseModel):
    kind: Literal["normal", "takeover", "group"]
    date: dt_date
    slot: str
    person_ids: list[int] = Field(min_length=1)


class ProfilePreferencesIn(BaseModel):
    badge_visibility: bool | None = None
    push_enabled: bool | None = None
    reminders_enabled: bool | None = None


class PushSubscriptionKeysIn(BaseModel):
    p256dh: str = Field(min_length=1, max_length=128)
    auth: str = Field(min_length=1, max_length=64)


class PushSubscriptionIn(BaseModel):
    endpoint: str = Field(min_length=1, max_length=4096)
    keys: PushSubscriptionKeysIn


class PushSubscriptionDeleteIn(BaseModel):
    endpoint: str = Field(min_length=1, max_length=4096)


class WalkCompletionIn(BaseModel):
    date: dt_date
    slot: str
    source: Literal["plan"]
    person_id: int | None = Field(default=None, ge=1)
    co_walker_ids: list[int] = Field(default_factory=list)


class WalkTakeoverRequestIn(BaseModel):
    date: dt_date
    slot: str
    person_id: int | None = Field(default=None, ge=1)


class WalkTakeoverDecisionIn(BaseModel):
    approved: bool
    person_id: int | None = Field(default=None, ge=1)


class WalkTakeoverGroupIn(BaseModel):
    person_id: int | None = Field(default=None, ge=1)


def week_dates(year: int, week: int) -> list[str]:
    """Montag bis Sonntag der ISO-Kalenderwoche als ISO-Datumsstrings."""
    return [dt_date.fromisocalendar(year, week, d).isoformat() for d in range(1, 8)]


def expand_prefs(
    dates: list[str], weekday_prefs: dict[tuple[int, str, int], int]
) -> dict[tuple[str, str, int], int]:
    """Bildet wochentagsbasierte Prioritäten auf konkrete Datumstage ab.

    dates muss an einem Montag beginnen und lückenlos aufeinanderfolgen
    (Index 0 = Montag = ISO-Wochentag 1).
    """
    out: dict[tuple[str, str, int], int] = {}
    for i, d in enumerate(dates):
        wd = (i % 7) + 1
        for (w, s, pid), v in weekday_prefs.items():
            if w == wd:
                out[(d, s, pid)] = v
    return out


def create_app(db_path: str | None = None, *, auth_enabled: bool = True) -> FastAPI:
    db = Database(db_path or os.environ.get("GASSI_DB", "gassi.sqlite3"))

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        vapid_config = load_vapid_configuration()
        task = asyncio.create_task(reminder_dispatcher(vapid_config)) if vapid_config else None
        try:
            yield
        finally:
            if task:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

    app = FastAPI(title="Gassi-Planung", lifespan=lifespan)
    base_url = os.environ.get("GASSI_BASE_URL", "http://localhost:8585").rstrip("/")
    session_secret = os.environ.get("GASSI_SESSION_SECRET") or secrets.token_urlsafe(32)
    if auth_enabled and len(session_secret.encode()) < 32:
        raise ValueError("GASSI_SESSION_SECRET muss mindestens 32 Bytes lang sein")
    invite_code = os.environ.get("GASSI_INVITE_CODE", "")
    serializer = URLSafeSerializer(session_secret, salt="gassi-calendar")
    app.state.auth_enabled = auth_enabled
    if auth_enabled:
        app.add_middleware(
            SessionMiddleware,
            secret_key=session_secret,
            same_site="lax",
            https_only=base_url.startswith("https://"),
        )

    def require_account(request: Request) -> dict | None:
        if not auth_enabled:
            return None
        person_id = request.session.get("person_id")
        person = db.account_for_person(person_id) if isinstance(person_id, int) else None
        if not person or request.session.get("auth_version") != person["auth_version"]:
            request.session.clear()
            raise HTTPException(401, "Anmeldung erforderlich")
        return person

    def require_admin(account: dict | None = Depends(require_account)) -> dict:
        if not account or not account["is_admin"]:
            raise HTTPException(403, "Admin-Berechtigung erforderlich")
        return account

    def calendar_url(person_id: int) -> str:
        version = db.calendar_person_version(person_id)
        token = serializer.dumps([person_id, version])
        return f"{base_url}/api/calendar/{token}.ics"

    def resolve_week(year: int | None, week: int | None) -> tuple[int, int, list[str]]:
        if year is None or week is None:
            current_year, current_week = current_iso_week()
            year = year if year is not None else current_year
            week = week if week is not None else current_week
        try:
            dates = week_dates(year, week)
        except ValueError:
            raise HTTPException(422, "Ungültige Kalenderwoche")
        return year, week, dates

    if auth_enabled:
        @app.post("/auth/register", status_code=201)
        def register(body: RegistrationIn, request: Request):
            if len(invite_code) < 32:
                raise HTTPException(503, "GASSI_INVITE_CODE muss mindestens 32 Zeichen lang sein")
            if not hmac.compare_digest(body.invite_code, invite_code):
                raise HTTPException(403, "Einladungscode ungültig")
            try:
                person = db.add_account(body.display_name, hash_password(body.password))
            except sqlite3.IntegrityError:
                raise HTTPException(409, "Name existiert bereits")
            except ValueError as exc:
                raise HTTPException(422, str(exc))
            account = db.account_for_person(person["id"])
            assert account is not None
            request.session.clear()
            request.session["person_id"] = person["id"]
            request.session["auth_version"] = account["auth_version"]
            return {"ok": True}

        @app.post("/auth/login")
        def login(body: LoginIn, request: Request):
            account = db.account_for_username(body.display_name)
            encoded = account["password_hash"] if account and account["password_hash"] else DUMMY_PASSWORD_HASH
            valid_password = verify_password(body.password, encoded)
            if not account or not valid_password:
                raise HTTPException(401, "Name oder Passwort falsch")
            request.session.clear()
            request.session["person_id"] = account["id"]
            request.session["auth_version"] = account["auth_version"]
            db.record_activity(account["name"], "login", account["name"])
            return {"ok": True}

        @app.get("/api/news")
        def get_news(account: dict | None = Depends(require_account)):
            assert account is not None
            read_ids = db.news_read_ids(account["id"])
            return {
                "news": [item for item in RELEASE_NEWS if item["id"] not in read_ids]
            }

        @app.post("/api/news/{news_id}/read", status_code=204)
        def mark_news_read(
            news_id: str,
            account: dict | None = Depends(require_account),
        ):
            assert account is not None
            if not any(item["id"] == news_id for item in RELEASE_NEWS):
                raise HTTPException(404, "Neuigkeit nicht gefunden")
            db.mark_news_read(account["id"], news_id)

        @app.post("/auth/logout", status_code=204)
        def logout(request: Request):
            request.session.clear()

        @app.get("/api/profile")
        def get_profile(account: dict | None = Depends(require_account)):
            assert account is not None
            profile = db.profile(account["id"])
            if profile is None:
                raise HTTPException(404, "Profil nicht gefunden")
            progress = summarize_completions(db.list_walk_completions(account["id"]))
            profile["level"] = progress["level"]
            profile["level_name"] = db.level_definition(progress["level"])["name"]
            profile["points"] = progress["points"]
            return profile

        @app.patch("/api/profile/preferences")
        def update_profile_preferences(
            body: ProfilePreferencesIn,
            account: dict | None = Depends(require_account),
        ):
            assert account is not None
            changed = db.update_profile_preferences(
                account["id"],
                badge_visibility=body.badge_visibility,
                push_enabled=body.push_enabled,
                reminders_enabled=body.reminders_enabled,
            )
            if not changed:
                raise HTTPException(404, "Profil nicht gefunden")
            return get_profile(account)

        @app.get("/api/push/public-key")
        def get_push_public_key(account: dict | None = Depends(require_account)):
            assert account is not None
            vapid_config = load_vapid_configuration()
            if not vapid_config:
                raise HTTPException(503, "Browser-Push ist nicht konfiguriert")
            return {"public_key": vapid_config[2]}

        @app.post("/api/push/subscriptions", status_code=201)
        def register_push_subscription(
            body: PushSubscriptionIn,
            account: dict | None = Depends(require_account),
        ):
            assert account is not None
            if not valid_push_subscription(
                body.endpoint, body.keys.p256dh, body.keys.auth
            ):
                raise HTTPException(422, "Ungültiges Browser-Abo")
            db.save_push_subscription(
                account["id"],
                endpoint=body.endpoint,
                p256dh=body.keys.p256dh,
                auth=body.keys.auth,
            )
            return {"ok": True}

        @app.delete("/api/push/subscriptions", status_code=204)
        def delete_push_subscription(
            body: PushSubscriptionDeleteIn,
            account: dict | None = Depends(require_account),
        ):
            assert account is not None
            if not db.delete_push_subscription(account["id"], body.endpoint):
                raise HTTPException(404, "Browser-Abo nicht gefunden")

        @app.put("/api/profile/avatar")
        async def upload_profile_avatar(
            request: Request,
            account: dict | None = Depends(require_account),
        ):
            assert account is not None
            content_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
            if content_type not in {"image/png", "image/jpeg", "image/webp"}:
                raise HTTPException(415, "Nur PNG-, JPEG- und WebP-Bilder sind zulässig")
            content_length = request.headers.get("content-length")
            if content_length:
                try:
                    if int(content_length) > MAX_AVATAR_BYTES:
                        raise HTTPException(413, "Profilbild darf höchstens 2 MiB groß sein")
                except ValueError:
                    raise HTTPException(400, "Ungültige Content-Length")
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > MAX_AVATAR_BYTES:
                    raise HTTPException(413, "Profilbild darf höchstens 2 MiB groß sein")
            detected_type = avatar_mime_type(bytes(body))
            if detected_type != content_type:
                raise HTTPException(422, "Dateiinhalt passt nicht zum Bildformat")
            if not db.save_avatar(account["id"], bytes(body), detected_type):
                raise HTTPException(404, "Profil nicht gefunden")
            return get_profile(account)

        @app.get("/api/profile/avatar")
        def get_profile_avatar(account: dict | None = Depends(require_account)):
            assert account is not None
            image = db.avatar(account["id"])
            if image is None:
                raise HTTPException(404, "Kein Profilbild vorhanden")
            return Response(
                content=image[0],
                media_type=image[1],
                headers={
                    "Cache-Control": "private, no-store",
                    "X-Content-Type-Options": "nosniff",
                },
            )

        @app.delete("/api/profile/avatar", status_code=204)
        def delete_profile_avatar(account: dict | None = Depends(require_account)):
            assert account is not None
            if not db.remove_avatar(account["id"]):
                raise HTTPException(404, "Profil nicht gefunden")

        def badge_view(definition: dict, completions: list[dict], earned_ids: set[str]) -> dict:
            result = badge_progress(
                definition,
                completions,
                definition["id"] in earned_ids,
                as_of=berlin_now(),
            )
            result["condition"] = json.loads(result.pop("condition_json") or "{}")
            result.pop("icon", None)
            result.pop("sort_order", None)
            return result

        @app.get("/api/badges")
        def get_badge_catalog(
            history: bool = Query(False),
            account: dict | None = Depends(require_account),
        ):
            assert account is not None
            sync_person_badges(account["id"])
            completions = db.list_walk_completions(account["id"])
            earned_ids = {
                row["badge_id"] for row in db.list_person_badges(account["id"])
            }
            definitions = db.badge_definitions()
            today_date = berlin_now().date()
            today = today_date.isoformat()
            horizon_month = today_date.month + 6
            horizon_year = today_date.year + (horizon_month - 1) // 12
            horizon_month = (horizon_month - 1) % 12 + 1
            horizon = today_date.replace(
                year=horizon_year,
                month=horizon_month,
                day=min(today_date.day, calendar.monthrange(horizon_year, horizon_month)[1]),
            ).isoformat()
            if history:
                selected = [
                    item for item in definitions
                    if item["season"] is not None and item["ends_at"] < today
                ]
            else:
                selected = [
                    item for item in definitions
                    if item["season"] is None
                    or (item["starts_at"] <= horizon and item["ends_at"] >= today)
                ]
            badges = [badge_view(item, completions, earned_ids) for item in selected]
            badges = [badge for badge in badges if not badge["secret"] or badge["earned"]]
            earned_count = sum(badge["earned"] for badge in badges)
            visible_category_ids = {badge["category_id"] for badge in badges}
            categories = [
                category for category in db.badge_categories()
                if category["id"] in visible_category_ids
            ]
            return {
                "categories": categories,
                "badges": badges,
                "progress": {"earned": earned_count, "available": len(badges)},
                "view": "history" if history else "current",
            }

        @app.get("/api/badges/{badge_id}/participants/{person_id}/avatar")
        def get_badge_participant_avatar(
            badge_id: str,
            person_id: int,
            account: dict | None = Depends(require_account),
        ):
            assert account is not None
            definition = db.badge_definition(badge_id)
            if definition is None:
                raise HTTPException(404, "Profilbild nicht verfügbar")
            if definition["secret"]:
                sync_person_badges(account["id"])
                earned_ids = {
                    row["badge_id"] for row in db.list_person_badges(account["id"])
                }
                if badge_id not in earned_ids:
                    raise HTTPException(404, "Profilbild nicht verfügbar")
            image = db.badge_participant_avatar(badge_id, person_id)
            if image is None:
                raise HTTPException(404, "Profilbild nicht verfügbar")
            return Response(
                content=image[0],
                media_type=image[1],
                headers={
                    "Cache-Control": "private, no-store",
                    "X-Content-Type-Options": "nosniff",
                },
            )

        @app.get("/api/badges/{badge_id}")
        def get_badge_details(
            badge_id: str,
            account: dict | None = Depends(require_account),
        ):
            assert account is not None
            definition = db.badge_definition(badge_id)
            if definition is None:
                raise HTTPException(404, "Abzeichen nicht gefunden")
            sync_person_badges(account["id"])
            completions = db.list_walk_completions(account["id"])
            earned_ids = {
                row["badge_id"] for row in db.list_person_badges(account["id"])
            }
            if definition["secret"] and badge_id not in earned_ids:
                raise HTTPException(404, "Abzeichen nicht gefunden")
            return {
                **badge_view(definition, completions, earned_ids),
                "participants": db.badge_participants(badge_id),
            }

        @app.get("/api/me")
        def get_me(account: dict | None = Depends(require_account)):
            assert account is not None
            progress = summarize_completions(db.list_walk_completions(account["id"]))
            return {
                "person": {
                    **{
                        key: account[key]
                        for key in ("id", "name", "color", "active", "is_admin")
                    },
                    "level": progress["level"],
                    "level_name": db.level_definition(progress["level"])["name"],
                },
                "calendar_url": calendar_url(account["id"]),
            }

        @app.post("/api/me/password")
        def change_password(
            body: PasswordChangeIn,
            request: Request,
            account: dict | None = Depends(require_account),
        ):
            assert account is not None
            stored = db.account_for_username(account["name"])
            if not stored or not verify_password(body.current_password, stored["password_hash"]):
                raise HTTPException(403, "Aktuelles Passwort ist falsch")
            auth_version = db.set_account_password(
                account["id"], hash_password(body.new_password)
            )
            request.session["auth_version"] = auth_version
            return {"ok": True}

        @app.post("/api/me/calendar-token")
        def rotate_calendar_token(account: dict | None = Depends(require_account)):
            assert account is not None
            db.rotate_calendar_token(account["id"])
            return {"calendar_url": calendar_url(account["id"])}

        @app.get("/api/admin/users", dependencies=[Depends(require_admin)])
        def admin_users():
            prefs: dict[str, dict[str, dict[str, int]]] = {}
            for (weekday, slot, person_id), value in db.prefs_all().items():
                prefs.setdefault(str(person_id), {}).setdefault(str(weekday), {})[slot] = value
            return {"users": db.list_admin_users(), "prefs": prefs}

        @app.get("/api/admin/activity", dependencies=[Depends(require_admin)])
        def admin_activity():
            return {"events": db.recent_activity()}

        @app.post("/api/admin/completions")
        def admin_add_completion(
            body: AdminCompletionIn,
            admin: dict = Depends(require_admin),
        ):
            if body.slot not in SLOTS:
                raise HTTPException(422, f"Ungültiger Slot: {body.slot}")
            if body.date > berlin_now().date():
                raise HTTPException(422, "Gassirunden können nicht für zukünftige Tage nachgetragen werden")
            if len(set(body.person_ids)) != len(body.person_ids):
                raise HTTPException(422, "Teilnehmende dürfen nur einmal ausgewählt werden")
            if body.kind in {"normal", "takeover"} and len(body.person_ids) != 1:
                raise HTTPException(422, "Für eine Einzelrunde genau eine Person auswählen")
            if body.kind == "group" and len(body.person_ids) < 2:
                raise HTTPException(422, "Eine Gruppenrunde braucht mindestens zwei Teilnehmende")

            persons = []
            for person_id in body.person_ids:
                person = db.get_person(person_id)
                if person is None:
                    raise HTTPException(404, "Teilnehmer nicht gefunden")
                persons.append(person)
            names = [person["name"] for person in persons]
            walk_date = body.date.isoformat()
            off_plan_ids = off_plan_people(body.person_ids, body.date, body.slot)
            shared_walk_id = None
            if body.kind == "group":
                try:
                    result = db.add_shared_walk_completions(
                        body.person_ids[0],
                        walk_date,
                        body.slot,
                        body.person_ids[1:],
                        source="manual",
                        off_plan_person_ids=off_plan_ids,
                    )
                except ValueError as exc:
                    raise HTTPException(409, str(exc))
                created = result["created"]
                shared_walk_id = result["shared_walk_id"]
            else:
                created = db.add_walk_completion(
                    body.person_ids[0], walk_date, body.slot, "manual",
                    off_plan=body.person_ids[0] in off_plan_ids,
                )

            if created:
                for person_id in body.person_ids:
                    sync_person_badges(person_id)
                db.record_activity(
                    admin["name"],
                    "walk_completion_add",
                    ", ".join(names),
                    {
                        "kind": body.kind,
                        "date": walk_date,
                        "slot": body.slot,
                        "participants": names,
                    },
                )
            return {
                "ok": True,
                "created": created,
                "kind": body.kind,
                "shared_walk_id": shared_walk_id,
            }

        @app.post("/api/admin/users/{person_id}/password")
        def admin_reset_password(
            person_id: int,
            body: AdminPasswordResetIn,
            admin: dict = Depends(require_admin),
        ):
            account = db.account_for_person(person_id)
            if not account:
                raise HTTPException(404, "Teilnehmer nicht gefunden")
            if person_id == admin["id"]:
                raise HTTPException(422, "Eigenes Passwort bitte über das eigene Konto ändern")
            if db.set_account_password(person_id, hash_password(body.new_password)) is None:
                raise HTTPException(404, "Teilnehmerkonto nicht gefunden")
            return {"ok": True}

        @app.put("/api/admin/prefs")
        def admin_set_pref(body: PrefIn, admin: dict = Depends(require_admin)):
            return save_preference(body, admin["name"])

    # --- Slots / Metadaten -------------------------------------------------

    @app.get("/api/slots")
    def get_slots():
        return {
            "slots": [{"key": k, "label": SLOT_LABELS[k]} for k in SLOTS],
            "weekdays": list(WEEKDAYS),
        }

    # --- Personen ------------------------------------------------------------

    @app.get("/api/persons", dependencies=[Depends(require_account)])
    def list_persons():
        persons = db.list_registered_persons() if auth_enabled else db.list_persons()
        return {"persons": persons}

    @app.post("/api/persons", status_code=201, dependencies=[Depends(require_account)])
    def add_person(body: PersonIn):
        if auth_enabled:
            raise HTTPException(403, "Teilnehmer registrieren sich selbst")
        try:
            return db.add_person(body.name, body.color)
        except sqlite3.IntegrityError:
            raise HTTPException(409, "Name existiert bereits")
        except ValueError as exc:
            raise HTTPException(422, str(exc))

    @app.delete(
        "/api/persons/{person_id}", status_code=204, dependencies=[Depends(require_account)]
    )
    def delete_person(person_id: int):
        if auth_enabled:
            raise HTTPException(403, "Teilnehmer können sich nicht selbst entfernen")
        if not db.delete_person(person_id):
            raise HTTPException(404, "Person nicht gefunden")

    # --- Woche: Prioritäten + berechneter Plan ------------------------------

    def build_week(
        year: int | None,
        week: int | None,
        viewer_person_id: int | None = None,
        *,
        redact_preferences: bool = True,
    ) -> dict:
        year, week, dates = resolve_week(year, week)
        persons = db.list_registered_persons() if auth_enabled else db.list_persons()
        weekday_prefs = db.prefs_all()
        plan_data = db.frozen_plan(year, week)
        if plan_data is None:
            result = compute_plan(
                dates, [p["id"] for p in persons], expand_prefs(dates, weekday_prefs)
            )
            by_key = {(a.date, a.slot): a for a in result.assignments}
            person_by_id = {p["id"]: p for p in persons}

            days = []
            for i, d in enumerate(dates):
                slots_out = {}
                for s in SLOTS:
                    a = by_key[(d, s)]
                    if a.person_id is None:
                        slots_out[s] = {"unassigned": True}
                    else:
                        p = person_by_id[a.person_id]
                        slots_out[s] = {
                            "person_id": p["id"],
                            "name": p["name"],
                            "color": p["color"],
                            "pref": a.pref,
                            "unassigned": False,
                        }
                days.append({"date": d, "weekday": WEEKDAYS[i], "slots": slots_out})
            plan_data = {
                "days": days,
                "counts": [
                    {
                        "person_id": pid,
                        "name": person_by_id[pid]["name"],
                        "color": person_by_id[pid]["color"],
                        "count": count,
                    }
                    for pid, count in result.counts.items()
                ],
                "unassigned": [
                    {"date": d, "slot": s} for d, s in result.unassigned
                ],
            }

        prefs_out: dict[str, dict[str, dict[str, int]]] = {}
        for (wd, s, pid), v in weekday_prefs.items():
            if auth_enabled and pid != viewer_person_id:
                continue
            prefs_out.setdefault(str(pid), {}).setdefault(str(wd), {})[s] = v

        if auth_enabled and redact_preferences:
            for day in plan_data["days"]:
                for cell in day["slots"].values():
                    person_id = cell.get("person_id")
                    if person_id is not None and person_id != viewer_person_id:
                        cell["pref"] = None

        return {
            "year": year,
            "week": week,
            "dates": dates,
            "persons": persons,
            "prefs": prefs_out,
            "plan": plan_data,
        }

    async def reminder_dispatcher(vapid_config):
        vapid, subject, _ = vapid_config
        while True:
            try:
                enabled_person_ids = db.enabled_reminder_person_ids()
                plans = []
                if enabled_person_ids:
                    year, week = current_iso_week()
                    next_monday = dt_date.fromisocalendar(year, week, 1) + timedelta(days=7)
                    next_week = next_monday.isocalendar()
                    plans = await asyncio.to_thread(
                        lambda: [
                            build_week(year, week, redact_preferences=False)["plan"],
                            build_week(
                                next_week.year, next_week.week, redact_preferences=False
                            )["plan"],
                        ]
                    )
                jobs = reminder_jobs(plans, enabled_person_ids)
                await dispatch_due_reminders(
                    db, jobs, enabled_person_ids, datetime.now(timezone.utc), vapid, subject
                )
            except Exception as error:
                logger.warning("Reminder-Dispatcher fehlgeschlagen (%s)", type(error).__name__)
            await asyncio.sleep(30)

    @app.get("/api/week")
    def get_week(
        year: int | None = Query(None),
        week: int | None = Query(None),
        account: dict | None = Depends(require_account),
    ):
        return build_week(year, week, account["id"] if account else None)

    @app.get("/api/plan")
    def get_plan(
        year: int | None = Query(None),
        week: int | None = Query(None),
        account: dict | None = Depends(require_account),
    ):
        return build_week(year, week, account["id"] if account else None)["plan"]

    def completion_person_id(
        requested_person_id: int | None, account: dict | None
    ) -> int:
        if auth_enabled:
            assert account is not None
            if requested_person_id is not None and requested_person_id != account["id"]:
                raise HTTPException(403, "Du kannst nur eigene Runden erfassen")
            return account["id"]
        if requested_person_id is None:
            raise HTTPException(422, "person_id ist im Entwicklungsmodus erforderlich")
        return requested_person_id

    def sync_person_badges(person_id: int) -> None:
        completions = db.list_walk_completions(person_id)
        already_earned = {row["badge_id"] for row in db.list_person_badges(person_id)}
        definitions = db.badge_definitions()
        reached_ids = {
            definition["id"]
            for definition in definitions
            if badge_progress(
                definition, completions, definition["id"] in already_earned
            )["reached_now"]
        }
        db.award_badges(person_id, list(reached_ids))
        db.remove_badges(
            person_id,
            [
                definition["id"]
                for definition in definitions
                if definition["retention"] == "current-count"
                and definition["id"] not in reached_ids
            ],
        )

    def stored_badges() -> dict[int, set[str]]:
        badges: dict[int, set[str]] = {}
        for row in db.list_person_badges():
            badges.setdefault(row["person_id"], set()).add(row["badge_id"])
        return badges

    def assert_current_walk_window(walk_date: dt_date, slot: str) -> None:
        window = current_walk_window()
        if not window or window["date"] != walk_date.isoformat() or window["slot"] != slot:
            raise HTTPException(
                422,
                "Gassirunden können nur im aktuellen Zeitfenster mit 30 Minuten Toleranz erfasst werden",
            )

    def planned_assignment_person_id(walk_date: dt_date, slot: str) -> int | None:
        iso = walk_date.isocalendar()
        plan = build_week(iso.year, iso.week, redact_preferences=False)["plan"]
        day = next((item for item in plan["days"] if item["date"] == walk_date.isoformat()), None)
        assignee_id = day["slots"].get(slot, {}).get("person_id") if day else None
        return assignee_id

    def off_plan_people(person_ids: list[int], walk_date: dt_date, slot: str) -> set[int]:
        assignee_id = planned_assignment_person_id(walk_date, slot)
        return {person_id for person_id in person_ids if person_id != assignee_id}

    def require_planned_assignment_person_id(walk_date: dt_date, slot: str) -> int:
        assignee_id = planned_assignment_person_id(walk_date, slot)
        if assignee_id is None:
            raise HTTPException(422, "Für diese Runde ist keine Person eingetragen")
        return assignee_id

    def assert_original_assignee(person_id: int, walk_date: dt_date, slot: str) -> None:
        assert_current_walk_window(walk_date, slot)
        if require_planned_assignment_person_id(walk_date, slot) != person_id:
            raise HTTPException(403, "Die Runde ist dieser Person nicht zugewiesen")

    def assert_can_complete_planned_walk(
        person_id: int, walk_date: dt_date, slot: str
    ) -> None:
        assert_current_walk_window(walk_date, slot)
        assignee_id = require_planned_assignment_person_id(walk_date, slot)
        takeover = db.approved_walk_takeover_for_slot(walk_date.isoformat(), slot)
        if assignee_id == person_id:
            if takeover:
                raise HTTPException(403, "Die Runde wurde zur Übernahme freigegeben")
        elif not takeover or takeover["requester_id"] != person_id:
            raise HTTPException(403, "Die Runde ist dieser Person nicht zugewiesen")

    @app.get("/api/walk-takeovers")
    def get_walk_takeovers(
        person_id: int | None = Query(None, ge=1),
        account: dict | None = Depends(require_account),
    ):
        owner_id = completion_person_id(person_id, account)
        return {"requests": db.list_walk_takeover_requests(owner_id)}

    @app.post("/api/walk-takeovers", status_code=201)
    def request_walk_takeover(
        body: WalkTakeoverRequestIn,
        account: dict | None = Depends(require_account),
    ):
        if body.slot not in SLOTS:
            raise HTTPException(422, f"Ungültiger Slot: {body.slot}")
        requester_id = completion_person_id(body.person_id, account)
        if db.get_person(requester_id) is None:
            raise HTTPException(404, "Teilnehmer nicht gefunden")
        assert_current_walk_window(body.date, body.slot)
        assignee_id = require_planned_assignment_person_id(body.date, body.slot)
        if db.walk_completion_exists(body.date.isoformat(), body.slot):
            raise HTTPException(409, "Diese Runde wurde bereits abgeschlossen")
        if requester_id == assignee_id:
            raise HTTPException(409, "Diese Runde ist dir bereits zugewiesen")
        try:
            request = db.create_walk_takeover_request(
                body.date.isoformat(),
                body.slot,
                requester_id,
                assignee_id,
                berlin_now().astimezone(timezone.utc).isoformat(timespec="seconds"),
            )
        except sqlite3.IntegrityError:
            raise HTTPException(409, "Für diese Runde gibt es bereits eine aktive Übernahme")
        requester = db.get_person(requester_id)
        send_event_push(
            db,
            assignee_id,
            {
                "title": "Gassi-Runde übernehmen?",
                "body": f"{requester['name']} möchte die Runde {SLOT_LABELS[body.slot]} am {body.date:%d.%m.%Y} übernehmen.",
                "tag": f"gassi-takeover-{request['id']}",
                "url": "/",
            },
            load_vapid_configuration(),
        )
        return {"ok": True, "request": request}

    @app.put("/api/walk-takeovers/{request_id}")
    def decide_walk_takeover(
        request_id: int,
        body: WalkTakeoverDecisionIn,
        account: dict | None = Depends(require_account),
    ):
        assignee_id = completion_person_id(body.person_id, account)
        request = db.decide_walk_takeover_request(
            request_id,
            assignee_id,
            body.approved,
            berlin_now().astimezone(timezone.utc).isoformat(timespec="seconds"),
        )
        if request is None:
            raise HTTPException(404, "Übernahmeanfrage nicht gefunden oder bereits entschieden")
        approved = request["status"] == "approved"
        send_event_push(
            db,
            request["requester_id"],
            {
                "title": "Gassi-Runde freigegeben" if approved else "Gassi-Runde bleibt eingeplant",
                "body": (
                    f"Die Runde {SLOT_LABELS[request['slot']]} am {request['walk_date']} "
                    + ("wurde für dich freigegeben." if approved else "wird von der eingetragenen Person wahrgenommen.")
                ),
                "tag": f"gassi-takeover-{request['id']}",
                "url": "/",
            },
            load_vapid_configuration(),
        )
        return {"ok": True, "request": request}

    @app.post("/api/walk-takeovers/{request_id}/group")
    def confirm_group_walk(
        request_id: int,
        body: WalkTakeoverGroupIn,
        account: dict | None = Depends(require_account),
    ):
        assignee_id = completion_person_id(body.person_id, account)
        request = next(
            (
                item for item in db.list_walk_takeover_requests(assignee_id)
                if item["id"] == request_id and item["status"] == "pending"
            ),
            None,
        )
        if request is None:
            raise HTTPException(404, "Übernahmeanfrage nicht gefunden oder bereits entschieden")
        walk_date = dt_date.fromisoformat(request["walk_date"])
        assert_original_assignee(assignee_id, walk_date, request["slot"])
        result = db.complete_walk_takeover_as_shared(
            request_id,
            assignee_id,
            berlin_now().astimezone(timezone.utc).isoformat(timespec="seconds"),
        )
        if result is None:
            raise HTTPException(409, "Die Runde wurde bereits abgeschlossen oder die Anfrage entschieden")
        for completion in result["completions"]:
            sync_person_badges(completion["person_id"])
        send_event_push(
            db,
            result["request"]["requester_id"],
            {
                "title": "Gemeinsame Gassirunde bestätigt",
                "body": (
                    f"Die Runde {SLOT_LABELS[request['slot']]} am {walk_date:%d.%m.%Y} "
                    "wurde gemeinsam eingetragen."
                ),
                "tag": f"gassi-takeover-{request_id}",
                "url": "/",
            },
            load_vapid_configuration(),
        )
        return {"ok": True, **result}

    @app.get("/api/gamification")
    def get_gamification(
        person_id: int | None = Query(None, ge=1),
        account: dict | None = Depends(require_account),
    ):
        persons = db.list_registered_persons() if auth_enabled else db.list_persons()
        completions = db.list_walk_completions()
        for person in persons:
            sync_person_badges(person["id"])
        viewer_id = account["id"] if account else person_id
        active = db.active_walk(viewer_id) if viewer_id is not None else None
        window = current_walk_window()
        assignee_id = (
            planned_assignment_person_id(dt_date.fromisoformat(window["date"]), window["slot"])
            if window else None
        )
        progress = group_progress(persons, completions, stored_badges())
        for person in progress:
            person["level_name"] = db.level_definition(person["level"])["name"]
        return {
            "persons": progress,
            "completions": completions,
            "walk_status": {
                "active": active,
                "window": window,
                "assignee_id": assignee_id,
                "can_start": bool(window) and active is None,
            },
        }

    @app.post("/api/walks/start")
    def start_walk(
        person_id: int | None = Query(None, ge=1),
        date: dt_date | None = None,
        weekday: Annotated[int | None, Query(ge=1, le=7)] = None,
        slot: str | None = None,
        account: dict | None = Depends(require_account),
    ):
        owner_id = completion_person_id(person_id, account)
        if not db.person_exists(owner_id):
            raise HTTPException(404, "Teilnehmer nicht gefunden")
        has_target = date is not None or weekday is not None or slot is not None
        if has_target and (slot not in SLOTS or (date is None) == (weekday is None)):
            raise HTTPException(422, "Ungültiger Kalenderlink")
        active = db.active_walk(owner_id)
        if active:
            if has_target:
                active_date = dt_date.fromisoformat(active["date"])
                target_matches_active = (
                    date == active_date
                    if date is not None
                    else active_date == berlin_now().date()
                    and weekday == active_date.isoweekday()
                )
                if slot != active["slot"] or not target_matches_active:
                    raise HTTPException(409, "Eine andere Gassirunde ist bereits gestartet")
            return {"ok": True, "created": False, "active": active}
        window = current_walk_window()
        if not window:
            raise HTTPException(
                422,
                "Gassi-Runden können nur im aktuellen Zeitfenster mit 30 Minuten Toleranz gestartet werden",
            )
        walk_date = dt_date.fromisoformat(window["date"])
        if has_target and (
            slot != window["slot"]
            or (date is not None and date != walk_date)
            or (weekday is not None and weekday != walk_date.isoweekday())
        ):
            raise HTTPException(422, "Der Kalenderlink gilt für eine andere Gassirunde")
        assert_can_complete_planned_walk(
            owner_id, walk_date, window["slot"]
        )
        off_plan = owner_id in off_plan_people([owner_id], walk_date, window["slot"])
        active = db.start_walk(
            owner_id,
            window["date"],
            window["slot"],
            berlin_now().astimezone(timezone.utc).isoformat(timespec="seconds"),
            off_plan=off_plan,
        )
        return {"ok": True, "created": True, "active": active}

    @app.post("/api/walks/end")
    def end_walk(
        person_id: int | None = Query(None, ge=1),
        account: dict | None = Depends(require_account),
    ):
        owner_id = completion_person_id(person_id, account)
        result = db.finish_walk(
            owner_id,
            berlin_now().astimezone(timezone.utc).isoformat(timespec="seconds"),
        )
        if result is None:
            raise HTTPException(404, "Keine aktive Gassi-Runde vorhanden")
        sync_person_badges(owner_id)
        return {"ok": True, **result}

    @app.put("/api/completions")
    def put_completion(
        body: WalkCompletionIn,
        account: dict | None = Depends(require_account),
    ):
        if body.slot not in SLOTS:
            raise HTTPException(422, f"Ungültiger Slot: {body.slot}")
        person_id = completion_person_id(body.person_id, account)
        if not db.person_exists(person_id):
            raise HTTPException(404, "Teilnehmer nicht gefunden")
        if body.co_walker_ids:
            if len(set(body.co_walker_ids)) != len(body.co_walker_ids) or person_id in body.co_walker_ids:
                raise HTTPException(422, "Teilnehmende dürfen nur einmal aufgeführt werden")
            assert_original_assignee(person_id, body.date, body.slot)
            for co_walker_id in body.co_walker_ids:
                if db.get_person(co_walker_id) is None:
                    raise HTTPException(404, "Teilnehmer nicht gefunden")
            try:
                result = db.add_shared_walk_completions(
                    person_id,
                    body.date.isoformat(),
                    body.slot,
                    body.co_walker_ids,
                    off_plan_person_ids=off_plan_people(
                        [person_id, *body.co_walker_ids], body.date, body.slot
                    ),
                )
            except ValueError as exc:
                raise HTTPException(409, str(exc))
            for completion in result["completions"]:
                sync_person_badges(completion["person_id"])
            return {
                "ok": True,
                "created": result["created"],
                "shared_walk_id": result["shared_walk_id"],
                "completions": result["completions"],
            }
        if body.source == "plan":
            assert_can_complete_planned_walk(person_id, body.date, body.slot)
        created = db.add_walk_completion(
            person_id,
            body.date.isoformat(),
            body.slot,
            body.source,
            off_plan=person_id in off_plan_people([person_id], body.date, body.slot),
        )
        sync_person_badges(person_id)
        return {"ok": True, "created": created}

    @app.delete("/api/completions/{walk_date}/{slot}")
    def delete_completion(
        walk_date: dt_date,
        slot: str,
        person_id: int | None = Query(None, ge=1),
        account: dict | None = Depends(require_account),
    ):
        if slot not in SLOTS:
            raise HTTPException(422, f"Ungültiger Slot: {slot}")
        owner_id = completion_person_id(person_id, account)
        affected_people = set(db.shared_walk_participant_ids(walk_date.isoformat(), slot))
        affected_people.add(owner_id)
        if not db.remove_walk_completion(owner_id, walk_date.isoformat(), slot):
            raise HTTPException(404, "Abschluss nicht gefunden")
        for affected_person_id in affected_people:
            sync_person_badges(affected_person_id)
        return {"ok": True}

    @app.api_route("/api/calendar/{calendar_token}.ics", methods=["GET", "HEAD"])
    def person_calendar(calendar_token: str, request: Request):
        """Feed mit fixen Terminen dieser Woche und Wiederholungen ab nächster Woche."""
        if auth_enabled:
            try:
                person_id, token_version = serializer.loads(calendar_token)
                if not isinstance(person_id, int) or not isinstance(token_version, int):
                    raise BadSignature("invalid token")
            except (BadSignature, TypeError, ValueError):
                raise HTTPException(404, "Kalender-Feed nicht gefunden")
            person = db.calendar_person(person_id, token_version)
        else:
            try:
                person_id = int(calendar_token)
            except ValueError:
                raise HTTPException(404, "Kalender-Feed nicht gefunden")
            person = db.get_person(person_id)
        if not person:
            raise HTTPException(404, "Kalender-Feed nicht gefunden")

        headers = {
            "Content-Disposition": f'attachment; filename="gassi-{person["name"]}.ics"',
            "Cache-Control": "no-cache",
        }
        year, week = current_iso_week()
        current_plan = build_week(year, week, redact_preferences=False)["plan"]
        next_monday = dt_date.fromisocalendar(year, week, 1) + timedelta(days=7)
        next_iso = next_monday.isocalendar()
        future_plan = build_week(
            next_iso.year, next_iso.week, redact_preferences=False
        )["plan"]

        def assignments_for(plan: dict) -> list[Assignment]:
            return [
                Assignment(
                    date=day["date"], slot=slot, person_id=person_id, pref=cell["pref"]
                )
                for day in plan["days"]
                for slot, cell in day["slots"].items()
                if cell.get("person_id") == person_id
            ]

        ics = build_ics(
            person["id"],
            person["name"],
            assignments_for(current_plan),
            recurring=False,
            future_assignments=assignments_for(future_plan),
            reminders_enabled=bool(person["reminders_enabled"]),
            base_url=base_url,
        )
        if request.method == "HEAD":
            headers["Content-Length"] = str(len(ics.encode("utf-8")))
            return Response(media_type="text/calendar; charset=utf-8", headers=headers)
        return Response(
            content=ics,
            media_type="text/calendar; charset=utf-8",
            headers=headers,
        )

    def save_preference(body: PrefIn, actor_username: str | None) -> dict:
        if not db.person_exists(body.person_id):
            raise HTTPException(404, "Teilnehmer nicht gefunden")
        if body.slot not in SLOTS:
            raise HTTPException(422, f"Ungültiger Slot: {body.slot}")
        if body.value is not None and body.value not in VALID_PREF_VALUES:
            raise HTTPException(422, "Wert muss -1 (blockiert) oder 1–3 sein")
        freeze_year, freeze_week = current_iso_week()
        frozen_plan = build_week(
            freeze_year, freeze_week, redact_preferences=False
        )["plan"]
        changed = db.set_pref(
            body.person_id,
            body.weekday,
            body.slot,
            body.value,
            freeze_week=(freeze_year, freeze_week),
            frozen_plan=frozen_plan,
            actor_username=actor_username,
        )
        next_monday = dt_date.fromisocalendar(freeze_year, freeze_week, 1) + timedelta(days=7)
        effective = next_monday.isocalendar()
        return {
            "ok": True,
            "changed": changed,
            "effective_year": effective.year,
            "effective_week": effective.week,
        }

    @app.put("/api/prefs")
    def put_pref(
        body: PrefIn, account: dict | None = Depends(require_account)
    ):
        if auth_enabled and (account is None or body.person_id != account["id"]):
            raise HTTPException(403, "Du kannst nur eigene Prioritäten ändern")
        return save_preference(body, account["name"] if account else None)

    # --- Frontend -------------------------------------------------------------

    @app.get("/service-worker.js", include_in_schema=False)
    def service_worker():
        return FileResponse(
            STATIC_DIR / "service-worker.js",
            media_type="application/javascript",
            headers={"Service-Worker-Allowed": "/"},
        )

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


app = create_app()
