#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Convert raw commentary/tactical signals into structured timeline events.

Input:
- database/eventflow/raw/raw_match_commentary_signals.csv

Output:
- database/eventflow/processed/match_timeline_events.csv
- database/eventflow/processed/match_phase_profile.csv
- database/eventflow/processed/commentary_signals.jsonl

Copyright policy: do not store full commentary transcripts. Store short factual
summaries, tags, event types, and source URLs only.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Dict, List

from eventflow_common import EVENTFLOW_DB, read_csv, write_csv, fnum, snum

RAW = Path(__file__).resolve().parents[1] / "database" / "eventflow" / "raw"

PHASES = [(0,15,"00-15"),(16,30,"16-30"),(31,45,"31-45+"),(46,60,"46-60"),(61,75,"61-75"),(76,130,"76-90+")]


def phase_from_minute(m: int) -> str:
    for lo, hi, label in PHASES:
        if lo <= m <= hi:
            return label
    return "unknown"


def infer_event_type(signal_type: str, tags: str) -> str:
    text = f"{signal_type} {tags}".lower()
    if any(x in text for x in ["goal", "进球"]):
        return "goal"
    if any(x in text for x in ["penalty", "点球"]):
        return "penalty_or_box_incident"
    if any(x in text for x in ["red", "红牌"]):
        return "red_card_or_dismissal"
    if any(x in text for x in ["sub", "换人"]):
        return "substitution_shift"
    if any(x in text for x in ["press", "压迫"]):
        return "pressing_signal"
    if any(x in text for x in ["transition", "counter", "反击", "转换"]):
        return "transition_signal"
    if any(x in text for x in ["set", "corner", "free kick", "定位球", "角球"]):
        return "set_piece_signal"
    if any(x in text for x in ["shape", "formation", "阵型"]):
        return "formation_shift"
    return "commentary_signal"


def map_impact(v: str) -> float:
    v = (v or "").strip().lower()
    if v in {"++", "high", "strong", "大", "强"}:
        return 1.0
    if v in {"+", "medium", "中"}:
        return 0.5
    if v in {"-", "low", "弱"}:
        return -0.5
    if v in {"--"}:
        return -1.0
    try:
        return float(v)
    except Exception:
        return 0.0


def main() -> None:
    rows = read_csv(RAW / "raw_match_commentary_signals.csv")
    events: List[Dict[str, Any]] = []
    signal_json: List[Dict[str, Any]] = []
    for idx, r in enumerate(rows, 1):
        minute = int(fnum(r, "minute"))
        phase = snum(r, "phase") or phase_from_minute(minute)
        event_type = infer_event_type(snum(r,"signal_type"), snum(r,"tags"))
        event_id = f"{snum(r,'match_id')}_{minute:03d}_{idx:03d}"
        events.append({
            "event_id": event_id,
            "match_id": snum(r,"match_id"),
            "date": snum(r,"date"),
            "minute": minute,
            "stoppage": snum(r,"stoppage") or 0,
            "team": snum(r,"team"),
            "opponent": snum(r,"opponent"),
            "phase": phase,
            "event_type": event_type,
            "event_subtype": snum(r,"signal_type"),
            "score_before": "",
            "score_after": "",
            "xg": "",
            "xthreat": "",
            "directness": map_impact(snum(r,"impact_tempo")),
            "pressure_context": snum(r,"tags"),
            "source": snum(r,"source"),
            "source_url": snum(r,"source_url"),
            "confidence": fnum(r,"confidence",0.55),
        })
        signal_json.append({
            "match_id": snum(r,"match_id"),
            "minute": minute,
            "phase": phase,
            "team": snum(r,"team"),
            "opponent": snum(r,"opponent"),
            "signal_type": snum(r,"signal_type"),
            "summary": snum(r,"short_summary")[:240],
            "tags": [x.strip() for x in snum(r,"tags").replace(";",",").split(",") if x.strip()],
            "impact": {
                "attack": map_impact(snum(r,"impact_attack")),
                "defense": map_impact(snum(r,"impact_defense")),
                "tempo": map_impact(snum(r,"impact_tempo")),
                "variance": map_impact(snum(r,"impact_variance")),
            },
            "source": snum(r,"source"),
            "source_url": snum(r,"source_url"),
            "confidence": fnum(r,"confidence",0.55),
        })
    write_csv(EVENTFLOW_DB / "match_timeline_events.csv", events)
    # jsonl
    with (EVENTFLOW_DB / "commentary_signals.jsonl").open("w", encoding="utf-8") as f:
        for obj in signal_json:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")

    # phase profile from signals, not a full event-data replacement
    grouped: Dict[tuple, List[Dict[str, str]]] = defaultdict(list)
    for r in rows:
        grouped[(snum(r,"match_id"), snum(r,"team"), snum(r,"opponent"), snum(r,"phase") or phase_from_minute(int(fnum(r,"minute"))))].append(r)
    phase_rows: List[Dict[str, Any]] = []
    for (match_id, team, opp, phase), rs in grouped.items():
        n = max(1, len(rs))
        attack = sum(map_impact(snum(r,"impact_attack")) for r in rs) / n
        defense = sum(map_impact(snum(r,"impact_defense")) for r in rs) / n
        tempo = sum(map_impact(snum(r,"impact_tempo")) for r in rs) / n
        variance = sum(map_impact(snum(r,"impact_variance")) for r in rs) / n
        tags = sorted({t.strip() for r in rs for t in snum(r,"tags").replace(";",",").split(",") if t.strip()})
        phase_rows.append({
            "match_id": match_id,
            "date": snum(rs[-1],"date"),
            "team": team,
            "opponent": opp,
            "phase": phase,
            "score_state": "unknown",
            "xg_for": "",
            "xg_against": "",
            "shots_for": "",
            "shots_against": "",
            "possession_pct": "",
            "territory_pct": "",
            "pressing_intensity": attack if "press" in ";".join(tags).lower() else 0,
            "transition_threat": attack if "transition" in ";".join(tags).lower() or "反击" in ";".join(tags) else 0,
            "set_piece_threat": attack if "set" in ";".join(tags).lower() or "定位球" in ";".join(tags) else 0,
            "defensive_stability": defense,
            "tempo": tempo,
            "variance": variance,
            "phase_tags": ";".join(tags),
            "data_confidence": min(fnum(r,"confidence",0.55) for r in rs),
        })
    write_csv(EVENTFLOW_DB / "match_phase_profile.csv", phase_rows)
    print(f"wrote {len(events)} timeline events and {len(phase_rows)} phase rows")


if __name__ == "__main__":
    main()
