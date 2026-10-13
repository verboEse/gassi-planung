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
from datetime import timedelta
from pathlib import Path

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
    SLOT_LABELS,
    SLOTS,
    VALID_PREF_VALUES,
    WEEKDAYS,
    compute_plan,
)

STATIC_DIR = Path(__file__).parent / "static"


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
        if not person:
            request.session.clear()
            raise HTTPException(401, "Anmeldung erforderlich")
        return person

    def calendar_url(person_id: int) -> str:
        version = db.calendar_person_version(person_id)
        token = serializer.dumps([person_id, version])
        return f"{base_url}/api/calendar/{token}.ics"

    def resolve_week(year: int | None, week: int | None) -> tuple[int, int, list[str]]:
        if year is None or week is None:
            iso = dt_date.today().isocalendar()
            year = year if year is not None else iso.year
            week = week if week is not None else iso.week
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
            request.session.clear()
            request.session["person_id"] = person["id"]
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
            return {"ok": True}

        @app.post("/auth/logout", status_code=204)
        def logout(request: Request):
            request.session.clear()

        @app.get("/api/me")
        def get_me(account: dict | None = Depends(require_account)):
            assert account is not None
            return {"person": account, "calendar_url": calendar_url(account["id"])}

        @app.post("/api/me/password")
        def change_password(
            body: PasswordChangeIn, account: dict | None = Depends(require_account)
        ):
            assert account is not None
            stored = db.account_for_username(account["name"])
            if not stored or not verify_password(body.current_password, stored["password_hash"]):
                raise HTTPException(403, "Aktuelles Passwort ist falsch")
            db.set_account_password(account["id"], hash_password(body.new_password))
            return {"ok": True}

        @app.post("/api/me/calendar-token")
        def rotate_calendar_token(account: dict | None = Depends(require_account)):
            assert account is not None
            db.rotate_calendar_token(account["id"])
            return {"calendar_url": calendar_url(account["id"])}

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
        year: int | None, week: int | None, viewer_person_id: int | None = None
    ) -> dict:
        year, week, dates = resolve_week(year, week)
        persons = db.list_registered_persons() if auth_enabled else db.list_persons()
        weekday_prefs = db.prefs_all()
        result = compute_plan(dates, [p["id"] for p in persons], expand_prefs(dates, weekday_prefs))

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
                        "pref": a.pref if not auth_enabled or p["id"] == viewer_person_id else None,
                        "unassigned": False,
                    }
            days.append({"date": d, "weekday": WEEKDAYS[i], "slots": slots_out})

        prefs_out: dict[str, dict[str, dict[str, int]]] = {}
        for (wd, s, pid), v in weekday_prefs.items():
            if auth_enabled and pid != viewer_person_id:
                continue
            prefs_out.setdefault(str(pid), {}).setdefault(str(wd), {})[s] = v

        return {
            "year": year,
            "week": week,
            "dates": dates,
            "persons": persons,
            "prefs": prefs_out,
            "plan": {
                "days": days,
                "counts": [
                    {
                        "person_id": pid,
                        "name": person_by_id[pid]["name"],
                        "color": person_by_id[pid]["color"],
                        "count": c,
                    }
                    for pid, c in result.counts.items()
                ],
                "unassigned": [
                    {"date": d, "slot": s} for d, s in result.unassigned
                ],
            },
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
        """iCal-Feed mit den Gassi-Slots einer Person (abonnierbar).

        Da Prioritäten allgemeingültig pro Wochentag sind, wiederholt sich der
        Plan identisch jede Woche: der Feed enthält pro Wochentag×Slot genau
        ein wöchentlich wiederkehrendes Event (RRULE:FREQ=WEEKLY, ohne
        Enddatum). UIDs sind wochentagsbasiert stabil – beim nächsten Abruf
        enthält der Feed den aktuellen Plan.
        """
        if auth_enabled:
            try:
                person_id, token_version = serializer.loads(calendar_token)
                if not isinstance(person_id, int) or not isinstance(token_version, int):
                    raise BadSignature("invalid token")
            except (BadSignature, TypeError, ValueError):
                raise HTTPException(404, "Kalender-Feed nicht gefunden")
            person = db.calendar_person(person_id, token_version)
            persons = db.list_registered_persons()
        else:
            try:
                person_id = int(calendar_token)
            except ValueError:
                raise HTTPException(404, "Kalender-Feed nicht gefunden")
            person = db.get_person(person_id)
            persons = db.list_persons()
        if not person:
            raise HTTPException(404, "Kalender-Feed nicht gefunden")

        headers = {
            "Content-Disposition": f'attachment; filename="gassi-{person["name"]}.ics"',
            "Cache-Control": "no-cache",
        }
        monday = dt_date.today() - timedelta(days=dt_date.today().weekday())
        iso = monday.isocalendar()
        dates = week_dates(iso.year, iso.week)
        result = compute_plan(
            dates, [p["id"] for p in persons], expand_prefs(dates, db.prefs_all())
        )
        assignments = [a for a in result.assignments if a.person_id == person_id]

        ics = build_ics(person["id"], person["name"], assignments)
        if request.method == "HEAD":
            headers["Content-Length"] = str(len(ics.encode("utf-8")))
            return Response(media_type="text/calendar; charset=utf-8", headers=headers)
        return Response(
            content=ics,
            media_type="text/calendar; charset=utf-8",
            headers=headers,
        )

    @app.put("/api/prefs")
    def put_pref(
        body: PrefIn, account: dict | None = Depends(require_account)
    ):
        if auth_enabled and (account is None or body.person_id != account["id"]):
            raise HTTPException(403, "Du kannst nur eigene Prioritäten ändern")
        if not db.person_exists(body.person_id):
            raise HTTPException(404, "Person nicht gefunden")
        if body.slot not in SLOTS:
            raise HTTPException(422, f"Ungültiger Slot: {body.slot}")
        if body.value is not None and body.value not in VALID_PREF_VALUES:
            raise HTTPException(422, "Wert muss -1 (blockiert) oder 1–3 sein")
        db.set_pref(body.person_id, body.weekday, body.slot, body.value)
        return {"ok": True}

    # --- Frontend -------------------------------------------------------------

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


app = create_app()
