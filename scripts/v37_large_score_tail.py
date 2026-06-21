#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V3.7-P2.2 large-score tail audit / re-ranking — no λ or probability mutation."""
from __future__ import annotations

import copy
from typing import Any, Mapping, Optional, Sequence

from eventflow_common import read_csv, snum
from scenario_realization_common import load_v37_features
from v37_common import (
    FEATURE_TABLES,
    TAIL_LAYER_VERSION,
    V37_TAIL_THRESHOLDS,
    clip,
    fnum,
)

from v37_tail_diagnostics_common import (
    BOOSTABLE_POOL,
    EXTREME_TAIL_LINES,
    MILD_BOOST_SCORES,
    MEDIUM_BOOST_SCORES,
    STRONG_BOOST_SCORES,
    TAIL_SCORELINE_BUCKETS,
    compute_tail_signal_score,
    is_top3_forbidden,
    scores_for_level,
    tail_scores_for_favorite,
)

EGCI_V2_OK = frozenset({"real", "partial"})
ACG_V2_OK = frozenset({"real", "partial"})
ACG_V2_BLOCK_ONLY = frozenset({"proxy_guarded", "proxy", "missing"})


def parse_score_home_fav(score: str) -> bool:
    try:
        h, a = map(int, score.split("-"))
        return h > a
    except ValueError:
        return True


# Backward-compatible aliases
TAIL_HOME_FAV = frozenset(s for s in BOOSTABLE_POOL if parse_score_home_fav(s))
TAIL_AWAY_FAV = frozenset(s for s in BOOSTABLE_POOL if not parse_score_home_fav(s))
MILD_SCORES = MILD_BOOST_SCORES
MEDIUM_SCORES = MEDIUM_BOOST_SCORES
STRONG_SCORES = STRONG_BOOST_SCORES
TOP3_FORBIDDEN = EXTREME_TAIL_LINES

TAIL_FEATURE_FIELDS = [
    "match_id", "favorite", "underdog", "favorite_acg", "egci", "egci_v2_quality",
    "acg_v2_quality", "underdog_fragility", "underdog_chase_pressure", "data_quality_score",
    "cold_guard_active", "deep_handicap_contra_flag", "must_win_no_convert_favorite",
    "eventflow_degraded", "confirmed_event_timeline", "tail_boost_level",
    "eligible_for_rerank", "block_reasons",
]


def _row_for_match(path: str, match_id: str) -> dict[str, str]:
    if not path:
        return {}
    return next((r for r in read_csv(path) if snum(r, "match_id") == match_id), {})


def _acg_v2_for_team(match_id: str, team: str) -> dict[str, str]:
    if not FEATURE_TABLES["acg_v2"].exists():
        return {}
    return next(
        (r for r in read_csv(FEATURE_TABLES["acg_v2"])
         if r["match_id"] == match_id and r["team"] == team),
        {},
    )


def load_p2_context(
    match_id: str,
    payload: Optional[Mapping[str, Any]] = None,
    *,
    context_override: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    if context_override:
        return dict(context_override)
    v37 = load_v37_features(match_id)
    egci_v1 = _row_for_match(str(FEATURE_TABLES["early_goal_cascade"]), match_id)
    egci_v2 = _row_for_match(str(FEATURE_TABLES["egci_v2"]), match_id)
    realization = _row_for_match(str(FEATURE_TABLES["realization"]), match_id)

    favorite = snum(v37, "favorite") or snum(egci_v1, "favorite")
    underdog = snum(v37, "underdog") or snum(egci_v1, "underdog")
    home = snum(realization, "home_team")
    away = snum(realization, "away_team")

    fav_acg_v1 = fnum(v37, "attack_conversion_home")
    if favorite == away:
        fav_acg_v1 = fnum(v37, "attack_conversion_away")

    acg_v2_row = _acg_v2_for_team(match_id, favorite) if favorite else {}
    acg_v2_quality = snum(acg_v2_row, "acg_v2_quality", "proxy")
    fav_acg = fnum(acg_v2_row, "acg_v2", 0.0) if acg_v2_quality in ACG_V2_OK else fav_acg_v1

    egci_v2_quality = snum(egci_v2, "egci_v2_quality", "proxy")
    egci_v2_val = fnum(egci_v2, "early_goal_cascade_index_v2") or fnum(egci_v2, "egci_v2")
    egci_v1_val = fnum(v37, "early_goal_cascade_index") or fnum(egci_v1, "early_goal_cascade_index")
    egci = egci_v2_val if egci_v2_quality in EGCI_V2_OK else egci_v1_val

    must_win_fav = bool(v37.get("must_win_no_convert_home"))
    if favorite == away:
        must_win_fav = bool(v37.get("must_win_no_convert_away"))
    if acg_v2_row and snum(acg_v2_row, "must_win_no_convert_v2") == "true":
        must_win_fav = True

    eventflow_degraded = bool(payload.get("eventflow_data_degraded")) if payload else False
    eventflow_ok = not eventflow_degraded

    timeline_count = int(fnum(egci_v2, "goal_timeline_count", 0))
    confirmed_timeline = egci_v2_quality == "real" and timeline_count >= 2

    return {
        "match_id": match_id,
        "home": home,
        "away": away,
        "favorite": favorite,
        "underdog": underdog,
        "favorite_acg": fav_acg,
        "favorite_acg_v1": fav_acg_v1,
        "acg_v2_quality": acg_v2_quality,
        "egci": egci,
        "egci_v2_quality": egci_v2_quality,
        "egci_v1": egci_v1_val,
        "underdog_fragility": fnum(egci_v1, "underdog_fragility_score"),
        "underdog_chase_pressure": fnum(egci_v1, "underdog_chase_pressure"),
        "data_quality_score": fnum(realization, "data_quality_score", 0.0),
        "cold_guard_active": bool(v37.get("cold_guard_active")),
        "deep_handicap_contra_flag": bool(v37.get("deep_handicap_contra_flag")),
        "must_win_no_convert_favorite": must_win_fav,
        "eventflow_degraded": eventflow_degraded,
        "eventflow_ok": eventflow_ok,
        "confirmed_event_timeline": confirmed_timeline,
        "loaded": bool(v37.get("loaded")),
    }


def evaluate_tail_level(ctx: Mapping[str, Any], th: Mapping[str, float]) -> dict[str, Any]:
    blockers: list[str] = []
    reasons: list[str] = []

    if fnum(ctx, "data_quality_score") < th["min_data_quality"]:
        blockers.append("data_quality_below_threshold")
    if ctx.get("cold_guard_active"):
        blockers.append("cold_guard_active")
    if ctx.get("deep_handicap_contra_flag"):
        blockers.append("deep_handicap_contra_flag")
    if ctx.get("must_win_no_convert_favorite"):
        blockers.append("must_win_no_convert_favorite")

    egci_q = snum(ctx, "egci_v2_quality", "proxy")
    if egci_q in ("proxy", "missing", ""):
        blockers.append("egci_v2_quality_proxy_or_missing")
    acg_q = snum(ctx, "acg_v2_quality", "proxy")
    if acg_q not in ACG_V2_OK:
        blockers.append("acg_v2_quality_not_real_or_partial")
    if ctx.get("eventflow_degraded") and egci_q != "real":
        blockers.append("eventflow_degraded_egci_not_real")

    if fnum(ctx, "favorite_acg") < th["acg_mild"]:
        blockers.append("favorite_acg_below_mild")
    if fnum(ctx, "egci") < th["egci_mild"]:
        blockers.append("egci_below_mild")

    frag = fnum(ctx, "underdog_fragility")
    chase = fnum(ctx, "underdog_chase_pressure")
    if frag < th.get("fragility_mild", 0.50):
        blockers.append("underdog_fragility_below_mild")

    if blockers:
        return {
            "tail_boost_level": "none",
            "eligible_for_rerank": False,
            "block_reasons": blockers,
            "trigger_reasons": reasons,
            "guard_suppression": any(
                b in blockers for b in (
                    "cold_guard_active", "deep_handicap_contra_flag",
                    "must_win_no_convert_favorite",
                )
            ),
        }

    acg = fnum(ctx, "favorite_acg")
    egci = fnum(ctx, "egci")
    level = "mild"
    if (
        acg >= th["acg_strong"]
        and egci >= th["egci_strong"]
        and frag >= th.get("fragility_strong", 0.70)
        and chase >= th.get("chase_strong", 0.65)
        and ctx.get("confirmed_event_timeline")
        and egci_q == "real"
    ):
        level = "strong"
        reasons.extend(["ACG_strong", "EGCI_strong", "fragility_strong", "event_timeline_confirmed"])
    elif (
        acg >= th["acg_medium"]
        and egci >= th["egci_medium"]
        and frag >= th.get("fragility_medium", 0.62)
        and chase >= th["chase_medium"]
    ):
        level = "medium"
        reasons.extend(["ACG_medium", "EGCI_medium", "chase_pressure"])
    else:
        reasons.extend(["ACG_mild", "EGCI_mild"])

    return {
        "tail_boost_level": level,
        "eligible_for_rerank": True,
        "block_reasons": [],
        "trigger_reasons": reasons,
        "guard_suppression": False,
    }


def compute_score_boost(
    score: str, level: str, favorite: str, home: str, max_boost: float, reasons: Sequence[str],
) -> tuple[float, list[str]]:
    allowed = tail_scores_for_favorite(favorite, home) & scores_for_level(level)
    if is_top3_forbidden(score) or score in EXTREME_TAIL_LINES:
        return 0.0, []
    if score not in allowed:
        return 0.0, []
    mult = {"mild": 0.5, "medium": 0.75, "strong": 1.0}.get(level, 0.0)
    return round(max_boost * mult, 4), list(reasons)


def _eligibility(ctx: Mapping[str, Any], th: Mapping[str, float], eval_result: Mapping[str, Any]) -> dict[str, bool]:
    return {
        "data_quality_ok": fnum(ctx, "data_quality_score") >= th["min_data_quality"],
        "eventflow_ok": bool(ctx.get("eventflow_ok")),
        "egci_real_ok": snum(ctx, "egci_v2_quality") in EGCI_V2_OK,
        "acg_ok": snum(ctx, "acg_v2_quality") in ACG_V2_OK,
        "underdog_fragility_ok": fnum(ctx, "underdog_fragility") >= th.get("fragility_mild", 0.50),
        "chase_pressure_ok": fnum(ctx, "underdog_chase_pressure") >= th.get("chase_medium", 0.55),
        "guard_suppression": bool(eval_result.get("guard_suppression")),
    }


def build_tail_feature_row(ctx: Mapping[str, Any], eval_result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "match_id": ctx["match_id"],
        "favorite": ctx.get("favorite", ""),
        "underdog": ctx.get("underdog", ""),
        "favorite_acg": round(fnum(ctx, "favorite_acg"), 4),
        "egci": round(fnum(ctx, "egci"), 4),
        "egci_v2_quality": snum(ctx, "egci_v2_quality"),
        "acg_v2_quality": snum(ctx, "acg_v2_quality"),
        "underdog_fragility": round(fnum(ctx, "underdog_fragility"), 4),
        "underdog_chase_pressure": round(fnum(ctx, "underdog_chase_pressure"), 4),
        "data_quality_score": round(fnum(ctx, "data_quality_score"), 4),
        "cold_guard_active": str(bool(ctx.get("cold_guard_active"))).lower(),
        "deep_handicap_contra_flag": str(bool(ctx.get("deep_handicap_contra_flag"))).lower(),
        "must_win_no_convert_favorite": str(bool(ctx.get("must_win_no_convert_favorite"))).lower(),
        "eventflow_degraded": str(bool(ctx.get("eventflow_degraded"))).lower(),
        "confirmed_event_timeline": str(bool(ctx.get("confirmed_event_timeline"))).lower(),
        "tail_boost_level": eval_result["tail_boost_level"],
        "eligible_for_rerank": str(bool(eval_result["eligible_for_rerank"])).lower(),
        "block_reasons": ";".join(eval_result.get("block_reasons", [])),
    }


def _ranking_snapshot(ranking: list[dict]) -> list[dict[str, Any]]:
    return [
        {"score": r.get("score"), "rank": r.get("rank"), "fusion_ranking_score": r.get("fusion_ranking_score")}
        for r in ranking[:10]
    ]


def _sorted_top3(adjusted: list[dict[str, Any]]) -> list[str]:
    ranked = sorted(
        adjusted,
        key=lambda r: (
            -fnum(r, "v37_tail_adjusted_ranking_score", fnum(r, "fusion_ranking_score")),
            -fnum(r, "v2_scoreline_probability"),
        ),
    )
    return [snum(r, "score") for r in ranked[:3]]


def _demote_forbidden_top3(adjusted: list[dict[str, Any]]) -> tuple[list[str], bool]:
    """Demote 5+ scorelines from Top3; return (suppressed, applied)."""
    if not adjusted:
        return [], False
    sort_key = lambda r: (
        -fnum(r, "v37_tail_adjusted_ranking_score", fnum(r, "fusion_ranking_score")),
        -fnum(r, "v2_scoreline_probability"),
    )
    adjusted.sort(key=sort_key)
    top3_initial = _sorted_top3(adjusted)
    five_before = [s for s in top3_initial if is_top3_forbidden(s)]
    if not five_before:
        return [], False

    suppressed: list[str] = []
    demoted: set[str] = set()
    for _ in range(len(adjusted)):
        adjusted.sort(key=sort_key)
        forbidden_in_top3 = [s for s in _sorted_top3(adjusted) if is_top3_forbidden(s)]
        if not forbidden_in_top3:
            break
        non_forbidden = [
            fnum(r, "v37_tail_adjusted_ranking_score", fnum(r, "fusion_ranking_score", 0))
            for r in adjusted
            if not is_top3_forbidden(snum(r, "score"))
        ]
        floor = (min(non_forbidden) * 0.01) if non_forbidden else 0.0
        for score in forbidden_in_top3:
            if score in demoted:
                continue
            for row in adjusted:
                if snum(row, "score") != score:
                    continue
                row.setdefault(
                    "original_fusion_ranking_score",
                    fnum(row, "original_fusion_ranking_score", fnum(row, "fusion_ranking_score")),
                )
                row["fusion_ranking_score"] = floor
                row["v37_tail_adjusted_ranking_score"] = floor
                row["v37_tail_boost"] = 0.0
                row["tail_adjustment_reason"] = ["five_goal_top3_safety_demotion"]
                suppressed.append(score)
                demoted.add(score)

    adjusted.sort(key=sort_key)
    top3_after = _sorted_top3(adjusted)
    five_after = [s for s in top3_after if is_top3_forbidden(s)]
    applied = bool(five_before) and not bool(five_after)
    return suppressed, applied


def apply_tail_to_payload(
    payload: dict[str, Any],
    *,
    mode: str = "audit_only",
    max_tail_boost: float = V37_TAIL_THRESHOLDS["max_tail_boost_default"],
    min_data_quality: float = V37_TAIL_THRESHOLDS["min_data_quality"],
    disable_on_cold_guard: bool = True,
    disable_on_must_win_no_convert: bool = True,
    context_override: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    th = dict(V37_TAIL_THRESHOLDS)
    th["min_data_quality"] = min_data_quality

    original = payload
    out = copy.deepcopy(payload) if mode == "rerank_only" else payload
    match_id = snum(original, "match_id")
    ctx = load_p2_context(match_id, original, context_override=context_override)

    if disable_on_cold_guard and ctx.get("cold_guard_active"):
        ctx = dict(ctx)
        ctx["_force_block"] = True
    if disable_on_must_win_no_convert and ctx.get("must_win_no_convert_favorite"):
        ctx = dict(ctx)
        ctx["_force_block"] = True

    eval_result = evaluate_tail_level(ctx, th)
    if ctx.get("_force_block"):
        eval_result = {
            **eval_result,
            "tail_boost_level": "none",
            "eligible_for_rerank": False,
            "block_reasons": list(dict.fromkeys(
                eval_result.get("block_reasons", []) + ["guard_suppression_enabled"]
            )),
            "trigger_reasons": [],
            "guard_suppression": True,
        }

    favorite = snum(ctx, "favorite")
    home = snum(ctx, "home")
    level = eval_result["tail_boost_level"]
    reasons = eval_result.get("trigger_reasons", [])

    ranking_orig = list(original.get("final_fusion", {}).get("score_ranking", []))
    scoreline_before = _ranking_snapshot(ranking_orig)

    candidate_tail = sorted(
        tail_scores_for_favorite(favorite, home) & scores_for_level(level)
        if level != "none" else set(),
    )

    boosted: list[str] = []
    suppressed: list[str] = []
    safety_demotion_applied = False
    safety_demotion_rule_enabled = mode == "rerank_only"
    top3_before_rerank: list[str] = []
    top3_after_rerank: list[str] = []
    prob_engine = original.get("probability_engine", {})
    lambda_before = {"home": prob_engine.get("lambda_home"), "away": prob_engine.get("lambda_away")}

    if mode == "rerank_only" and ranking_orig:
        ranking = copy.deepcopy(ranking_orig)
        adjusted: list[dict[str, Any]] = []
        if eval_result["eligible_for_rerank"]:
            for row in ranking:
                score = snum(row, "score")
                orig = fnum(row, "fusion_ranking_score", fnum(row, "v2_scoreline_probability"))
                boost, boost_reasons = compute_score_boost(score, level, favorite, home, max_tail_boost, reasons)
                adj = round(clip(orig + boost, 0.0, 1.0), 4)
                new_row = dict(row)
                new_row["original_fusion_ranking_score"] = round(orig, 4)
                new_row["v37_tail_boost"] = boost
                new_row["v37_tail_adjusted_ranking_score"] = adj
                if boost > 0:
                    new_row["fusion_ranking_score"] = adj
                    new_row["tail_adjustment_reason"] = boost_reasons
                    boosted.append(score)
                else:
                    new_row["tail_adjustment_reason"] = []
                adjusted.append(new_row)
            adjusted.sort(
                key=lambda r: (
                    -fnum(r, "v37_tail_adjusted_ranking_score", fnum(r, "fusion_ranking_score")),
                    -fnum(r, "v2_scoreline_probability"),
                ),
            )
        else:
            for row in ranking:
                orig = fnum(row, "fusion_ranking_score", fnum(row, "v2_scoreline_probability"))
                new_row = dict(row)
                new_row["original_fusion_ranking_score"] = round(orig, 4)
                new_row["v37_tail_boost"] = 0.0
                new_row["v37_tail_adjusted_ranking_score"] = round(orig, 4)
                new_row["tail_adjustment_reason"] = []
                adjusted.append(new_row)

        top3_before_rerank = _sorted_top3(adjusted)
        demoted, safety_demotion_applied = _demote_forbidden_top3(adjusted)
        suppressed.extend(demoted)
        top3_after_rerank = _sorted_top3(adjusted)
        for i, row in enumerate(adjusted, start=1):
            row["rank"] = i
        out.setdefault("final_fusion", {})["score_ranking"] = adjusted

    scoreline_after = _ranking_snapshot(
        out.get("final_fusion", {}).get("score_ranking", ranking_orig)
    )
    lambda_after = {
        "home": out.get("probability_engine", {}).get("lambda_home"),
        "away": out.get("probability_engine", {}).get("lambda_away"),
    }

    block_reasons = eval_result.get("block_reasons", [])
    if level == "none" and not block_reasons:
        block_reasons = ["no_tail_level_triggered"]

    v2_before = {
        r.get("score"): r.get("v2_scoreline_probability")
        for r in ranking_orig
    }
    v2_after_rows = out.get("final_fusion", {}).get("score_ranking", ranking_orig)
    v2_unchanged = all(
        r.get("v2_scoreline_probability") == v2_before.get(r.get("score"))
        for r in v2_after_rows
        if r.get("score") in v2_before
    )

    signal = compute_tail_signal_score(ctx, th)
    tail_boost_applied = bool(boosted)
    if mode != "rerank_only":
        safety_demotion_rule_enabled = False
        safety_demotion_applied = False
        top3_before_rerank = []
        top3_after_rerank = []
    ranking_mutation_applied = (
        mode == "rerank_only" and scoreline_before != scoreline_after
    )
    if mode == "audit_only":
        ranking_mutation_applied = False
    mutation_reason = "none"
    if ranking_mutation_applied:
        if tail_boost_applied and safety_demotion_applied:
            mutation_reason = "tail_boost_and_five_goal_top3_safety_demotion"
        elif tail_boost_applied:
            mutation_reason = "tail_boost"
        elif safety_demotion_applied:
            mutation_reason = "five_goal_top3_safety_demotion"

    audit = {
        "tail_layer_version": TAIL_LAYER_VERSION,
        "match_id": match_id,
        "mode": mode,
        "no_lambda_mutation": lambda_before == lambda_after,
        "no_v2_probability_mutation": v2_unchanged,
        "lambda_unchanged": lambda_before,
        "eligibility": _eligibility(ctx, th, eval_result),
        "block_reasons": block_reasons,
        "candidate_tail_scorelines": candidate_tail,
        "tail_scoreline_buckets": {k: sorted(v) for k, v in TAIL_SCORELINE_BUCKETS.items()},
        "forbidden_top3_scorelines": sorted(s for s in EXTREME_TAIL_LINES if is_top3_forbidden(s)),
        "scoreline_before": scoreline_before,
        "scoreline_after": scoreline_after,
        "tail_signal_score": signal["tail_signal_score"],
        "tail_signal_components": signal["tail_signal_components"],
        "delta_summary": {
            "ranking_changed": scoreline_before != scoreline_after,
            "boosted_scores": boosted,
            "suppressed_scores": suppressed,
            "max_boost_applied": max_tail_boost,
        },
        "context": {
            "favorite_acg": round(fnum(ctx, "favorite_acg"), 4),
            "favorite_acg_v1": round(fnum(ctx, "favorite_acg_v1"), 4),
            "acg_v2_quality": snum(ctx, "acg_v2_quality"),
            "egci": round(fnum(ctx, "egci"), 4),
            "egci_v2_quality": snum(ctx, "egci_v2_quality"),
            "data_quality_score": round(fnum(ctx, "data_quality_score"), 4),
            "underdog_fragility": round(fnum(ctx, "underdog_fragility"), 4),
            "underdog_chase_pressure": round(fnum(ctx, "underdog_chase_pressure"), 4),
            "confirmed_event_timeline": bool(ctx.get("confirmed_event_timeline")),
        },
        "evaluation": eval_result,
        "v37_large_score_tail": {
            "enabled": True,
            "mode": mode,
            "tail_boost_level": level,
            "tail_boost_applied": tail_boost_applied,
            "safety_demotion_rule_enabled": safety_demotion_rule_enabled,
            "safety_demotion_applied": safety_demotion_applied,
            "ranking_mutation_applied": ranking_mutation_applied,
            "ranking_mutation_reason": mutation_reason,
            "ranking_mutation_allowed": mode == "rerank_only",
            "top3_before": top3_before_rerank,
            "top3_after": top3_after_rerank,
            "five_plus_in_top3_before": [s for s in top3_before_rerank if is_top3_forbidden(s)],
            "five_plus_in_top3_after": [s for s in top3_after_rerank if is_top3_forbidden(s)],
            "boosted_scores": boosted,
            "suppressed_scores": suppressed,
            "reason": reasons + block_reasons,
            "no_lambda_mutation": True,
            "no_v2_probability_mutation": v2_unchanged,
            **signal,
        },
    }

    if mode == "rerank_only":
        out["v37_large_score_tail"] = audit["v37_large_score_tail"]

    return {"payload": out, "audit": audit, "feature_row": build_tail_feature_row(ctx, eval_result)}
