"""Optimale Berechnung des Gassi-Plans.

Das Problem wird als ganzzahliges lineares Programm (ILP) formuliert und mit
dem in PuLP gebundelten CBC-Solver exakt gelöst:

* Jeder Slot wird genau einer Person zugewiesen – oder als unbesetzt markiert,
  wenn alle Personen blockiert haben.
* Blockierte Slots sind harte Nebenbedingungen.
* Zielfunktion: Einsatzzahlen ausgleichen, Prioritäten als Tie-Breaker nutzen.
"""
from __future__ import annotations

from dataclasses import dataclass

import pulp

SLOTS: tuple[str, ...] = ("morning", "noon", "evening")
SLOT_LABELS: dict[str, str] = {
    "morning": "Morgens",
    "noon": "Mittags",
    "evening": "Abends",
}
WEEKDAYS: tuple[str, ...] = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")

BLOCKED = -1
MIN_PREF = 1
MAX_PREF = 3
DEFAULT_PREF = 2
VALID_PREF_VALUES = (BLOCKED, 1, 2, 3)

#: Strafe pro unbesetztem Slot. Muss deutlich größer sein als jeder
#: erreichbare Prioritätengewinn, damit „unbesetzt“ nur als Notlösung vorkommt.
UNASSIGNED_PENALTY = 1000


@dataclass(frozen=True)
class Assignment:
    date: str
    slot: str
    person_id: int | None  # None = unbesetzt (alle blockiert)
    pref: int | None       # verwendete Priorität, None wenn unbesetzt


@dataclass(frozen=True)
class PlanResult:
    assignments: tuple[Assignment, ...]
    counts: dict[int, int]                 # person_id -> Anzahl Einsätze
    unassigned: tuple[tuple[str, str], ...]  # (date, slot) ohne Zuweisung


def compute_plan(
    dates: list[str],
    person_ids: list[int],
    prefs: dict[tuple[str, str, int], int],
    slots: tuple[str, ...] = SLOTS,
    fairness_weight: float | None = None,
    default_pref: int = DEFAULT_PREF,
) -> PlanResult:
    """Berechnet die optimale Zuweisung für die gegebenen Tage.

    :param dates: ISO-Datumsstrings, z. B. die 7 Tage einer Kalenderwoche
    :param person_ids: IDs der aktiven Personen
    :param prefs: {(date, slot, person_id): wert} mit wert in {-1, 1, 2, 3};
        fehlende Einträge gelten als ``default_pref`` (neutral)
    :param fairness_weight: Gewicht der Fairness-Strafe pro Slot Unterschied
        in der Einsatzzahl. Standardmäßig wird es so gewählt, dass die Balance
        Vorrang vor jedem möglichen Prioritätsgewinn hat.
    :raises RuntimeError: wenn der Solver keine optimale Lösung findet
    """
    if fairness_weight is None:
        fairness_weight = (MAX_PREF - MIN_PREF) * len(dates) * len(slots) + 1

    prob = pulp.LpProblem("gassi-plan", pulp.LpMaximize)

    def pref_of(d: str, s: str, p: int) -> int:
        return prefs.get((d, s, p), default_pref)

    # Zuweisungsvariablen nur für nicht-blockierte Kombinationen anlegen
    x: dict[tuple[str, str, int], pulp.LpVariable] = {}
    for d in dates:
        for s in slots:
            for p in person_ids:
                if pref_of(d, s, p) != BLOCKED:
                    x[(d, s, p)] = pulp.LpVariable(f"x_{d}_{s}_{p}", cat="Binary")

    u = {
        (d, s): pulp.LpVariable(f"u_{d}_{s}", cat="Binary")
        for d in dates
        for s in slots
    }

    # Jeder Slot: genau eine Person ODER unbesetzt
    for d in dates:
        for s in slots:
            prob += (
                pulp.lpSum(var for (dd, ss, _), var in x.items() if dd == d and ss == s)
                + u[(d, s)]
            ) == 1

    counts_expr = {
        p: pulp.lpSum(var for (_, _, pp), var in x.items() if pp == p)
        for p in person_ids
    }

    objective: list = []
    for (d, s, p), var in x.items():
        objective.append(pref_of(d, s, p) * var)
    objective.extend(-UNASSIGNED_PENALTY * var for var in u.values())

    # Weiche Fairness: Spanne zwischen meisten und wenigsten Einsätzen.
    # Personen ohne einen einzigen verfügbaren Slot werden ausgenommen,
    # damit sie die Balance nicht verzerren.
    eligible = [p for p in person_ids if any(pp == p for (_, _, pp) in x)]
    if len(eligible) > 1:
        cmax = pulp.LpVariable("count_max", lowBound=0, cat="Integer")
        cmin = pulp.LpVariable("count_min", lowBound=0, cat="Integer")
        for p in eligible:
            prob += cmax >= counts_expr[p]
            prob += cmin <= counts_expr[p]
        objective.append(-fairness_weight * (cmax - cmin))

    prob += pulp.lpSum(objective)
    status = prob.solve(pulp.PULP_CBC_CMD(msg=False))
    if pulp.LpStatus[status] != "Optimal":
        raise RuntimeError(f"Optimierung fehlgeschlagen: Status {pulp.LpStatus[status]}")

    assignments: list[Assignment] = []
    unassigned: list[tuple[str, str]] = []
    counts = {p: 0 for p in person_ids}
    for d in dates:
        for s in slots:
            chosen = None
            for p in person_ids:
                var = x.get((d, s, p))
                if var is not None and round(pulp.value(var) or 0) == 1:
                    chosen = p
                    break
            if chosen is None:
                unassigned.append((d, s))
                assignments.append(Assignment(d, s, None, None))
            else:
                counts[chosen] += 1
                assignments.append(Assignment(d, s, chosen, pref_of(d, s, chosen)))

    return PlanResult(tuple(assignments), counts, tuple(unassigned))
