#!/usr/bin/env python3
"""Ablation gate for competition route audit_only -> rerank_only."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

MIN_SAMPLE = 20
MAX_LOG_LOSS_REGRESSION = 0.01
MAX_BRIER_REGRESSION = 0.005
MAX_RANKING_REGRESSION = 0.01


def evaluate_route_ablation(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_variant = {str(r.get("variant")): r for r in rows}
    baseline = by_variant.get("state_plus_advance", {})
    route = by_variant.get("state_plus_advance_plus_route", {})
    sample = min(int(baseline.get("n", 0) or 0), int(route.get("n", 0) or 0))
    required = {
        "no_competition_state",
        "state_only",
        "state_plus_advance",
        "state_plus_advance_plus_route",
    }
    complete = required.issubset(by_variant)
    if not complete or sample < MIN_SAMPLE:
        return {
            "safety_pass": complete,
            "performance_pass": False,
            "rerank_only_allowed": False,
            "allowed_modes": ["audit_only"],
            "reason": "incomplete_ablation" if not complete else "insufficient_sample",
            "sample_size": sample,
        }

    def delta(metric: str) -> float:
        return float(route.get(metric, 0.0)) - float(baseline.get(metric, 0.0))

    log_loss_delta = delta("log_loss")
    brier_delta = delta("brier")
    topn_delta = delta("score_topn_hit_rate")
    htft_delta = delta("htft_rank_hit_rate")
    safety = (
        log_loss_delta <= MAX_LOG_LOSS_REGRESSION
        and brier_delta <= MAX_BRIER_REGRESSION
        and topn_delta >= -MAX_RANKING_REGRESSION
        and htft_delta >= -MAX_RANKING_REGRESSION
    )
    improvement = (
        log_loss_delta < 0
        or brier_delta < 0
        or topn_delta > 0
        or htft_delta > 0
    )
    allowed = safety and improvement
    return {
        "safety_pass": safety,
        "performance_pass": improvement,
        "rerank_only_allowed": allowed,
        "allowed_modes": ["audit_only", "rerank_only"] if allowed else ["audit_only"],
        "reason": "thresholds_met" if allowed else "performance_or_safety_threshold_not_met",
        "sample_size": sample,
        "deltas": {
            "log_loss": round(log_loss_delta, 6),
            "brier": round(brier_delta, 6),
            "score_topn_hit_rate": round(topn_delta, 6),
            "htft_rank_hit_rate": round(htft_delta, 6),
        },
        "no_lambda_mutation": True,
        "no_probability_mutation": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate competition route ablation gate")
    parser.add_argument("--metrics", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    with args.metrics.open(encoding="utf-8-sig", newline="") as handle:
        report = evaluate_route_ablation(list(csv.DictReader(handle)))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
