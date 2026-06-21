#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deduplicate v37 normalized tables by per-table merge keys."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from eventflow_common import read_csv, write_csv
from v37_common import NORMALIZED_TABLES, V37_AUDIT, ensure_v37_dirs
from v37_enrichment_common import AUDIT_FIELDS, MERGE_KEYS, dedupe_table_rows, new_run_id

TABLE_FIELDS = {
    "matches": [
        "match_id", "provider_match_id", "competition", "season", "stage", "group", "round",
        "home_team", "away_team", "kickoff_utc", "venue", "city", "country", "status",
        "home_score", "away_score", "home_ht_score", "away_ht_score",
    ],
    "standings_snapshot": [
        "snapshot_id", "match_id", "group", "team", "points_before", "played_before",
        "wins_before", "draws_before", "losses_before", "gf_before", "ga_before", "gd_before",
        "rank_before", "remaining_matches", "remaining_opponents", "can_qualify_if_win",
        "can_qualify_if_draw", "elimination_risk_if_loss", "draw_utility", "win_necessity",
        "round_before", "path_state", "state_reason_code",
        "p_finish_1", "p_finish_2", "p_finish_3", "p_finish_4",
        "p_top2", "p_best8_third", "p_advance",
    ],
    "match_events": [
        "match_id", "event_id", "minute", "stoppage_minute", "team", "event_type", "player",
        "assist_player", "score_home_after", "score_away_after", "card_type", "sub_in", "sub_out",
        "source", "confirmed",
    ],
    "lineups": [
        "match_id", "team", "player_id", "player_name", "is_starter", "is_bench", "position",
        "role_group", "importance_tier", "formation_slot", "lineup_status", "source",
        "evidence_grade", "confirmed_at_utc",
    ],
    "player_availability": [
        "match_id", "team", "player", "signal_type", "status", "role_group", "importance_tier",
        "evidence_grade", "confirmed", "source", "updated_at",
    ],
    "match_stats": [
        "match_id", "team", "data_timing", "shots", "shots_on_target", "xg", "big_chances",
        "corners", "passes", "pass_accuracy", "possession", "saves", "sot_faced",
        "goals_prevented", "ppda", "field_tilt", "source", "quality_flag",
    ],
    "team_recent_stats": [
        "match_id", "team", "matches_played", "xg_for_avg", "xg_against_avg", "shots_avg",
        "sot_avg", "big_chances_avg", "goals_for_avg", "goals_against_avg", "form_points",
        "data_timing", "source", "quality_flag",
    ],
    "odds_snapshots": [
        "match_id", "market", "selection", "sp", "handicap", "total_line", "single_allowed",
        "pool_status", "provider", "fetched_at_utc", "is_opening", "is_closing",
    ],
}


def dedupe_all(run_id: str = "") -> dict[str, int]:
    ensure_v37_dirs()
    run_id = run_id or new_run_id()
    audit: list[dict[str, str]] = []
    counts: dict[str, int] = {}

    for table, keys in MERGE_KEYS.items():
        path = NORMALIZED_TABLES.get(table)
        if not path or not path.exists():
            continue
        fields = TABLE_FIELDS.get(table)
        if not fields:
            continue
        before = len(read_csv(path))
        rows = dedupe_table_rows(table, read_csv(path), audit, run_id=run_id, provider="dedupe")
        write_csv(path, rows, fields)
        counts[table] = before - len(rows)

    audit_path = V37_AUDIT / "normalized_dedup_audit.csv"
    existing = read_csv(audit_path) if audit_path.exists() else []
    existing.extend(audit)
    write_csv(audit_path, existing, AUDIT_FIELDS)

    (V37_AUDIT / "normalized_dedup_log.json").write_text(
        json.dumps({
            "deduped_at": datetime.now(timezone.utc).isoformat(),
            "run_id": run_id,
            "rows_removed": counts,
            "audit_rows": len(audit),
        }, indent=2),
        encoding="utf-8",
    )
    return counts


def main() -> None:
    ap = argparse.ArgumentParser(description="Dedupe v37 normalized tables")
    ap.add_argument("--run-id", default="")
    args = ap.parse_args()
    counts = dedupe_all(args.run_id)
    print(f"Dedup complete: removed {counts}")


if __name__ == "__main__":
    main()
