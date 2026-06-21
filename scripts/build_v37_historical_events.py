#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build historical_events.csv from StatsBomb Open Data cache."""
from __future__ import annotations

import argparse
from pathlib import Path

from data_providers.provider_cache_common import list_cached_match_keys, load_cache_list
from eventflow_common import write_csv
from v37_common import ensure_v37_dirs
from v37_historical_common import HISTORICAL_EVENT_FIELDS


def _normalize_event(mid: str, ev: dict, source: str) -> dict[str, str]:
    etype = str(ev.get("type", ev.get("event_type", "")))
    subtype = str(ev.get("subtype", ev.get("event_subtype", "")))
    team = str(ev.get("team", ev.get("team_name", "")))
    player = str(ev.get("player", ev.get("player_name", "")))
    minute = str(ev.get("minute", ev.get("time", 0)))
    second = str(ev.get("second", 0))
    is_goal = etype.lower() in ("shot", "goal") and str(ev.get("shot_outcome", ev.get("outcome", ""))).lower() in ("goal", "own goal")
    if etype.lower() == "goal":
        is_goal = True
    is_own = "own" in subtype.lower() or str(ev.get("is_own_goal", "")).lower() == "true"
    is_red = etype.lower() == "foul committed" and "red" in subtype.lower()
    is_pen = "penalty" in subtype.lower() or str(ev.get("is_penalty", "")).lower() == "true"
    score_after = str(ev.get("score_after", ev.get("score", "")))
    return {
        "historical_match_id": mid,
        "minute": minute,
        "second": second,
        "team": team,
        "player": player,
        "event_type": etype,
        "event_subtype": subtype,
        "score_after": score_after,
        "is_goal": str(is_goal).lower(),
        "is_red_card": str(is_red).lower(),
        "is_penalty": str(is_pen).lower(),
        "is_own_goal": str(is_own).lower(),
        "source_event_id": str(ev.get("id", ev.get("source_event_id", ""))),
        "source": source,
    }


def build_statsbomb() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for key in list_cached_match_keys("statsbomb_open", "matches"):
        mid = f"SB-{key}"
        for ev in load_cache_list("statsbomb_open", "events", key):
            rows.append(_normalize_event(mid, ev, "statsbomb_open"))
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description="Build V3.7 historical events")
    ap.add_argument("--source", default="statsbomb_open")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    ensure_v37_dirs()
    rows = build_statsbomb() if args.source == "statsbomb_open" else []
    write_csv(Path(args.output), rows, HISTORICAL_EVENT_FIELDS)
    print(f"Wrote {len(rows)} historical events -> {args.output}")


if __name__ == "__main__":
    main()
