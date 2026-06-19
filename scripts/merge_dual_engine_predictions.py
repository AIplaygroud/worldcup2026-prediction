#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Merge Probability Engine and EventFlow Engine outputs with score semantics clarified."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from eventflow_common import EVENTFLOW_DB, read_csv, read_json, write_csv, write_json, fnum, snum, normalize_weights
from eventflow_htft import resolve_match_id, summarize_data_quality, count_prematch_evidence, resolve_source_notes_path

MODE = {
    "safe": (0.65, 0.35),
    "balanced": (0.50, 0.50),
    "hit_hunting": (0.35, 0.65),
}

FUSION_SCORE_NOTE = (
    "normalized_fusion_score 为双引擎加权后再归一化的排序分，不是严格校准概率；"
    "raw_probability 来自 V2 Dixon-Coles；eventflow_score 来自事件流剧本叠加分。"
)


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
    summary_c = read_csv(EVENTFLOW_DB / "eventflow_evidence_summary.csv")
    summary_c = [r for r in summary_c if not match_id or snum(r, "match_id") == match_id]
    iso = count_prematch_evidence(match_id)

    by_grade: Dict[str, List[Dict[str, Any]]] = {"A": [], "B": [], "C": []}
    for c in claims:
        g = snum(c, "evidence_grade", "C")
        entry = {
            "signal_type": snum(c, "signal_type"),
            "summary": snum(c, "canonical_signal"),
            "confidence": fnum(c, "final_confidence"),
            "sources": snum(c, "sources"),
            "evidence_grade": g,
            "single_source_penalty": fnum(c, "single_source_penalty") if snum(c, "single_source_penalty") else None,
            "agreement_count": int(float(snum(c, "agreement_count") or 0)),
            "conflict_count": int(float(snum(c, "conflict_count") or 0)),
        }
        by_grade.setdefault(g, []).append(entry)

    conflicts = [snum(c, "conflict_note") for c in claims if snum(c, "conflict_note")]
    source_summary = [
        {
            "source_id": snum(e, "source_id"),
            "source_url": snum(e, "source_url"),
            "signal_type": snum(e, "signal_type"),
            "summary": snum(e, "summary"),
            "confidence": fnum(e, "raw_confidence"),
            "evidence_usage": snum(e, "evidence_usage"),
            "available_before_kickoff": snum(e, "available_before_kickoff"),
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
        for e in events
    ]
    return {
        "evidence_count": len(events),
        "pre_match_evidence_count": iso["pre_match_evidence_count"],
        "post_match_evidence_count": iso["post_match_evidence_count"],
        "excluded_post_match_evidence_count": iso["excluded_post_match_evidence_count"],
        "uses_pre_match_evidence_only": iso["excluded_post_match_evidence_count"] == 0 or iso["pre_match_evidence_count"] > 0,
        "grade_A_count": len(by_grade.get("A", [])),
        "grade_B_count": len(by_grade.get("B", [])),
        "grade_C_count": len(by_grade.get("C", [])) + len(summary_c),
        "high_confidence_claims": by_grade.get("A", []) + by_grade.get("B", []),
        "summary_only_claims": by_grade.get("C", []) + [
            {"signal_type": snum(r, "signal_type"), "summary": snum(r, "evidence_summary"), "evidence_grade": "C"}
            for r in summary_c
        ],
        "conflicts": conflicts,
        "conflict_count": sum(int(float(snum(c, "conflict_count") or 0)) for c in claims),
        "source_summary": source_summary,
        "fused_evidence_rows": len(fused),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--baseline",
        default=str(Path(__file__).resolve().parents[1] / "database" / "eventflow" / "raw" / "probability_engine_scores.csv"),
    )
    ap.add_argument("--mode", choices=sorted(MODE), default="balanced")
    ap.add_argument("--match-id", default="")
    ap.add_argument("--home", default="")
    ap.add_argument("--away", default="")
    ap.add_argument("--topn", type=int, default=5)
    ap.add_argument("--export-json", default=str(EVENTFLOW_DB / "dual_engine_output.json"))
    args = ap.parse_args()

    resolved = resolve_match_id(args.match_id, args.home, args.away)
    mid = snum(resolved, "internal_match_id") or args.match_id
    home = args.home or snum(resolved, "home_team")
    away = args.away or snum(resolved, "away_team")

    prob_rows = filter_rows(read_csv(args.baseline), mid, home, away)
    ev_rows = filter_rows(read_csv(EVENTFLOW_DB / "eventflow_predictions.csv"), mid, home, away)
    ev_json = read_json(EVENTFLOW_DB / "eventflow_output.json", {}) or {}

    if not prob_rows:
        print("warning: no probability_engine rows for this match; merge will be EventFlow-only")

    p_weight, e_weight = MODE[args.mode]
    prob_by_score = {snum(r, "score"): fnum(r, "probability") for r in prob_rows}
    ev_by_score = {snum(r, "score"): r for r in ev_rows}
    scores = set(prob_by_score) | set(ev_by_score)

    lam_home = fnum(prob_rows[0], "lambda_home") if prob_rows else fnum(ev_json.get("eventflow_engine", {}), "lambda_home")
    lam_away = fnum(prob_rows[0], "lambda_away") if prob_rows else fnum(ev_json.get("eventflow_engine", {}), "lambda_away")

    out: List[Dict[str, Any]] = []
    for score in scores:
        ev = ev_by_score.get(score, {})
        raw_p = prob_by_score.get(score, 0.0)
        ef = fnum(ev, "eventflow_score") or fnum(ev, "event_probability")
        raw_blend = p_weight * raw_p + e_weight * ef
        out.append({
            "match_id": mid,
            "home": home,
            "away": away,
            "mode": args.mode,
            "rank": 0,
            "score": score,
            "raw_probability": raw_p,
            "eventflow_score": ef,
            "probability_engine_prob": raw_p,
            "eventflow_prob": ef,
            "final_weight": raw_blend,
            "normalized_fusion_score": raw_blend,
            "score_family": snum(ev, "score_family"),
            "total_goals_bucket": snum(ev, "total_goals_bucket"),
            "htft": snum(ev, "htft"),
            "main_reason": snum(ev, "reason"),
            "risk_note": "若上半场无早球/无红牌/无明确战术错位，事件流大比分权重应下调。",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        })
    normalize_weights(out, "normalized_fusion_score")
    for r in out:
        r["final_weight"] = r["normalized_fusion_score"]
    out = sorted(out, key=lambda x: x["normalized_fusion_score"], reverse=True)
    for i, r in enumerate(out, 1):
        r["rank"] = i

    top_csv = out[: max(3, args.topn)]
    write_csv(EVENTFLOW_DB / "dual_engine_predictions.csv", top_csv)
    for r in top_csv:
        print(
            f"#{r['rank']} {r['score']} fusion={float(r['normalized_fusion_score']):.3f} "
            f"raw_P={float(r['raw_probability']):.3f} E={float(r['eventflow_score']):.3f}"
        )

    prob_top = sorted(prob_by_score.items(), key=lambda x: -x[1])[:5]
    ef_engine = ev_json.get("eventflow_engine", {})
    activated = ef_engine.get("activated_scenarios", [])
    htft_top3 = ef_engine.get("half_full_time_top3", [])
    top3 = out[:3]
    dq = summarize_data_quality(mid, home, away)
    baseline_degraded = ev_json.get("baseline_degraded", False)
    eventflow_degraded = ev_json.get("eventflow_data_degraded", False)
    v2_diag_path = Path(__file__).resolve().parents[1] / "database" / "eventflow" / "raw" / "v2_engine_diagnostics.json"
    v2_diag_all = read_json(v2_diag_path, {}) or {}
    v2_diag = v2_diag_all.get(mid, {})

    payload = {
        "match": f"{home} vs {away}",
        "match_id": mid,
        "fifa_match_id": snum(resolved, "fifa_match_id"),
        "mode": args.mode,
        "score_semantics_note": FUSION_SCORE_NOTE,
        "baseline_degraded": baseline_degraded,
        "eventflow_data_degraded": eventflow_degraded,
        "data_quality": dq,
        "probability_engine": {
            "lambda_home": lam_home,
            "lambda_away": lam_away,
            "probability_data_degraded": v2_diag.get("probability_data_degraded", False),
            "diagnostics": v2_diag,
            "top_scores": [s for s, _ in prob_top[:3]],
            "total_goals": total_goals_fusion([s for s, _ in prob_top[:3]]),
        },
        "eventflow_engine": {
            "eventflow_data_degraded": eventflow_degraded,
            "activated_scenarios": activated,
            "phase_simulation": ef_engine.get("phase_simulation", {}),
            "top_scores": [snum(r, "score") for r in ev_rows[:3]],
            "half_full_time_top3": htft_top3,
            "half_full_time": [h.get("label", h) if isinstance(h, dict) else h for h in htft_top3[:3]],
            "total_goals": ef_engine.get("total_goals", ""),
        },
        "source_fusion": load_source_fusion(mid),
        "final_fusion": {
            "score_ranking": [
                {
                    "score": r["score"],
                    "rank": r["rank"],
                    "reason": r["main_reason"] or "概率派与事件流加权",
                    "raw_probability": round(float(r["raw_probability"]), 4),
                    "eventflow_score": round(float(r["eventflow_score"]), 4),
                    "normalized_fusion_score": round(float(r["normalized_fusion_score"]), 4),
                    "display_probability": (
                        f"{float(r['raw_probability'])*100:.1f}% (V2 calibrated scoreline prob)"
                        if r["raw_probability"] > 0
                        else "ranking score only"
                    ),
                    "display_fusion": (
                        f"{float(r['normalized_fusion_score'])*100:.1f}% ranking score (not calibrated joint prob)"
                    ),
                }
                for r in top3
            ],
            "total_goals": total_goals_fusion([r["score"] for r in top3]),
            "half_full_time_top3": htft_top3,
            "half_full_time": [h.get("label", "") for h in htft_top3[:3]],
            "confidence": confidence_label(prob_rows, len(activated), dq),
            "risk_notes": [
                "normalized_fusion_score 是排序分，不可与赔率隐含概率直接对比",
                "若上半场无早球，大比分权重下降",
                f"估算数据占比 {dq.get('estimated_data_ratio', 0)*100:.0f}%，EventFlow 尾部已降权",
            ],
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    if args.export_json:
        write_json(args.export_json, payload)
        print(f"Wrote {args.export_json}")


if __name__ == "__main__":
    main()
