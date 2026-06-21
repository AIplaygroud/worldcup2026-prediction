#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build EGCI v2 features from real match events timeline."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from eventflow_common import read_csv, snum, write_csv
from v37_common import FEATURE_TABLES, NORMALIZED_TABLES, V37_AUDIT, clip, ensure_v37_dirs, fnum

EGCI_V2_FIELDS = [
    "match_id",
    "first_goal_minute",
    "first_goal_team",
    "first_goal_side",
    "second_goal_minute",
    "second_goal_team",
    "half_time_score",
    "goal_timeline_count",
    "early_goal_present",
    "second_goal_within_15min",
    "red_card_before_60",
    "trailing_team_chase_pressure",
    "favorite_acg_at_goal",
    "early_goal_cascade_index_v2",
    "egci_v2_quality",
    "egci_v2_source",
]


def _goal_events(events: list[dict]) -> list[dict]:
    return sorted(
        [
            e for e in events
            if snum(e, "event_type").lower() in ("goal", "own_goal", "penalty_goal")
            and snum(e, "minute") != ""
        ],
        key=lambda e: fnum(e, "minute"),
    )


def _quality(goals: list[dict], events: list[dict]) -> tuple[str, str]:
    if len(goals) >= 2:
        return "real", "match_events"
    if len(goals) == 1:
        return "partial", "match_events_partial"
    if events:
        return "proxy", "tactical_proxy"
    return "missing", "none"


def compute_egci_v2_row(
    match_id: str,
    match_row: dict,
    events: list[dict],
    gpi_rows: list[dict],
    egci_v1_row: dict,
    acg_v2_rows: list[dict],
) -> dict[str, str]:
    goals = _goal_events(events)
    home = snum(match_row, "home_team")
    away = snum(match_row, "away_team")

    first = goals[0] if goals else {}
    second = goals[1] if len(goals) > 1 else {}
    first_min = snum(first, "minute")
    first_team = snum(first, "team")
    first_side = "home" if first_team == home else "away" if first_team == away else ""
    second_min = snum(second, "minute")
    second_team = snum(second, "team")

    ht_score = ""
    if snum(match_row, "home_ht_score") and snum(match_row, "away_ht_score"):
        ht_score = f"{match_row['home_ht_score']}-{match_row['away_ht_score']}"

    early = bool(first_min) and float(first_min) <= 25
    second_within_15 = False
    if first_min and second_min:
        second_within_15 = float(second_min) - float(first_min) <= 15

    reds = [
        e for e in events
        if snum(e, "event_type").lower() in ("red_card", "second_yellow")
        and fnum(e, "minute") <= 60
    ]

    chase = 0.45
    for g in gpi_rows:
        chase = max(chase, fnum(g, "group_pressure_index"))

    fav_team = snum(egci_v1_row, "favorite") or (home if fnum(match_row, "home_strength_rating", 0) else home)
    acg_fav = next((r for r in acg_v2_rows if r.get("team") == fav_team), {})
    fav_acg = fnum(acg_fav, "acg_v2", fnum(egci_v1_row, "favorite_early_goal_profile", 0.5))

    egci_v2 = clip(
        0.30 * (1.0 if early else 0.0)
        + 0.25 * (1.0 if second_within_15 else 0.0)
        + 0.20 * chase
        + 0.15 * fav_acg
        + 0.10 * (1.0 if reds else 0.0),
        0.0,
        1.0,
    )
    if not goals and egci_v1_row:
        egci_v2 = clip(fnum(egci_v1_row, "early_goal_cascade_index", egci_v2), 0, 1)

    quality, source = _quality(goals, events)

    return {
        "match_id": match_id,
        "first_goal_minute": first_min,
        "first_goal_team": first_team,
        "first_goal_side": first_side,
        "second_goal_minute": second_min,
        "second_goal_team": second_team,
        "half_time_score": ht_score,
        "goal_timeline_count": str(len(goals)),
        "early_goal_present": str(early).lower(),
        "second_goal_within_15min": str(second_within_15).lower(),
        "red_card_before_60": str(bool(reds)).lower(),
        "trailing_team_chase_pressure": f"{chase:.4f}",
        "favorite_acg_at_goal": f"{fav_acg:.4f}",
        "early_goal_cascade_index_v2": f"{egci_v2:.4f}",
        "egci_v2_quality": quality,
        "egci_v2_source": source,
    }


def build_egci_v2(match_filter: str = "") -> int:
    ensure_v37_dirs()
    matches = {r["match_id"]: r for r in read_csv(NORMALIZED_TABLES["matches"])}
    events_all = read_csv(NORMALIZED_TABLES["match_events"])
    gpi_all = read_csv(FEATURE_TABLES["group_pressure"])
    egci_v1 = {r["match_id"]: r for r in read_csv(FEATURE_TABLES["early_goal_cascade"])}
    acg_v2_all = read_csv(FEATURE_TABLES["acg_v2"]) if FEATURE_TABLES["acg_v2"].exists() else []

    mids = sorted(matches.keys())
    if match_filter:
        mids = [m for m in mids if m == match_filter]

    out: list[dict[str, str]] = []
    for mid in mids:
        ev = [e for e in events_all if e["match_id"] == mid]
        gpi = [g for g in gpi_all if g["match_id"] == mid]
        acg = [a for a in acg_v2_all if a["match_id"] == mid]
        out.append(compute_egci_v2_row(mid, matches[mid], ev, gpi, egci_v1.get(mid, {}), acg))

    write_csv(FEATURE_TABLES["egci_v2"], out, EGCI_V2_FIELDS)
    (V37_AUDIT / "egci_v2_build_log.json").write_text(
        json.dumps({"built_at": datetime.now(timezone.utc).isoformat(), "rows": len(out)}, indent=2),
        encoding="utf-8",
    )
    return len(out)


def main() -> None:
    ap = argparse.ArgumentParser(description="Build EGCI v2 features")
    ap.add_argument("--match-id", default="")
    args = ap.parse_args()
    n = build_egci_v2(args.match_id)
    print(f"EGCI v2: {n} rows -> {FEATURE_TABLES['egci_v2']}")


if __name__ == "__main__":
    main()
