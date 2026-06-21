#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Analyze missed large-score tail backtest cases."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from eventflow_common import read_csv, write_csv
from v37_common import BACKTEST_TABLES, DIAGNOSTICS_TABLES, ensure_v37_dirs, identify_favorite, load_team_model_index, load_tier_index
from v37_tail_diagnostics_common import (
    MISSED_CASE_FIELDS,
    covered_by_tail_pool,
    is_true_large_score_row,
    nearest_tail_candidate,
    primary_miss_reason,
    validate_missed_large_score_rows,
)


def analyze(
    backtest_path: Path,
    cases_path: Path,
    audit_dir: Path,
    matches_path: Path | None = None,
) -> list[dict[str, str]]:
    cases_by_id = {r["match_id"]: r for r in read_csv(cases_path)}
    match_meta = {}
    if matches_path and matches_path.exists():
        for r in read_csv(matches_path):
            match_meta[r.get("historical_match_id", r.get("match_id", ""))] = r

    rows: list[dict[str, str]] = []
    for bt in read_csv(backtest_path):
        rerank_rank = int(bt.get("rerank_actual_rank") or 999)
        if rerank_rank <= 5:
            continue

        mid = bt["match_id"]
        case = cases_by_id.get(mid, {})
        meta = match_meta.get(mid, {})
        large_score_type = meta.get("large_score_type", case.get("large_score_type", ""))
        is_large = meta.get("is_large_score", bt.get("is_large_score", "false"))

        candidate = {
            "is_large_score": is_large,
            "large_score_type": large_score_type,
        }
        if not is_true_large_score_row(candidate):
            continue

        audit_path = audit_dir / f"{mid}.json"
        audit_full: dict = {}
        if audit_path.exists():
            audit_full = json.loads(audit_path.read_text(encoding="utf-8"))
        tail = audit_full.get("v37_large_score_tail", audit_full)

        home = bt.get("home_team") or case.get("home_team", "")
        away = bt.get("away_team") or case.get("away_team", "")
        actual = bt.get("actual_scoreline", "")
        fav = identify_favorite(home, away, load_tier_index(), load_team_model_index())
        case_row = {**case, **bt, "baseline_actual_rank": bt.get("baseline_actual_rank", ""),
                    "large_score_type": large_score_type, "is_large_score": is_large}
        primary, secondary = primary_miss_reason(case_row, audit_full)

        rows.append({
            "match_id": mid,
            "source": bt.get("source", ""),
            "competition": bt.get("competition", ""),
            "home_team": home,
            "away_team": away,
            "actual_scoreline": actual,
            "is_large_score": str(is_large).lower(),
            "large_score_type": large_score_type,
            "baseline_actual_rank": bt.get("baseline_actual_rank", ""),
            "rerank_actual_rank": bt.get("rerank_actual_rank", ""),
            "rank_delta": str(int(bt.get("rank_improvement") or 0)),
            "tail_boost_level": tail.get("tail_boost_level", bt.get("tail_boost_level", "")),
            "tail_boost_applied": str(tail.get("tail_boost_applied", False)).lower(),
            "safety_demotion_applied": str(tail.get("safety_demotion_applied", False)).lower(),
            "ranking_mutation_reason": tail.get("ranking_mutation_reason", ""),
            "candidate_pool_contains_actual": str(covered_by_tail_pool(actual)).lower(),
            "nearest_tail_candidate": nearest_tail_candidate(actual, fav, home),
            "egci_v2": case.get("egci_v2", ""),
            "egci_v2_quality": case.get("egci_v2_quality", ""),
            "acg_favorite": case.get("acg_favorite", ""),
            "acg_v2_quality": case.get("acg_v2_quality", ""),
            "underdog_fragility": case.get("underdog_fragility", ""),
            "chase_pressure": case.get("chase_pressure", ""),
            "cold_guard_active": case.get("cold_guard_active", bt.get("cold_guard_active", "")),
            "must_win_no_convert": case.get("must_win_no_convert", bt.get("must_win_no_convert", "")),
            "deep_handicap_contra": case.get("deep_handicap_contra", bt.get("deep_handicap_contra", "")),
            "eventflow_degraded": case.get("eventflow_degraded", "false"),
            "block_reasons": ";".join(audit_full.get("block_reasons", [])),
            "primary_miss_reason": primary,
            "secondary_miss_reason": secondary,
        })
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description="Analyze missed large-score cases")
    ap.add_argument("--backtest", default=str(BACKTEST_TABLES["results"]))
    ap.add_argument("--cases", default="")
    ap.add_argument("--matches", default="")
    ap.add_argument("--audit-dir", default=str(BACKTEST_TABLES["case_audit_dir"]))
    ap.add_argument("--output", default=str(DIAGNOSTICS_TABLES["missed_cases"]))
    args = ap.parse_args()
    ensure_v37_dirs()
    cases = Path(args.cases) if args.cases else Path(args.backtest).parent.parent / "historical" / "historical_tail_backtest_cases.csv"
    matches = Path(args.matches) if args.matches else cases.parent / "historical_matches.csv"
    rows = analyze(Path(args.backtest), cases, Path(args.audit_dir), matches)
    try:
        validate_missed_large_score_rows(rows)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    write_csv(Path(args.output), rows, MISSED_CASE_FIELDS)
    print(f"Wrote {len(rows)} missed large-score cases -> {args.output}")


if __name__ == "__main__":
    main()
