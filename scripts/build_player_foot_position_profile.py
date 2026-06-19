#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build player preferred-foot, position, and role profiles.

Inputs:
- database/player_style/raw/raw_player_master.csv
- database/player_style/raw/raw_player_league_stats.csv

Outputs:
- database/player_style/processed/player_foot_position_profile.csv
- database/player_style/processed/player_league_style_profile.csv
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Dict, List

from eventflow_common import PLAYER_DB, read_csv, write_csv, fnum, snum, normalize_weights, add_zscores, safe_div

RAW = Path(__file__).resolve().parents[1] / "database" / "player_style" / "raw"


def infer_role_tags(r: Dict[str, Any]) -> List[str]:
    tags: List[str] = []
    pos = snum(r, "primary_position").upper()
    foot = snum(r, "preferred_foot").lower()
    secondary = snum(r, "secondary_positions").lower()
    if "RW" in pos or "LW" in pos or "wing" in secondary:
        tags.append("边路爆点")
    if "AM" in pos or "10" in secondary:
        tags.append("肋部组织者")
    if "ST" in pos or "CF" in pos:
        tags.append("禁区终结点")
    if "DM" in pos or "CM" in pos:
        tags.append("中场连接点")
    if "CB" in pos:
        tags.append("中卫防守核心")
    if "LB" in pos or "RB" in pos or "WB" in pos:
        tags.append("边路支撑点")
    if foot in ("left", "左脚"):
        tags.append("左脚倾向")
    elif foot in ("right", "右脚"):
        tags.append("右脚倾向")
    elif foot in ("both", "双足"):
        tags.append("双足")
    return tags or ["待标注"]


def role_family(position: str) -> str:
    p = (position or "").upper()
    if any(x in p for x in ["ST", "CF", "FW"]):
        return "forward"
    if any(x in p for x in ["LW", "RW", "LM", "RM", "W"]):
        return "wide_attacker"
    if any(x in p for x in ["AM", "CM", "DM", "MF"]):
        return "midfielder"
    if any(x in p for x in ["LB", "RB", "WB", "CB", "DF"]):
        return "defender"
    if "GK" in p:
        return "goalkeeper"
    return "unknown"


def build_foot_position_profile() -> List[Dict[str, Any]]:
    rows = read_csv(RAW / "raw_player_master.csv")
    out: List[Dict[str, Any]] = []
    for r in rows:
        player = snum(r, "player")
        if not player:
            continue
        foot = snum(r, "preferred_foot")
        primary = snum(r, "primary_position")
        secondary = snum(r, "secondary_positions")
        tags = infer_role_tags(r)
        two_footed = 1.0 if foot.lower() in {"both", "双足", "either"} else 0.35 if not foot else 0.15
        flex = min(1.0, 0.20 + 0.20 * len([x for x in secondary.replace(";", ",").split(",") if x.strip()]))
        out.append({
            "player_id": snum(r, "player_id") or player,
            "player": player,
            "team": snum(r, "team"),
            "club": snum(r, "club"),
            "primary_position": primary,
            "secondary_positions": secondary,
            "preferred_foot": foot or "unknown",
            "weak_foot_note": "manual_required" if not foot else "",
            "role_tags": ";".join(tags),
            "role_family": role_family(primary),
            "same_foot_side": "unknown",
            "inverted_role_possible": "yes" if ("LW" in primary.upper() and foot.lower() in {"right", "右脚"}) or ("RW" in primary.upper() and foot.lower() in {"left", "左脚"}) else "unknown",
            "two_footed_score": two_footed,
            "position_flexibility_score": flex,
            "profile_confidence": fnum(r, "confidence", 0.60),
            "source_urls": snum(r, "source_url"),
            "data_origin": snum(r, "source", "manual"),
            "source_url": snum(r, "source_url"),
            "is_estimated": snum(r, "is_estimated", "true"),
            "confidence": fnum(r, "confidence", 0.60),
            "last_updated": snum(r, "updated_at") or date.today().isoformat(),
            "updated_at": date.today().isoformat(),
        })
    return out


def build_league_style_profile() -> List[Dict[str, Any]]:
    rows = read_csv(RAW / "raw_player_league_stats.csv")
    # aggregate by player_id/player/team
    grouped: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for r in rows:
        key = snum(r, "player_id") or f"{snum(r,'player')}|{snum(r,'team')}"
        if snum(r, "player"):
            grouped[key].append(r)
    out: List[Dict[str, Any]] = []
    for key, rs in grouped.items():
        mins = sum(fnum(r, "minutes") for r in rs)
        if mins <= 0:
            mins = float(len(rs))
        def wm(col: str) -> float:
            return sum(fnum(r, col) * max(1.0, fnum(r, "minutes", 1.0)) for r in rs) / max(1.0, sum(max(1.0, fnum(r, "minutes", 1.0)) for r in rs))
        base = rs[-1]
        attack_level = 0.35 * wm("xg") + 0.25 * wm("shots90") + 0.25 * wm("touches_box90") + 0.15 * wm("goals")
        creation_level = 0.35 * wm("xa") + 0.25 * wm("key_passes90") + 0.20 * wm("through_balls90") + 0.20 * wm("progressive_passes90")
        transition_level = 0.45 * wm("progressive_carries90") + 0.25 * wm("successful_dribbles90") + 0.30 * wm("progressive_passes90")
        press_resistance = 0.45 * wm("successful_dribbles90") + 0.35 * wm("progressive_carries90") + 0.20 * wm("fouls_won90")
        defensive_workrate = 0.35 * wm("pressures90") + 0.30 * wm("tackles90") + 0.25 * wm("interceptions90") + 0.10 * wm("fouls_committed90")
        tags = []
        if attack_level > creation_level and attack_level > 0:
            tags.append("终结倾向")
        if creation_level >= attack_level and creation_level > 0:
            tags.append("创造倾向")
        if transition_level > 1:
            tags.append("转换推进")
        if press_resistance > 1:
            tags.append("抗压推进")
        if defensive_workrate > 1:
            tags.append("高参与防守")
        out.append({
            "player_id": key,
            "player": snum(base, "player"),
            "team": snum(base, "team"),
            "season_window": ";".join(sorted(set(snum(r, "season") for r in rs if snum(r, "season")))) or "unknown",
            "minutes_weighted": mins,
            "attack_level": attack_level,
            "creation_level": creation_level,
            "transition_level": transition_level,
            "press_resistance": press_resistance,
            "defensive_workrate": defensive_workrate,
            "aerial_level": wm("aerial_won90"),
            "set_piece_level": wm("crosses90") + 0.5 * wm("key_passes90"),
            "card_risk": wm("yellow_cards90") + 2.0 * wm("red_cards90") + 0.15 * wm("fouls_committed90"),
            "foul_draw_level": wm("fouls_won90"),
            "finishing_level": wm("goals") + wm("npxg"),
            "role_tags": ";".join(tags) or "待标注",
            "data_confidence": min(0.90, 0.45 + mins / 5000),
            "updated_at": date.today().isoformat(),
        })
    return out


def main() -> None:
    foot_rows = build_foot_position_profile()
    write_csv(PLAYER_DB / "player_foot_position_profile.csv", foot_rows)

    style_rows = build_league_style_profile()
    write_csv(PLAYER_DB / "player_league_style_profile.csv", style_rows)
    print(f"wrote {len(foot_rows)} player foot/position rows and {len(style_rows)} league style rows")


if __name__ == "__main__":
    main()
