#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compare players' league/normal roles with World Cup actual usage.

Input:
- database/player_style/raw/raw_worldcup_lineups_positions.csv
- database/player_style/processed/player_foot_position_profile.csv

Output:
- database/player_style/processed/player_worldcup_position_shift.csv
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List
from datetime import date

from eventflow_common import PLAYER_DB, read_csv, write_csv, fnum, snum, safe_div

RAW = Path(__file__).resolve().parents[1] / "database" / "player_style" / "raw"


def side_bias(r: Dict[str, str]) -> str:
    left = fnum(r, "touches_left")
    center = fnum(r, "touches_center")
    right = fnum(r, "touches_right")
    total = left + center + right
    if total <= 0:
        return "unknown"
    mx = max(left, center, right)
    if mx == left:
        return "left"
    if mx == right:
        return "right"
    return "center"


def shift_type(listed: str, primary: str, actual: str, side: str, foot: str) -> str:
    text = " ".join([listed, actual, side]).upper()
    primary_u = primary.upper()
    foot_l = foot.lower()
    if primary and primary_u not in text:
        return "role_or_position_changed"
    if (side == "left" and foot_l in {"right", "右脚"}) or (side == "right" and foot_l in {"left", "左脚"}):
        return "inverted_side_usage"
    if side in {"left", "right"}:
        return "same_lane_usage"
    return "stable_or_unknown"


def tactical_meaning(typ: str) -> str:
    return {
        "role_or_position_changed": "世界杯实际职责与联赛/常规位置不同，需降低历史标签直接迁移权重。",
        "inverted_side_usage": "逆足站位可能增加内切射门/肋部传球，也可能牵制对方边后卫内收。",
        "same_lane_usage": "顺足/同侧使用更可能提供传中、套边和宽度。",
        "stable_or_unknown": "暂无明显位置偏移信号。",
    }.get(typ, "待人工复核")


def main() -> None:
    master = {snum(r, "player_id") or snum(r, "player"): r for r in read_csv(PLAYER_DB / "player_foot_position_profile.csv")}
    rows = read_csv(RAW / "raw_worldcup_lineups_positions.csv")
    out: List[Dict[str, Any]] = []
    for r in rows:
        pid = snum(r, "player_id") or snum(r, "player")
        m = master.get(pid, {})
        side = snum(r, "side") or side_bias(r)
        typ = shift_type(
            snum(r, "position_listed") or snum(r, "listed_position"),
            snum(m, "primary_position"), snum(r, "actual_role"), side, snum(m, "preferred_foot"),
        )
        x_shift = fnum(r, "avg_x") - 50.0 if snum(r, "avg_x") else 0.0
        y_shift = fnum(r, "avg_y") - 50.0 if snum(r, "avg_y") else 0.0
        shift_score = min(1.0, abs(x_shift) / 50 * 0.35 + abs(y_shift) / 50 * 0.35 + (0.30 if typ != "stable_or_unknown" else 0.0))
        out.append({
            "player_id": pid,
            "player": snum(r, "player"),
            "team": snum(r, "team"),
            "match_id": snum(r, "match_id"),
            "opponent": snum(r, "opponent"),
            "listed_position": snum(r, "position_listed") or snum(r, "listed_position"),
            "actual_role": snum(r, "actual_role"),
            "league_primary_position": snum(m, "primary_position"),
            "side": side,
            "role_shift_type": typ,
            "x_shift": x_shift,
            "y_shift": y_shift,
            "touch_side_bias": side_bias(r),
            "inverted_usage": "yes" if typ == "inverted_side_usage" else "no",
            "position_shift_score": shift_score,
            "tactical_meaning": tactical_meaning(typ),
            "data_confidence": min(fnum(r, "confidence", 0.5), fnum(m, "profile_confidence", 0.5) or 0.5),
            "data_origin": snum(r, "source", "manual"),
            "source_url": snum(r, "source_url"),
            "is_estimated": snum(r, "is_estimated", "true"),
            "confidence": min(fnum(r, "confidence", 0.5), fnum(m, "profile_confidence", 0.5) or 0.5),
            "last_updated": date.today().isoformat(),
        })
    write_csv(PLAYER_DB / "player_worldcup_position_shift.csv", out)
    print(f"wrote {len(out)} position shift rows")


if __name__ == "__main__":
    main()
