#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""EventFlow prediction engine (V3.3) with HTFT Top 3 and weight traceability."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from eventflow_common import (
    EVENTFLOW_DB, read_csv, read_json, write_csv, write_json,
    fnum, snum, top_score_distribution, htft_label, normalize_weights,
)
from eventflow_v32_gates import parse_gates_json, competition_context_for
from eventflow_htft import compute_htft_top3, enrich_phase_simulation, summarize_data_quality, count_prematch_evidence

MODE_WEIGHT = {
    "safe": {"prob": 0.65, "event": 0.35, "tail": 0.60},
    "balanced": {"prob": 0.50, "event": 0.50, "tail": 0.85},
    "hit_hunting": {"prob": 0.35, "event": 0.65, "tail": 1.20},
}

SCORE_FAMILY_BONUS = {
    "0-0": -0.03, "1-0": 0.00, "0-1": 0.00, "1-1": 0.00,
    "2-0": 0.02, "0-2": 0.02, "2-1": 0.03, "1-2": 0.03,
    "3-0": 0.06, "0-3": 0.06, "3-1": 0.07, "1-3": 0.07,
    "3-2": 0.08, "2-3": 0.08, "4-1": 0.09, "1-4": 0.09,
    "4-2": 0.10, "2-4": 0.10, "5-1": 0.11, "1-5": 0.11,
}

DEGRADED_REASON = (
    "EventFlow disabled because match-specific scenario rows are unavailable."
)


def parse_score(s: str) -> Tuple[int, int]:
    h, a = s.split("-")
    return int(h), int(a)


def total_bucket(score: str) -> str:
    h, a = parse_score(score)
    t = h + a
    if t <= 1:
        return "0-1球"
    if t == 2:
        return "2球"
    if t == 3:
        return "3球"
    if t == 4:
        return "4球"
    return "5+球"


def total_goals_range(scores: List[str]) -> str:
    if not scores:
        return "未知"
    totals = [sum(parse_score(s)) for s in scores]
    lo, hi = min(totals), max(totals)
    return f"{lo}球" if lo == hi else f"{lo}-{hi}球"


def scenario_rows(match_id: str, home: str, away: str) -> Tuple[List[Dict[str, str]], bool, float]:
    rows = read_csv(EVENTFLOW_DB / "eventflow_scenario_weights.csv")
    got = [
        r for r in rows
        if (not match_id or snum(r, "match_id") == match_id)
        and snum(r, "home") == home and snum(r, "away") == away
    ]
    if got:
        fb = max(fnum(r, "fallback_ratio", 0.0) for r in got)
        return got, False, fb
    fallback = [r for r in rows if snum(r, "home") == home and snum(r, "away") == away]
    return fallback, len(fallback) == 0, 1.0 if len(fallback) == 0 else max(fnum(r, "fallback_ratio", 0.0) for r in fallback)


def _w(s: Dict[str, str]) -> float:
    return (
        fnum(s, "scenario_ranking_weight")
        or fnum(s, "normalized_weight")
        or fnum(s, "final_weight_deprecated")
        or fnum(s, "final_weight")
        or fnum(s, "weight")
    )


def is_prior_only(s: Dict[str, str]) -> bool:
    tac = fnum(s, "raw_tactical_delta", fnum(s, "tactical_delta"))
    src = fnum(s, "raw_source_delta", fnum(s, "source_delta"))
    prob = fnum(s, "raw_probability_context_delta", fnum(s, "probability_context_delta"))
    ply = fnum(s, "raw_player_delta", fnum(s, "player_delta"))
    gates = parse_gates_json(snum(s, "weight_gates"))
    if gates.get("gate_applied") or gates.get("fallback_gate_applied"):
        return tac < 0.02 and src < 0.01 and prob < 0.02
    return tac < 0.02 and src < 0.01 and prob < 0.02 and ply < 0.01


def weight_composition_from_row(s: Dict[str, str]) -> Dict[str, Any]:
    gates = parse_gates_json(snum(s, "weight_gates"))
    refs = [x.strip() for x in snum(s, "evidence_refs").split(";") if x.strip()]
    if refs and "evidence_refs" not in gates:
        gates["evidence_refs"] = refs
    return {
        "raw_base_weight": fnum(s, "raw_base_weight", fnum(s, "base_weight", 0.1)),
        "raw_tactical_delta": fnum(s, "raw_tactical_delta", fnum(s, "tactical_delta")),
        "raw_player_delta": fnum(s, "raw_player_delta", fnum(s, "player_delta")),
        "raw_source_delta": fnum(s, "raw_source_delta", fnum(s, "source_delta")),
        "raw_probability_context_delta": fnum(s, "raw_probability_context_delta", fnum(s, "probability_context_delta")),
        "raw_total_score": fnum(s, "raw_total_score") or _w(s),
        "normalized_weight": _w(s),
        "gates": gates,
        "evidence_refs": refs,
    }


def pick_activated(scenarios: List[Dict[str, str]], min_n: int = 3, max_n: int = 6) -> List[Dict[str, str]]:
    ranked = sorted(scenarios, key=_w, reverse=True)
    substantive = [s for s in ranked if not is_prior_only(s)]
    prior = [s for s in ranked if is_prior_only(s)]
    pool = substantive + prior
    n = min(max_n, max(min_n, len(pool)))
    return pool[:n]


def build_activated_payload(activated: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    out = []
    for s in activated:
        fam = [x.strip() for x in snum(s, "score_family").split(";") if x.strip()]
        raw_total = fnum(s, "raw_total_score") or _w(s)
        out.append({
            "scenario_id": snum(s, "scenario_id"),
            "name": snum(s, "scenario_name"),
            "weight": round(_w(s), 4),
            "normalized_weight": round(_w(s), 4),
            "scenario_ranking_weight": round(_w(s), 4),
            "weight_composition": weight_composition_from_row(s),
            "evidence_summary": snum(s, "evidence_summary") or snum(s, "triggered_by"),
            "affected_score_families": fam,
        })
    return out


def event_bonus_for_score(
    score: str, all_scenarios: List[Dict[str, str]], activated: List[Dict[str, str]], tail_strength: float,
) -> Tuple[float, List[str], List[str], List[str]]:
    bonus = SCORE_FAMILY_BONUS.get(score, 0.0) * tail_strength
    scenario_ids: List[str] = []
    reasons: List[str] = []
    ht_biases: List[str] = []
    activated_ids = {snum(s, "scenario_id") for s in activated}
    for s in all_scenarios:
        sid = snum(s, "scenario_id")
        weight = _w(s)
        est_penalty = 0.65 if str(s.get("is_estimated", "")).lower() == "true" else 1.0
        weight *= est_penalty
        if sid not in activated_ids:
            weight *= 0.35
        fam = [x.strip() for x in snum(s, "score_family").split(";") if x.strip()]
        if score in fam:
            bonus += weight * 0.22 * tail_strength
            if sid == "S11_group_state_draw_control" and score == "1-1":
                bonus += weight * 0.06 * tail_strength
            if sid in activated_ids:
                scenario_ids.append(sid)
                reasons.append(snum(s, "scenario_name"))
                if snum(s, "htft_bias"):
                    ht_biases.append(snum(s, "htft_bias"))
        else:
            try:
                sh, sa = parse_score(score)
                for fs in fam:
                    fh, fa = parse_score(fs)
                    if sh + sa == fh + fa:
                        bonus += weight * 0.05 * tail_strength
            except Exception:
                pass
    return bonus, scenario_ids, reasons, ht_biases


def generate_candidates(
    lam_home: float, lam_away: float, all_scenarios: List[Dict[str, str]],
    activated: List[Dict[str, str]], mode: str, degraded: bool = False,
) -> List[Dict[str, Any]]:
    weights = MODE_WEIGHT[mode]
    base = top_score_distribution(lam_home, lam_away, max_goals=6)
    candidates: List[Dict[str, Any]] = []
    for row in base:
        score = row["score"]
        if degraded:
            event_score = max(0.0, row["probability"] * weights["prob"])
            reason = "baseline_prior_only; EventFlow degraded"
            sids: List[str] = []
        else:
            b, sids, reasons, _ = event_bonus_for_score(score, all_scenarios, activated, weights["tail"])
            event_score = max(0.0, row["probability"] * weights["prob"] + b * weights["event"])
            reason = "；".join(reasons[:3]) if reasons else "多剧本叠加；概率基准参与"
        candidates.append({
            "score": score,
            "eventflow_ranking_score": event_score,
            "eventflow_score": event_score,
            "event_probability_deprecated": event_score,
            "score_family": "tail" if sum(parse_score(score)) >= 4 else "normal",
            "total_goals_bucket": total_bucket(score),
            "htft": "",
            "reason": reason,
            "scenario_ids": ";".join(dict.fromkeys(sids[:6])),
            "data_confidence": min([fnum(s, "data_confidence", 0.55) for s in all_scenarios] or [0.55]),
        })
    normalize_weights(candidates, "eventflow_ranking_score")
    for c in candidates:
        c["eventflow_score"] = c["eventflow_ranking_score"]
        c["event_probability_deprecated"] = c["eventflow_ranking_score"]
    return sorted(candidates, key=lambda x: x["eventflow_ranking_score"], reverse=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--match-id", default="")
    ap.add_argument("--home", required=True)
    ap.add_argument("--away", required=True)
    ap.add_argument("--lam-home", type=float, required=True)
    ap.add_argument("--lam-away", type=float, required=True)
    ap.add_argument("--mode", choices=sorted(MODE_WEIGHT), default="balanced")
    ap.add_argument("--topn", type=int, default=5)
    ap.add_argument("--export-json", default=str(EVENTFLOW_DB / "eventflow_output.json"))
    args = ap.parse_args()

    all_scenarios, baseline_degraded, fallback_ratio = scenario_rows(args.match_id, args.home, args.away)
    degradation_reason = ""
    precision_warning = ""
    if baseline_degraded:
        print("warning: no scenario rows found; EventFlow degraded to baseline distribution")
        degradation_reason = "missing_scenario_rows"
        precision_warning = DEGRADED_REASON
        lib = read_json(EVENTFLOW_DB / "scenario_library.json", [])
        all_scenarios = [{
            "match_id": args.match_id, "home": args.home, "away": args.away,
            "scenario_id": s["scenario_id"], "scenario_name": s["name"],
            "base_weight": 0.10, "tactical_delta": 0, "player_delta": 0, "source_delta": 0,
            "probability_context_delta": 0, "weight": 0.1,
            "scenario_ranking_weight": 0.1, "final_weight_deprecated": 0.1,
            "score_family": ";".join(s.get("effects", {}).get("score_family", [])),
            "htft_bias": ";".join(s.get("effects", {}).get("htft_bias", [])),
            "evidence_summary": "", "data_confidence": "0.45",
            "is_fallback": "true", "fallback_ratio": "1.0",
            "triggered_by": "baseline_prior_only",
        } for s in lib]
        normalize_weights(all_scenarios, "weight")
        fallback_ratio = 1.0
    elif fallback_ratio >= 0.50:
        degradation_reason = "fallback_ratio_too_high"
        precision_warning = "EventFlow degraded: insufficient match-specific tactical evidence."

    activated_raw = [] if baseline_degraded or fallback_ratio >= 0.50 else pick_activated(all_scenarios)
    activated = build_activated_payload(activated_raw)
    phase_sim = enrich_phase_simulation(activated, all_scenarios, args.match_id) if activated else {}
    evidence_counts = count_prematch_evidence(args.match_id)
    if evidence_counts.get("pre_match_evidence_count", 0) == 0 and evidence_counts.get("excluded_post_match_evidence_count", 0) > 0:
        degradation_reason = degradation_reason or "no_prematch_evidence"
    high_conf = evidence_counts.get("pre_match_evidence_count", 0) >= 2
    htft_top3 = compute_htft_top3(
        all_scenarios, phase_sim, args.lam_home, args.lam_away,
        home=args.home, away=args.away, high_confidence_evidence=high_conf,
        match_id=args.match_id, top_n=3,
    ) if activated else []
    data_quality = summarize_data_quality(args.match_id, args.home, args.away)
    eventflow_degraded = (
        baseline_degraded
        or fallback_ratio >= 0.35
        or data_quality.get("real_data_ratio", 0) < 0.25
    )
    if fallback_ratio >= 0.50:
        eventflow_degraded = True
    cand = generate_candidates(
        args.lam_home, args.lam_away, all_scenarios, activated_raw, args.mode,
        degraded=eventflow_degraded,
    )
    now = datetime.now(timezone.utc).isoformat()

    out: List[Dict[str, Any]] = []
    for i, c in enumerate(cand[: max(3, args.topn)], 1):
        out.append({
            "match_id": args.match_id, "home": args.home, "away": args.away,
            "engine_mode": args.mode, "rank": i, **c, "generated_at": now,
        })
    write_csv(EVENTFLOW_DB / "eventflow_predictions.csv", out)

    top_scores = [snum(r, "score") for r in out[:5]] if not eventflow_degraded else []
    comp_ctx = competition_context_for(args.match_id) if args.match_id else {}
    eventflow_process_summary = {
        "structured_competition_context_used": bool(comp_ctx),
        "competition_context_quality": snum(comp_ctx, "context_quality"),
        "competition_context_reason": snum(comp_ctx, "context_reason"),
    }
    payload = {
        "match": f"{args.home} vs {args.away}",
        "match_id": args.match_id,
        "mode": args.mode,
        "baseline_degraded": baseline_degraded,
        "eventflow_data_degraded": eventflow_degraded,
        "degradation_reason": degradation_reason,
        "precision_warning": precision_warning,
        "fallback_ratio": fallback_ratio,
        "evidence_isolation": evidence_counts,
        "data_quality": data_quality,
        "eventflow_process_summary": eventflow_process_summary,
        "eventflow_engine": {
            "lambda_home": args.lam_home,
            "lambda_away": args.lam_away,
            "competition_context": comp_ctx,
            "eventflow_data_degraded": eventflow_degraded,
            "degradation_reason": degradation_reason,
            "precision_warning": precision_warning,
            "fallback_ratio": fallback_ratio,
            "activated_scenarios": activated,
            "all_scenario_weights": [
                {
                    "scenario_id": snum(s, "scenario_id"),
                    "name": snum(s, "scenario_name"),
                    "weight_composition": weight_composition_from_row(s),
                }
                for s in sorted(all_scenarios, key=_w, reverse=True)
            ],
            "phase_simulation": phase_sim,
            "top_scores": top_scores,
            "half_full_time_top3": htft_top3,
            "half_full_time": [h["label"] for h in htft_top3],
            "total_goals": total_goals_range(top_scores) if top_scores else "未知",
        },
        "generated_at": now,
    }
    write_json(args.export_json, payload)

    print(f"Activated {len(activated)} scenarios (baseline_degraded={baseline_degraded}, fallback_ratio={fallback_ratio:.2f}):")
    for a in activated:
        wc = a["weight_composition"]
        print(f"  - {a['scenario_id']} norm={a['weight']:.3f} [raw_total={wc['raw_total_score']:.2f} tac={wc['raw_tactical_delta']:.2f} src={wc['raw_source_delta']:.2f}]")
    if htft_top3:
        print("半全场 Top3:")
        for h in htft_top3:
            print(f"  - {h['label']} score={h['score']:.3f} | {h.get('perspective_basis', '')[:50]}")
    for r in out[: args.topn]:
        print(f"#{r['rank']} {r['score']} eventflow_ranking_score={float(r['eventflow_ranking_score']):.3f} | {r['reason']}")
    print(f"数据: 真实={data_quality['real_data_rows']} 估算={data_quality['estimated_data_rows']} ratio={data_quality['real_data_ratio']}")
    if precision_warning:
        print(f"precision_warning: {precision_warning}")
    print(f"Wrote {args.export_json}")


if __name__ == "__main__":
    main()
