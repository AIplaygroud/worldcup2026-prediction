#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build ACG v2 features with real/proxy quality separation."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from eventflow_common import read_csv, snum, write_csv
from v37_common import FEATURE_TABLES, NORMALIZED_TABLES, V37_AUDIT, clip, ensure_v37_dirs, fnum

ACG_V2_FIELDS = [
    "match_id",
    "team",
    "acg_v2",
    "shot_quality_score",
    "xg_real_available",
    "sot_real_available",
    "big_chance_real_available",
    "lineup_function_real_available",
    "creator_starting",
    "pace_outlet_starting",
    "central_target_starting",
    "set_piece_height_advantage",
    "conversion_proxy_ratio",
    "must_win_no_convert_v2",
    "acg_v2_quality",
    "acg_v2_source",
]


def _lineup_roles(lineups: list[dict], team: str) -> tuple[float, float, float, float, bool]:
    starters = [lu for lu in lineups if lu.get("team") == team and snum(lu, "is_starter") == "true"]
    if not starters:
        return 0.0, 0.0, 0.0, 0.0, False
    confirmed = any(snum(s, "lineup_status") == "confirmed" for s in starters)
    creators = sum(1 for s in starters if snum(s, "role_group") == "creator")
    pace = sum(1 for s in starters if snum(s, "role_group") == "wide_attacker")
    central = sum(1 for s in starters if snum(s, "role_group") in ("striker", "creator"))
    set_piece = sum(1 for s in starters if snum(s, "role_group") in ("striker", "creator", "wide_attacker"))
    n = max(len(starters), 1)
    return (
        clip(creators / n, 0, 1),
        clip(pace / n, 0, 1),
        clip(central / n, 0, 1),
        clip(set_piece / n, 0, 1),
        confirmed,
    )


def compute_acg_v2_row(
    acg_row: dict,
    stats_row: dict,
    recent_row: dict,
    lineups: list[dict],
    gpi_row: dict,
) -> dict[str, str]:
    team = acg_row["team"]
    shots = fnum(stats_row, "shots") or fnum(recent_row, "shots_avg", 10)
    xg = fnum(stats_row, "xg") or fnum(recent_row, "xg_for_avg", 0)
    sot = fnum(stats_row, "shots_on_target") or fnum(recent_row, "sot_avg", 0)
    bc = fnum(stats_row, "big_chances") or fnum(recent_row, "big_chances_avg", 0)

    xg_real = fnum(stats_row, "xg") > 0 or (fnum(recent_row, "xg_for_avg") > 0 and snum(stats_row, "quality_flag") != "proxy")
    sot_real = fnum(stats_row, "shots_on_target") > 0 or fnum(recent_row, "sot_avg") > 0
    bc_real = fnum(stats_row, "big_chances") > 0 or fnum(recent_row, "big_chances_avg") > 0

    sot_rate = clip(sot / max(shots, 1), 0, 1) if shots else fnum(acg_row, "shot_on_target_rate")
    xg_per_shot = clip(xg / max(shots, 1), 0, 0.5) * 2 if shots and xg else fnum(acg_row, "xg_per_shot")
    shot_quality = clip(0.35 * clip(xg_per_shot, 0, 1) + 0.35 * sot_rate + 0.30 * clip(bc / 10, 0, 1), 0, 1)

    creator, pace, central, set_piece, lineup_real = _lineup_roles(lineups, team)
    proxy_ratio = 0.0
    source = "team_style_proxy"
    if not xg_real:
        proxy_ratio += 0.25
    if not sot_real:
        proxy_ratio += 0.15
    if not lineup_real:
        proxy_ratio += 0.25
    if xg_real or sot_real:
        source = "match_stats" if fnum(stats_row, "xg") else "team_recent_stats"

    acg_v2 = clip(0.55 * shot_quality + 0.25 * (creator + pace + central) / 3 + 0.20 * fnum(acg_row, "attack_conversion_gate", 0.5), 0, 1)
    acg_v2 = clip(acg_v2 - proxy_ratio * 0.12, 0, 1)

    if xg_real and sot_real and lineup_real:
        quality = "real"
    elif xg_real or sot_real or lineup_real:
        quality = "partial"
    elif proxy_ratio >= 0.5:
        quality = "proxy"
    else:
        quality = "proxy_guarded"

    must_win_v2 = (
        snum(gpi_row, "pressure_type") == "must_win"
        and acg_v2 < 0.42
        and quality in ("real", "partial", "proxy_guarded")
    )

    return {
        "match_id": acg_row["match_id"],
        "team": team,
        "acg_v2": f"{acg_v2:.4f}",
        "shot_quality_score": f"{shot_quality:.4f}",
        "xg_real_available": str(xg_real).lower(),
        "sot_real_available": str(sot_real).lower(),
        "big_chance_real_available": str(bc_real).lower(),
        "lineup_function_real_available": str(lineup_real).lower(),
        "creator_starting": f"{creator:.4f}",
        "pace_outlet_starting": f"{pace:.4f}",
        "central_target_starting": f"{central:.4f}",
        "set_piece_height_advantage": f"{set_piece:.4f}",
        "conversion_proxy_ratio": f"{proxy_ratio:.4f}",
        "must_win_no_convert_v2": str(must_win_v2).lower(),
        "acg_v2_quality": quality,
        "acg_v2_source": source,
    }


def build_acg_v2(match_filter: str = "") -> int:
    ensure_v37_dirs()
    acg_rows = read_csv(FEATURE_TABLES["attack_conversion"])
    stats_all = read_csv(NORMALIZED_TABLES["match_stats"])
    recent_all = read_csv(NORMALIZED_TABLES["team_recent_stats"])
    lineups_all = read_csv(NORMALIZED_TABLES["lineups"])
    gpi_all = read_csv(FEATURE_TABLES["group_pressure"])

    out: list[dict[str, str]] = []
    for acg in acg_rows:
        mid = acg["match_id"]
        if match_filter and mid != match_filter:
            continue
        team = acg["team"]
        st = next((s for s in stats_all if s["match_id"] == mid and s["team"] == team), {})
        rec = next((s for s in recent_all if s["match_id"] == mid and s["team"] == team), {})
        gpi = next((g for g in gpi_all if g["match_id"] == mid and g["team"] == team), {})
        lu = [x for x in lineups_all if x["match_id"] == mid]
        out.append(compute_acg_v2_row(acg, st, rec, lu, gpi))

    write_csv(FEATURE_TABLES["acg_v2"], out, ACG_V2_FIELDS)
    (V37_AUDIT / "acg_v2_build_log.json").write_text(
        json.dumps({"built_at": datetime.now(timezone.utc).isoformat(), "rows": len(out)}, indent=2),
        encoding="utf-8",
    )
    return len(out)


def main() -> None:
    ap = argparse.ArgumentParser(description="Build ACG v2 features")
    ap.add_argument("--match-id", default="")
    args = ap.parse_args()
    n = build_acg_v2(args.match_id)
    print(f"ACG v2: {n} rows -> {FEATURE_TABLES['acg_v2']}")


if __name__ == "__main__":
    main()
