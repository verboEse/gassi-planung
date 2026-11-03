from __future__ import annotations

from datetime import date as dt_date
from datetime import timedelta

from app.gamification import level_for_points, summarize_completions


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
