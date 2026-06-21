#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V3.7-P4 tail calibration report — safety / performance / rerank gates."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from eventflow_common import read_csv
from v37_common import (
    BACKTEST_TABLES,
    HISTORICAL_TABLES,
    P4_RERANK_THRESHOLDS,
    TAIL_LAYER_VERSION,
    V37_AUDIT,
    V37_VERSION,
    ensure_v37_dirs,
)
from validate_v37_normalized_dedup import validate_all


def _load_summary(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate(summary: dict, dedup_errors: list[str], manual_approval: bool = False) -> dict:
    th = P4_RERANK_THRESHOLDS
    sample = int(summary.get("sample_size", 0))
    large_n = int(summary.get("large_score_cases", 0))
    recall_delta = float(summary.get("large_score_top5_recall_delta", 0) or 0)
    fp_delta = float(summary.get("tail_false_positive_delta", 0) or 0)
    avg_imp = float(summary.get("avg_rank_improvement", 0) or 0)
    cold = int(summary.get("cold_guard_false_boost_count", 0))
    must = int(summary.get("must_win_no_convert_false_boost_count", 0))
    deep = int(summary.get("deep_handicap_false_boost_count", 0))
    five = int(summary.get("five_goal_top3_violation_count", 0))

    guard_ok = cold == 0 and must == 0 and deep == 0 and five == 0
    dedup_ok = len(dedup_errors) == 0
    safety_pass = guard_ok and dedup_ok

    performance_pass = (
        sample >= th["min_sample_size_performance"]
        and large_n >= th["min_large_score_cases"]
        and recall_delta >= th["large_score_top5_recall_improvement_min"]
        and fp_delta <= th["tail_false_positive_increase_max"]
        and avg_imp > 0
        and safety_pass
    )

    rerank_only_allowed = performance_pass and sample >= th["min_sample_size_performance"]

    rerank_default_allowed = (
        manual_approval
        and sample >= th["min_sample_size_default"]
        and large_n >= th["min_large_score_cases_default"]
        and recall_delta >= 0.10
        and fp_delta <= 0.03
        and safety_pass
    )

    reason = "ok"
    if sample < 5:
        reason = "insufficient_historical_labeled_sample"
    elif sample < th["min_sample_size_performance"]:
        reason = "exploratory_sample_below_rerank_threshold"
    elif not guard_ok:
        reason = "guard_violation_detected"
    elif not performance_pass:
        reason = "performance_thresholds_not_met"

    allowed_modes = ["audit_only"]
    if rerank_only_allowed:
        allowed_modes.append("rerank_only")

    return {
        "version": "v37_p4_tail_calibration",
        "system_version": V37_VERSION,
        "tail_layer_version": TAIL_LAYER_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "safety_pass": safety_pass,
        "performance_pass": performance_pass,
        "rerank_only_allowed": rerank_only_allowed,
        "rerank_default_allowed": rerank_default_allowed,
        "sample_status": {
            "sample_size": sample,
            "large_score_cases": large_n,
            "minimum_for_performance": th["min_sample_size_performance"],
            "minimum_for_default": th["min_sample_size_default"],
        },
        "performance": {
            "baseline_large_score_top5_recall": summary.get("baseline_large_score_top5_recall"),
            "rerank_large_score_top5_recall": summary.get("rerank_large_score_top5_recall"),
            "large_score_top5_recall_delta": recall_delta if sample >= 5 else None,
            "tail_false_positive_delta": fp_delta if sample >= 5 else None,
            "avg_rank_improvement": avg_imp if sample >= 5 else None,
        },
        "guard_safety": {
            "cold_guard_false_boost_count": cold,
            "must_win_no_convert_false_boost_count": must,
            "deep_handicap_false_boost_count": deep,
            "five_goal_top3_violation_count": five,
        },
        "decision": {
            "reason": reason,
            "allowed_modes": allowed_modes,
            "no_lambda_mutation": True,
            "no_v2_probability_mutation": True,
            "no_adjusted_probability_mutation": True,
            "no_auto_betting": True,
        },
        "dedup_errors": dedup_errors,
    }


def render_md(report: dict) -> str:
    ss = report["sample_status"]
    perf = report["performance"]
    guard = report["guard_safety"]
    lines = [
        "# V3.7-P4 Tail Calibration Report",
        "",
        f"- **Version**: {report['version']} ({report['system_version']})",
        f"- **Generated**: {report['generated_at']}",
        "",
        "## Sample",
        f"- Sample size: **{ss['sample_size']}**",
        f"- Large-score cases: **{ss['large_score_cases']}**",
        f"- Minimum for performance pass: {ss['minimum_for_performance']}",
        "",
        "## Performance",
        f"- Baseline large-score Top5 recall: {perf['baseline_large_score_top5_recall']}",
        f"- Rerank large-score Top5 recall: {perf['rerank_large_score_top5_recall']}",
        f"- Recall delta: {perf['large_score_top5_recall_delta']}",
        f"- Tail false positive delta: {perf['tail_false_positive_delta']}",
        f"- Avg rank improvement: {perf['avg_rank_improvement']}",
        "",
        "## Guard safety",
        f"- cold_guard false boost: {guard['cold_guard_false_boost_count']}",
        f"- must_win_no_convert false boost: {guard['must_win_no_convert_false_boost_count']}",
        f"- deep_handicap false boost: {guard['deep_handicap_false_boost_count']}",
        f"- 5-0/5-1 Top3 violations: {guard['five_goal_top3_violation_count']}",
        "",
        "## Gates",
        f"- safety_pass: **{report['safety_pass']}**",
        f"- performance_pass: **{report['performance_pass']}**",
        f"- rerank_only_allowed: **{report['rerank_only_allowed']}**",
        f"- rerank_default_allowed: **{report['rerank_default_allowed']}**",
        "",
        "## Decision",
        f"- Reason: {report['decision']['reason']}",
        f"- Allowed modes: {', '.join(report['decision']['allowed_modes'])}",
        "",
        "This stage does **not** mutate λ, V2 probabilities, adjusted probabilities, or betting outputs.",
        "Rerank remains **audit_only** by default unless `rerank_only_allowed=true`.",
        "",
    ]
    return "\n".join(lines)


def ci_gate(report: dict) -> list[str]:
    errors: list[str] = []
    ss = report["sample_status"]
    if ss["sample_size"] < 5 and report["performance_pass"]:
        errors.append("performance_pass=true with sample_size < 5")
    if not report["safety_pass"] and report["guard_safety"]["five_goal_top3_violation_count"] == 0:
        if any(report["guard_safety"].values()):
            errors.append("safety_pass=false due to guard violations")
    if report["rerank_default_allowed"] and not report.get("manual_approval"):
        errors.append("rerank_default_allowed without manual approval")
    hist = HISTORICAL_TABLES["feature_snapshot"]
    if hist.exists():
        forbidden = {"actual_scoreline", "home_score", "away_score", "is_large_score"}
        header = hist.read_text(encoding="utf-8").splitlines()[0]
        for col in forbidden:
            if col in header.split(","):
                errors.append(f"postmatch label {col} in feature snapshot")
    return errors


def main() -> None:
    ap = argparse.ArgumentParser(description="V3.7 P4 tail calibration report")
    ap.add_argument("--backtest", default="")
    ap.add_argument("--summary", default="")
    ap.add_argument("--output-json", default="")
    ap.add_argument("--output-md", default="")
    ap.add_argument("--manual-approval", action="store_true")
    ap.add_argument("--ci", action="store_true")
    args = ap.parse_args()
    ensure_v37_dirs()

    summary_path = Path(args.summary) if args.summary else BACKTEST_TABLES["summary"]
    summary = _load_summary(summary_path)
    dedup_errors = validate_all()
    report = evaluate(summary, dedup_errors, manual_approval=args.manual_approval)
    if args.manual_approval:
        report["manual_approval"] = True

    out_json = Path(args.output_json) if args.output_json else V37_AUDIT / "v37_p4_tail_calibration_report.json"
    out_md = Path(args.output_md) if args.output_md else V37_AUDIT / "v37_p4_tail_calibration_report.md"
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    out_md.write_text(render_md(report), encoding="utf-8")
    print(json.dumps(report, indent=2))

    if args.ci:
        errors = ci_gate(report)
        if errors:
            print("CI gate failures:", file=sys.stderr)
            for e in errors:
                print(f"  - {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
