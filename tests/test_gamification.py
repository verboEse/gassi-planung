from __future__ import annotations

import json
from datetime import date as dt_date
from datetime import timedelta

from app.gamification import badge_progress, level_for_points, summarize_completions


def completion(date: str, slot: str = "morning") -> dict:
    return {"date": date, "slot": slot}


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
