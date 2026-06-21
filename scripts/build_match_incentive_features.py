#!/usr/bin/env python3
"""Build per-match runtime incentive features from advancement path snapshot."""
from __future__ import annotations

import argparse
from pathlib import Path

from group_state_common import (
    ROOT,
    build_standings,
    classify_path_state,
    kickoff_utc_from_mapping_row,
    parse_cutoff,
    pre_kickoff_cutoff,
    read_csv,
    remaining_group_matches,
    write_csv,
)
from competition_state_engine import evaluate_team_state

OUT_PHASE = ROOT / "outputs" / "phase06_group_state"
OUT_STAGING = ROOT / "database" / "eventflow" / "staging"
MAPPING = ROOT / "database" / "competition" / "wc2026_match_id_mapping.csv"

INCENTIVE_FIELDS = [
    "snapshot_id", "match_id", "as_of_utc", "kickoff_utc", "home", "away",
    "home_points", "away_points", "home_rank", "away_rank",
    "home_path_state", "away_path_state", "home_must_win", "away_must_win",
    "home_state_reason_code", "away_state_reason_code",
    "home_draw_acceptance", "away_draw_acceptance",
    "home_goal_diff_chase", "away_goal_diff_chase",
    "home_rotation_risk", "away_rotation_risk",
    "mutual_draw_risk", "late_chaos_risk", "third_place_pressure_index",
    "top_slot_chase_index", "confidence", "notes",
]


def path_lookup(paths: list[dict], team: str) -> dict:
    for p in paths:
        if p["team"] == team:
            return p
    return {}


def standings_for_cutoff(cutoff) -> list[dict]:
    rows, _, _ = build_standings(cutoff)
    return [
        {
            "group": r["group"],
            "rank": int(r["rank"]),
            "team": r["team"],
            "played": int(r["played"]),
            "wins": int(r["wins"]),
            "draws": int(r["draws"]),
            "losses": int(r["losses"]),
            "points": int(r["points"]),
            "gd": int(r["gd"]),
            "gf": int(r["gf"]),
        }
        for r in rows
    ]


def build_match_row(
    snap: str,
    match: dict,
    paths: list[dict],
) -> dict | None:
    home, away = match["home_team"], match["away_team"]
    group = match["group"]
    round_num = int(match.get("round", 0) or 0)
    kickoff = kickoff_utc_from_mapping_row(match)
    if kickoff is None:
        return None
    match_cutoff = pre_kickoff_cutoff(kickoff)
    standings = standings_for_cutoff(match_cutoff)
    remaining = remaining_group_matches(match_cutoff)

    hp = path_lookup(paths, home)
    ap = path_lookup(paths, away)
    home_rank = int(hp.get("current_rank") or next(
        (r["rank"] for r in standings if r["team"] == home and r["group"] == group), 4
    ))
    away_rank = int(ap.get("current_rank") or next(
        (r["rank"] for r in standings if r["team"] == away and r["group"] == group), 4
    ))

    h_detail = evaluate_team_state(
        home, group, standings, match_cutoff, round_num=round_num, remaining=remaining,
    )
    a_detail = evaluate_team_state(
        away, group, standings, match_cutoff, round_num=round_num, remaining=remaining,
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
        f"as_of={match_cutoff.strftime('%Y-%m-%dT%H:%M:%SZ')}; fusion_effect=eventflow_delta_only"
    )

    return {
        "snapshot_id": snap,
        "match_id": match["internal_match_id"],
        "as_of_utc": match_cutoff.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "kickoff_utc": kickoff.strftime("%Y-%m-%dT%H:%M:%SZ"),
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
        "home_state_reason_code": h_detail["state_reason_code"],
        "away_state_reason_code": a_detail["state_reason_code"],
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

    global_cutoff = parse_cutoff(args.source_cutoff_time)
    paths = read_csv(args.out_dir / "advancement_path_snapshot.csv")
    paths = [p for p in paths if p.get("snapshot_id", args.snapshot_id) == args.snapshot_id] or paths

    mapping = read_csv(MAPPING)
    targets = [
        m for m in mapping
        if m.get("round") == args.round
        and (not args.match_id or m["internal_match_id"] == args.match_id)
    ]

    out: list[dict] = []
    for m in targets:
        row = build_match_row(args.snapshot_id, m, paths)
        if row:
            out.append(row)

    write_csv(args.out_dir / "match_incentive_features_runtime.csv", INCENTIVE_FIELDS, out)
    write_csv(OUT_STAGING / "match_incentive_features_runtime.csv", INCENTIVE_FIELDS, out)
    print(f"Wrote {len(out)} per-match incentive rows (round={args.round}, independent pre-kickoff snapshots)")


if __name__ == "__main__":
    main()
