#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run the daily EventFlow build pipeline.

This script intentionally does not scrape protected sites. It only transforms
local raw/manual CSV files already placed under database/*/raw.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
PIPELINE = [
    "build_player_foot_position_profile.py",
    "build_worldcup_position_shift.py",
    "build_team_tactical_profile.py",
    "build_tactical_matchup_matrix.py",
    "build_match_timeline_events.py",
    "build_eventflow_scenario_weights.py",
    "validate_eventflow_data.py",
]


def main() -> None:
    for name in PIPELINE:
        path = SCRIPTS / name
        print(f"\n=== running {name} ===")
        res = subprocess.run([sys.executable, str(path)], cwd=str(SCRIPTS.parents[0]))
        if res.returncode != 0:
            raise SystemExit(res.returncode)
    print("\nEventFlow daily build completed.")


if __name__ == "__main__":
    main()
