#!/usr/bin/env python3
"""Build advancement path snapshot from live group standings."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from group_state_common import (
    ROOT,
    classify_path_state,
    parse_cutoff,
    read_csv,
    remaining_group_matches,
    write_csv,
)

OUT_PHASE = ROOT / "outputs" / "phase06_group_state"
OUT_DB = ROOT / "database" / "competition"

PATH_FIELDS = [
    "snapshot_id", "team", "group", "current_rank", "points", "gd", "gf",
    "remaining_matches", "can_finish_top1", "can_finish_top2", "can_finish_top3",
    "can_be_eliminated", "clinched_top2", "clinched_any_path", "eliminated",
    "third_place_viability", "path_confidence", "path_state", "path_notes",
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot-id", required=True)
    ap.add_argument("--source-cutoff-time", required=True)
    ap.add_argument("--standings", type=Path, default=OUT_PHASE / "live_group_standings.csv")
    ap.add_argument("--out-dir", type=Path, default=OUT_PHASE)
    args = ap.parse_args()

    cutoff = parse_cutoff(args.source_cutoff_time)
    rows = read_csv(args.standings)
    rows = [r for r in rows if r.get("snapshot_id") == args.snapshot_id]
    if not rows:
        rows = read_csv(args.standings)

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
        for r in rows
    ]
    remaining = remaining_group_matches(cutoff)

    out: list[dict] = []
    for r in standings:
        team, group = r["team"], r["group"]
        info = classify_path_state(team, group, r["rank"], standings, remaining.get(group, []))
        notes = (
            f"{info['path_state']}; qual_secure={info.get('qualification_secure_prob', 0):.2f}; "
            f"rem={info['remaining_matches']}"
        )
        out.append({
            "snapshot_id": args.snapshot_id,
            "team": team,
            "group": group,
            "current_rank": info["current_rank"],
            "points": info["points"],
            "gd": info["gd"],
            "gf": info["gf"],
            "remaining_matches": info["remaining_matches"],
            "can_finish_top1": str(info["can_finish_top1"]).lower(),
            "can_finish_top2": str(info["can_finish_top2"]).lower(),
            "can_finish_top3": str(info["can_finish_top3"]).lower(),
            "can_be_eliminated": str(info["can_be_eliminated"]).lower(),
            "clinched_top2": str(info["clinched_top2"]).lower(),
            "clinched_any_path": str(info["clinched_any_path"]).lower(),
            "eliminated": str(info["eliminated"]).lower(),
            "third_place_viability": info["third_place_viability"],
            "path_confidence": info["path_confidence"],
            "path_state": info["path_state"],
            "path_notes": notes,
        })

    write_csv(args.out_dir / "advancement_path_snapshot.csv", PATH_FIELDS, out)
    write_csv(OUT_DB / "advancement_path_snapshot.csv", PATH_FIELDS, out)
    print(f"Wrote {len(out)} advancement path rows for {args.snapshot_id}")


if __name__ == "__main__":
    main()
