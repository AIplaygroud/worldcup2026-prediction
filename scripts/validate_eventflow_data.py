#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate EventFlow V3.0 data completeness and confidence.

Output:
- database/eventflow/processed/eventflow_data_quality.csv
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Dict, List

from eventflow_common import DB, EVENTFLOW_DB, read_csv, write_csv, snum, fnum

TABLE_REQUIREMENTS = {
    "player_style/processed/player_foot_position_profile.csv": ["player","team","preferred_foot","primary_position","profile_confidence"],
    "player_style/processed/player_worldcup_position_shift.csv": ["player","team","match_id","actual_role","position_shift_score"],
    "team_style/processed/team_tactical_profile.csv": ["team","formation_base","pressing_height","build_up_style","chaos_index","data_confidence"],
    "team_style/processed/tactical_matchup_matrix.csv": ["match_id","home","away","home_breakthrough_score","away_breakthrough_score","data_confidence"],
    "eventflow/processed/eventflow_scenario_weights.csv": ["match_id","home","away","scenario_id","weight","score_family","data_confidence"],
    "eventflow/processed/eventflow_predictions.csv": ["match_id","home","away","score","event_probability","htft"],
}


def score_table(rel: str, req: List[str]) -> Dict[str, Any]:
    rows = read_csv(DB / rel)
    missing = 0
    low_conf = 0
    for r in rows:
        for k in req:
            if snum(r, k) == "":
                missing += 1
        conf_keys = [k for k in r.keys() if "confidence" in k]
        if conf_keys and min(fnum(r,k,1.0) for k in conf_keys) < 0.45:
            low_conf += 1
    denom = max(1, len(rows) * max(1, len(req)))
    quality = max(0.0, 1.0 - missing / denom - 0.25 * low_conf / max(1,len(rows)))
    return {
        "dataset": rel.split("/")[0],
        "table_name": rel,
        "rows": len(rows),
        "required_fields_missing": missing,
        "stale_rows": 0,
        "low_confidence_rows": low_conf,
        "last_updated": date.today().isoformat(),
        "quality_score": quality,
        "notes": "empty_table_or_not_built" if len(rows) == 0 else "ok" if quality >= 0.75 else "needs_review",
    }


def main() -> None:
    out = [score_table(rel, req) for rel, req in TABLE_REQUIREMENTS.items()]
    write_csv(EVENTFLOW_DB / "eventflow_data_quality.csv", out)
    for r in out:
        print(f"{r['table_name']}: rows={r['rows']} quality={float(r['quality_score']):.2f} {r['notes']}")


if __name__ == "__main__":
    main()
