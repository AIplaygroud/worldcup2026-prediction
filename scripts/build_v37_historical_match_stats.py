#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build historical_match_stats.csv from xG database and StatsBomb cache."""
from __future__ import annotations

import argparse
from pathlib import Path

from data_providers.provider_cache_common import list_cached_match_keys, load_cache_list
from eventflow_common import read_csv, write_csv
from v37_common import V37_NORMALIZED, ensure_v37_dirs
from v37_historical_common import HISTORICAL_STATS_FIELDS


def from_wc2026_xg() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    xg_path = Path(__file__).resolve().parents[1] / "database" / "xGdatabase" / "processed" / "wc2026_match_xg.csv"
    if not xg_path.exists():
        return rows
    match_by_teams: dict[tuple[str, str], str] = {}
    for m in read_csv(V37_NORMALIZED / "matches.csv"):
        if m.get("status") == "finished":
            match_by_teams[(m["home_team"], m["away_team"])] = m["match_id"]
    for row in read_csv(xg_path):
        mid = match_by_teams.get((row["home_team"], row["away_team"]))
        if not mid:
            continue
        for side, team in (("home", row["home_team"]), ("away", row["away_team"])):
            prefix = f"{side}_"
            rows.append({
                "historical_match_id": mid,
                "team": team,
                "xg": row.get(f"{prefix}xg", ""),
                "shots": row.get(f"{prefix}shots", ""),
                "shots_on_target": "",
                "big_chances": "",
                "possession": "",
                "corners": "",
                "box_entries": "",
                "source": "wc2026_xg",
                "quality": row.get("quality_flag", "ok"),
            })
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description="Build V3.7 historical match stats")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    ensure_v37_dirs()
    rows = from_wc2026_xg()
    write_csv(Path(args.output), rows, HISTORICAL_STATS_FIELDS)
    print(f"Wrote {len(rows)} historical match stats -> {args.output}")


if __name__ == "__main__":
    main()
