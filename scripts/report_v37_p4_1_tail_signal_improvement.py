#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V3.7-P4.1 diagnostic report — why rerank did not improve recall."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from eventflow_common import read_csv, write_csv
from report_v37_p4_tail_calibration import evaluate as evaluate_p4
from v37_common import (
    BACKTEST_TABLES,
    DIAGNOSTICS_TABLES,
    HISTORICAL_TABLES,
    V37_AUDIT,
    V37_VERSION,
    ensure_v37_dirs,
)
from validate_v37_normalized_dedup import validate_all
from v37_tail_diagnostics_common import (
    RANKING_MUTATION_FIELDS,
    covered_by_tail_pool,
    gate_interpretation,
    validate_missed_large_score_rows,
)
from v37_historical_common import classify_large_score


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _count_timeline_cases() -> int:
    if not HISTORICAL_TABLES["matches"].exists():
        return 0
    return sum(
        1 for r in read_csv(HISTORICAL_TABLES["matches"])
        if r.get("event_timeline_available") == "true"
        and r.get("egci_v2_quality", "") in ("real", "partial", "")
    )


def _labeling_valid() -> bool:
    if not HISTORICAL_TABLES["matches"].exists():
        return True
    for r in read_csv(HISTORICAL_TABLES["matches"]):
        line = r.get("actual_scoreline", "")
        if line in ("3-0", "0-3") and r.get("large_score_type") == "not_large_score":
            return False
        try:
            h, a = map(int, line.split("-"))
            cls = classify_large_score(h, a)
            if cls["is_large_score"] and r.get("large_score_type") == "not_large_score":
                return False
        except ValueError:
            continue
    return True


def _ranking_semantics_valid(backtest_path: Path) -> tuple[bool, dict]:
    rule_enabled = applied = mutation = 0
    invalid = False
    for bt in read_csv(backtest_path):
        audit_path = BACKTEST_TABLES["case_audit_dir"] / f"{bt['match_id']}.json"
        if not audit_path.exists():
            continue
        tail = json.loads(audit_path.read_text(encoding="utf-8")).get("v37_large_score_tail", {})
        if tail.get("safety_demotion_rule_enabled"):
            rule_enabled += 1
        if tail.get("safety_demotion_applied"):
            applied += 1
        if tail.get("ranking_mutation_applied"):
            mutation += 1
        if tail.get("ranking_mutation_applied") and tail.get("ranking_mutation_reason", "none") == "none":
            invalid = True
        if tail.get("tail_boost_level") == "none" and not tail.get("safety_demotion_applied"):
            if tail.get("ranking_mutation_applied"):
                invalid = True
    return not invalid, {
        "safety_demotion_rule_enabled_count": rule_enabled,
        "safety_demotion_applied_count": applied,
        "ranking_mutation_applied_count": mutation,
    }


def build_report(
    summary: dict,
    missed_rows: list[dict[str, str]],
    gate_rows: list[dict[str, str]],
    coverage_rows: list[dict[str, str]],
    signal_summary: dict,
    dedup_errors: list[str],
    ranking_stats: dict,
) -> dict:
    p4 = evaluate_p4(summary, dedup_errors)
    miss_reasons = Counter(r.get("primary_miss_reason", "") for r in missed_rows)
    large_n = int(summary.get("large_score_cases", 0))
    covered_n = sum(
        1 for r in read_csv(BACKTEST_TABLES["results"])
        if r.get("is_large_score") == "true"
        and covered_by_tail_pool(r.get("actual_scoreline", ""))
    ) if BACKTEST_TABLES["results"].exists() else 0
    coverage_rate = round(covered_n / max(large_n, 1), 4)

    top_gates = sorted(gate_rows, key=lambda x: -int(x.get("blocked_count", 0)))[:5]
    overblock = [
        g["gate_name"] for g in gate_rows
        if float(g.get("false_block_rate", 0)) >= 0.5 and int(g.get("blocked_count", 0)) >= 3
    ]

    missed_valid = True
    try:
        validate_missed_large_score_rows(missed_rows)
    except ValueError:
        missed_valid = False
    labeling_valid = _labeling_valid()
    rates_valid = all(
        float(g.get("false_block_rate", -1)) >= 0
        and float(g.get("true_block_rate", -1)) >= 0
        for g in gate_rows
    ) if gate_rows else True
    ranking_valid, _ = _ranking_semantics_valid(BACKTEST_TABLES["results"])

    diagnostic_semantics_clean = (
        missed_valid and labeling_valid and ranking_valid and rates_valid
    )

    hist_rows = read_csv(HISTORICAL_TABLES["matches"]) if HISTORICAL_TABLES["matches"].exists() else []
    timeline_cases = sum(1 for r in hist_rows if r.get("event_timeline_available") == "true")

    recommendations = []
    if miss_reasons.get("acg_quality_insufficient", 0) >= 3:
        recommendations.append("improve_egci_v2_real_coverage")
    if miss_reasons.get("guard_suppressed", 0) >= 2:
        recommendations.append("review_guard_attribution_not_threshold_tuning")
    if coverage_rate < 0.6:
        recommendations.append("extend_candidate_pool_for_4_2_and_open_game_high_total")
    if not recommendations:
        recommendations.append("continue_audit_only_monitoring")

    return {
        "version": "v37_p4_1_tail_diagnostics_clean",
        "diagnostic_cleanup_version": "v37_p4_1_cleanup",
        "system_version": V37_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "diagnostics_complete": True,
        "diagnostic_semantics_clean": diagnostic_semantics_clean,
        "missed_case_filter_valid": missed_valid,
        "large_score_labeling_valid": labeling_valid,
        "ranking_semantics_valid": ranking_valid,
        "gate_attribution_rates_valid": rates_valid,
        "safety_pass": p4["safety_pass"],
        "performance_pass": p4["performance_pass"],
        "rerank_only_allowed": False,
        "rerank_default_allowed": False,
        "sample_status": {
            "sample_size": int(summary.get("sample_size", 0)),
            "large_score_cases": large_n,
            "real_or_partial_event_timeline_cases": timeline_cases,
            "target_sample_size": 50,
        },
        "missed_large_score_analysis": {
            "missed_count": len(missed_rows),
            "missed_count_cleaned": len(missed_rows),
            "top_primary_miss_reasons": miss_reasons.most_common(5),
            "candidate_pool_coverage_rate": coverage_rate,
        },
        "cleanup_summary": {
            **ranking_stats,
            "top_overblocking_gates": overblock,
        },
        "gate_attribution": {
            "top_blocking_gates": [g["gate_name"] for g in top_gates],
            "potential_overblocking_gates": overblock,
        },
        "performance_metrics": {
            "large_score_top5_recall_delta": summary.get("large_score_top5_recall_delta"),
            "avg_rank_improvement": summary.get("avg_rank_improvement"),
            "candidate_pool_coverage_rate": coverage_rate,
            "missed_large_score_count": len(missed_rows),
            "guard_suppression_rate": round(
                int(summary.get("cold_guard_false_boost_count", 0)) / max(int(summary.get("sample_size", 1)), 1), 4,
            ),
        },
        "recommendations": list(dict.fromkeys(recommendations)),
        "decision": {
            "allowed_modes": ["audit_only"],
            "reason": "performance_not_yet_improved",
            "next_action": "expand_sample_and_review_gate_attribution",
            "no_lambda_mutation": True,
            "no_v2_probability_mutation": True,
            "no_adjusted_probability_mutation": True,
            "no_auto_betting": True,
        },
        "signal_summary": signal_summary,
        "dedup_errors": dedup_errors,
    }


def render_md(report: dict) -> str:
    ss = report["sample_status"]
    miss = report["missed_large_score_analysis"]
    gate = report["gate_attribution"]
    lines = [
        "# V3.7-P4.1 Tail Signal Improvement Report",
        "",
        f"**Version:** {report['version']} ({report['system_version']})",
        "",
        "## Sample",
        f"- Total: {ss['sample_size']} (target {ss['target_sample_size']})",
        f"- Large-score cases: {ss['large_score_cases']}",
        f"- Event timeline available: {ss['real_or_partial_event_timeline_cases']}",
        "",
        "## Missed large scores",
        f"- Missed count (rank > 5): {miss['missed_count']}",
        f"- Top miss reasons: {miss['top_primary_miss_reasons']}",
        f"- Candidate pool coverage: {miss['candidate_pool_coverage_rate']}",
        "",
        "## Gate attribution",
        f"- Top blocking gates: {gate['top_blocking_gates']}",
        f"- Potential overblocking: {gate['potential_overblocking_gates']}",
        "",
        "## Gates",
        f"- safety_pass: **{report['safety_pass']}**",
        f"- performance_pass: **{report['performance_pass']}**",
        f"- rerank_only_allowed: **{report['rerank_only_allowed']}**",
        "",
        "## Recommendations",
        *[f"- {r}" for r in report["recommendations"]],
        "",
        "**Do not tune thresholds on F35 alone.** Rerank remains audit_only.",
        "No λ mutation. No auto-betting.",
        "",
    ]
    return "\n".join(lines)


def ci_gate(report: dict) -> list[str]:
    errors: list[str] = []
    if report.get("rerank_only_allowed") and not report.get("performance_pass"):
        errors.append("rerank_only_allowed=true while performance_pass=false")
    if report.get("performance_pass") and report["sample_status"]["sample_size"] < 20:
        errors.append("performance_pass=true with sample_size < 20")
    if not report.get("diagnostic_semantics_clean"):
        errors.append("diagnostic_semantics_clean=false")
    if not report.get("missed_case_filter_valid"):
        errors.append("missed_large_score_cases filter invalid")
    if not report.get("large_score_labeling_valid"):
        errors.append("3-0 labeled as not_large_score")
    if not report.get("gate_attribution_rates_valid"):
        errors.append("gate attribution rates invalid")
    return errors


def main() -> None:
    ap = argparse.ArgumentParser(description="P4.1 tail signal improvement report")
    ap.add_argument("--backtest", default=str(BACKTEST_TABLES["results"]))
    ap.add_argument("--summary", default=str(BACKTEST_TABLES["summary"]))
    ap.add_argument("--missed", default=str(DIAGNOSTICS_TABLES["missed_cases"]))
    ap.add_argument("--gates", default=str(DIAGNOSTICS_TABLES["gate_attribution"]))
    ap.add_argument("--coverage", default=str(DIAGNOSTICS_TABLES["candidate_coverage"]))
    ap.add_argument("--output-json", default=str(V37_AUDIT / "v37_p4_1_tail_signal_improvement_report.json"))
    ap.add_argument("--output-md", default=str(V37_AUDIT / "v37_p4_1_tail_signal_improvement_report.md"))
    ap.add_argument("--ci", action="store_true")
    args = ap.parse_args()
    ensure_v37_dirs()

    summary = _load_json(Path(args.summary))
    missed = read_csv(Path(args.missed)) if Path(args.missed).exists() else []
    gates = read_csv(Path(args.gates)) if Path(args.gates).exists() else []
    coverage = read_csv(Path(args.coverage)) if Path(args.coverage).exists() else []
    signal_summary = _load_json(DIAGNOSTICS_TABLES["signal_summary"])
    dedup = validate_all()

    ranking_valid, ranking_stats = _ranking_semantics_valid(Path(args.backtest))
    report = build_report(summary, missed, gates, coverage, signal_summary, dedup, ranking_stats)
    Path(args.output_json).write_text(json.dumps(report, indent=2), encoding="utf-8")
    md = render_md(report)
    Path(args.output_md).write_text(md, encoding="utf-8")

    # ranking mutation audit
    mut_rows: list[dict[str, str]] = []
    for bt in read_csv(Path(args.backtest)):
        audit_path = BACKTEST_TABLES["case_audit_dir"] / f"{bt['match_id']}.json"
        if not audit_path.exists():
            continue
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        tail = audit.get("v37_large_score_tail", audit)
        mut_rows.append({
            "match_id": bt["match_id"],
            "tail_boost_level": tail.get("tail_boost_level", ""),
            "tail_boost_applied": str(tail.get("tail_boost_applied", False)).lower(),
            "safety_demotion_rule_enabled": str(tail.get("safety_demotion_rule_enabled", False)).lower(),
            "safety_demotion_applied": str(tail.get("safety_demotion_applied", False)).lower(),
            "ranking_mutation_applied": str(tail.get("ranking_mutation_applied", False)).lower(),
            "ranking_mutation_reason": tail.get("ranking_mutation_reason", "none"),
            "top3_before": ";".join(tail.get("top3_before", [])),
            "top3_after": ";".join(tail.get("top3_after", [])),
            "five_plus_in_top3_before": ";".join(tail.get("five_plus_in_top3_before", [])),
            "five_plus_in_top3_after": ";".join(tail.get("five_plus_in_top3_after", [])),
            "baseline_actual_rank": bt.get("baseline_actual_rank", ""),
            "rerank_actual_rank": bt.get("rerank_actual_rank", ""),
            "rank_delta": bt.get("rank_improvement", "0"),
        })
    write_csv(DIAGNOSTICS_TABLES["ranking_mutation"], mut_rows, RANKING_MUTATION_FIELDS)

    print(json.dumps(report, indent=2))
    if args.ci:
        errors = ci_gate(report)
        if errors:
            for e in errors:
                print(f"CI FAIL: {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
