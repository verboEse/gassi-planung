"""Berechnung von Punkten, Leveln und Badges aus erledigten Gassirunden."""
from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import date as dt_date

BADGE_DEFINITIONS = (
    ("first-walk", "Erste Runde"),
    ("ten-walks", "10 Runden"),
    ("fifty-walks", "50 Runden"),
    ("full-week", "Volle Woche"),
)
COUNT_BADGE_IDS = ("first-walk", "ten-walks", "fifty-walks")


def badges_for_ids(badge_ids: Iterable[str]) -> list[dict]:
    ids = set(badge_ids)
    return [
        {"id": badge_id, "label": label}
        for badge_id, label in BADGE_DEFINITIONS
        if badge_id in ids
    ]


def group_progress(
    persons: Iterable[dict],
    completions: Iterable[dict],
    awarded_badges: dict[int, set[str]] | None = None,
) -> list[dict]:
    """Baut die Fortschrittsübersicht für alle aktiven Personen."""
    by_person: dict[int, list[dict]] = {}
    for completion in completions:
        by_person.setdefault(completion["person_id"], []).append(completion)
    progress = []
    for person in persons:
        summary = summarize_completions(by_person.get(person["id"], []))
        if awarded_badges is not None:
            summary["badges"] = badges_for_ids(awarded_badges.get(person["id"], set()))
        progress.append({**person, **summary})
    return progress


def badge_progress(definition: dict, completions: Iterable[dict], already_earned: bool) -> dict:
    rows = list(completions)
    unique = {(row["date"], row["slot"]) for row in rows}
    target = definition["target_value"] or 1
    condition = json.loads(definition["condition_json"] or "{}")
    condition_type = definition["condition_type"]

    if condition_type == "completion-count":
        value = sum(
            1 for row in rows
            if condition.get("source", "any") == "any" or row["source"] == condition["source"]
        )
        value = len({(row["date"], row["slot"]) for row in rows}) if condition.get("source", "any") == "any" else value
    elif condition_type == "full-iso-week":
        days_by_week: dict[tuple[int, int], set[int]] = {}
        for date, _ in unique:
            iso = dt_date.fromisoformat(date).isocalendar()
            days_by_week.setdefault((iso.year, iso.week), set()).add(iso.weekday)
        value = max((len(days) for days in days_by_week.values()), default=0)
    elif condition_type == "date-completion":
        event_date = condition.get("date")
        value = int(any(row["date"] == event_date for row in rows))
    else:
        value = 0

    reached = value >= target
    unlocked = already_earned or reached
    return {
        **definition,
        "progress": target if already_earned else min(value, target),
        "target": target,
        "show_progress": condition_type != "date-completion",
        "earned": unlocked,
        "reached_now": reached,
    }


def level_for_points(points: int) -> int:
    """Leitet ein progressiv langsamer steigendes Level aus Punkten ab."""
    level = 1
    next_threshold = 10
    threshold_step = 15
    while points >= next_threshold:
        level += 1
        next_threshold += threshold_step
        threshold_step += 5
    return level


def summarize_completions(completions: Iterable[dict]) -> dict:
    """Leitet den aktuellen Fortschritt aus eindeutigen Abschlüssen ab."""
    unique: set[tuple[str, str]] = set()
    days_by_week: dict[tuple[int, int], set[int]] = {}
    for completion in completions:
        key = (completion["date"], completion["slot"])
        if key in unique:
            continue
        unique.add(key)
        iso = dt_date.fromisoformat(completion["date"]).isocalendar()
        days_by_week.setdefault((iso.year, iso.week), set()).add(iso.weekday)

    points = len(unique)
    badge_ids = []
    if points >= 1:
        badge_ids.append("first-walk")
    if points >= 10:
        badge_ids.append("ten-walks")
    if points >= 50:
        badge_ids.append("fifty-walks")
    if any(len(days) == 7 for days in days_by_week.values()):
        badge_ids.append("full-week")
    return {
        "points": points,
        "level": level_for_points(points),
        "badges": badges_for_ids(badge_ids),
    }
