from __future__ import annotations

import json
from datetime import date as dt_date
from datetime import datetime
from datetime import timedelta

from app.gamification import badge_progress, level_for_points, summarize_completions


def completion(date: str, slot: str = "morning") -> dict:
    return {"date": date, "slot": slot}


def badge_definition(condition_type: str, target: int = 10) -> dict:
    return {
        "id": "test-series",
        "condition_type": condition_type,
        "condition_json": "{}",
        "target_value": target,
        "retention": "current-count",
    }


def test_points_and_progressive_level_boundaries():
    assert [level_for_points(points) for points in (0, 9, 10, 24, 25, 44, 45, 69, 70)] == [
        1, 1, 2, 2, 3, 3, 4, 4, 5
    ]
    assert summarize_completions([])["level"] == 1
    nine = [completion(f"2026-10-{day:02d}") for day in range(1, 10)]
    assert summarize_completions(nine)["points"] == 9
    assert summarize_completions(nine)["level"] == 1
    ten = nine + [completion("2026-10-10")]
    assert summarize_completions(ten)["points"] == 10
    assert summarize_completions(ten)["level"] == 2


def test_total_badges_and_duplicate_completion():
    start = dt_date(2026, 1, 1)
    completions = [
        completion((start + timedelta(days=offset)).isoformat()) for offset in range(50)
    ]
    completions.append(completion(start.isoformat()))
    result = summarize_completions(completions)
    assert result["points"] == 50
    assert {badge["id"] for badge in result["badges"]} >= {
        "first-walk", "ten-walks", "fifty-walks"
    }


def test_distance_badge_uses_the_longest_measured_walk():
    badge = badge_definition("distance-at-least", target=5000)
    walks = [
        {"date": "2026-10-12", "slot": "morning", "distance_meters": 4999},
        {"date": "2026-10-12", "slot": None, "walk_type": "extra", "distance_meters": 4200},
    ]

    progress = badge_progress(badge, walks, False)
    assert progress["progress"] == 4999
    assert not progress["reached_now"]

    progress = badge_progress(
        badge,
        walks + [{"date": "2026-10-13", "slot": "noon", "distance_meters": 5000}],
        False,
    )
    assert progress["progress"] == 5000
    assert progress["reached_now"]


def test_full_week_badge_candidate():
    full_week = [completion(f"2026-10-{day:02d}") for day in range(12, 19)]
    assert "full-week" in {badge["id"] for badge in summarize_completions(full_week)["badges"]}
    without_sunday = full_week[:-1]
    assert "full-week" not in {
        badge["id"] for badge in summarize_completions(without_sunday)["badges"]
    }


def test_shared_walk_badges_use_unique_participations_and_group_size():
    start = dt_date(2026, 1, 1)
    shared = [
        {
            "date": (start + timedelta(days=day)).isoformat(),
            "slot": "morning",
            "shared_walk_id": day,
            "shared_group_size": 4,
        }
        for day in range(50)
    ]

    def badge(condition_type, condition, target=1):
        return {
            "id": "test",
            "condition_type": condition_type,
            "condition_json": json.dumps(condition),
            "target_value": target,
            "retention": "current-count",
        }

    shared_count = badge("shared-walk-count", {}, target=10)
    assert badge_progress(shared_count, shared[:9], False)["progress"] == 9
    assert badge_progress(shared_count, shared[:10], False)["reached_now"]
    assert badge_progress(
        badge("shared-walk-count", {}, target=50), shared, False
    )["reached_now"]
    assert badge_progress(
        badge("group-size", {"size": 3}),
        [{**shared[0], "shared_group_size": 3}],
        False,
    )["reached_now"]
    assert not badge_progress(badge("group-size", {"size": 3}), shared, False)["reached_now"]
    assert badge_progress(badge("group-size", {"size": 4}), shared, False)["reached_now"]
    assert badge_progress(badge("group-size", {"minimum_size": 4}), shared, False)["reached_now"]
    assert not badge_progress(
        badge("group-size", {"minimum_size": 4}),
        [{**shared[0], "shared_group_size": 3}],
        False,
    )["reached_now"]


def test_secret_day_streak_tracks_current_and_best_and_recalculates_after_correction():
    start = dt_date(2026, 1, 1)
    completions = [
        completion((start + timedelta(days=day)).isoformat()) for day in range(10)
    ]
    completions.append(completion("2026-01-12"))
    result = badge_progress(
        badge_definition("consecutive-days"),
        completions,
        True,
        as_of=datetime(2026, 1, 12, 12),
    )
    assert result["current_streak"] == 1
    assert result["best_streak"] == 10
    assert result["reached_now"]

    corrected = [row for row in completions if row["date"] != "2026-01-05"]
    result = badge_progress(
        badge_definition("consecutive-days"),
        corrected,
        True,
        as_of=datetime(2026, 1, 12, 12),
    )
    assert result["best_streak"] == 5
    assert not result["reached_now"]


def test_secret_slot_streak_breaks_on_any_missed_slot():
    slots = ["morning", "noon", "evening"]
    completions = [
        completion(f"2026-01-{day:02d}", slot)
        for day in range(1, 5)
        for slot in slots
    ][:10]
    definition = badge_definition("consecutive-slots")

    reached = badge_progress(
        definition,
        completions,
        False,
        as_of=datetime(2026, 1, 4, 9),
    )
    assert reached["best_streak"] == 10
    assert reached["current_streak"] == 10
    assert reached["reached_now"]

    missed_noon = badge_progress(
        definition,
        completions,
        True,
        as_of=datetime(2026, 1, 4, 16),
    )
    assert missed_noon["best_streak"] == 10
    assert missed_noon["current_streak"] == 0
    assert not missed_noon["reached_now"]

    recovery_completions = completions + [
        completion("2026-01-04", "evening"),
        completion("2026-01-05", "morning"),
        completion("2026-01-05", "noon"),
        completion("2026-01-05", "evening"),
        completion("2026-01-06", "morning"),
        completion("2026-01-06", "noon"),
        completion("2026-01-06", "evening"),
        completion("2026-01-07", "morning"),
        completion("2026-01-07", "noon"),
        completion("2026-01-07", "evening"),
    ]
    recovered = badge_progress(
        definition,
        recovery_completions,
        True,
        as_of=datetime(2026, 1, 7, 23),
    )
    assert recovered["current_streak"] == 10
    assert recovered["best_streak"] == 10
    assert recovered["reached_now"]


def test_off_plan_badge_counts_distinct_walks_without_a_streak():
    completions = []
    start = dt_date(2026, 1, 1)
    for day in range(20):
        row = completion((start + timedelta(days=day)).isoformat())
        completions.append({**row, "off_plan": int(day % 2 == 0)})
    completions.append({**completions[0]})

    result = badge_progress(
        badge_definition("off-plan-count"), completions, False
    )
    assert result["progress"] == 10
    assert result["reached_now"]


def test_extra_walks_do_not_affect_standard_progression_or_badges():
    start = dt_date(2026, 10, 12)
    extras = [
        {
            "completion_id": index + 1,
            "date": (start + timedelta(days=index)).isoformat(),
            "slot": None,
            "walk_type": "extra",
            "source": "manual",
            "off_plan": 1,
            "shared_walk_id": index + 1,
            "shared_group_size": 4,
        }
        for index in range(14)
    ]
    summary = summarize_completions(extras)
    assert summary["points"] == 0
    assert summary["level"] == 1
    assert summary["badges"] == []

    conditions = (
        ("completion-count", {}),
        ("shared-walk-count", {}),
        ("group-size", {"size": 4}),
        ("off-plan-count", {}),
        ("consecutive-days", {}),
        ("consecutive-slots", {}),
        ("full-iso-week", {}),
        ("date-completion", {"date": extras[0]["date"]}),
    )
    for condition_type, condition in conditions:
        definition = {
            **badge_definition(condition_type, target=1),
            "condition_json": json.dumps(condition),
        }
        progress = badge_progress(
            definition, extras, False, as_of=datetime(2026, 10, 26, 12)
        )
        assert not progress["reached_now"], condition_type
        assert progress["progress"] == 0, condition_type


def test_extra_walk_badge_counts_distinct_same_day_completion_ids():
    definition = {
        **badge_definition("extra-walk-count", target=10),
        "condition_json": "{}",
    }
    extras = [
        {
            "completion_id": index,
            "date": "2026-10-12",
            "slot": None,
            "walk_type": "extra",
        }
        for index in range(1, 11)
    ]
    extras.append(dict(extras[0]))

    before_tenth = badge_progress(definition, extras[:9], False)
    reached = badge_progress(definition, extras, False)

    assert before_tenth["progress"] == 9
    assert not before_tenth["reached_now"]
    assert reached["progress"] == 10
    assert reached["reached_now"]


def test_repeated_day_streak_reports_current_progress_against_previous_best():
    start = dt_date(2026, 1, 1)
    previous_best = [
        completion((start + timedelta(days=day)).isoformat()) for day in range(23)
    ]
    repeated_start = start + timedelta(days=24)
    repeated = [
        completion((repeated_start + timedelta(days=day)).isoformat())
        for day in range(11)
    ]

    result = badge_progress(
        badge_definition("consecutive-days"),
        previous_best + repeated,
        True,
        as_of=datetime(2026, 2, 4, 12),
    )
    assert result["current_streak"] == 11
    assert result["best_streak"] == 23
