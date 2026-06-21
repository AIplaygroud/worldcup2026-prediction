#!/usr/bin/env python3
"""Canonical competition-state adapter shared by Phase 06, V3.4, and V3.7."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from group_state_common import (
    build_standings,
    classify_path_state,
    pre_kickoff_cutoff,
    remaining_group_matches,
)


def canonical_reason_code(detail: dict[str, Any]) -> str:
    return str(detail.get("state_reason_code") or detail.get("state_reason_codes") or "STATE_UNKNOWN")


def evaluate_team_state(
    team: str,
    group: str,
    standings: list[dict[str, Any]],
    cutoff: datetime,
    *,
    round_num: int = 0,
    remaining: dict[str, list[dict[str, str]]] | None = None,
) -> dict[str, Any]:
    row = next(r for r in standings if r["team"] == team and r["group"] == group)
    rem = remaining if remaining is not None else remaining_group_matches(cutoff)
    detail = classify_path_state(
        team,
        group,
        int(row["rank"]),
        standings,
        rem.get(group, []),
        round_num=round_num,
        cutoff=cutoff,
    )
    reason = canonical_reason_code(detail)
    detail["state_reason_code"] = reason
    detail["state_reason_codes"] = reason
    return detail


def must_win_pressure(detail: dict[str, Any]) -> float:
    state = str(detail.get("path_state", ""))
    if state in ("opening_round", "baseline_opening"):
        return 0.0
    if state == "must_win_big":
        return 0.90
    if state == "must_win":
        return 0.80
    if state == "third_place_bubble":
        return 0.45
    return 0.0


def top_spot_incentive(detail: dict[str, Any]) -> float:
    if not detail.get("can_finish_top1", False):
        return 0.0
    state = str(detail.get("path_state", ""))
    base = float(detail.get("p_finish_1", 0.0))
    if state == "top_slot_chase":
        base = max(base, 0.55)
    elif state in ("clinched_top2", "near_clinched"):
        base = max(base, 0.35)
    return round(min(1.0, base), 4)


def controlled_win_incentive(detail: dict[str, Any]) -> float:
    top = top_spot_incentive(detail)
    draw = float(detail.get("draw_acceptance", 0.3))
    pressure = must_win_pressure(detail)
    return round(max(0.0, min(1.0, top * 0.70 + draw * 0.20 - pressure * 0.35)), 4)


def evaluate_match_state(
    home: str,
    away: str,
    group: str,
    kickoff: datetime,
    *,
    round_num: int = 0,
) -> dict[str, Any]:
    cutoff = pre_kickoff_cutoff(kickoff)
    standings, _, _ = build_standings(cutoff)
    remaining = remaining_group_matches(cutoff)
    home_state = evaluate_team_state(
        home, group, standings, cutoff, round_num=round_num, remaining=remaining,
    )
    away_state = evaluate_team_state(
        away, group, standings, cutoff, round_num=round_num, remaining=remaining,
    )
    mutual_draw = min(
        float(home_state.get("draw_acceptance", 0.0)),
        float(away_state.get("draw_acceptance", 0.0)),
    )
    max_pressure = max(must_win_pressure(home_state), must_win_pressure(away_state))
    late_draw = max(0.0, min(1.0, mutual_draw * (1.0 - 0.55 * max_pressure)))
    return {
        "as_of_utc": cutoff,
        "standings": standings,
        "home": home_state,
        "away": away_state,
        "mutual_draw_acceptance": round(mutual_draw, 4),
        "late_draw_control_index": round(late_draw, 4),
        "late_chase_suppression": round(min(0.55, late_draw * 0.45), 4),
    }
