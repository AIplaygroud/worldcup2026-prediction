#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build prematch historical feature snapshot — no postmatch score leakage."""
from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

from eventflow_common import read_csv, write_csv
from v37_common import clip, ensure_v37_dirs, identify_favorite, load_team_model_index, load_tier_index
from v37_historical_common import FEATURE_SNAPSHOT_FIELDS


def _events_by_match(events_path: Path) -> dict[str, list[dict[str, str]]]:
    out: dict[str, list[dict[str, str]]] = defaultdict(list)
    if events_path.exists():
        for row in read_csv(events_path):
            out[row["historical_match_id"]].append(row)
    return out


def _stats_by_match(stats_path: Path) -> dict[str, list[dict[str, str]]]:
    out: dict[str, list[dict[str, str]]] = defaultdict(list)
    if stats_path.exists():
        for row in read_csv(stats_path):
            out[row["historical_match_id"]].append(row)
    return out


def _egci_from_events(events: list[dict[str, str]]) -> tuple[float, int, bool]:
    goals = [e for e in events if e.get("is_goal") == "true"]
    early = [g for g in goals if int(g.get("minute") or 99) <= 30]
    if len(goals) >= 2:
        cascade = min(1.0, 0.45 + 0.12 * len(early) + 0.08 * len(goals))
        return cascade, len(goals), True
    if goals:
        return 0.55, len(goals), True
    return 0.40, 0, False


def _acg_from_stats(stats: list[dict[str, str]], favorite: str) -> tuple[float, str]:
    for row in stats:
        if row.get("team") == favorite:
            try:
                xg = float(row.get("xg") or 0)
                shots = float(row.get("shots") or 1)
                acg = clip(xg / max(shots, 1) * 2.5, 0.0, 1.0)
                q = "real" if xg > 0 else "proxy"
                return acg, q
            except ValueError:
                break
    return 0.50, "proxy"


def build_snapshot(
    matches_path: Path,
    events_path: Path,
    lineups_path: Path,
    stats_path: Path,
) -> list[dict[str, str]]:
    events_map = _events_by_match(events_path)
    stats_map = _stats_by_match(stats_path)
    tiers = load_tier_index()
    models = load_team_model_index()
    rows: list[dict[str, str]] = []

    for m in read_csv(matches_path):
        mid = m["historical_match_id"]
        home = m["home_team"]
        away = m["away_team"]
        favorite = identify_favorite(home, away, tiers, models)

        try:
            lam_h = float(m.get("home_xg") or 1.3)
            lam_a = float(m.get("away_xg") or 1.0)
        except ValueError:
            lam_h, lam_a = 1.3, 1.0
        if lam_h <= 0:
            lam_h = 1.3
        if lam_a <= 0:
            lam_a = 1.0

        evs = events_map.get(mid, [])
        egci, goal_count, timeline_ok = _egci_from_events(evs)
        egci_q = "real" if m.get("event_timeline_available") == "true" and timeline_ok else "proxy"
        acg, acg_q = _acg_from_stats(stats_map.get(mid, []), favorite)

        dq = float(m.get("data_quality") or 0.55)
        cold = "false"
        must_win = "false"
        deep_handicap = "false"
        if favorite and lam_h > 0 and lam_a > 0:
            ratio = lam_h / lam_a if favorite == home else lam_a / lam_h
            if ratio >= 2.5:
                deep_handicap = "true"
            if ratio >= 3.0 and acg < 0.45:
                cold = "true"

        rows.append({
            "historical_match_id": mid,
            "lambda_home": str(round(lam_h, 3)),
            "lambda_away": str(round(lam_a, 3)),
            "data_quality_score": str(round(dq, 3)),
            "egci_v2": str(round(egci, 4)),
            "egci_v2_quality": egci_q,
            "acg_favorite": str(round(acg, 4)),
            "acg_v2_quality": acg_q,
            "underdog_fragility": str(round(clip(egci * 0.7, 0, 1), 4)),
            "chase_pressure": str(round(clip(egci * 0.5, 0, 1), 4)),
            "cold_guard_active": cold,
            "must_win_no_convert": must_win,
            "deep_handicap_contra": deep_handicap,
            "eventflow_degraded": "false",
            "goal_timeline_count": str(goal_count),
            "confirmed_event_timeline": str(timeline_ok and egci_q == "real").lower(),
        })
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description="Build V3.7 historical feature snapshot")
    ap.add_argument("--matches", required=True)
    ap.add_argument("--events", required=True)
    ap.add_argument("--lineups", required=True)
    ap.add_argument("--stats", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    ensure_v37_dirs()
    rows = build_snapshot(
        Path(args.matches), Path(args.events), Path(args.lineups), Path(args.stats),
    )
    write_csv(Path(args.output), rows, FEATURE_SNAPSHOT_FIELDS)
    print(f"Wrote {len(rows)} feature snapshots -> {args.output}")


if __name__ == "__main__":
    main()
