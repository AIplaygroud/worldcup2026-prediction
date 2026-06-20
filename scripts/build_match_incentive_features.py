#!/usr/bin/env python3
"""Build per-match runtime incentive features from advancement path snapshot."""
from __future__ import annotations

import argparse
from pathlib import Path

from group_state_common import ROOT, classify_path_state, parse_cutoff, read_csv, remaining_group_matches, write_csv

OUT_PHASE = ROOT / "outputs" / "phase06_group_state"
OUT_STAGING = ROOT / "database" / "eventflow" / "staging"
MAPPING = ROOT / "database" / "competition" / "wc2026_match_id_mapping.csv"

INCENTIVE_FIELDS = [
    "snapshot_id", "match_id", "home", "away", "home_points", "away_points",
    "home_rank", "away_rank", "home_path_state", "away_path_state",
    "home_must_win", "away_must_win", "home_draw_acceptance", "away_draw_acceptance",
    "home_goal_diff_chase", "away_goal_diff_chase", "home_rotation_risk", "away_rotation_risk",
    "mutual_draw_risk", "late_chaos_risk", "third_place_pressure_index",
    "top_slot_chase_index", "confidence", "notes",
]


def path_lookup(paths: list[dict], team: str) -> dict:
    for p in paths:
        if p["team"] == team:
            return p
    return {}


def build_match_row(
    snap: str,
    match: dict,
    paths: list[dict],
    standings: list[dict],
    remaining: dict,
) -> dict:
    home, away = match["home_team"], match["away_team"]
    group = match["group"]
    hp = path_lookup(paths, home)
    ap = path_lookup(paths, away)

    h_detail = classify_path_state(
        home, group, int(hp.get("current_rank", 4)), standings, remaining.get(group, [])
    )
    a_detail = classify_path_state(
        away, group, int(ap.get("current_rank", 4)), standings, remaining.get(group, [])
    )

    mutual_draw = (
        h_detail["draw_acceptance"] >= 0.5
        and a_detail["draw_acceptance"] >= 0.5
        and h_detail["points"] == a_detail["points"] == 4
    )
    late_chaos = max(
        0.0,
        (1.0 - h_detail["draw_acceptance"]) * 0.5 + (1.0 - a_detail["draw_acceptance"]) * 0.5,
    )
    if "must_win" in h_detail["path_state"] or "must_win" in a_detail["path_state"]:
        late_chaos = min(1.0, late_chaos + 0.25)

    third_pressure = 0.0
    if h_detail["path_state"] == "third_place_bubble" or a_detail["path_state"] == "third_place_bubble":
        third_pressure = 0.55
    if h_detail["path_state"] == "third_place_bubble" and a_detail["path_state"] == "third_place_bubble":
        third_pressure = 0.72

    top_chase = 0.0
    if h_detail["path_state"] in ("top_slot_chase", "control_destiny"):
        top_chase += 0.4
    if a_detail["path_state"] in ("top_slot_chase", "control_destiny"):
        top_chase += 0.4

    notes = (
        f"{home}={h_detail['path_state']}; {away}={a_detail['path_state']}; "
        f"fusion_effect=eventflow_delta_only"
    )

    return {
        "snapshot_id": snap,
        "match_id": match["internal_match_id"],
        "home": home,
        "away": away,
        "home_points": h_detail["points"],
        "away_points": a_detail["points"],
        "home_rank": h_detail["current_rank"],
        "away_rank": a_detail["current_rank"],
        "home_path_state": h_detail["path_state"],
        "away_path_state": a_detail["path_state"],
        "home_must_win": str("must_win" in h_detail["path_state"]).lower(),
        "away_must_win": str("must_win" in a_detail["path_state"]).lower(),
        "home_draw_acceptance": h_detail["draw_acceptance"],
        "away_draw_acceptance": a_detail["draw_acceptance"],
        "home_goal_diff_chase": h_detail["goal_diff_chase"],
        "away_goal_diff_chase": a_detail["goal_diff_chase"],
        "home_rotation_risk": h_detail["rotation_risk"],
        "away_rotation_risk": a_detail["rotation_risk"],
        "mutual_draw_risk": round(0.35 if mutual_draw else 0.1, 3),
        "late_chaos_risk": round(late_chaos, 3),
        "third_place_pressure_index": round(third_pressure, 3),
        "top_slot_chase_index": round(min(1.0, top_chase), 3),
        "confidence": round(min(h_detail["path_confidence"], a_detail["path_confidence"]), 3),
        "notes": notes,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot-id", required=True)
    ap.add_argument("--source-cutoff-time", required=True)
    ap.add_argument("--match-id", default="")
    ap.add_argument("--round", default="2")
    ap.add_argument("--out-dir", type=Path, default=OUT_PHASE)
    args = ap.parse_args()

    cutoff = parse_cutoff(args.source_cutoff_time)
    paths = read_csv(args.out_dir / "advancement_path_snapshot.csv")
    paths = [p for p in paths if p.get("snapshot_id", args.snapshot_id) == args.snapshot_id] or paths

    standings_rows = read_csv(args.out_dir / "live_group_standings.csv")
    standings = [
        {
            "group": r["group"],
            "rank": int(r["rank"]),
            "team": r["team"],
            "played": int(r["played"]),
            "points": int(r["points"]),
            "gd": int(r["gd"]),
            "gf": int(r["gf"]),
        }
        for r in standings_rows
        if r.get("snapshot_id", args.snapshot_id) == args.snapshot_id or "snapshot_id" not in r
    ]
    remaining = remaining_group_matches(cutoff)
    mapping = read_csv(MAPPING)

    targets = [
        m for m in mapping
        if m.get("round") == args.round
        and (not args.match_id or m["internal_match_id"] == args.match_id)
    ]

    out = [build_match_row(args.snapshot_id, m, paths, standings, remaining) for m in targets]
    write_csv(args.out_dir / "match_incentive_features_runtime.csv", INCENTIVE_FIELDS, out)
    write_csv(OUT_STAGING / "match_incentive_features_runtime.csv", INCENTIVE_FIELDS, out)
    print(f"Wrote {len(out)} match incentive rows (round={args.round})")


if __name__ == "__main__":
    main()
