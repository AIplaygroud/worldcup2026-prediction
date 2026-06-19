#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Score EventFlow scenario weights with full weight decomposition per S01–S10."""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from eventflow_common import (
    EVENTFLOW_DB, TEAM_DB, PLAYER_DB, DB, read_csv, read_json, write_csv,
    fnum, snum, normalize_weights,
)
from scenario_htft_semantics import semantic_patterns_for

MAPPING_PATH = EVENTFLOW_DB / "scenario_signal_mapping.csv"

S08_ID = "S08_strict_ref_card_penalty_chaos"
REF_STYLE_MIN_CONF = 0.65
REF_STRICT_FLOOR = 0.45
REF_PK_RC_FLOOR = 0.40
REF_IMPACT_FLOOR = 0.35


def _fifa_match_num(match_id: str) -> str:
    if match_id.startswith("WC2026-"):
        suffix = match_id.split("-", 1)[1]
        m = re.search(r"(\d+)$", suffix)
        return m.group(1) if m else suffix
    return match_id


def _match_referee_name(match_id: str) -> str:
    num = _fifa_match_num(match_id)
    for row in read_csv(DB / "referee" / "processed" / "match_officials.csv"):
        if snum(row, "match_id") == num:
            return snum(row, "referee")
    return ""


def _referee_style_row(name: str) -> Dict[str, str]:
    if not name:
        return {}
    for row in read_csv(DB / "referee" / "processed" / "referee_style_index.csv"):
        if snum(row, "referee") == name:
            return row
    return {}


def _referee_impact_row(name: str) -> Dict[str, str]:
    if not name:
        return {}
    for row in read_csv(DB / "referee" / "processed" / "referee_impact_summary.csv"):
        if snum(row, "referee") == name:
            return row
    return {}


def s08_tactical_delta(
    match_id: str,
    home_prof: Dict[str, str],
    away_prof: Dict[str, str],
    src_d: float,
) -> tuple[float, str]:
    """S08 only rises with card/ref/VAR evidence — not generic chaos_index alone."""
    if src_d > 0:
        return min(0.22, 0.08 + src_d * 1.6), "fused_card_or_referee_AB"

    ref = _match_referee_name(match_id)
    style = _referee_style_row(ref)
    if style and fnum(style, "data_confidence") >= REF_STYLE_MIN_CONF:
        strict = fnum(style, "strictness_index")
        pk = abs(fnum(style, "penalty_tendency"))
        rc = max(0.0, fnum(style, "red_card_tendency"))
        if strict >= REF_STRICT_FLOOR or pk >= REF_PK_RC_FLOOR or rc >= REF_PK_RC_FLOOR:
            bonus = 0.06 + strict * 0.12 + max(pk, rc) * 0.08
            return min(0.20, bonus), f"referee_style:{ref}"

    impact = _referee_impact_row(ref)
    if impact and fnum(impact, "impact_index") >= REF_IMPACT_FLOOR:
        bonus = 0.08 + fnum(impact, "impact_index") * 0.12
        return min(0.18, bonus), f"referee_impact:{ref}"

    chaos = (fnum(home_prof, "chaos_index") + fnum(away_prof, "chaos_index")) / 2
    if chaos >= 0.55:
        return min(0.06, chaos * 0.08), "high_team_chaos_index_only"
    return 0.0, "no_ref_card_var_evidence_baseline_only"


def count_position_shift(team: str, match_id: str) -> float:
    rows = read_csv(PLAYER_DB / "player_worldcup_position_shift.csv")
    vals = [
        fnum(r, "position_shift_score")
        for r in rows
        if snum(r, "team") == team and (not match_id or snum(r, "match_id") == match_id)
    ]
    return sum(vals) / len(vals) if vals else 0.0


def load_signal_mapping() -> Dict[str, Dict[str, str]]:
    return {snum(r, "signal_type"): r for r in read_csv(MAPPING_PATH) if snum(r, "signal_type")}


def fused_adjustments(match_id: str) -> Tuple[Dict[str, float], Dict[str, List[str]], Dict[str, str]]:
    mapping = load_signal_mapping()
    fused = read_csv(EVENTFLOW_DB / "eventflow_fused_evidence.csv")
    deltas: Dict[str, float] = defaultdict(float)
    evidence: Dict[str, List[str]] = defaultdict(list)
    grades: Dict[str, str] = {}
    for row in fused:
        if match_id and snum(row, "match_id") != match_id:
            continue
        if snum(row, "evidence_usage") in ("post_match_review", "backtest_only"):
            continue
        if str(row.get("available_before_kickoff", "")).lower() == "false":
            continue
        sig = snum(row, "signal_type")
        m = mapping.get(sig)
        grade = snum(row, "evidence_grade", "B")
        if m:
            sid = snum(m, "scenario_id")
            direction = snum(m, "weight_direction", "+1")
            sign = -1.0 if direction.startswith("-") else 1.0
            base = fnum(m, "base_delta", 0.02)
            conf = fnum(row, "confidence", 0.5)
            weight_mult = 1.0 if grade == "A" else (fnum(row, "single_source_penalty", 0.65) if grade == "B" else 0.0)
            if snum(row, "use_for_weighting") == "true":
                deltas[sid] += sign * base * conf * weight_mult
        else:
            sid = snum(row, "scenario_id")
            if sid.startswith("S"):
                deltas[sid] += fnum(row, "weight_delta", 0.0)
        summary = snum(row, "evidence_summary")
        sid_use = snum(m, "scenario_id") if m else snum(row, "scenario_id")
        if sid_use and summary:
            evidence[sid_use].append(summary)
            grades[sid_use] = grade
    return dict(deltas), dict(evidence), grades


def tactical_component(sid: str, m: Dict[str, str], home_prof: Dict[str, str], away_prof: Dict[str, str]) -> float:
    hb = fnum(m, "home_breakthrough_score")
    ab = fnum(m, "away_breakthrough_score")
    imbalance = fnum(m, "matchup_imbalance_index")
    htrans = fnum(m, "home_transition_edge")
    atrans = fnum(m, "away_transition_edge")
    hset = fnum(m, "home_set_piece_edge")
    aset = fnum(m, "away_set_piece_edge")
    hflank = fnum(m, "home_flank_edge")
    aflank = fnum(m, "away_flank_edge")
    hpress = fnum(m, "home_press_trap_edge")
    apress = fnum(m, "away_press_trap_edge")
    chaos = (fnum(home_prof, "chaos_index") + fnum(away_prof, "chaos_index")) / 2
    collapse = max(fnum(home_prof, "collapse_risk"), fnum(away_prof, "collapse_risk"))

    if sid == "S01_favorite_early_break_open":
        return max(0, max(hb, ab)) * 0.35 + imbalance * 0.25 + collapse * 0.20
    if sid == "S02_low_block_survival":
        return max(0, fnum(home_prof, "low_block_quality") + fnum(away_prof, "low_block_quality")) * 0.20 - abs(hb - ab) * 0.10
    if sid == "S03_wide_overload_crossfire":
        return max(hflank, aflank, 0) * 0.45
    if sid == "S04_press_trap_turnover_goal":
        return max(hpress, apress, 0) * 0.25 + max(collapse, 0) * 0.20
    if sid == "S05_high_line_vs_runner":
        return max(htrans, atrans, 0) * 0.35 + max(fnum(home_prof, "high_line_risk"), fnum(away_prof, "high_line_risk"), 0) * 0.25
    if sid == "S06_set_piece_breakthrough":
        return max(hset, aset, 0) * 0.50
    if sid == "S07_late_chase_open_game":
        return max(chaos, 0) * 0.30 + imbalance * 0.10
    if sid == S08_ID:
        return 0.0
    if sid == "S09_fatigue_travel_second_half_drop":
        return max(0, fnum(home_prof, "late_game_aggression") + fnum(away_prof, "late_game_aggression")) * 0.10
    if sid == "S10_tactical_stalemate_mutual_constraint":
        return max(0, 0.45 - abs(hb - ab)) * 0.40 + max(0, -chaos) * 0.15
    return 0.0


def player_component(sid: str, m: Dict[str, str]) -> float:
    if sid != "S03_wide_overload_crossfire":
        return 0.0
    return max(
        count_position_shift(snum(m, "home"), snum(m, "match_id")),
        count_position_shift(snum(m, "away"), snum(m, "match_id")),
    ) * 0.20


def probability_context_delta(sid: str, m: Dict[str, str]) -> float:
    imbalance = fnum(m, "matchup_imbalance_index")
    if sid in ("S01_favorite_early_break_open", "S07_late_chase_open_game"):
        return imbalance * 0.05
    return 0.0


def score_family_for(sid: str, scenarios: List[Dict[str, Any]]) -> str:
    for s in scenarios:
        if s["scenario_id"] == sid:
            return ";".join(s.get("effects", {}).get("score_family", []))
    return ""


def htft_bias_for(sid: str, scenarios: List[Dict[str, Any]]) -> str:
    for s in scenarios:
        if s["scenario_id"] == sid:
            return ";".join(s.get("effects", {}).get("htft_bias", []))
    return ""


def collect_matchups() -> List[Dict[str, str]]:
    matchups = read_csv(TEAM_DB / "tactical_matchup_matrix.csv")
    if matchups:
        return matchups
    fixtures = read_csv(TEAM_DB / "team_formation_matchups.csv")
    profiles = {snum(r, "team"): r for r in read_csv(TEAM_DB / "team_tactical_profile.csv")}
    out: List[Dict[str, str]] = []
    for fx in fixtures:
        home, away = snum(fx, "home"), snum(fx, "away")
        if not home or not away:
            continue
        hp, ap = profiles.get(home, {}), profiles.get(away, {})
        out.append({
            "match_id": snum(fx, "match_id"),
            "home": home,
            "away": away,
            "home_breakthrough_score": "0.35",
            "away_breakthrough_score": "0.15",
            "matchup_imbalance_index": "0.40",
            "home_transition_edge": snum(hp, "transition_attack", "0.2"),
            "away_transition_edge": snum(ap, "transition_attack", "0.1"),
            "home_set_piece_edge": snum(hp, "set_piece_attack", "0.1"),
            "away_set_piece_edge": snum(ap, "set_piece_attack", "0.05"),
            "home_flank_edge": snum(hp, "attack_width", "0.2"),
            "away_flank_edge": snum(ap, "attack_width", "0.1"),
            "home_press_trap_edge": "0.1",
            "away_press_trap_edge": "0.05",
            "data_confidence": "0.45",
        })
    return out


def main() -> None:
    scenarios = read_json(EVENTFLOW_DB / "scenario_library.json", [])
    scenario_names = {s["scenario_id"]: s["name"] for s in scenarios}
    profiles = {snum(r, "team"): r for r in read_csv(TEAM_DB / "team_tactical_profile.csv")}
    matchups = collect_matchups()
    out: List[Dict[str, Any]] = []
    now = datetime.now(timezone.utc).isoformat()

    for m in matchups:
        home, away = snum(m, "home"), snum(m, "away")
        mid = snum(m, "match_id")
        hp, ap = profiles.get(home, {}), profiles.get(away, {})
        fused_delta, fused_evidence, _ = fused_adjustments(mid)
        s08_tac, s08_trigger = s08_tactical_delta(mid, hp, ap, fused_delta.get(S08_ID, 0.0))
        rows: List[Dict[str, Any]] = []
        for s in scenarios:
            sid = s["scenario_id"]
            base_w = 0.10
            tac_d = tactical_component(sid, m, hp, ap)
            if sid == S08_ID:
                tac_d = s08_tac
            ply_d = player_component(sid, m)
            src_d = fused_delta.get(sid, 0.0)
            prob_d = probability_context_delta(sid, m)
            raw = max(0.0, base_w + tac_d + ply_d + src_d + prob_d)
            ev_parts = fused_evidence.get(sid, [])
            if sid == S08_ID:
                trigger = s08_trigger if s08_tac > 0 or src_d > 0 else s08_trigger
            elif ev_parts:
                trigger = "matchup+fused_evidence"
            else:
                trigger = "auto_matchup_features"
            rows.append({
                "match_id": mid,
                "home": home,
                "away": away,
                "scenario_id": sid,
                "scenario_name": scenario_names[sid],
                "raw_base_weight": round(base_w, 4),
                "raw_tactical_delta": round(tac_d, 4),
                "raw_player_delta": round(ply_d, 4),
                "raw_source_delta": round(src_d, 4),
                "raw_probability_context_delta": round(prob_d, 4),
                "raw_total_score": round(raw, 4),
                "normalized_weight": 0.0,
                "base_weight": round(base_w, 4),
                "tactical_delta": round(tac_d, 4),
                "player_delta": round(ply_d, 4),
                "source_delta": round(src_d, 4),
                "probability_context_delta": round(prob_d, 4),
                "weight": raw,
                "final_weight": 0.0,
                "home_lambda_delta": 0.0,
                "away_lambda_delta": 0.0,
                "variance_delta": 0.0,
                "over25_delta": 0.0,
                "btts_delta": 0.0,
                "htft_bias": htft_bias_for(sid, scenarios),
                "htft_bias_semantic": semantic_patterns_for(sid),
                "score_family": score_family_for(sid, scenarios),
                "triggered_by": trigger,
                "evidence_summary": " | ".join(ev_parts[:3]) if ev_parts else "",
                "data_confidence": min(
                    fnum(m, "data_confidence", 0.5),
                    fnum(hp, "data_confidence", 0.5),
                    fnum(ap, "data_confidence", 0.5),
                ),
                "generated_at": now,
            })
        normalize_weights(rows, "weight")
        for r in rows:
            r["normalized_weight"] = r["weight"]
            r["final_weight"] = r["weight"]
        out.extend(rows)

    write_csv(EVENTFLOW_DB / "eventflow_scenario_weights.csv", out)
    n_matches = len({(snum(r, "match_id"), snum(r, "home"), snum(r, "away")) for r in out})
    print(f"wrote {len(out)} scenario weights ({n_matches} matches × {len(scenarios)} scenarios)")


if __name__ == "__main__":
    main()
