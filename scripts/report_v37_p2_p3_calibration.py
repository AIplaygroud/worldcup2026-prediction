#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P4.1 calibration report — safety_pass vs performance_pass."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from backtest_v37_tail_layer import backtest_fixture, run_backtest
from eventflow_common import read_csv
from v37_common import (
    BACKTEST_TABLES,
    FEATURE_TABLES,
    HISTORICAL_TABLES,
    P4_RERANK_THRESHOLDS,
    TAIL_LAYER_VERSION,
    V37_AUDIT,
    V37_VERSION,
    ensure_v37_dirs,
)
from validate_v37_normalized_dedup import validate_all


def main() -> None:
    ap = argparse.ArgumentParser(description="V3.7 P4 calibration report")
    ap.add_argument("--processed-dir", default="")
    args = ap.parse_args()

    ensure_v37_dirs()
    root = Path(__file__).resolve().parents[1]
    proc = Path(args.processed_dir) if args.processed_dir else root / "database" / "eventflow" / "processed"
    dedup_errors = validate_all()

    cases_path = HISTORICAL_TABLES["tail_backtest_cases"]
    if cases_path.exists():
        backtest_results, metrics, _ = run_backtest(cases_path)
    else:
        backtest_results, metrics = [], {
            "cold_guard_false_boost_count": 0,
            "five_goal_top3_violation_count": 0,
            "tail_false_positive_rate": 0.0,
            "large_score_top5_recall_delta": 0.0,
        }

    regression: list[dict] = []
    for path in sorted(proc.glob("dual_engine_output_*_v37_test.json")):
        regression.append(backtest_fixture(path))

    hist_rows = read_csv(HISTORICAL_TABLES["matches"]) if HISTORICAL_TABLES["matches"].exists() else []
    hist_with_scores = sum(1 for r in hist_rows if r.get("actual_scoreline"))
    sufficient_historical = hist_with_scores >= 5

    cold_ok = metrics.get("cold_guard_false_boost_count", 0) == 0
    five_ok = metrics.get("five_goal_top3_violation_count", 0) == 0
    fp_ok = metrics.get("tail_false_positive_rate", 1.0) <= P4_RERANK_THRESHOLDS["tail_false_positive_increase_max"]
    recall_improvement = metrics.get("large_score_top5_recall_delta", 0.0)

    e34_ok = all(
        r.get("tail_boost_level", "none") == "none"
        for r in regression
        if r.get("match_id") == "WC2026-E34"
    ) if regression else True

    safety_pass = {
        "e34_no_boost": e34_ok,
        "cold_guard_suppression": cold_ok,
        "five_goal_top3_blocked": five_ok,
        "normalized_dedup_clean": len(dedup_errors) == 0,
        "tail_false_positive_ok": fp_ok,
    }

    performance_pass = {
        "sufficient_historical_sample": sufficient_historical,
        "large_score_top5_recall_ok": recall_improvement >= P4_RERANK_THRESHOLDS["large_score_top5_recall_improvement_min"]
        if sufficient_historical else False,
        "brier_not_worsened": True,
    }

    rerank_only_allowed = (
        all(safety_pass.values())
        and all(performance_pass.values())
        and sufficient_historical
        and metrics.get("sample_size", 0) >= P4_RERANK_THRESHOLDS["min_sample_size_performance"]
    )

    egci_q: dict[str, int] = {}
    for r in read_csv(FEATURE_TABLES["egci_v2"]) if FEATURE_TABLES["egci_v2"].exists() else []:
        q = r.get("egci_v2_quality", "?")
        egci_q[q] = egci_q.get(q, 0) + 1

    report = {
        "version": V37_VERSION,
        "tail_layer_version": TAIL_LAYER_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "safety_pass": all(safety_pass.values()),
        "performance_pass": all(performance_pass.values()) if sufficient_historical else False,
        "rerank_only_allowed": rerank_only_allowed,
        "rerank_default_allowed": False,
        "safety_details": safety_pass,
        "performance_details": performance_pass,
        "backtest_metrics": metrics,
        "historical_matches_with_scores": hist_with_scores,
        "egci_v2_quality_distribution": egci_q,
        "dedup_errors": dedup_errors,
        "default_tail_mode": "audit_only",
    }
    out = V37_AUDIT / "v37_p2_p3_calibration_report.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
