#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build team tactical style and match-state response profiles.

Inputs:
- database/team_style/raw/raw_team_phase_metrics.csv
- database/team_style/raw/raw_match_state_response.csv

Outputs:
- database/team_style/processed/team_tactical_profile.csv
- database/team_style/processed/team_match_state_response.csv
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Dict, List

from eventflow_common import TEAM_DB, read_csv, write_csv, fnum, snum, safe_div, add_zscores

RAW = Path(__file__).resolve().parents[1] / "database" / "team_style" / "raw"


def style_label(metric: float, high: str, mid: str, low: str) -> str:
    if metric >= 0.33:
        return high
    if metric <= -0.33:
        return low
    return mid


def build_profile() -> List[Dict[str, Any]]:
    rows = read_csv(RAW / "raw_team_phase_metrics.csv")
    groups: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for r in rows:
        team = snum(r, "team")
        if team:
            groups[team].append(r)
    base_rows: List[Dict[str, Any]] = []
    for team, rs in groups.items():
        total_m = sum(max(1.0, fnum(r, "matches", 1.0)) for r in rs)
        def wm(col: str) -> float:
            return sum(fnum(r, col) * max(1.0, fnum(r, "matches", 1.0)) for r in rs) / total_m
        base_rows.append({
            "team": team,
            "period": ";".join(sorted(set(snum(r,"period") for r in rs if snum(r,"period")))) or "mixed",
            "matches": total_m,
            "formation_base": snum(rs[-1], "formation_base"),
            "possession_pct": wm("possession_pct"),
            "ppda": wm("ppda"),
            "high_turnovers90": wm("high_turnovers90"),
            "direct_attacks90": wm("direct_attacks90"),
            "fast_breaks90": wm("fast_breaks90"),
            "passes_per_sequence": wm("passes_per_sequence"),
            "field_tilt_pct": wm("field_tilt_pct"),
            "deep_completions90": wm("deep_completions90"),
            "box_entries90": wm("box_entries90"),
            "crosses90": wm("crosses90"),
            "cutbacks90": wm("cutbacks90"),
            "set_piece_xg90": wm("set_piece_xg90"),
            "xg90": wm("xg90"),
            "xga90": wm("xga90"),
            "shots90": wm("shots90"),
            "shots_against90": wm("shots_against90"),
            "confidence": min(0.92, sum(fnum(r, "confidence", 0.6) for r in rs) / max(1, len(rs))),
            "data_origin": snum(rs[-1], "source", "aggregated_metrics"),
            "source_url": snum(rs[-1], "source_url"),
            "is_estimated": snum(rs[-1], "is_estimated", "true"),
            "last_updated": snum(rs[-1], "updated_at") or date.today().isoformat(),
        })
    add_zscores(base_rows, ["possession_pct","ppda","high_turnovers90","direct_attacks90","fast_breaks90","passes_per_sequence","field_tilt_pct","box_entries90","crosses90","cutbacks90","set_piece_xg90","xg90","xga90","shots_against90"])
    out: List[Dict[str, Any]] = []
    for r in base_rows:
        # lower ppda means stronger press, hence negative z becomes higher pressing score
        pressing_score = -float(r.get("ppda_z", 0.0)) * 0.55 + float(r.get("high_turnovers90_z", 0.0)) * 0.45
        build_score = float(r.get("possession_pct_z", 0.0)) * 0.45 + float(r.get("passes_per_sequence_z", 0.0)) * 0.35 + float(r.get("field_tilt_pct_z", 0.0)) * 0.20
        width_score = float(r.get("crosses90_z", 0.0)) * 0.50 + float(r.get("cutbacks90_z", 0.0)) * 0.25 + float(r.get("box_entries90_z", 0.0)) * 0.25
        central_score = float(r.get("deep_completions90_z", 0.0)) * 0.45 + float(r.get("field_tilt_pct_z", 0.0)) * 0.35 + float(r.get("possession_pct_z", 0.0)) * 0.20
        transition = float(r.get("direct_attacks90_z", 0.0)) * 0.45 + float(r.get("fast_breaks90_z", 0.0)) * 0.55
        set_piece_attack = float(r.get("set_piece_xg90_z", 0.0))
        low_block = -float(r.get("xga90_z", 0.0)) * 0.55 - float(r.get("shots_against90_z", 0.0)) * 0.45
        high_line_risk = float(r.get("xga90_z", 0.0)) * 0.45 + float(r.get("shots_against90_z", 0.0)) * 0.35 + pressing_score * 0.20
        rest_defense = -high_line_risk
        chaos = abs(transition) * 0.20 + max(0, float(r.get("xg90_z", 0.0))) * 0.25 + max(0, float(r.get("xga90_z", 0.0))) * 0.25 + max(0, pressing_score) * 0.15 + max(0, width_score) * 0.15
        out.append({
            "team": r["team"],
            "period": r["period"],
            "matches": r["matches"],
            "formation_base": r["formation_base"],
            "pressing_height": style_label(pressing_score, "高位压迫", "中位压迫", "低位/被动"),
            "build_up_style": style_label(build_score, "控球推进", "混合推进", "直接打法"),
            "attack_width": width_score,
            "central_progression": central_score,
            "transition_attack": transition,
            "set_piece_attack": set_piece_attack,
            "set_piece_defense": low_block * 0.50,
            "low_block_quality": low_block,
            "high_line_risk": high_line_risk,
            "rest_defense_quality": rest_defense,
            "late_game_aggression": 0.0,
            "comeback_tendency": 0.0,
            "collapse_risk": max(0, high_line_risk) * 0.45 + max(0, -low_block) * 0.35 + max(0, chaos) * 0.20,
            "chaos_index": chaos,
            "break_low_block_score": 0.35 * central_score + 0.25 * width_score + 0.25 * set_piece_attack + 0.15 * build_score,
            "defend_pressure_score": 0.45 * low_block + 0.30 * rest_defense + 0.25 * (-float(r.get("xga90_z", 0.0))),
            "data_confidence": r["confidence"],
            "data_origin": r["data_origin"],
            "source_url": r["source_url"],
            "is_estimated": r["is_estimated"],
            "confidence": r["confidence"],
            "last_updated": r["last_updated"],
            "updated_at": date.today().isoformat(),
        })
    return out


def build_state_response() -> List[Dict[str, Any]]:
    rows = read_csv(RAW / "raw_match_state_response.csv")
    out: List[Dict[str, Any]] = []
    for r in rows:
        state = snum(r, "state") or "level"
        attack_delta = fnum(r, "xg_for90") - fnum(r, "goals_for") * 0.05
        defense_delta = fnum(r, "xg_against90") - fnum(r, "goals_against") * 0.05
        tempo_delta = fnum(r, "direct_attacks90") + 0.03 * fnum(r, "possession_pct") + fnum(r, "pressing_intensity")
        risk_delta = defense_delta + 0.5 * tempo_delta
        tags = []
        if state == "trailing" and fnum(r, "substitution_aggression") > 0.5:
            tags.append("落后敢压上")
        if state == "leading" and risk_delta < 0:
            tags.append("领先会收缩")
        if risk_delta > 1:
            tags.append("状态变化后比赛变开放")
        out.append({
            "team": snum(r, "team"),
            "period": snum(r, "period"),
            "state": state,
            "minutes": fnum(r, "minutes"),
            "attack_delta": attack_delta,
            "defense_delta": defense_delta,
            "tempo_delta": tempo_delta,
            "risk_delta": risk_delta,
            "substitution_aggression": fnum(r, "substitution_aggression"),
            "late_goal_for_rate": fnum(r, "goals_for") / max(1.0, fnum(r, "minutes")) * 90,
            "late_goal_against_rate": fnum(r, "goals_against") / max(1.0, fnum(r, "minutes")) * 90,
            "state_response_tags": ";".join(tags) or "待观察",
            "data_confidence": fnum(r, "confidence", 0.55),
            "updated_at": date.today().isoformat(),
        })
    return out


def main() -> None:
    profile = build_profile()
    write_csv(TEAM_DB / "team_tactical_profile.csv", profile)
    state = build_state_response()
    write_csv(TEAM_DB / "team_match_state_response.csv", state)
    print(f"wrote {len(profile)} tactical profile rows and {len(state)} state response rows")


if __name__ == "__main__":
    main()
