"""FastAPI-Backend der Gassi-Planung.

Start: uvicorn app.main:app --host 0.0.0.0 --port 8000
DB-Pfad per Umgebungsvariable GASSI_DB überschreibbar (Default: ./gassi.sqlite3).
"""
from __future__ import annotations

import hmac
import os
import secrets
import sqlite3
from datetime import date as dt_date
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware
from itsdangerous import BadSignature, URLSafeSerializer

from .auth import DUMMY_PASSWORD_HASH, hash_password, verify_password
from .db import Database
from .ical import build_ics
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


def current_iso_week() -> tuple[int, int]:
    iso = datetime.now(BERLIN).date().isocalendar()
    return iso.year, iso.week


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
    app = FastAPI(title="Gassi-Planung")
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

        @app.post("/auth/logout", status_code=204)
        def logout(request: Request):
            request.session.clear()

        @app.get("/api/me")
        def get_me(account: dict | None = Depends(require_account)):
            assert account is not None
            return {
                "person": {
                    key: account[key] for key in ("id", "name", "color", "active", "is_admin")
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

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


app = create_app()
