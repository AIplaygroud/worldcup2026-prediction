#!/usr/bin/env python3
"""Weighted Annex C scenarios and future-position route expectations."""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from group_state_common import ROOT, read_csv, team_strength

ANNEX_C = ROOT / "database" / "competition" / "annex_c_round_of_32.csv"
WINNER_SLOTS = ("1A", "1B", "1D", "1E", "1G", "1I", "1K", "1L")


def _clip(value: float, lo: float = 0.01, hi: float = 0.99) -> float:
    return max(lo, min(hi, value))


def expected_finish_strength(
    group: str,
    finish: int,
    team_states: dict[str, dict[str, Any]],
) -> tuple[float, float]:
    weighted: list[tuple[float, float]] = []
    key = f"p_finish_{finish}"
    for team, detail in team_states.items():
        if detail.get("group") != group:
            continue
        weight = float(detail.get(key, 0.0))
        if weight > 0:
            weighted.append((weight, team_strength(team)))
    total = sum(w for w, _ in weighted)
    if total <= 0:
        return 0.5, 0.35
    mean = sum(w * s for w, s in weighted) / total
    variance = sum(w * (s - mean) ** 2 for w, s in weighted) / total
    return round(mean, 4), round(math.sqrt(variance), 4)


def third_group_quality(
    group: str,
    team_states: dict[str, dict[str, Any]],
) -> tuple[float, float]:
    weighted: list[tuple[float, float, float]] = []
    for team, detail in team_states.items():
        if detail.get("group") != group:
            continue
        p3 = float(detail.get("p_finish_3", 0.0))
        if p3 <= 0:
            continue
        points = float(detail.get("points", 0.0))
        gd = float(detail.get("gd", 0.0))
        profile = _clip(0.32 + 0.08 * points + 0.025 * gd, 0.08, 0.92)
        weighted.append((p3, profile, team_strength(team)))
    total = sum(w for w, _, _ in weighted)
    if total <= 0:
        return 0.5, 0.5
    qualify_score = sum(w * q for w, q, _ in weighted) / total
    strength = sum(w * s for w, _, s in weighted) / total
    return round(_clip(qualify_score, 0.08, 0.92), 4), round(strength, 4)


def annex_scenario_weights(
    team_states: dict[str, dict[str, Any]],
    annex_rows: list[dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    rows = annex_rows if annex_rows is not None else read_csv(ANNEX_C)
    group_scores = {
        group: third_group_quality(group, team_states)[0]
        for group in "ABCDEFGHIJKL"
    }
    scenarios: list[dict[str, Any]] = []
    for row in rows:
        advancing = set(row["advancing_groups"])
        raw = 1.0
        for group, score in group_scores.items():
            raw *= score if group in advancing else (1.0 - score)
        scenarios.append({**row, "raw_weight": raw})
    total = sum(s["raw_weight"] for s in scenarios)
    if total <= 0:
        total = float(len(scenarios) or 1)
        for scenario in scenarios:
            scenario["raw_weight"] = 1.0
    for scenario in scenarios:
        scenario["weight"] = scenario["raw_weight"] / total
    return scenarios


def best8_third_probabilities(
    team_states: dict[str, dict[str, Any]],
    scenarios: list[dict[str, Any]],
) -> dict[str, float]:
    group_prob = {
        group: sum(s["weight"] for s in scenarios if group in s["advancing_groups"])
        for group in "ABCDEFGHIJKL"
    }
    return {
        team: round(float(detail.get("p_finish_3", 0.0)) * group_prob.get(detail["group"], 0.0), 4)
        for team, detail in team_states.items()
    }


def expected_route_for_slot(
    slot: str,
    team_states: dict[str, dict[str, Any]],
    scenarios: list[dict[str, Any]],
) -> dict[str, Any]:
    if slot in WINNER_SLOTS:
        column = f"vs_{slot}"
        values: list[tuple[float, float]] = []
        groups: set[str] = set()
        for scenario in scenarios:
            opponent = scenario[column]
            group = opponent[1]
            groups.add(group)
            strength = third_group_quality(group, team_states)[1]
            values.append((scenario["weight"], strength))
        mean = sum(w * strength for w, strength in values)
        variance = sum(w * (strength - mean) ** 2 for w, strength in values)
        entropy = -sum(
            scenario["weight"] * math.log(max(scenario["weight"], 1e-12))
            for scenario in scenarios
        )
        max_entropy = math.log(max(len(scenarios), 1))
        scenario_uncertainty = 0.15 * entropy / max_entropy if max_entropy > 0 else 0.0
        return {
            "difficulty": round(mean, 4),
            "uncertainty": round(min(1.0, math.sqrt(variance) + scenario_uncertainty), 4),
            "opponent_label": "weighted_annex_c_third",
            "annex_scenarios_covered": len(scenarios),
            "candidate_groups": "".join(sorted(groups)),
        }

    if len(slot) == 2 and slot[0] in "12":
        finish = int(slot[0])
        group = slot[1]
        mean, uncertainty = expected_finish_strength(group, finish, team_states)
        return {
            "difficulty": mean,
            "uncertainty": uncertainty,
            "opponent_label": f"expected_{slot}",
            "annex_scenarios_covered": 0,
            "candidate_groups": group,
        }
    return {
        "difficulty": 0.5,
        "uncertainty": 0.35,
        "opponent_label": slot or "unknown",
        "annex_scenarios_covered": 0,
        "candidate_groups": "",
    }
