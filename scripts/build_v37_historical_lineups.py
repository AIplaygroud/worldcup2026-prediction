#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build historical_lineups.csv from StatsBomb Open Data cache."""
from __future__ import annotations

import argparse
from pathlib import Path

from data_providers.provider_cache_common import list_cached_match_keys, load_cache_list
from eventflow_common import write_csv
from v37_common import ensure_v37_dirs
from v37_historical_common import HISTORICAL_LINEUP_FIELDS


def build_statsbomb() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for key in list_cached_match_keys("statsbomb_open", "matches"):
        mid = f"SB-{key}"
        for lu in load_cache_list("statsbomb_open", "lineups", key):
            team = str(lu.get("team", lu.get("team_name", "")))
            for player in lu.get("lineup", lu.get("players", [lu])):
                if not isinstance(player, dict):
                    continue
                status = str(player.get("lineup_status", player.get("status", "starter")))
                rows.append({
                    "historical_match_id": mid,
                    "team": team,
                    "player_name": str(player.get("player_name", player.get("name", ""))),
                    "lineup_status": status,
                    "position": str(player.get("position", "")),
                    "is_starter": str(status.lower() in ("starting xi", "starter", "start")).lower(),
                    "confirmed": str(lu.get("confirmed", True)).lower(),
                    "source": "statsbomb_open",
                })
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description="Build V3.7 historical lineups")
    ap.add_argument("--source", default="statsbomb_open")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    ensure_v37_dirs()
    rows = build_statsbomb() if args.source == "statsbomb_open" else []
    write_csv(Path(args.output), rows, HISTORICAL_LINEUP_FIELDS)
    print(f"Wrote {len(rows)} historical lineups -> {args.output}")


if __name__ == "__main__":
    main()
