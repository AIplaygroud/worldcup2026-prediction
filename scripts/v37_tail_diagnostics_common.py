#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V3.7-P4.1 tail signal diagnostics — buckets, coverage, miss attribution."""
from __future__ import annotations

from typing import Any, Mapping

from v37_common import V37_TAIL_THRESHOLDS, clip, fnum, snum

TAIL_SCORELINE_BUCKETS: dict[str, frozenset[str]] = {
    "favorite_clean_blowout": frozenset({"3-0", "4-0", "0-3", "0-4"}),
    "favorite_btts_blowout": frozenset({"3-1", "4-1", "4-2", "1-3", "1-4", "2-4"}),
    "open_game_high_total": frozenset({"3-2", "4-2", "2-3", "2-4", "3-3", "4-3", "3-4"}),
    "extreme_tail_warning": frozenset({
        "5-0", "5-1", "5-2", "6-0", "6-1", "7-0", "7-1",
        "0-5", "1-5", "2-5", "0-6", "1-6", "0-7", "1-7",
    }),
}

LEGACY_TAIL_POOL = (
    TAIL_SCORELINE_BUCKETS["favorite_clean_blowout"]
    | TAIL_SCORELINE_BUCKETS["favorite_btts_blowout"]
)

BOOSTABLE_POOL = LEGACY_TAIL_POOL | TAIL_SCORELINE_BUCKETS["open_game_high_total"]

MILD_BOOST_SCORES = frozenset({"3-0", "3-1", "0-3", "1-3"})
MEDIUM_BOOST_SCORES = MILD_BOOST_SCORES | frozenset({"4-0", "4-1", "0-4", "1-4", "4-2", "2-4"})
STRONG_BOOST_SCORES = MEDIUM_BOOST_SCORES | frozenset({"3-2", "2-3", "3-3", "4-3", "3-4"})

EXTREME_TAIL_LINES = TAIL_SCORELINE_BUCKETS["extreme_tail_warning"]

TOP3_FORBIDDEN_LEGACY = frozenset({"5-0", "5-1", "0-5", "1-5"})

MISSED_CASE_FIELDS = [
    "match_id", "source", "competition", "home_team", "away_team", "actual_scoreline",
    "is_large_score", "large_score_type", "baseline_actual_rank", "rerank_actual_rank", "rank_delta",
    "tail_boost_level", "tail_boost_applied", "safety_demotion_applied", "ranking_mutation_reason",
    "candidate_pool_contains_actual", "nearest_tail_candidate", "egci_v2", "egci_v2_quality",
    "acg_favorite", "acg_v2_quality", "underdog_fragility", "chase_pressure",
    "cold_guard_active", "must_win_no_convert", "deep_handicap_contra", "eventflow_degraded",
    "block_reasons", "primary_miss_reason", "secondary_miss_reason",
]

GATE_ATTRIBUTION_FIELDS = [
    "gate_name", "blocked_count", "blocked_large_score_count", "blocked_non_large_score_count",
    "false_block_rate", "true_block_rate", "avg_actual_total_goals", "interpretation", "examples",
]

RANKING_MUTATION_FIELDS = [
    "match_id", "tail_boost_level", "tail_boost_applied",
    "safety_demotion_rule_enabled", "safety_demotion_applied",
    "ranking_mutation_applied", "ranking_mutation_reason",
    "top3_before", "top3_after", "five_plus_in_top3_before", "five_plus_in_top3_after",
    "baseline_actual_rank", "rerank_actual_rank", "rank_delta",
]


def is_true_large_score_row(row: Mapping[str, Any]) -> bool:
    """True large-score label — excludes polluted not_large_score rows."""
    flag = str(row.get("is_large_score", "")).lower()
    if flag not in ("true", "1"):
        return False
    lst = str(row.get("large_score_type", "")).strip()
    return lst != "" and lst != "not_large_score"


def validate_missed_large_score_rows(rows: list[dict[str, str]]) -> None:
    for row in rows:
        if not is_true_large_score_row(row):
            raise ValueError(
                f"missed_large_score_cases pollution: match_id={row.get('match_id')} "
                f"is_large_score={row.get('is_large_score')} "
                f"large_score_type={row.get('large_score_type')}"
            )
        if not row.get("primary_miss_reason"):
            raise ValueError(f"missed case missing primary_miss_reason: {row.get('match_id')}")


def gate_interpretation(false_block_rate: float, true_block_rate: float) -> str:
    if false_block_rate >= 0.5:
        return "potential_overblocking_large_scores"
    if true_block_rate >= 0.7:
        return "mostly_correct_suppression"
    return "mixed"


COVERAGE_FIELDS = [
    "actual_scoreline", "count", "covered_by_current_tail_pool",
    "recommended_bucket", "notes",
]


def parse_score(score: str) -> tuple[int, int] | None:
    try:
        h, a = score.split("-")
        return int(h), int(a)
    except (ValueError, AttributeError):
        return None


def is_top3_forbidden(score: str) -> bool:
    """Any 5+ goal line cannot enter Top3."""
    parsed = parse_score(score)
    if not parsed:
        return False
    return max(parsed) >= 5


def is_extreme_tail(score: str) -> bool:
    if score in EXTREME_TAIL_LINES:
        return True
    parsed = parse_score(score)
    if not parsed:
        return False
    return max(parsed) >= 5


def tail_home_fav() -> frozenset[str]:
    return frozenset(s for s in BOOSTABLE_POOL if s.startswith(tuple(f"{h}-" for h in range(8))))


def tail_scores_for_favorite(favorite: str, home: str) -> frozenset[str]:
    out: set[str] = set()
    for score in BOOSTABLE_POOL:
        parsed = parse_score(score)
        if not parsed:
            continue
        h, a = parsed
        if favorite == home and h > a:
            out.add(score)
        elif favorite != home and a > h:
            out.add(score)
    return frozenset(out)


def scores_for_level(level: str) -> frozenset[str]:
    if level == "strong":
        return STRONG_BOOST_SCORES
    if level == "medium":
        return MEDIUM_BOOST_SCORES
    if level == "mild":
        return MILD_BOOST_SCORES
    return frozenset()


def recommended_bucket(scoreline: str) -> str:
    for bucket, scores in TAIL_SCORELINE_BUCKETS.items():
        if scoreline in scores:
            return bucket
    parsed = parse_score(scoreline)
    if not parsed:
        return "not_supported"
    h, a = parsed
    if max(h, a) >= 5:
        return "extreme_tail_warning"
    if h + a >= 4 and h != a:
        return "open_game_high_total"
    return "not_supported"


def covered_by_tail_pool(scoreline: str) -> bool:
    return scoreline in LEGACY_TAIL_POOL or scoreline in TAIL_SCORELINE_BUCKETS["open_game_high_total"]


def nearest_tail_candidate(scoreline: str, favorite: str, home: str) -> str:
    pool = sorted(tail_scores_for_favorite(favorite, home) | LEGACY_TAIL_POOL)
    parsed = parse_score(scoreline)
    if not parsed:
        return ""
    target = sum(parsed)
    best = ""
    best_dist = 999
    for s in pool:
        p = parse_score(s)
        if not p:
            continue
        dist = abs(sum(p) - target) + abs(p[0] - parsed[0]) + abs(p[1] - parsed[1])
        if dist < best_dist:
            best_dist = dist
            best = s
    return best


def compute_tail_signal_score(ctx: Mapping[str, Any], th: Mapping[str, float] | None = None) -> dict[str, Any]:
    th = th or V37_TAIL_THRESHOLDS
    egci = clip(fnum(ctx, "egci") / max(th["egci_strong"], 0.01), 0, 1)
    acg = clip(fnum(ctx, "favorite_acg") / max(th["acg_strong"], 0.01), 0, 1)
    frag = clip(fnum(ctx, "underdog_fragility") / max(th.get("fragility_strong", 0.70), 0.01), 0, 1)
    chase = clip(fnum(ctx, "underdog_chase_pressure") / max(th.get("chase_strong", 0.65), 0.01), 0, 1)
    open_game = clip((egci + frag) / 2, 0, 1)
    guard_penalty = 0.0
    if ctx.get("cold_guard_active"):
        guard_penalty += 0.4
    if ctx.get("must_win_no_convert_favorite"):
        guard_penalty += 0.35
    if ctx.get("deep_handicap_contra_flag"):
        guard_penalty += 0.25
    if ctx.get("eventflow_degraded"):
        guard_penalty += 0.15
    guard_penalty = clip(guard_penalty, 0, 1)
    score = clip(
        0.25 * egci + 0.25 * acg + 0.20 * frag + 0.15 * chase + 0.10 * open_game - 0.25 * guard_penalty,
        0, 1,
    )
    return {
        "tail_signal_score": round(score, 4),
        "tail_signal_components": {
            "egci": round(egci, 4),
            "acg": round(acg, 4),
            "fragility": round(frag, 4),
            "chase_pressure": round(chase, 4),
            "open_game": round(open_game, 4),
            "guard_penalty": round(guard_penalty, 4),
        },
    }


def classify_case_outcome(
    is_large: bool,
    rerank_rank: int,
    tail_boost_applied: bool,
    false_positive: bool,
) -> str:
    if is_large and rerank_rank <= 5 and tail_boost_applied:
        return "true_positive"
    if is_large and rerank_rank > 5:
        return "missed_positive"
    if not is_large and false_positive:
        return "false_positive"
    return "true_negative"


def primary_miss_reason(
    case: Mapping[str, str],
    audit: Mapping[str, Any],
    th: Mapping[str, float] | None = None,
) -> tuple[str, str]:
    th = th or V37_TAIL_THRESHOLDS
    blockers = audit.get("block_reasons", [])
    if isinstance(blockers, str):
        blockers = [b for b in blockers.split(";") if b]

    actual = snum(case, "actual_scoreline")
    if case.get("cold_guard_active") == "true" or case.get("must_win_no_convert") == "true":
        return "guard_suppressed", "cold_or_must_win"
    if case.get("deep_handicap_contra") == "true":
        return "guard_suppressed", "deep_handicap"

    egci_q = snum(case, "egci_v2_quality", "proxy")
    if egci_q not in ("real", "partial"):
        return "egci_quality_insufficient", egci_q
    if fnum(case, "egci_v2") < th["egci_mild"]:
        return "egci_score_below_threshold", ""

    acg_q = snum(case, "acg_v2_quality", "proxy")
    if acg_q not in ("real", "partial"):
        return "acg_quality_insufficient", acg_q
    if fnum(case, "acg_favorite") < th["acg_mild"]:
        return "acg_score_below_threshold", ""

    if case.get("eventflow_degraded") == "true":
        return "eventflow_degraded_proxy_block", ""

    if fnum(case, "data_quality_score") < th["min_data_quality"]:
        return "data_quality_low", ""

    if not covered_by_tail_pool(actual):
        if is_extreme_tail(actual):
            return "five_goal_safety_demotion", "extreme_tail_not_boostable"
        return "candidate_pool_missing_actual", recommended_bucket(actual)

    baseline_rank = int(case.get("baseline_actual_rank") or 999)
    if baseline_rank > 15:
        return "baseline_rank_too_low", ""

    if "guard_suppression_enabled" in blockers:
        return "guard_suppressed", "enabled"

    return "unknown", ""


def gate_from_block_reason(reason: str) -> str:
    mapping = {
        "data_quality_below_threshold": "data_quality",
        "cold_guard_active": "cold_guard",
        "deep_handicap_contra_flag": "deep_handicap_contra",
        "must_win_no_convert_favorite": "must_win_no_convert",
        "eventflow_degraded_egci_not_real": "eventflow_degraded_egci_proxy",
        "egci_v2_quality_proxy_or_missing": "egci_quality",
        "egci_below_mild": "egci_threshold",
        "acg_v2_quality_not_real_or_partial": "acg_quality",
        "favorite_acg_below_mild": "acg_threshold",
        "underdog_fragility_below_mild": "underdog_fragility",
        "guard_suppression_enabled": "cold_guard",
    }
    return mapping.get(reason, reason)
