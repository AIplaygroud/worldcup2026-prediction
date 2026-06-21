#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build tail backtest cases from historical feature snapshot — labels only for evaluation."""
from __future__ import annotations

import argparse
from pathlib import Path

from eventflow_common import read_csv, write_csv
from v37_common import ensure_v37_dirs
from v37_historical_common import BACKTEST_CASE_FIELDS


def build_cases(snapshot_path: Path, matches_path: Path) -> list[dict[str, str]]:
    match_meta = {r["historical_match_id"]: r for r in read_csv(matches_path)}
    rows: list[dict[str, str]] = []
    for snap in read_csv(snapshot_path):
        mid = snap["historical_match_id"]
        meta = match_meta.get(mid, {})
        if meta.get("eligible_for_tail_backtest", "false") != "true":
            continue
        rows.append({
            "match_id": mid,
            "historical_match_id": mid,
            "source": meta.get("source", ""),
            "competition": meta.get("competition", ""),
            "home_team": meta.get("home_team", ""),
            "away_team": meta.get("away_team", ""),
            "actual_scoreline": meta.get("actual_scoreline", ""),
            "is_large_score": meta.get("is_large_score", "false"),
            "lambda_home": snap.get("lambda_home", "1.3"),
            "lambda_away": snap.get("lambda_away", "1.0"),
            "data_quality_score": snap.get("data_quality_score", "0.55"),
            "egci_v2": snap.get("egci_v2", "0.5"),
            "egci_v2_quality": snap.get("egci_v2_quality", "proxy"),
            "acg_favorite": snap.get("acg_favorite", "0.5"),
            "acg_v2_quality": snap.get("acg_v2_quality", "proxy"),
            "underdog_fragility": snap.get("underdog_fragility", "0"),
            "chase_pressure": snap.get("chase_pressure", "0"),
            "cold_guard_active": snap.get("cold_guard_active", "false"),
            "must_win_no_convert": snap.get("must_win_no_convert", "false"),
            "deep_handicap_contra": snap.get("deep_handicap_contra", "false"),
            "eventflow_degraded": snap.get("eventflow_degraded", "false"),
            "confirmed_event_timeline": snap.get("confirmed_event_timeline", "false"),
            "eligible_for_tail_backtest": "true",
        })
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description="Build V3.7 tail backtest cases")
    ap.add_argument("--snapshot", required=True)
    ap.add_argument("--matches", default="")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    ensure_v37_dirs()
    matches = Path(args.matches) if args.matches else Path(args.snapshot).parent / "historical_matches.csv"
    rows = build_cases(Path(args.snapshot), matches)
    write_csv(Path(args.output), rows, BACKTEST_CASE_FIELDS)
    print(f"Wrote {len(rows)} backtest cases -> {args.output}")


if __name__ == "__main__":
    main()
