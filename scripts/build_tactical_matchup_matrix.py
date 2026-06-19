#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build tactical matchup matrix for every match.

Inputs:
- database/team_style/processed/team_tactical_profile.csv
- database/team_style/processed/team_formation_matchups.csv

Output:
- database/team_style/processed/tactical_matchup_matrix.csv
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

from eventflow_common import TEAM_DB, read_csv, write_csv, fnum, snum, clip


def breakthrough(att: Dict[str, str], deff: Dict[str, str]) -> float:
    # Can this team break the opponent shape?
    return (
        0.35 * fnum(att, "break_low_block_score")
        + 0.20 * fnum(att, "central_progression")
        + 0.18 * fnum(att, "attack_width")
        + 0.15 * fnum(att, "set_piece_attack")
        + 0.12 * fnum(att, "transition_attack")
        - 0.30 * fnum(deff, "defend_pressure_score")
        - 0.18 * fnum(deff, "low_block_quality")
    )


def control(att: Dict[str, str], deff: Dict[str, str]) -> float:
    return 0.40 * fnum(att, "central_progression") + 0.25 * fnum(att, "rest_defense_quality") + 0.20 * fnum(att, "defend_pressure_score") - 0.15 * fnum(deff, "transition_attack")


def path_summary(att: Dict[str, str], deff: Dict[str, str]) -> str:
    parts = []
    if fnum(att, "attack_width") - fnum(deff, "low_block_quality") > 0.25:
        parts.append("边路宽度/套边制造入口")
    if fnum(att, "central_progression") > 0.35:
        parts.append("中路/肋部推进")
    if fnum(att, "transition_attack") + fnum(deff, "high_line_risk") > 0.50:
        parts.append("反击冲身后")
    if fnum(att, "set_piece_attack") - fnum(deff, "set_piece_defense") > 0.30:
        parts.append("定位球破局")
    return "；".join(parts) or "无明显单点破阵路径"


def survival_summary(deff: Dict[str, str], att: Dict[str, str]) -> str:
    parts = []
    if fnum(deff, "low_block_quality") > 0.25:
        parts.append("低位密度压缩禁区")
    if fnum(deff, "rest_defense_quality") > 0.25:
        parts.append("反抢/防反保护较好")
    if fnum(att, "attack_width") < 0:
        parts.append("可诱导对手无效传中")
    return "；".join(parts) or "需要依赖门将/个人防守质量"


def main() -> None:
    profiles = {snum(r, "team"): r for r in read_csv(TEAM_DB / "team_tactical_profile.csv")}
    fixtures = read_csv(TEAM_DB / "team_formation_matchups.csv")
    out: List[Dict[str, Any]] = []
    for fx in fixtures:
        home = snum(fx, "home")
        away = snum(fx, "away")
        hp = profiles.get(home, {})
        ap = profiles.get(away, {})
        hb = breakthrough(hp, ap)
        ab = breakthrough(ap, hp)
        hc = control(hp, ap)
        ac = control(ap, hp)
        ht = fnum(hp, "transition_attack") + fnum(ap, "high_line_risk")
        at = fnum(ap, "transition_attack") + fnum(hp, "high_line_risk")
        hs = fnum(hp, "set_piece_attack") - fnum(ap, "set_piece_defense")
        as_ = fnum(ap, "set_piece_attack") - fnum(hp, "set_piece_defense")
        hf = fnum(hp, "attack_width") - 0.5 * fnum(ap, "low_block_quality")
        af = fnum(ap, "attack_width") - 0.5 * fnum(hp, "low_block_quality")
        hcent = fnum(hp, "central_progression") - 0.5 * fnum(ap, "defend_pressure_score")
        acent = fnum(ap, "central_progression") - 0.5 * fnum(hp, "defend_pressure_score")
        hpress = (1 if snum(hp,"pressing_height") == "高位压迫" else 0) + fnum(ap, "collapse_risk")
        apress = (1 if snum(ap,"pressing_height") == "高位压迫" else 0) + fnum(hp, "collapse_risk")
        imbalance = abs(hb - ab) + 0.35 * abs(hc - ac) + 0.20 * abs(ht - at)
        out.append({
            "match_id": snum(fx, "match_id"),
            "home": home,
            "away": away,
            "home_breakthrough_score": hb,
            "away_breakthrough_score": ab,
            "home_control_score": hc,
            "away_control_score": ac,
            "home_transition_edge": ht,
            "away_transition_edge": at,
            "home_set_piece_edge": hs,
            "away_set_piece_edge": as_,
            "home_flank_edge": hf,
            "away_flank_edge": af,
            "home_central_edge": hcent,
            "away_central_edge": acent,
            "home_press_trap_edge": hpress,
            "away_press_trap_edge": apress,
            "home_shape_countered_by_away": "yes" if ab - hb > 0.45 else "no",
            "away_shape_countered_by_home": "yes" if hb - ab > 0.45 else "no",
            "matchup_imbalance_index": imbalance,
            "likely_breakthrough_path_home": path_summary(hp, ap),
            "likely_breakthrough_path_away": path_summary(ap, hp),
            "likely_defensive_survival_path_home": survival_summary(hp, ap),
            "likely_defensive_survival_path_away": survival_summary(ap, hp),
            "data_confidence": min(fnum(hp, "data_confidence", 0.5), fnum(ap, "data_confidence", 0.5), fnum(fx, "confidence", 0.55)),
        })
    write_csv(TEAM_DB / "tactical_matchup_matrix.csv", out)
    print(f"wrote {len(out)} tactical matchup rows")


if __name__ == "__main__":
    main()
