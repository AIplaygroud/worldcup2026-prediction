#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build historical_matches.csv from StatsBomb Open Data cache and finished WC2026."""
from __future__ import annotations

import argparse
from pathlib import Path

from data_providers.provider_cache_common import list_cached_match_keys, load_cache_list
from eventflow_common import read_csv, write_csv
from v37_common import V37_NORMALIZED, ensure_v37_dirs
from v37_historical_common import HISTORICAL_MATCH_FIELDS, label_large_score


def _xg_lookup() -> dict[tuple[str, str], tuple[float, float]]:
    out: dict[tuple[str, str], tuple[float, float]] = {}
    xg_path = Path(__file__).resolve().parents[1] / "database" / "xGdatabase" / "processed" / "wc2026_match_xg.csv"
    if not xg_path.exists():
        return out
    for row in read_csv(xg_path):
        key = (row.get("home_team", "").strip(), row.get("away_team", "").strip())
        try:
            out[key] = (float(row.get("home_xg") or 0), float(row.get("away_xg") or 0))
        except ValueError:
            continue
    return out


def from_finished_wc2026(xg: dict[tuple[str, str], tuple[float, float]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for m in read_csv(V37_NORMALIZED / "matches.csv"):
        if m.get("status") != "finished":
            continue
        hs = int(m.get("home_score") or 0)
        as_ = int(m.get("away_score") or 0)
        home = m["home_team"]
        away = m["away_team"]
        labels = label_large_score(home, away, hs, as_)
        hxg, axg = xg.get((home, away), (0.0, 0.0))
        mid = m["match_id"]
        rows.append({
            "historical_match_id": mid,
            "source": "finished_wc2026",
            "competition": m.get("competition", "WC2026"),
            "season": m.get("season", "2026"),
            "match_date": (m.get("kickoff_utc") or "")[:10],
            "home_team": home,
            "away_team": away,
            "neutral_venue": "false",
            "home_score": str(hs),
            "away_score": str(as_),
            "total_goals": labels["total_goals"],
            "winner": labels["winner"],
            "home_xg": str(hxg) if hxg else "",
            "away_xg": str(axg) if axg else "",
            "data_quality": "0.75" if hxg else "0.55",
            "event_timeline_available": "true" if mid in _wc_event_matches() else "false",
            "lineup_available": "false",
            "match_stats_available": "true" if hxg else "false",
            "eligible_for_tail_backtest": "true",
            **{k: labels[k] for k in (
                "is_large_score", "large_score_type", "favorite_side", "favorite_score",
                "underdog_score", "favorite_margin", "actual_scoreline",
            )},
        })
    return rows


def _wc_event_matches() -> set[str]:
    out: set[str] = set()
    for row in read_csv(V37_NORMALIZED / "events.csv"):
        mid = row.get("match_id", "")
        if mid:
            out.add(mid)
    return out


def from_statsbomb_open(
    include_competitions: list[str] | None = None,
    min_data_quality: str = "partial",
) -> list[dict[str, str]]:
    comp_filters = include_competitions or []
    comp_map = {
        "world_cup": ("world cup",),
        "euro": ("euro", "uefa euro"),
        "copa": ("copa",),
        "wwc": ("women", "wwc"),
    }
    allowed_phrases: list[str] = []
    for key in comp_filters:
        allowed_phrases.extend(comp_map.get(key, (key,)))

    def _comp_ok(name: str) -> bool:
        if not allowed_phrases:
            return True
        low = name.lower()
        return any(p in low for p in allowed_phrases)

    def _dq_ok(dq: str) -> bool:
        try:
            v = float(dq)
        except ValueError:
            v = 0.5
        if min_data_quality == "full":
            return v >= 0.75
        if min_data_quality == "partial":
            return v >= 0.50
        return True

    rows: list[dict[str, str]] = []
    keys = list_cached_match_keys("statsbomb_open", "matches")
    for key in keys:
        for m in load_cache_list("statsbomb_open", "matches", key):
            comp = str(m.get("competition_name", m.get("competition", "unknown")))
            if not _comp_ok(comp):
                continue
            mid = f"SB-{m.get('match_id', key)}"
            home = m.get("home_team", m.get("home_team_name", ""))
            away = m.get("away_team", m.get("away_team_name", ""))
            hs = int(m.get("home_score", 0) or 0)
            as_ = int(m.get("away_score", 0) or 0)
            labels = label_large_score(str(home), str(away), hs, as_)
            has_events = bool(load_cache_list("statsbomb_open", "events", str(m.get("match_id", key))))
            has_lineups = bool(load_cache_list("statsbomb_open", "lineups", str(m.get("match_id", key))))
            dq = "0.80" if has_events else "0.50"
            if not _dq_ok(dq):
                continue
            rows.append({
                "historical_match_id": mid,
                "source": "statsbomb_open",
                "competition": comp,
                "season": str(m.get("season", m.get("season_name", ""))),
                "match_date": str(m.get("match_date", ""))[:10],
                "home_team": str(home),
                "away_team": str(away),
                "neutral_venue": str(m.get("neutral_venue", "false")).lower(),
                "home_score": str(hs),
                "away_score": str(as_),
                "total_goals": labels["total_goals"],
                "winner": labels["winner"],
                "home_xg": str(m.get("home_xg", "")),
                "away_xg": str(m.get("away_xg", "")),
                "data_quality": dq,
                "event_timeline_available": str(has_events).lower(),
                "lineup_available": str(has_lineups).lower(),
                "match_stats_available": "false",
                "eligible_for_tail_backtest": "true" if has_events else "false",
                **{k: labels[k] for k in (
                    "is_large_score", "large_score_type", "favorite_side", "favorite_score",
                    "underdog_score", "favorite_margin", "actual_scoreline",
                )},
            })
    return rows


def build(
    sources: list[str],
    include_competitions: list[str] | None = None,
    min_data_quality: str = "partial",
) -> list[dict[str, str]]:
    xg = _xg_lookup()
    rows: list[dict[str, str]] = []
    if "finished_wc2026" in sources:
        rows.extend(from_finished_wc2026(xg))
    if "statsbomb_open" in sources:
        rows.extend(from_statsbomb_open(include_competitions, min_data_quality))
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description="Build V3.7 historical matches")
    ap.add_argument("--sources", default="statsbomb_open,finished_wc2026")
    ap.add_argument("--min-data-quality", default="partial", choices=("any", "partial", "full"))
    ap.add_argument("--include-competitions", default="world_cup,euro,copa,wwc")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    ensure_v37_dirs()
    sources = [s.strip() for s in args.sources.split(",") if s.strip()]
    comps = [c.strip() for c in args.include_competitions.split(",") if c.strip()]
    rows = build(sources, comps, args.min_data_quality)
    write_csv(Path(args.output), rows, HISTORICAL_MATCH_FIELDS)
    print(f"Wrote {len(rows)} historical matches -> {args.output}")


if __name__ == "__main__":
    main()
