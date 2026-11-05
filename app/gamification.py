"""Berechnung von Punkten, Leveln und Badges aus erledigten Gassirunden."""
from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import date as dt_date
from datetime import datetime, timedelta

from .ical import SLOT_TIMES, WALK_WINDOW_TOLERANCE
from .scheduler import SLOTS

BADGE_DEFINITIONS = (
    ("first-walk", "Erste Runde"),
    ("ten-walks", "10 Runden"),
    ("fifty-walks", "50 Runden"),
    ("full-week", "Volle Woche"),
    ("ten-day-streak", "10 Tage am Stück"),
    ("ten-round-streak", "10 Runden am Stück"),
    ("ten-off-plan-walks", "10 Runden außer Plan"),
    ("first-shared-walk", "Gemeinsam gestartet"),
    ("ten-shared-walks", "Teamgeist 10"),
    ("fifty-shared-walks", "Teamgeist 50"),
    ("three-person-walk", "Zu dritt unterwegs"),
    ("four-plus-walk", "Große Gassi-Gruppe"),
)
COUNT_BADGE_IDS = ("first-walk", "ten-walks", "fifty-walks")


def badges_for_ids(badge_ids: Iterable[str]) -> list[dict]:
    ids = set(badge_ids)
    return [
        {"id": badge_id, "label": label}
        for badge_id, label in BADGE_DEFINITIONS
        if badge_id in ids
    ]


def _longest_streak(values: set[int]) -> int:
    longest = current = 0
    previous = None
    for value in sorted(values):
        current = current + 1 if previous is not None and value == previous + 1 else 1
        longest = max(longest, current)
        previous = value
    return longest


def _current_streak(values: set[int], end: int | None) -> int:
    if end is None or end not in values:
        return 0
    current = 1
    while end - current in values:
        current += 1
    return current


def _latest_elapsed_slot(as_of: datetime) -> int | None:
    elapsed = []
    for days_ago in (1, 0):
        walk_date = as_of.date() - timedelta(days=days_ago)
        for index, slot in enumerate(SLOTS):
            end_hour, end_minute = SLOT_TIMES[slot][1]
            deadline = as_of.replace(
                year=walk_date.year,
                month=walk_date.month,
                day=walk_date.day,
                hour=end_hour,
                minute=end_minute,
                second=0,
                microsecond=0,
            ) + WALK_WINDOW_TOLERANCE
            if deadline <= as_of:
                elapsed.append(walk_date.toordinal() * len(SLOTS) + index)
    return max(elapsed, default=None)


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


def badge_progress(
    definition: dict,
    completions: Iterable[dict],
    already_earned: bool,
    as_of: datetime | None = None,
) -> dict:
    rows = list(completions)
    unique = {(row["date"], row["slot"]) for row in rows}
    target = definition["target_value"] or 1
    condition = json.loads(definition["condition_json"] or "{}")
    condition_type = definition["condition_type"]
    streak_progress = {}

    if condition_type == "completion-count":
        value = sum(
            1 for row in rows
            if condition.get("source", "any") == "any" or row["source"] == condition["source"]
        )
        value = len({(row["date"], row["slot"]) for row in rows}) if condition.get("source", "any") == "any" else value
    elif condition_type == "shared-walk-count":
        value = len({
            (row["date"], row["slot"])
            for row in rows
            if row.get("shared_walk_id") is not None
        })
    elif condition_type == "group-size":
        exact_size = condition.get("size")
        minimum_size = condition.get("minimum_size")
        value = int(any(
            (row.get("shared_group_size", 0) == exact_size if exact_size is not None
             else row.get("shared_group_size", 0) >= minimum_size)
            for row in rows
        ))
    elif condition_type == "off-plan-count":
        value = len({
            (row["date"], row["slot"])
            for row in rows
            if row.get("off_plan") == 1
        })
    elif condition_type == "consecutive-days":
        days = {dt_date.fromisoformat(date).toordinal() for date, _ in unique}
        best = _longest_streak(days)
        current_end = max(days, default=None)
        if as_of is not None:
            today = as_of.date().toordinal()
            current_end = today if today in days else today - 1
        value = best
        streak_progress = {
            "current_streak": _current_streak(days, current_end),
            "best_streak": best,
        }
    elif condition_type == "consecutive-slots":
        slots = {
            dt_date.fromisoformat(date).toordinal() * len(SLOTS) + SLOTS.index(slot)
            for date, slot in unique
        }
        best = _longest_streak(slots)
        current_end = max(slots, default=None)
        if as_of is not None:
            current_end = _latest_elapsed_slot(as_of)
        current = _current_streak(slots, current_end)
        value = current
        streak_progress = {
            "current_streak": current,
            "best_streak": best,
        }
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
        "progress": (
            streak_progress["current_streak"]
            if streak_progress
            else target if already_earned else min(value, target)
        ),
        "target": target,
        "show_progress": condition_type != "date-completion",
        "earned": unlocked,
        "reached_now": reached,
        **streak_progress,
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
