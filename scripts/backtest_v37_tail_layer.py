#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P4 historical tail backtest — baseline vs rerank ranking metrics."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from eventflow_common import read_csv, read_json, write_csv
from v37_common import BACKTEST_TABLES, ensure_v37_dirs
from v37_historical_common import (
    BACKTEST_RESULT_FIELDS,
    context_from_case,
    is_large_tail_score,
    payload_from_case,
    rank_of_score,
    top_k_scores,
)
from v37_large_score_tail import apply_tail_to_payload
from v37_tail_diagnostics_common import covered_by_tail_pool, is_top3_forbidden


def _is_large_tail(score: str, min_goals: int = 3) -> bool:
    try:
        h, a = map(int, score.split("-"))
        return max(h, a) >= min_goals and h != a
    except ValueError:
        return False


def backtest_fixture(path: Path, actual_score: str = "", split: str = "") -> dict:
    """Regression fixture backtest (E34/F35/F36 dual-engine JSON)."""
    payload = read_json(path, {})
    mid = payload.get("match_id", path.stem)
    audit = apply_tail_to_payload(payload, mode="audit_only")["audit"]
    rerank = apply_tail_to_payload(payload, mode="rerank_only")
    ranking = rerank["payload"].get("final_fusion", {}).get("score_ranking", [])
    baseline_ranking = list(payload.get("final_fusion", {}).get("score_ranking", []))
    actual = actual_score or ""
    b_rank = rank_of_score(baseline_ranking, actual) if actual else 999
    r_rank = rank_of_score(ranking, actual) if actual else 999
    top3 = [r.get("score") for r in ranking[:3]]
    is_large = _is_large_tail(actual) if actual else False
    boosted = rerank["audit"]["v37_large_score_tail"]["boosted_scores"]
    false_fp = bool(boosted) and actual and not is_large
    five_viol = any(is_top3_forbidden(s) for s in top3)
    return {
        "match_id": mid,
        "source": "regression",
        "competition": "WC2026",
        "home_team": "",
        "away_team": "",
        "actual_scoreline": actual,
        "is_large_score": str(is_large).lower(),
        "baseline_actual_rank": str(b_rank),
        "rerank_actual_rank": str(r_rank),
        "rank_improvement": str(b_rank - r_rank),
        "baseline_top3": top_k_scores(baseline_ranking, 3),
        "rerank_top3": top_k_scores(ranking, 3),
        "baseline_top5": top_k_scores(baseline_ranking, 5),
        "rerank_top5": top_k_scores(ranking, 5),
        "tail_boost_level": audit["v37_large_score_tail"]["tail_boost_level"],
        "tail_false_positive": str(false_fp).lower(),
        "cold_guard_active": "false",
        "must_win_no_convert": "false",
        "deep_handicap_contra": "false",
        "guard_violation": str(five_viol).lower(),
        "five_goal_top3_violation": str(five_viol).lower(),
        "split": split,
    }


def _false_positive(rerank_top3: str, rerank_top5: str, is_large: bool) -> bool:
    if is_large:
        return False
    for part in (rerank_top3.split(";"), rerank_top5.split(";")):
        for score in part:
            if score and is_large_tail_score(score):
                return True
    return False


def _guard_violation(case: dict[str, str], audit: dict, rerank_ranking: list[dict]) -> tuple[bool, bool]:
    tail = audit.get("v37_large_score_tail", {})
    boosted = tail.get("boosted_scores", [])
    cold_fp = case.get("cold_guard_active") == "true" and bool(boosted)
    must_fp = case.get("must_win_no_convert") == "true" and bool(boosted)
    deep_fp = case.get("deep_handicap_contra") == "true" and bool(boosted)
    top3 = [r.get("score") for r in rerank_ranking[:3]]
    five_viol = any(is_top3_forbidden(s) for s in top3)
    guard = cold_fp or must_fp or deep_fp or five_viol
    return guard, five_viol


def backtest_case(case: dict[str, str]) -> tuple[dict[str, str], dict]:
    actual = case.get("actual_scoreline", "")
    is_large = case.get("is_large_score", "false") == "true"
    ctx = context_from_case(case)
    payload = payload_from_case(case)
    baseline_ranking = list(payload.get("final_fusion", {}).get("score_ranking", []))

    audit_result = apply_tail_to_payload(
        payload, mode="audit_only", context_override=ctx,
    )
    rerank_result = apply_tail_to_payload(
        payload, mode="rerank_only", context_override=ctx,
    )
    rerank_ranking = rerank_result["payload"].get("final_fusion", {}).get("score_ranking", [])

    b_rank = rank_of_score(baseline_ranking, actual)
    r_rank = rank_of_score(rerank_ranking, actual)
    guard, five_viol = _guard_violation(case, rerank_result["audit"], rerank_ranking)
    tail_level = audit_result["audit"]["v37_large_score_tail"]["tail_boost_level"]

    return {
        "match_id": case.get("match_id", ""),
        "source": case.get("source", ""),
        "competition": case.get("competition", ""),
        "home_team": case.get("home_team", ""),
        "away_team": case.get("away_team", ""),
        "actual_scoreline": actual,
        "is_large_score": str(is_large).lower(),
        "baseline_actual_rank": str(b_rank),
        "rerank_actual_rank": str(r_rank),
        "rank_improvement": str(b_rank - r_rank),
        "baseline_top3": top_k_scores(baseline_ranking, 3),
        "rerank_top3": top_k_scores(rerank_ranking, 3),
        "baseline_top5": top_k_scores(baseline_ranking, 5),
        "rerank_top5": top_k_scores(rerank_ranking, 5),
        "tail_boost_level": tail_level,
        "tail_false_positive": str(_false_positive(
            top_k_scores(rerank_ranking, 3),
            top_k_scores(rerank_ranking, 5),
            is_large,
        )).lower(),
        "cold_guard_active": case.get("cold_guard_active", "false"),
        "must_win_no_convert": case.get("must_win_no_convert", "false"),
        "deep_handicap_contra": case.get("deep_handicap_contra", "false"),
        "guard_violation": str(guard).lower(),
        "five_goal_top3_violation": str(five_viol).lower(),
    }, rerank_result["audit"]


def summarize(results: list[dict[str, str]]) -> dict:
    large = [r for r in results if r.get("is_large_score") == "true" and r.get("actual_scoreline")]
    non_large = [r for r in results if r.get("is_large_score") != "true" and r.get("actual_scoreline")]
    nn = max(len(non_large), 1)

    def top5_recall(rows: list[dict[str, str]], prefix: str) -> float:
        if not large:
            return 0.0
        hits = sum(
            1 for r in large
            if r.get("actual_scoreline", "") in r.get(f"{prefix}_top5", "").split(";")
        )
        return round(hits / len(large), 4)

    baseline_r5 = top5_recall(large, "baseline")
    rerank_r5 = top5_recall(large, "rerank")
    rerank_fp = sum(1 for r in non_large if r.get("tail_false_positive") == "true") / nn
    improvements = [int(r.get("rank_improvement", 0)) for r in results if r.get("actual_scoreline")]

    large_with_score = [r for r in large if r.get("actual_scoreline")]
    pool_covered = sum(
        1 for r in large_with_score if covered_by_tail_pool(r.get("actual_scoreline", ""))
    )
    missed = sum(1 for r in large_with_score if int(r.get("rerank_actual_rank", 999)) > 5)
    guarded = sum(
        1 for r in results
        if r.get("cold_guard_active") == "true" or r.get("must_win_no_convert") == "true"
        or r.get("deep_handicap_contra") == "true"
    )

    return {
        "sample_size": len(results),
        "large_score_cases": len(large),
        "non_large_score_cases": len(non_large),
        "baseline_large_score_top5_recall": baseline_r5,
        "rerank_large_score_top5_recall": rerank_r5,
        "large_score_top5_recall_delta": round(rerank_r5 - baseline_r5, 4),
        "tail_false_positive_rate": round(rerank_fp, 4),
        "tail_false_positive_delta": 0.0,
        "avg_rank_improvement": round(sum(improvements) / max(len(improvements), 1), 4),
        "candidate_pool_coverage_rate": round(pool_covered / max(len(large_with_score), 1), 4),
        "missed_large_score_count": missed,
        "guard_suppression_rate": round(guarded / max(len(results), 1), 4),
        "cold_guard_false_boost_count": sum(
            1 for r in results
            if r.get("cold_guard_active") == "true"
            and r.get("tail_boost_level", "none") not in ("none", "")
        ),
        "must_win_no_convert_false_boost_count": sum(
            1 for r in results
            if r.get("must_win_no_convert") == "true"
            and r.get("tail_boost_level", "none") not in ("none", "")
        ),
        "deep_handicap_false_boost_count": sum(
            1 for r in results
            if r.get("deep_handicap_contra") == "true"
            and r.get("tail_boost_level", "none") not in ("none", "")
        ),
        "five_goal_top3_violation_count": sum(
            1 for r in results if r.get("five_goal_top3_violation") == "true"
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def run_backtest(cases_path: Path, include_regression: bool = False, processed_dir: Path | None = None) -> tuple[list[dict[str, str]], dict, dict[str, dict]]:
    results: list[dict[str, str]] = []
    audits: dict[str, dict] = {}
    for c in read_csv(cases_path):
        if c.get("eligible_for_tail_backtest", "true") != "true":
            continue
        row, audit = backtest_case(c)
        results.append(row)
        audits[row["match_id"]] = audit
    if include_regression and processed_dir and processed_dir.exists():
        for path in sorted(processed_dir.glob("dual_engine_output_*_v37_test.json")):
            results.append(backtest_fixture(path))
    return results, summarize(results), audits


def main() -> None:
    ap = argparse.ArgumentParser(description="Backtest V3.7 tail layer")
    ap.add_argument("--cases", default="")
    ap.add_argument("--output", default="")
    ap.add_argument("--summary", default="")
    ap.add_argument("--processed-dir", default="")
    ap.add_argument("--include-regression", action="store_true")
    args = ap.parse_args()
    ensure_v37_dirs()
    root = Path(__file__).resolve().parents[1]
    cases = Path(args.cases) if args.cases else (
        BACKTEST_TABLES["results"].parent.parent / "historical" / "historical_tail_backtest_cases.csv"
    )
    proc = Path(args.processed_dir) if args.processed_dir else root / "database" / "eventflow" / "processed"

    results, summary, audits = run_backtest(cases, args.include_regression, proc)

    out_csv = Path(args.output) if args.output else BACKTEST_TABLES["results"]
    out_json = Path(args.summary) if args.summary else BACKTEST_TABLES["summary"]
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    write_csv(out_csv, results, BACKTEST_RESULT_FIELDS)
    out_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    audit_dir = BACKTEST_TABLES["case_audit_dir"]
    audit_dir.mkdir(parents=True, exist_ok=True)
    for mid, audit in audits.items():
        (audit_dir / f"{mid}.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
