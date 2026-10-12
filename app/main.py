"""FastAPI-Backend der Gassi-Planung.

Start: uvicorn app.main:app --host 0.0.0.0 --port 8000
DB-Pfad per Umgebungsvariable GASSI_DB überschreibbar (Default: ./gassi.sqlite3).
"""
from __future__ import annotations

import os
import sqlite3
from datetime import date as dt_date
from datetime import timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

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


def create_app(db_path: str | None = None) -> FastAPI:
    db = Database(db_path or os.environ.get("GASSI_DB", "gassi.sqlite3"))
    app = FastAPI(title="Gassi-Planung")

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

    # --- Slots / Metadaten -------------------------------------------------

    @app.get("/api/slots")
    def get_slots():
        return {
            "slots": [{"key": k, "label": SLOT_LABELS[k]} for k in SLOTS],
            "weekdays": list(WEEKDAYS),
        }

    # --- Personen ------------------------------------------------------------

    @app.get("/api/persons")
    def list_persons():
        return {"persons": db.list_persons()}

    @app.post("/api/persons", status_code=201)
    def add_person(body: PersonIn):
        try:
            return db.add_person(body.name, body.color)
        except sqlite3.IntegrityError:
            raise HTTPException(409, "Name existiert bereits")
        except ValueError as exc:
            raise HTTPException(422, str(exc))

    @app.delete("/api/persons/{person_id}", status_code=204)
    def delete_person(person_id: int):
        if not db.delete_person(person_id):
            raise HTTPException(404, "Person nicht gefunden")

    # --- Woche: Prioritäten + berechneter Plan ------------------------------

    def build_week(year: int | None, week: int | None) -> dict:
        year, week, dates = resolve_week(year, week)
        persons = db.list_persons()
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
                        "pref": a.pref,
                        "unassigned": False,
                    }
            days.append({"date": d, "weekday": WEEKDAYS[i], "slots": slots_out})

        prefs_out: dict[str, dict[str, dict[str, int]]] = {}
        for (wd, s, pid), v in weekday_prefs.items():
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
        year: int | None = Query(None), week: int | None = Query(None)
    ):
        return build_week(year, week)

    @app.get("/api/plan")
    def get_plan(
        year: int | None = Query(None), week: int | None = Query(None)
    ):
        return build_week(year, week)["plan"]

    @app.get("/api/calendar/{person_id}.ics")
    def person_calendar(person_id: int):
        """iCal-Feed mit den Gassi-Slots einer Person (abonnierbar).

        Da Prioritäten allgemeingültig pro Wochentag sind, wiederholt sich der
        Plan identisch jede Woche: der Feed enthält pro Wochentag×Slot genau
        ein wöchentlich wiederkehrendes Event (RRULE:FREQ=WEEKLY, ohne
        Enddatum). UIDs sind wochentagsbasiert stabil – nach Planänderungen
        sehen Abonnenten automatisch den neuen Stand.
        """
        person = db.get_person(person_id)
        if not person:
            raise HTTPException(404, "Person nicht gefunden")

        persons = db.list_persons()
        monday = dt_date.today() - timedelta(days=dt_date.today().weekday())
        iso = monday.isocalendar()
        dates = week_dates(iso.year, iso.week)
        result = compute_plan(
            dates, [p["id"] for p in persons], expand_prefs(dates, db.prefs_all())
        )
        assignments = [a for a in result.assignments if a.person_id == person_id]

        ics = build_ics(person["id"], person["name"], assignments)
        return Response(
            content=ics,
            media_type="text/calendar; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="gassi-{person["name"]}.ics"',
                "Cache-Control": "no-cache",
            },
        )

    @app.put("/api/prefs")
    def put_pref(body: PrefIn):
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
