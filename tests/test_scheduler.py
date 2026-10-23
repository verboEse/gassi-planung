"""Unit-Tests für den Optimierungs-Scheduler."""
from __future__ import annotations

import pytest

from app.scheduler import BLOCKED, SLOTS, compute_plan

WEEK = ["2026-10-12", "2026-10-13", "2026-10-14", "2026-10-15",
        "2026-10-16", "2026-10-17", "2026-10-18"]
ONE_DAY = ["2026-10-12"]


def make_prefs(entries: dict[tuple[str, str, int], int]) -> dict[tuple[str, str, int], int]:
    return dict(entries)


def assignment_map(result):
    return {(a.date, a.slot): a for a in result.assignments}


class TestBlocks:
    def test_blocked_person_is_never_assigned(self):
        persons = [1, 2]
        prefs = {("2026-10-12", s, 1): BLOCKED for s in SLOTS}
        result = compute_plan(ONE_DAY, persons, prefs)
        amap = assignment_map(result)
        assert all(amap[("2026-10-12", s)].person_id == 2 for s in SLOTS)
        assert result.counts == {1: 0, 2: 3}
        assert result.unassigned == ()

    def test_all_blocked_leaves_slot_unassigned(self):
        persons = [1, 2]
        prefs = {
            ("2026-10-12", "morning", 1): BLOCKED,
            ("2026-10-12", "morning", 2): BLOCKED,
        }
        result = compute_plan(ONE_DAY, persons, prefs)
        amap = assignment_map(result)
        assert amap[("2026-10-12", "morning")].person_id is None
        assert ("2026-10-12", "morning") in result.unassigned
        # Restliche Slots werden normal besetzt
        assert amap[("2026-10-12", "noon")].person_id in (1, 2)
        assert amap[("2026-10-12", "evening")].person_id in (1, 2)

    def test_person_blocked_all_week_does_not_break_fairness(self):
        persons = [1, 2]
        prefs = {(d, s, 1): BLOCKED for d in WEEK for s in SLOTS}
        result = compute_plan(WEEK, persons, prefs)
        assert result.counts[1] == 0
        assert result.counts[2] == 21
        assert result.unassigned == ()


class TestPriorities:
    def test_higher_priority_breaks_ties_after_balancing(self):
        persons = [1, 2]
        prefs = {("2026-10-12", s, 1): 1 for s in SLOTS}
        prefs.update({("2026-10-12", s, 2): 3 for s in SLOTS})
        result = compute_plan(ONE_DAY, persons, prefs)
        assert sorted(result.counts.values()) == [1, 2]
        assert result.counts[2] == 2

    def test_higher_priority_gets_extra_slot_when_balance_is_equal(self):
        persons = [1, 2]
        prefs = {("2026-10-12", s, 1): 3 for s in SLOTS}  # p2 bleibt neutral (2)
        result = compute_plan(ONE_DAY, persons, prefs)
        assert sorted(result.counts.values()) == [1, 2]
        assert result.counts[1] == 2

    def test_unset_means_neutral_when_breaking_balance_ties(self):
        persons = [1, 2]
        # p1 bleibt neutral (2), p2 ist explizit ungern (1).
        prefs = {("2026-10-12", s, 2): 1 for s in SLOTS}
        result = compute_plan(ONE_DAY, persons, prefs)
        assert sorted(result.counts.values()) == [1, 2]
        assert result.counts[1] == 2


class TestFairness:
    def test_equal_preferences_are_balanced(self):
        persons = [1, 2, 3]
        result = compute_plan(WEEK, persons, {})
        counts = sorted(result.counts.values())
        assert counts == [7, 7, 7]
        assert result.unassigned == ()

    def test_preferences_do_not_outweigh_equal_distribution(self):
        persons = [1, 2, 3]
        slots = tuple(f"slot_{index}" for index in range(16))
        prefs = {("2026-10-12", slot, 1): 1 for slot in slots}

        result = compute_plan(ONE_DAY, persons, prefs, slots=slots)

        assert sorted(result.counts.values()) == [5, 5, 6]

    def test_balanced_with_two_persons(self):
        persons = [1, 2]
        result = compute_plan(WEEK, persons, {})
        counts = sorted(result.counts.values())
        # 21 Slots auf 2 Personen -> 10/11 ist die beste Balance
        assert counts == [10, 11]


class TestEdgeCases:
    def test_no_persons_everything_unassigned(self):
        result = compute_plan(ONE_DAY, [], {})
        assert len(result.assignments) == 3
        assert all(a.person_id is None for a in result.assignments)
        assert len(result.unassigned) == 3

    def test_single_person_gets_everything(self):
        result = compute_plan(WEEK, [1], {})
        assert result.counts == {1: 21}
        assert result.unassigned == ()

    def test_single_day_week(self):
        result = compute_plan(ONE_DAY, [1, 2], {})
        assert len(result.assignments) == 3
        assert result.unassigned == ()
