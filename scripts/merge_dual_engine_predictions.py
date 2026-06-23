#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Merge Probability Engine and EventFlow Engine outputs with score semantics clarified."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from eventflow_common import EVENTFLOW_DB, read_csv, read_json, write_csv, write_json, fnum, snum, normalize_weights
from eventflow_htft import (
    resolve_match_id,
    summarize_data_quality,
    count_prematch_evidence,
    resolve_source_notes_path,
    resolve_eventflow_merge_attachments,
    validate_htft_output,
    halftime_layer_status,
)
from scenario_realization_common import load_v37_features
from eventflow_dynamic_weight import AUTO_MODE, MODE_CHOICES, compute_dynamic_fusion_profile

# Import compatibility for older tests/integrations. Runtime fusion no longer
# reads this mapping; all legacy names resolve through auto_dynamic instead.
MODE = {
    "safe": (0.80, 0.20),
    "balanced": (0.80, 0.20),
    "hit_hunting": (0.80, 0.20),
}

FUSION_SCORE_NOTE = (
    "fusion_ranking_score is not a calibrated probability; "
    "v2_scoreline_probability comes from V2 Dixon-Coles; "
    "eventflow_ranking_score is a non-probabilistic EventFlow ranking score."
)

DEGRADATION_REASONS_PROB_ONLY = {
    "missing_scenario_rows",
    "fallback_ratio_too_high",
    "no_prematch_evidence",
}


def classify_eventflow_contribution(
    ev_rows: List[Dict[str, Any]],
    ev_by_score: Dict[str, Dict[str, Any]],
    score: str,
) -> str:
    """Clarify EventFlow=0 semantics: active row vs missing-match fallback vs missing-score fallback."""
    if not ev_rows:
        return "missing_match_fallback_zero"
    if score not in ev_by_score:
        return "missing_score_fallback_zero"
    ev = ev_by_score[score]
    rank = (
        fnum(ev, "eventflow_ranking_score")
        or fnum(ev, "eventflow_score")
        or fnum(ev, "event_probability")
    )
    if rank > 0:
        return "active"
    if snum(ev, "score"):
        return "active_zero_rank"
    return "missing_score_fallback_zero"


def row_home(r: Dict[str, str]) -> str:
    return snum(r, "home") or snum(r, "home_team")


def row_away(r: Dict[str, str]) -> str:
    return snum(r, "away") or snum(r, "away_team")


def filter_rows(rows: List[Dict[str, str]], match_id: str, home: str, away: str) -> List[Dict[str, str]]:
    out = rows
    if match_id:
        out = [r for r in out if snum(r, "match_id") == match_id]
    if home:
        out = [r for r in out if row_home(r) == home and row_away(r) == away]
    return out


def total_goals_fusion(scores: List[str]) -> str:
    if not scores:
        return "未知"
    totals = []
    for s in scores:
        try:
            h, a = s.split("-")
            totals.append(int(h) + int(a))
        except Exception:
            pass
    if not totals:
        return "未知"
    lo, hi = min(totals), max(totals)
    return f"{lo}球" if lo == hi else f"{lo}/{hi}球优先，防{hi + 1}球"


def confidence_label(prob_rows: List[Dict[str, str]], activated_n: int, dq: Dict[str, Any]) -> str:
    if not prob_rows or activated_n < 3:
        return "低"
    if dq.get("real_data_ratio", 0) < 0.3:
        return "低"
    if activated_n >= 4 and dq.get("real_data_ratio", 0) >= 0.4:
        return "中高"
    return "中"


def load_source_fusion(match_id: str) -> Dict[str, Any]:
    events = filter_rows(read_csv(EVENTFLOW_DB / "source_signal_events.csv"), match_id, "", "")
    claims = filter_rows(read_csv(EVENTFLOW_DB / "source_signal_claims.csv"), match_id, "", "")
    fused = filter_rows(read_csv(EVENTFLOW_DB / "eventflow_fused_evidence.csv"), match_id, "", "")
    prematch_summary = read_csv(EVENTFLOW_DB / "eventflow_prematch_evidence_summary.csv")
    prematch_summary = [r for r in prematch_summary if not match_id or snum(r, "match_id") == match_id]
    excluded_rows = read_csv(EVENTFLOW_DB / "eventflow_excluded_evidence.csv")
    excluded_rows = [r for r in excluded_rows if not match_id or snum(r, "match_id") == match_id]
    iso = count_prematch_evidence(match_id)

    from eventflow_source_common import prematch_eligibility

    by_grade: Dict[str, List[Dict[str, Any]]] = {"A": [], "B": [], "C": []}
    for c in claims:
        g = snum(c, "evidence_grade", "C")
        entry = {
            "signal_type": snum(c, "signal_type"),
            "summary": snum(c, "canonical_signal"),
            "confidence": fnum(c, "final_confidence"),
            "sources": snum(c, "sources"),
            "evidence_grade": g,
            "evidence_partition": snum(c, "evidence_partition"),
            "exclusion_reason": snum(c, "exclusion_reason"),
            "single_source_penalty": fnum(c, "single_source_penalty") if snum(c, "single_source_penalty") else None,
            "agreement_count": int(float(snum(c, "agreement_count") or 0)),
            "conflict_count": int(float(snum(c, "conflict_count") or 0)),
        }
        by_grade.setdefault(g, []).append(entry)

    conflicts = [snum(c, "conflict_note") for c in claims if snum(c, "conflict_note")]

    def _event_summary(e: Dict[str, str]) -> Dict[str, Any] | None:
        elig = prematch_eligibility(e)
        if elig.get("evidence_partition") == "excluded_non_prematch":
            return None
        return {
            "source_id": snum(e, "source_id"),
            "source_url": snum(e, "source_url"),
            "signal_type": snum(e, "signal_type"),
            "summary": snum(e, "summary"),
            "confidence": fnum(e, "raw_confidence"),
            "evidence_usage": snum(e, "evidence_usage"),
            "available_before_kickoff": snum(e, "available_before_kickoff"),
            "evidence_partition": elig.get("evidence_partition", ""),
            "evidence_grade": next(
                (
                    snum(c, "evidence_grade")
                    for c in claims
                    if snum(c, "signal_type") == snum(e, "signal_type")
                    and snum(c, "sources") == snum(e, "source_id")
                ),
                "C",
            ),
        }

    prematch_source_summary = [s for s in (_event_summary(e) for e in events) if s]
    excluded_evidence_summary = [
        {
            "source_id": snum(e, "source_id"),
            "signal_type": snum(e, "signal_type"),
            "summary": snum(e, "summary"),
            "evidence_usage": snum(e, "evidence_usage"),
            "exclusion_reason": prematch_eligibility(e).get("exclusion_reason", ""),
        }
        for e in events
        if prematch_eligibility(e).get("evidence_partition") == "excluded_non_prematch"
    ]
    excluded_evidence_summary.extend([
        {
            "signal_type": snum(r, "signal_type"),
            "summary": snum(r, "evidence_summary"),
            "exclusion_reason": snum(r, "exclusion_reason"),
            "evidence_partition": snum(r, "evidence_partition"),
        }
        for r in excluded_rows
    ])

    all_prematch = (
        iso["excluded_post_match_evidence_count"] == 0
        and len(prematch_source_summary) == len([e for e in events if prematch_eligibility(e).get("evidence_partition") != "excluded_non_prematch"])
    )
    uses_only = iso["excluded_post_match_evidence_count"] == 0 and (
        len(events) == 0 or all_prematch
    )

    return {
        "evidence_count": len(events),
        "pre_match_evidence_count": iso["pre_match_evidence_count"],
        "post_match_evidence_count": iso["post_match_evidence_count"],
        "excluded_post_match_evidence_count": iso["excluded_post_match_evidence_count"],
        "uses_pre_match_evidence_only": uses_only,
        "grade_A_count": len(by_grade.get("A", [])),
        "grade_B_count": len(by_grade.get("B", [])),
        "grade_C_count": len(by_grade.get("C", [])) + len(prematch_summary),
        "high_confidence_claims": by_grade.get("A", []) + by_grade.get("B", []),
        "summary_only_claims": by_grade.get("C", []) + [
            {
                "signal_type": snum(r, "signal_type"),
                "summary": snum(r, "evidence_summary"),
                "evidence_grade": "C",
                "evidence_partition": snum(r, "evidence_partition"),
            }
            for r in prematch_summary
        ],
        "conflicts": conflicts,
        "conflict_count": sum(int(float(snum(c, "conflict_count") or 0)) for c in claims),
        "prematch_source_summary": prematch_source_summary,
        "excluded_evidence_summary": excluded_evidence_summary,
        "source_summary_deprecated": prematch_source_summary,
        "fused_evidence_rows": len(fused),
    }


def _component_label(key: str) -> str:
    labels = {
        "raw_base_weight": "基础剧本先验",
        "raw_tactical_delta": "战术对位",
        "raw_player_delta": "球员/阵容信号",
        "raw_source_delta": "多源赛前证据",
        "raw_probability_context_delta": "V2概率上下文",
    }
    return labels.get(key, key)


def _nonzero_components(comp: Dict[str, Any]) -> List[str]:
    keys = [
        "raw_tactical_delta",
        "raw_player_delta",
        "raw_source_delta",
        "raw_probability_context_delta",
        "raw_base_weight",
    ]
    out: List[str] = []
    for k in keys:
        try:
            v = float(comp.get(k, 0) or 0)
        except Exception:
            v = 0.0
        if abs(v) > 1e-6:
            out.append(f"{_component_label(k)} {v:+.3f}" if k != "raw_base_weight" else f"{_component_label(k)} {v:.3f}")
    return out


def _scenario_map(activated: List[Dict[str, Any]]) -> Dict[str, str]:
    return {str(s.get("scenario_id", "")): str(s.get("name", "")) for s in activated}


def build_eventflow_process_summary(
    ef_engine: Dict[str, Any],
    ev_rows: List[Dict[str, str]],
    source_fusion: Dict[str, Any],
    data_quality: Dict[str, Any],
    mode: str,
    p_weight: float,
    e_weight: float,
    dynamic_profile: Dict[str, Any] | None = None,
    topn: int = 3,
) -> Dict[str, Any]:
    """Expose the EventFlow reasoning path in the final dual-engine JSON.

    This is a report layer only: it does not change V2 probabilities, EventFlow
    scores, or the final fusion ranking.
    """
    activated = ef_engine.get("activated_scenarios", []) or []
    phase_sim = ef_engine.get("phase_simulation", {}) or {}
    names = _scenario_map(activated)

    scenario_path: List[Dict[str, Any]] = []
    for i, s in enumerate(activated[:6], 1):
        comp = s.get("weight_composition", {}) or {}
        score_families = s.get("affected_score_families", []) or []
        scenario_path.append({
            "rank": i,
            "scenario_id": s.get("scenario_id", ""),
            "name": s.get("name", ""),
            "normalized_weight": round(float(s.get("normalized_weight", s.get("weight", 0)) or 0), 4),
            "trigger_factors": _nonzero_components(comp),
            "evidence_summary": s.get("evidence_summary", ""),
            "affected_score_families": score_families,
            "interpretation": (
                f"该剧本主要抬升 {'、'.join(score_families[:4])} 等比分族。"
                if score_families else "该剧本参与事件流排序，但未显式绑定比分族。"
            ),
        })

    phase_order = ["phase_0_30", "phase_31_60", "phase_61_90"]
    phase_path: List[Dict[str, Any]] = []
    for k in phase_order:
        ph = phase_sim.get(k, {}) or {}
        sid = ph.get("dominant_scenario_id", "")
        supporting = ph.get("supporting_scenario_ids", []) or []
        phase_path.append({
            "phase": ph.get("label", k),
            "dominant_scenario_id": sid,
            "dominant_scenario_name": ph.get("dominant_scenario_name") or names.get(sid, ""),
            "supporting_scenarios": [
                {"scenario_id": x, "name": names.get(x, "")} for x in supporting
            ],
            "goal_tendency": ph.get("goal_tendency", ""),
            "scenario_weight": round(float(ph.get("scenario_weight", 0) or 0), 4),
        })

    ev_ranked = sorted(ev_rows, key=lambda r: fnum(r, "eventflow_ranking_score") or fnum(r, "eventflow_score") or fnum(r, "event_probability"), reverse=True)
    score_path: List[Dict[str, Any]] = []
    for r in ev_ranked[:topn]:
        sids = [x for x in snum(r, "scenario_ids").split(";") if x]
        score_path.append({
            "score": snum(r, "score"),
            "eventflow_ranking_score": round(
                fnum(r, "eventflow_ranking_score") or fnum(r, "eventflow_score") or fnum(r, "event_probability"), 4
            ),
            "linked_scenarios": [{"scenario_id": x, "name": names.get(x, "")} for x in sids],
            "reason": snum(r, "reason") or "多剧本叠加；概率基准参与",
            "score_family": snum(r, "score_family"),
            "total_goals_bucket": snum(r, "total_goals_bucket"),
        })

    top_names = [x.get("name") for x in scenario_path[:3] if x.get("name")]
    evidence_text = (
        f"赛前可用证据 {source_fusion.get('pre_match_evidence_count', 0)} 条，"
        f"A/B级主证据 {source_fusion.get('grade_A_count', 0) + source_fusion.get('grade_B_count', 0)} 条，"
        f"真实数据占比 {float(data_quality.get('real_data_ratio', 0) or 0) * 100:.0f}%"
    )
    summary = (
        f"EventFlow 先将赛前信号映射为 {len(activated)} 个激活剧本，"
        f"再由自动可靠度策略进行比分族加权；当前主线为"
        f"{'、'.join(top_names) if top_names else '无明确主线'}。{evidence_text}。"
    )

    return {
        "summary": summary,
        "fusion_weight_note": f"最终融合使用 V2概率引擎 {p_weight:.0%} + EventFlow事件流 {e_weight:.0%}；本摘要只解释 EventFlow 侧，不改变最终分数。",
        "dynamic_weight_profile": dynamic_profile or {},
        "evidence_gate": {
            "uses_pre_match_evidence_only": source_fusion.get("uses_pre_match_evidence_only", True),
            "pre_match_evidence_count": source_fusion.get("pre_match_evidence_count", 0),
            "post_match_evidence_count": source_fusion.get("post_match_evidence_count", 0),
            "excluded_post_match_evidence_count": source_fusion.get("excluded_post_match_evidence_count", 0),
            "grade_A_count": source_fusion.get("grade_A_count", 0),
            "grade_B_count": source_fusion.get("grade_B_count", 0),
            "grade_C_count": source_fusion.get("grade_C_count", 0),
            "conflict_count": source_fusion.get("conflict_count", 0),
        },
        "scenario_activation_path": scenario_path,
        "phase_path": phase_path,
        "score_translation_path": score_path,
        "risk_checks": [
            "若开场无早球、红牌、点球或明确战术错位，开放式/大比分剧本应动态下调。",
            "若赛前证据不足或多为C级摘要证据，EventFlow只作为排序辅助，不能替代V2校准概率。",
            f"当前估算数据占比 {float(data_quality.get('estimated_data_ratio', 0) or 0) * 100:.0f}%，需要在报告中显式披露。",
        ],
    }


def build_v37_cold_reserve(
    prob_by_score: Dict[str, float],
    fusion_top3_scores: List[str],
    v37: Dict[str, Any],
    max_reserve: int = 2,
) -> List[Dict[str, Any]]:
    """Add cold reserve scorelines from V2 top-5 when LBKG active. Does not alter fusion ranks."""
    if not v37.get("cold_guard_active"):
        return []

    prob_top5 = sorted(prob_by_score.items(), key=lambda x: -x[1])[:5]
    prob_top5_scores = [s for s, _ in prob_top5]
    priority = ["0-0", "1-1"]
    reserves: List[Dict[str, Any]] = []
    seen: set[str] = set()

    for score in priority + prob_top5_scores:
        if score in seen or score in fusion_top3_scores:
            continue
        if score not in prob_top5_scores:
            continue
        try:
            h, a = map(int, score.split("-"))
        except Exception:
            continue
        if score in priority or (h + a) <= 2:
            reserves.append({
                "score": score,
                "v2_scoreline_probability": round(prob_by_score.get(score, 0.0), 4),
                "reason": (
                    "cold_guard_active + probability_top5"
                    if score in priority
                    else "low_block_keeper_guard"
                ),
            })
            seen.add(score)
        if len(reserves) >= max_reserve:
            break
    return reserves


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--baseline",
        default=str(Path(__file__).resolve().parents[1] / "database" / "eventflow" / "raw" / "probability_engine_scores.csv"),
    )
    ap.add_argument(
        "--mode",
        choices=MODE_CHOICES,
        default=AUTO_MODE,
        help="Compatibility input only; fusion weights are automatic.",
    )
    ap.add_argument("--match-id", default="")
    ap.add_argument("--home", default="")
    ap.add_argument("--away", default="")
    ap.add_argument("--topn", type=int, default=5)
    ap.add_argument("--export-json", default=str(EVENTFLOW_DB / "dual_engine_output.json"))
    ap.add_argument("--use-v37", action="store_true", help="Enable V3.7 phase-1 fusion guards")
    ap.add_argument("--use-v37-cold-reserve", action="store_true",
                    help="Add cold reserve scorelines when LBKG active (implies --use-v37)")
    ap.add_argument("--cold-reserve-max", type=int, default=2)
    ap.add_argument("--fail-on-htft-mismatch", action="store_true",
                    help="Exit non-zero if half_full_time_top3 is not bound to this match")
    args = ap.parse_args()

    use_v37 = args.use_v37 or args.use_v37_cold_reserve

    resolved = resolve_match_id(args.match_id, args.home, args.away)
    mid = snum(resolved, "internal_match_id") or args.match_id
    home = args.home or snum(resolved, "home_team")
    away = args.away or snum(resolved, "away_team")

    prob_rows = filter_rows(read_csv(args.baseline), mid, home, away)
    ev_rows = filter_rows(read_csv(EVENTFLOW_DB / "eventflow_predictions.csv"), mid, home, away)
    ev_json = read_json(EVENTFLOW_DB / "eventflow_output.json", {}) or {}

    v2_diag_path = Path(__file__).resolve().parents[1] / "database" / "eventflow" / "raw" / "v2_engine_diagnostics.json"
    v2_diag_all = read_json(v2_diag_path, {}) or {}
    v2_diag = v2_diag_all.get(mid, {})
    probabilities_from = v2_diag.get("probabilities_from", "base_lambda")
    realized_snap = v2_diag.get("realized_probability", {})
    v36_layer = v2_diag.get("v36_realization_layer", {})
    scoreline_grid = v2_diag.get("scoreline_probability_grid", [])
    if probabilities_from == "v36_realized" and scoreline_grid:
        prob_rows = [
            {
                "score": snum(g, "score"),
                "probability": str(fnum(g, "probability")),
                "match_id": mid,
                "home_team": home,
                "away_team": away,
                "lambda_home": str(fnum(prob_rows[0], "lambda_home")) if prob_rows else "",
                "lambda_away": str(fnum(prob_rows[0], "lambda_away")) if prob_rows else "",
            }
            for g in scoreline_grid
        ]

    if not prob_rows:
        print("warning: no probability_engine rows for this match; merge will be EventFlow-only")

    ef_engine_pre = read_json(EVENTFLOW_DB / "eventflow_output.json", {}) or {}
    ef_engine_state = ef_engine_pre.get("eventflow_engine", {}) or {}
    eventflow_degraded_pre = bool(
        ef_engine_pre.get("eventflow_data_degraded", False)
        or ef_engine_state.get("eventflow_data_degraded", False)
    )
    degradation_reason = (
        ef_engine_pre.get("degradation_reason")
        or ef_engine_state.get("degradation_reason")
        or ""
    )
    dq = summarize_data_quality(mid, home, away)
    source_fusion = load_source_fusion(mid)
    dynamic_profile = compute_dynamic_fusion_profile(
        data_quality=dq,
        source_fusion=source_fusion,
        scenarios=(
            ef_engine_state.get("all_scenario_weights")
            or ef_engine_state.get("activated_scenarios")
            or []
        ),
        fallback_ratio=fnum(ef_engine_pre, "fallback_ratio"),
        eventflow_degraded=eventflow_degraded_pre,
        probability_degraded=bool(v2_diag.get("probability_data_degraded", False)),
        requested_mode=args.mode,
    )
    p_weight = dynamic_profile["probability_weight"]
    e_weight = dynamic_profile["eventflow_weight"]
    fusion_mode_effective = dynamic_profile["effective_mode"]
    if dynamic_profile.get("legacy_mode_ignored"):
        print(f"legacy mode '{args.mode}' accepted but ignored; effective mode=auto_dynamic")
    print(
        "Dynamic fusion weights: "
        f"prob={p_weight:.3f} event={e_weight:.3f} "
        f"reliability={dynamic_profile['reliability_score']:.3f}"
    )
    if eventflow_degraded_pre and degradation_reason in DEGRADATION_REASONS_PROB_ONLY:
        fusion_mode_effective = "probability_only_due_to_eventflow_degradation"

    prob_by_score = {snum(r, "score"): fnum(r, "probability") for r in prob_rows}
    ev_by_score = {snum(r, "score"): r for r in ev_rows}
    scores = set(prob_by_score) | set(ev_by_score)

    lam_home = fnum(prob_rows[0], "lambda_home") if prob_rows else fnum(ev_json.get("eventflow_engine", {}), "lambda_home")
    lam_away = fnum(prob_rows[0], "lambda_away") if prob_rows else fnum(ev_json.get("eventflow_engine", {}), "lambda_away")
    base_lam_home = fnum(v2_diag, "base_lambda_home") or lam_home
    base_lam_away = fnum(v2_diag, "base_lambda_away") or lam_away
    availability = v2_diag.get("availability_adjustment") or {}
    adj_block = {
        "base_lambda": {"home": round(base_lam_home, 4), "away": round(base_lam_away, 4)},
        "availability_adjustment": availability,
        "adjusted_lambda": {
            "home": round(lam_home, 4),
            "away": round(lam_away, 4),
        },
        "probabilities_from": probabilities_from,
        "base_probability_snapshot": v2_diag.get("base_probability_snapshot", {}),
        "adjusted_probability": v2_diag.get("adjusted_probability", {}),
        "excluded_availability_signals": v2_diag.get("excluded_signals_and_reasons", []),
    }
    fusion_penetration_ok = True
    if availability.get("enabled") and v2_diag.get("base_probability_snapshot"):
        base_top = v2_diag["base_probability_snapshot"].get("top_scores", [])
        adj_top = v2_diag.get("adjusted_probability", {}).get("top_scores", [])
        base_hw = v2_diag["base_probability_snapshot"].get("home_win")
        adj_hw = v2_diag.get("adjusted_probability", {}).get("home_win")
        if base_hw == adj_hw and base_top == adj_top:
            fusion_penetration_ok = False
            print(
                "WARNING: availability adjustment enabled but probability snapshots unchanged — "
                "fusion may not reflect adjusted_lambda"
            )

    out: List[Dict[str, Any]] = []
    eventflow_match_status = (
        "degraded_probability_only" if eventflow_degraded_pre
        else ("active" if ev_rows else "missing_match_fallback_zero")
    )
    for score in scores:
        ev = ev_by_score.get(score, {})
        v2_prob = prob_by_score.get(score, 0.0)
        ef_rank = (
            fnum(ev, "eventflow_ranking_score")
            or fnum(ev, "eventflow_score")
            or fnum(ev, "event_probability")
        )
        ef_contrib = classify_eventflow_contribution(ev_rows, ev_by_score, score)
        raw_blend = p_weight * v2_prob + e_weight * ef_rank
        out.append({
            "match_id": mid,
            "home": home,
            "away": away,
            "mode": fusion_mode_effective,
            "requested_mode": args.mode,
            "rank": 0,
            "score": score,
            "v2_scoreline_probability": v2_prob,
            "eventflow_ranking_score": ef_rank,
            "eventflow_contribution": ef_contrib,
            "fusion_ranking_score": raw_blend,
            "raw_probability": v2_prob,
            "eventflow_score": ef_rank,
            "probability_engine_prob": v2_prob,
            "eventflow_prob": ef_rank,
            "final_weight_deprecated": raw_blend,
            "normalized_fusion_score_deprecated": raw_blend,
            "score_family": snum(ev, "score_family"),
            "total_goals_bucket": snum(ev, "total_goals_bucket"),
            "htft": snum(ev, "htft"),
            "main_reason": snum(ev, "reason"),
            "risk_note": "若上半场无早球/无红牌/无明确战术错位，事件流大比分权重应下调。",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        })
    normalize_weights(out, "fusion_ranking_score")
    for r in out:
        r["final_weight_deprecated"] = r["fusion_ranking_score"]
        r["normalized_fusion_score_deprecated"] = r["fusion_ranking_score"]
    out = sorted(out, key=lambda x: x["fusion_ranking_score"], reverse=True)
    for i, r in enumerate(out, 1):
        r["rank"] = i

    top_csv = out[: max(3, args.topn)]
    write_csv(EVENTFLOW_DB / "dual_engine_predictions.csv", top_csv)
    for r in top_csv:
        print(
            f"#{r['rank']} {r['score']} fusion_ranking_score={float(r['fusion_ranking_score']):.3f} "
            f"v2_prob={float(r['v2_scoreline_probability']):.3f} eventflow_rank={float(r['eventflow_ranking_score']):.3f}"
        )

    prob_top = sorted(prob_by_score.items(), key=lambda x: -x[1])[:5]
    ef_attach = resolve_eventflow_merge_attachments(
        ev_json, mid, home, away, lam_home, lam_away,
    )
    htft_top3 = ef_attach["half_full_time_top3"]
    eventflow_degraded = bool(eventflow_degraded_pre or dynamic_profile.get("eventflow_weight", 0.0) == 0.0)
    halftime_status = halftime_layer_status(
        dq, dynamic_profile, eventflow_degraded=eventflow_degraded, htft_top3=htft_top3
    )
    if not halftime_status.get("halftime_output_allowed"):
        htft_top3 = []
    activated = ef_attach["activated_scenarios"]
    ef_engine = ev_json.get("eventflow_engine", {}) or {}
    if not ef_attach.get("eventflow_json_aligned"):
        print(
            f"warning: eventflow_output.json stale for {mid}; "
            f"rebound HT/FT source={ef_attach.get('half_full_time_source')}"
        )
    top3 = out[:3]
    baseline_degraded = ev_json.get("baseline_degraded", False)

    v37_features = load_v37_features(mid) if use_v37 else None
    risk_reserve: List[Dict[str, Any]] = []
    v37_guard_summary: Dict[str, Any] = {}
    if use_v37 and v37_features:
        v37_loaded = bool(v37_features.get("loaded"))
        v37_quality = str(v37_features.get("data_quality_grade", "degraded") or "degraded")
        v37_usable = v37_loaded and v37_quality != "degraded"
        v37_guard_summary = {
            "loaded": v37_loaded,
            "data_quality_grade": v37_quality,
            "applied": v37_usable,
            "reason": "loaded" if v37_usable else "v37_features_not_loaded_or_degraded",
            "group_pressure": (
                f"{v37_features.get('pressure_type_home')} / "
                f"{v37_features.get('pressure_type_away')}"
            ),
            "attack_conversion_gate": round(float(v37_features.get("attack_conversion_home", 0.5)), 3),
            "early_goal_cascade_index": round(float(v37_features.get("early_goal_cascade_index", 0)), 3),
            "low_block_keeper_guard": round(float(v37_features.get("cold_draw_guard_score", 0)), 3),
            "active_flags": v37_features.get("active_flags", []) if v37_usable else [],
            "risk_reserve_scorelines": [],
            "betting_risk_flags": [],
            "phase1_egci_enabled": False,
        }
        if v37_usable:
            risk_reserve = build_v37_cold_reserve(
                prob_by_score,
                [r["score"] for r in top3],
                v37_features,
                max_reserve=args.cold_reserve_max,
            )
            v37_guard_summary["risk_reserve_scorelines"] = risk_reserve
            from apply_v37_realization_guards import _risk_flags
            v37_guard_summary["betting_risk_flags"] = _risk_flags(v37_features)

    payload = {
        "match": f"{home} vs {away}",
        "match_id": mid,
        "fifa_match_id": snum(resolved, "fifa_match_id"),
        "mode": fusion_mode_effective,
        "requested_mode": args.mode,
        "fusion_mode_effective": fusion_mode_effective,
        "dynamic_weight_profile": dynamic_profile,
        "score_semantics_note": FUSION_SCORE_NOTE,
        "semantics": {
            "v2_scoreline_probability": "calibrated scoreline probability from V2 Dixon-Coles",
            "eventflow_ranking_score": "non-probabilistic EventFlow ranking score",
            "eventflow_contribution": (
                "active=EventFlow row present; active_zero_rank=row present but rank is 0; "
                "missing_match_fallback_zero=no EventFlow rows for match (0 is fallback, not signal); "
                "missing_score_fallback_zero=score absent from EventFlow export (0 is fallback)"
            ),
            "fusion_ranking_score": "normalized ranking score, not a calibrated probability",
        },
        "baseline_degraded": baseline_degraded,
        "eventflow_data_degraded": eventflow_degraded,
        "degradation_reason": degradation_reason,
        "data_quality": dq,
        "halftime_layer_status": halftime_status,
        "probability_engine": {
            "lambda_home": lam_home,
            "lambda_away": lam_away,
            **adj_block,
            "scoreline_probability_grid": scoreline_grid or v2_diag.get("scoreline_probability_grid", []),
            "realized_probability": realized_snap,
            "v36_realization_layer": v36_layer,
            "scenario_realization": v2_diag.get("scenario_realization", {}),
            "btts_conversion_gate": v2_diag.get("btts_conversion_gate", {}),
            "total_goals_tail_calibration": v2_diag.get("total_goals_tail_calibration", {}),
            "probability_data_degraded": v2_diag.get("probability_data_degraded", False),
            "diagnostics": v2_diag,
            "top_scores": realized_snap.get("top_scores") or [s for s, _ in prob_top[:3]],
            "total_goals": total_goals_fusion(
                realized_snap.get("top_scores") or [s for s, _ in prob_top[:3]],
            ),
        },
        "eventflow_engine": {
            "eventflow_data_degraded": eventflow_degraded,
            "eventflow_match_status": eventflow_match_status,
            "halftime_layer_status": halftime_status,
            "half_full_time_source": ef_attach.get("half_full_time_source", "eventflow_json"),
            "eventflow_json_aligned": ef_attach.get("eventflow_json_aligned", True),
            "competition_context": ef_attach.get("competition_context", {}),
            "realtime_signal_usage": v2_diag.get("realtime_signal_usage", []),
            "activated_scenarios": activated,
            "all_scenario_weights": ef_attach.get("all_scenario_weights", ef_engine.get("all_scenario_weights", [])),
            "phase_simulation": ef_attach.get("phase_simulation", ef_engine.get("phase_simulation", {})),
            "top_scores": [snum(r, "score") for r in ev_rows[:3]],
            "half_full_time_top3": htft_top3,
            "half_full_time": [h.get("label", h) if isinstance(h, dict) else h for h in htft_top3[:3]],
            "total_goals": ef_engine.get("total_goals", ""),
        },
        "source_fusion": source_fusion,
        "eventflow_process_summary": build_eventflow_process_summary(
            ef_engine, ev_rows, source_fusion, dq, fusion_mode_effective,
            p_weight, e_weight, dynamic_profile=dynamic_profile, topn=3
        ),
        "final_fusion": {
            "fusion_input": {
                "probability_source": probabilities_from,
                "eventflow_source": "prematch_realtime_eventflow",
                "availability_adjustment_applied": bool(availability.get("enabled")),
                "v36_realization_applied": bool(v36_layer),
                "v36_calibration_strength": v36_layer.get("calibration_strength", ""),
                "probability_file": str(Path(args.baseline)),
                "eventflow_file": str(EVENTFLOW_DB / "eventflow_predictions.csv"),
                "fusion_penetration_ok": fusion_penetration_ok,
                "dynamic_weight_policy": dynamic_profile["policy"],
                "probability_weight": p_weight,
                "eventflow_weight": e_weight,
                "eventflow_degraded": eventflow_degraded,
                "v37_feature_layer": v37_guard_summary if use_v37 else {},
            },
            "score_ranking": [
                {
                    "score": r["score"],
                    "rank": r["rank"],
                    "reason": r["main_reason"] or "概率派与事件流加权",
                    "v2_scoreline_probability": round(float(r["v2_scoreline_probability"]), 4),
                    "eventflow_ranking_score": round(float(r["eventflow_ranking_score"]), 4),
                    "eventflow_contribution": r.get("eventflow_contribution", "active"),
                    "fusion_ranking_score": round(float(r["fusion_ranking_score"]), 4),
                    "raw_probability_deprecated": round(float(r["v2_scoreline_probability"]), 4),
                    "eventflow_score_deprecated": round(float(r["eventflow_ranking_score"]), 4),
                    "normalized_fusion_score_deprecated": round(float(r["fusion_ranking_score"]), 4),
                    "display_v2_probability": (
                        f"{float(r['v2_scoreline_probability'])*100:.1f}% (V2 scoreline probability)"
                        if r["v2_scoreline_probability"] > 0
                        else "ranking score only"
                    ),
                    "display_fusion_score": (
                        f"{float(r['fusion_ranking_score']):.3f} ranking score (not probability)"
                    ),
                }
                for r in top3
            ],
            "total_goals": total_goals_fusion([r["score"] for r in top3]),
            "halftime_layer_status": halftime_status,
            "half_full_time_top3": htft_top3,
            "half_full_time": [h.get("label", "") for h in htft_top3[:3]],
            "confidence": confidence_label(prob_rows, len(activated), dq),
            "risk_notes": [
                "fusion_ranking_score 是排序分，不可与赔率隐含概率直接对比",
                "若上半场无早球，大比分权重下降",
                f"估算数据占比 {dq.get('estimated_data_ratio', 0)*100:.0f}%，EventFlow 尾部已降权",
                (
                    f"EventFlow动态权重 {e_weight:.1%}；"
                    f"可靠度 {dynamic_profile['reliability_score']:.2f}"
                ),
            ],
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    if use_v37:
        payload["v37_guard_summary"] = v37_guard_summary
        payload["final_fusion"]["risk_reserve_scorelines"] = risk_reserve
        payload["final_fusion"]["v37_phase1_enabled"] = bool(v37_guard_summary.get("applied"))
        if not v37_guard_summary.get("applied"):
            payload["final_fusion"]["risk_notes"].append(
                "V3.7特征层未加载或已降级：已按 fail-closed 处理，不参与融合/投注守门"
            )
        if risk_reserve:
            payload["final_fusion"]["risk_notes"].append(
                "V3.7 cold reserve: " + ", ".join(r["score"] for r in risk_reserve)
            )
    if args.export_json:
        write_json(args.export_json, payload)
        htft_errors = validate_htft_output(payload)
        if htft_errors:
            for err in htft_errors:
                print(f"HTFT_VALIDATION_ERROR: {err}")
            if args.fail_on_htft_mismatch:
                raise SystemExit(1)
        print(f"Wrote {args.export_json}")


if __name__ == "__main__":
    main()
