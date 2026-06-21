#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Report V3.7 data source coverage per match and provider."""
from __future__ import annotations

import argparse
from pathlib import Path

from eventflow_common import read_csv, write_csv
from v37_common import (
    AVAILABILITY_SIGNALS,
    MATCH_XG,
    NORMALIZED_TABLES,
    TEAM_TACTICAL,
    V37_AUDIT,
    ensure_v37_dirs,
    kickoff_from_mapping,
    load_mapping,
    match_odds_by_teams,
    snum,
)

REPORT_FIELDS = [
    "provider", "match_id", "has_fixture", "has_standing", "has_lineup", "has_events",
    "has_stats", "has_recent_xg_real", "has_recent_xg_proxy", "has_xg", "has_odds",
    "latency_minutes", "coverage_score", "notes",
]


def _bool_str(v: bool) -> str:
    return "true" if v else "false"


def _team_recent_xg_flags(mid: str, home: str, away: str) -> tuple[bool, bool]:
    """Return (has_real, has_proxy) from normalized team_recent_stats."""
    path = NORMALIZED_TABLES["team_recent_stats"]
    if not path.exists():
        return False, False
    rows = [r for r in read_csv(path) if r.get("match_id") == mid]
    if not rows:
        return False, True
    real = any(
        int(float(snum(r, "matches_played") or "0")) > 0
        and snum(r, "quality_flag") == "ok"
        for r in rows
        if r.get("team") in (home, away)
    )
    proxy = any(
        int(float(snum(r, "matches_played") or "0")) == 0
        or snum(r, "quality_flag") == "proxy"
        for r in rows
        if r.get("team") in (home, away)
    )
    return real, proxy and not real


def coverage_for_match(match: dict, provider: str) -> dict:
    mid = match["internal_match_id"]
    home, away = match["home_team"], match["away_team"]

    has_fixture = True
    has_standing = False
    if NORMALIZED_TABLES["standings_snapshot"].exists():
        snap_rows = [r for r in read_csv(NORMALIZED_TABLES["standings_snapshot"]) if r.get("match_id") == mid]
        has_standing = len(snap_rows) >= 2

    has_lineup = any(snum(r, "match_id") == mid for r in read_csv(AVAILABILITY_SIGNALS))

    xg_rows = read_csv(MATCH_XG)
    has_xg_match = any(r.get("home_team") == home and r.get("away_team") == away for r in xg_rows)
    has_xg_history = any(
        home in (r.get("home_team"), r.get("away_team")) for r in xg_rows
    )
    has_events = has_xg_match
    has_stats = has_xg_history or home in {r.get("team") for r in read_csv(TEAM_TACTICAL)}

    has_xg_real, has_xg_proxy = _team_recent_xg_flags(mid, home, away)
    if not NORMALIZED_TABLES["team_recent_stats"].exists():
        has_xg_real = has_xg_history
        has_xg_proxy = not has_xg_history

    has_odds = match_odds_by_teams(home, away) is not None

    flags = [
        has_fixture, has_standing, has_lineup, has_events, has_stats,
        has_xg_real or has_xg_proxy, has_odds,
    ]
    score = round(sum(1.0 if f else 0.0 for f in flags) / len(flags), 4)

    notes: list[str] = []
    if not has_odds:
        notes.append("no_jc_odds")
    if not has_lineup:
        notes.append("no_lineup")
    if has_xg_proxy and not has_xg_real:
        notes.append("xg_proxy_only")
    if not has_standing:
        notes.append("no_standings_snapshot")

    return {
        "provider": provider,
        "match_id": mid,
        "has_fixture": _bool_str(has_fixture),
        "has_standing": _bool_str(has_standing),
        "has_lineup": _bool_str(has_lineup),
        "has_events": _bool_str(has_events),
        "has_stats": _bool_str(has_stats),
        "has_recent_xg_real": _bool_str(has_xg_real),
        "has_recent_xg_proxy": _bool_str(has_xg_proxy),
        "has_xg": _bool_str(has_xg_match or has_xg_history),
        "has_odds": _bool_str(has_odds),
        "latency_minutes": "",
        "coverage_score": score,
        "notes": ";".join(notes),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="V3.7 data source coverage report")
    ap.add_argument("--competition", default="WC2026")
    ap.add_argument("--season", default="2026")
    ap.add_argument("--provider", default="local", help="Comma-separated providers")
    ap.add_argument("--match-id", default="")
    ap.add_argument(
        "--output",
        type=Path,
        default=V37_AUDIT / "data_source_coverage_report.csv",
    )
    args = ap.parse_args()

    ensure_v37_dirs()
    providers = [p.strip() for p in args.provider.split(",") if p.strip()]
    matches = load_mapping(args.match_id)

    rows: list[dict] = []
    for m in matches:
        for prov in providers:
            rows.append(coverage_for_match(m, prov))

    write_csv(args.output, rows, REPORT_FIELDS)

    if rows:
        avg = sum(float(r["coverage_score"]) for r in rows) / len(rows)
        high = sum(1 for r in rows if float(r["coverage_score"]) >= 0.85) / len(rows)
        print(f"Coverage report: {len(rows)} rows, avg_score={avg:.3f}, high_coverage_rate={high:.1%}")
        print(f"Wrote {args.output}")
    else:
        print("No matches found")


if __name__ == "__main__":
    main()
