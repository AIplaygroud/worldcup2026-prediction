#!/usr/bin/env python3
"""Build live group standings and third-place rankings with cutoff-time guard."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from group_state_common import (
    ROOT,
    build_standings,
    parse_cutoff,
    read_csv,
    write_csv,
)

OUT_DB = ROOT / "database" / "competition"
OUT_PHASE = ROOT / "outputs" / "phase06_group_state"

STANDINGS_FIELDS = [
    "snapshot_id", "generated_at", "source_cutoff_time", "group", "rank", "team",
    "played", "wins", "draws", "losses", "gf", "ga", "gd", "points",
    "source", "result_rows_used", "is_provisional",
]

THIRD_FIELDS = [
    "snapshot_id", "rank_3rd", "group", "team", "points", "gd", "gf",
    "conduct_score", "fifa_rank", "third_place_status", "source_cutoff_time",
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-cutoff-time", required=True)
    ap.add_argument("--out-snapshot-id", required=True)
    ap.add_argument("--out-dir", type=Path, default=OUT_PHASE)
    args = ap.parse_args()

    cutoff = parse_cutoff(args.source_cutoff_time)
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    standings, third_rows, meta = build_standings(cutoff)

    snap = args.out_snapshot_id
    is_prov = any(r["played"] < 3 for r in standings)

    live_rows = []
    for r in standings:
        live_rows.append({
            "snapshot_id": snap,
            "generated_at": generated_at,
            "source_cutoff_time": cutoff.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "group": r["group"],
            "rank": r["rank"],
            "team": r["team"],
            "played": r["played"],
            "wins": r["wins"],
            "draws": r["draws"],
            "losses": r["losses"],
            "gf": r["gf"],
            "ga": r["ga"],
            "gd": r["gd"],
            "points": r["points"],
            "source": "wc2026_match_xg+fixtures",
            "result_rows_used": meta["result_rows_used"],
            "is_provisional": str(is_prov).lower(),
        })

    third_out = []
    for t in third_rows:
        third_out.append({
            "snapshot_id": snap,
            "rank_3rd": t["rank_3rd"],
            "group": t["group"],
            "team": t["team"],
            "points": t["points"],
            "gd": t["gd"],
            "gf": t["gf"],
            "conduct_score": t["conduct_score"],
            "fifa_rank": t["fifa_rank"],
            "third_place_status": t["third_place_status"],
            "source_cutoff_time": cutoff.strftime("%Y-%m-%dT%H:%M:%SZ"),
        })

    out_dir = args.out_dir
    write_csv(out_dir / "live_group_standings.csv", STANDINGS_FIELDS, live_rows)
    write_csv(out_dir / "third_place_rankings.csv", THIRD_FIELDS, third_out)
    write_csv(OUT_DB / "live_group_standings.csv", STANDINGS_FIELDS, live_rows)
    write_csv(OUT_DB / "third_place_rankings.csv", THIRD_FIELDS, third_out)

    print(f"Wrote {len(live_rows)} standings rows, {len(third_out)} third-place rows")
    print(f"snapshot_id={snap} cutoff={cutoff.isoformat()} matches_used={meta['result_rows_used']}")


if __name__ == "__main__":
    main()
