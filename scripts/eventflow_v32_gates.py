#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S11–S16 calibration gates, base priors, and evidence helpers (EventFlow V3.2)."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Set, Tuple

from eventflow_common import DB, EVENTFLOW_DB, fnum, read_csv, snum

COMP_DB = DB / "competition"
HOST_NATIONS = {"USA", "Mexico", "Canada"}

SCENARIO_BASE_WEIGHT: Dict[str, float] = {
    "S11_group_state_draw_control": 0.09,
    "S12_rotation_tempo_drop": 0.05,
    "S13_must_win_early_aggression": 0.06,
    "S14_buildup_gk_error_chain": 0.05,
    "S15_weather_travel_pitch_adaptation": 0.05,
    "S16_var_penalty_momentum_swing": 0.05,
}
DEFAULT_BASE_WEIGHT = 0.10

S13_PRESSURE_SIGNALS = {"group_table_pressure"}
S12_SIGNALS = {"rotation_risk", "starter_rest_signal"}
S14_SPECIFIC_SIGNALS = {
    "buildup_gk_error", "buildup_press_risk", "goalkeeper_error",
}
S15_SIGNALS = {"weather_heat_humidity", "travel_fatigue", "pitch_adaptation"}
S16_SIGNALS = {"var_penalty_swing", "box_defending_risk"}

HOT_VENUE_CITIES = (
    "miami", "houston", "dallas", "atlanta", "mexico city", "monterrey", "guadalajara",
)


def base_weight_for(sid: str) -> float:
    return SCENARIO_BASE_WEIGHT.get(sid, DEFAULT_BASE_WEIGHT)


def _match_mapping_row(match_id: str) -> Dict[str, str]:
    for row in read_csv(COMP_DB / "wc2026_match_id_mapping.csv"):
        if snum(row, "internal_match_id") == match_id:
            return row
    return {}


def _standings_for_team(team: str, group: str) -> Dict[str, str]:
    for row in read_csv(COMP_DB / "group_standings.csv"):
        if snum(row, "group") == group and snum(row, "team_en") == team:
            return row
    return {}


def match_fused_signal_types(match_id: str) -> Set[str]:
    out: Set[str] = set()
    for row in read_csv(EVENTFLOW_DB / "eventflow_fused_evidence.csv"):
        if snum(row, "match_id") != match_id:
            continue
        if snum(row, "evidence_usage") in ("post_match_review", "backtest_only"):
            continue
        if str(row.get("available_before_kickoff", "")).lower() == "false":
            continue
        if snum(row, "use_for_weighting") != "true":
            continue
        sig = snum(row, "signal_type")
        if sig:
            out.add(sig)
    return out


def compute_group_table_pressure(match_id: str, home: str, away: str) -> float:
    """0–1 must-win pressure from standings only (no probability context)."""
    m = _match_mapping_row(match_id)
    grp = snum(m, "group")
    rnd = int(fnum(m, "round", 0))
    if rnd < 2 or not grp:
        return 0.0
    hs = _standings_for_team(home, grp)
    as_ = _standings_for_team(away, grp)
    if not hs or not as_:
        return 0.0
    scores: List[float] = []
    for row in (hs, as_):
        pts = int(fnum(row, "points", 0))
        gd = fnum(row, "goal_difference")
        s = 0.0
        if pts == 0 and rnd == 2:
            s = 0.90
        elif pts <= 1 and gd < -2 and rnd == 2:
            s = 0.75
        elif pts <= 1 and rnd == 3:
            s = 0.80
        scores.append(s)
    return max(scores) if scores else 0.0


def should_enable_s13_group_pressure(
    match_id: str,
    home: str,
    away: str,
    signal_types: Set[str],
) -> Tuple[bool, Dict[str, Any]]:
    group_pressure = compute_group_table_pressure(match_id, home, away)
    source_pressure = bool(signal_types & S13_PRESSURE_SIGNALS)
    enabled = group_pressure > 0.05 or source_pressure
    meta = {
        "group_table_pressure": round(group_pressure, 4),
        "source_pressure": source_pressure,
        "gate_applied": not enabled,
        "gate_reason": "" if enabled else "no_group_or_source_must_win_pressure",
    }
    return enabled, meta


def compute_team_draw_acceptance(
    team: str,
    standings_row: Dict[str, str],
    opponent_pts: int,
    rnd: int,
) -> float:
    if rnd < 2:
        return 0.0
    pts = int(fnum(standings_row, "points", 0))
    if pts == 0 and rnd == 2:
        return 0.10
    if pts >= 3 and rnd == 2:
        return 0.82 if opponent_pts >= 3 else 0.38
    if pts == 1 and rnd == 2:
        return 0.48
    if rnd == 3 and pts >= 3:
        return 0.68
    if rnd == 3 and pts >= 1:
        return 0.42
    return 0.22


def compute_top_spot_incentive(
    home: str,
    away: str,
    home_breakthrough: float,
    away_breakthrough: float,
) -> float:
    incentive = abs(home_breakthrough - away_breakthrough) * 0.45
    if home in HOST_NATIONS:
        incentive += 0.12
    return min(1.0, incentive)


def compute_s11_draw_control_score(
    match_id: str,
    home: str,
    away: str,
    home_breakthrough: float,
    away_breakthrough: float,
) -> Tuple[float, Dict[str, Any]]:
    m = _match_mapping_row(match_id)
    grp = snum(m, "group")
    rnd = int(fnum(m, "round", 0))
    detail: Dict[str, Any] = {
        "home_draw_acceptance": 0.0,
        "away_draw_acceptance": 0.0,
        "mutual_draw_control": 0.0,
        "one_side_control": 0.0,
        "favorite_top_spot_incentive": 0.0,
    }
    if rnd < 2 or not grp:
        return 0.0, detail

    hs = _standings_for_team(home, grp)
    as_ = _standings_for_team(away, grp)
    if not hs or not as_:
        return 0.0, detail

    hp, ap = int(fnum(hs, "points", 0)), int(fnum(as_, "points", 0))
    home_accept = compute_team_draw_acceptance(home, hs, ap, rnd)
    away_accept = compute_team_draw_acceptance(away, as_, hp, rnd)
    mutual = min(home_accept, away_accept)
    one_side = abs(home_accept - away_accept)
    top_spot = compute_top_spot_incentive(home, away, home_breakthrough, away_breakthrough)

    score = mutual * 0.35 + one_side * 0.12 - top_spot * 0.10
    score = max(0.0, min(1.0, score))

    detail.update({
        "home_draw_acceptance": round(home_accept, 4),
        "away_draw_acceptance": round(away_accept, 4),
        "mutual_draw_control": round(mutual, 4),
        "one_side_control": round(one_side, 4),
        "favorite_top_spot_incentive": round(top_spot, 4),
        "composite_score": round(score, 4),
    })
    return score, detail


def has_structured_buildup_risk(home_prof: Dict[str, str], away_prof: Dict[str, str]) -> bool:
    for prof in (home_prof, away_prof):
        style = snum(prof, "build_up_style")
        if ("控球" in style or "混合" in style) and fnum(prof, "collapse_risk") > 0.45:
            return True
    return False


def has_specific_buildup_evidence(
    signal_types: Set[str],
    home_prof: Dict[str, str],
    away_prof: Dict[str, str],
) -> Tuple[bool, List[str]]:
    refs = sorted(signal_types & S14_SPECIFIC_SIGNALS)
    if refs:
        return True, refs
    if has_structured_buildup_risk(home_prof, away_prof):
        return True, ["structured_buildup_risk"]
    return False, []


def cap_s14_tactical(
    raw_tactical: float,
    has_specific: bool,
) -> Tuple[float, Dict[str, Any]]:
    gates: Dict[str, Any] = {
        "specific_buildup_evidence": has_specific,
        "duplicate_press_cap_applied": False,
    }
    if has_specific:
        return raw_tactical, gates
    capped = min(raw_tactical, 0.25)
    if capped < raw_tactical:
        gates["duplicate_press_cap_applied"] = True
        gates["gate_applied"] = True
        gates["gate_reason"] = "no_buildup_gk_evidence_press_capped"
    return capped, gates


def buildup_risk_score_specific(
    home_prof: Dict[str, str],
    away_prof: Dict[str, str],
    hpress: float,
    apress: float,
    has_specific: bool,
) -> float:
    """GK/build-up chain risk — only from collapse under press when evidence exists."""
    if not has_specific:
        return 0.0
    risk = 0.0
    h_collapse = max(0.0, fnum(home_prof, "collapse_risk"))
    a_collapse = max(0.0, fnum(away_prof, "collapse_risk"))
    if hpress > 0.08 and a_collapse > 0.3:
        risk = max(risk, min(1.0, a_collapse * 0.55 + hpress * 0.25))
    if apress > 0.08 and h_collapse > 0.3:
        risk = max(risk, min(1.0, h_collapse * 0.55 + apress * 0.25))
    return risk


def environment_stress_structured(match_id: str, signal_types: Set[str]) -> Tuple[float, List[str]]:
    refs = sorted(signal_types & S15_SIGNALS)
    if refs:
        return min(1.0, 0.35 + 0.15 * len(refs)), refs
    return 0.0, []


def rotation_risk_gated(match_id: str, src_d: float, signal_types: Set[str]) -> Tuple[float, Dict[str, Any]]:
    refs = sorted(signal_types & S12_SIGNALS)
    if src_d > 0 or refs:
        score = min(1.0, 0.30 + src_d * 2.0 + 0.15 * len(refs))
        return score, {"evidence_refs": refs, "source_backed": True}
    return 0.0, {"gate_applied": True, "gate_reason": "no_rotation_evidence", "evidence_refs": []}


def gates_to_json(gates: Dict[str, Any]) -> str:
    return json.dumps(gates, ensure_ascii=False, separators=(",", ":"))


def parse_gates_json(raw: str) -> Dict[str, Any]:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}
