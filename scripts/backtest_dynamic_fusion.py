#!/usr/bin/env python3
"""Compare legacy fixed fusion with automatic fusion on completed matches."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "database" / "eventflow" / "raw" / "actual_results.csv"
OUT_JSON = ROOT / "outputs" / "anti_overfit_dynamic_fusion_backtest.json"
OUT_MD = ROOT / "outputs" / "anti_overfit_dynamic_fusion_backtest.md"

CASES = {
    "WC2026-C29": (
        "database/eventflow/processed/dual_engine_output_C29_BRA_HTI_balanced_v36.json",
        "outputs/phase05A_r2_prediction_pipeline/predictions/WC2026-C29_Brazil_Haiti_auto_phase05A.json",
    ),
    "WC2026-C30": (
        "database/eventflow/processed/dual_engine_output_C30_SCO_MAR_balanced_v36.json",
        "outputs/phase05A_r2_prediction_pipeline/predictions/WC2026-C30_Scotland_Morocco_auto_phase05A.json",
    ),
    "WC2026-D31": (
        "database/eventflow/processed/dual_engine_output_D31_TUR_PAR_balanced_v36.json",
        "outputs/phase05A_r2_prediction_pipeline/predictions/WC2026-D31_Turkey_Paraguay_auto_phase05A.json",
    ),
    "WC2026-D32": (
        "database/eventflow/processed/dual_engine_output_D32_USA_AUS_balanced_v36.json",
        "outputs/phase05A_r2_prediction_pipeline/predictions/WC2026-D32_USA_Australia_auto_phase05A.json",
    ),
    "WC2026-G39": (
        "outputs/WC2026-G39_Belgium_Iran_balanced_v36_v37_final.json",
        "outputs/phase05A_r2_prediction_pipeline/predictions/WC2026-G39_Belgium_Iran_auto_phase05A.json",
    ),
    "WC2026-G40": (
        "outputs/WC2026-G40_NewZealand_Egypt_balanced_v36_v37_final.json",
        "outputs/phase05A_r2_prediction_pipeline/predictions/WC2026-G40_New_Zealand_Egypt_auto_phase05A.json",
    ),
    "WC2026-H37": (
        "outputs/WC2026-H37_Uruguay_CapeVerde_balanced_v36_v37_final.json",
        "outputs/phase05A_r2_prediction_pipeline/predictions/WC2026-H37_Uruguay_Cape_Verde_auto_phase05A.json",
    ),
    "WC2026-H38": (
        "outputs/WC2026-H38_Spain_SaudiArabia_balanced_v36_v37_final.json",
        "outputs/phase05A_r2_prediction_pipeline/predictions/WC2026-H38_Spain_Saudi_Arabia_auto_phase05A.json",
    ),
}


def score_tuple(score: str) -> tuple[int, int]:
    home, away = score.split("-", 1)
    return int(home), int(away)


def result_class(score: str) -> str:
    home, away = score_tuple(score)
    return "H" if home > away else "A" if home < away else "D"


def load_results() -> dict[str, dict[str, str]]:
    with RESULTS.open(encoding="utf-8-sig", newline="") as handle:
        return {row["match_id"]: row for row in csv.DictReader(handle)}


def load_prediction(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    ranking = data.get("final_fusion", {}).get("score_ranking", [])
    return {
        "scores": [row["score"] for row in ranking],
        "dynamic_weight_profile": data.get("dynamic_weight_profile", {}),
    }


def evaluate(scores: list[str], actual: str) -> dict[str, Any]:
    actual_home, actual_away = score_tuple(actual)
    top = scores[0]
    top_home, top_away = score_tuple(top)
    rank = scores.index(actual) + 1 if actual in scores else None
    return {
        "top1": top,
        "actual_rank": rank,
        "top1_result_hit": result_class(top) == result_class(actual),
        "top3_exact_hit": rank is not None and rank <= 3,
        "top5_exact_hit": rank is not None and rank <= 5,
        "top1_total_goals_abs_error": abs((top_home + top_away) - (actual_home + actual_away)),
        "top1_goal_diff_abs_error": abs((top_home - top_away) - (actual_home - actual_away)),
        "reciprocal_rank": round(1.0 / rank, 4) if rank else 0.0,
    }


def summarize(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
    values = [row[key] for row in rows]
    count = len(values)
    if isinstance(values[0], bool):
        hits = sum(values)
        return {"hits": hits, "count": count, "rate": round(hits / count, 4)}
    return {"count": count, "mean": round(sum(values) / count, 4)}


def main() -> None:
    results = load_results()
    cases: list[dict[str, Any]] = []
    for match_id, (legacy_rel, dynamic_rel) in CASES.items():
        actual = results[match_id]["actual_score"]
        legacy = load_prediction(ROOT / legacy_rel)
        dynamic = load_prediction(ROOT / dynamic_rel)
        cases.append(
            {
                "match_id": match_id,
                "home": results[match_id]["home"],
                "away": results[match_id]["away"],
                "actual_score": actual,
                "legacy_fixed_50_50": evaluate(legacy["scores"], actual),
                "auto_dynamic": {
                    **evaluate(dynamic["scores"], actual),
                    "probability_weight": dynamic["dynamic_weight_profile"].get("probability_weight"),
                    "eventflow_weight": dynamic["dynamic_weight_profile"].get("eventflow_weight"),
                    "reliability_score": dynamic["dynamic_weight_profile"].get("reliability_score"),
                },
            }
        )

    metric_keys = (
        "top1_result_hit",
        "top3_exact_hit",
        "top5_exact_hit",
        "top1_total_goals_abs_error",
        "top1_goal_diff_abs_error",
        "reciprocal_rank",
    )
    report = {
        "design": {
            "sample": "eight completed matches with stored prematch artifacts",
            "comparison": "legacy fixed 50/50 vs auto_dynamic_v1",
            "anti_overfit_guard": (
                "Dynamic coefficients were fixed before this comparison and are not "
                "retuned from these outcomes."
            ),
            "limitations": (
                "Small convenience sample; ranking scores are not calibrated "
                "probabilities, so probability log loss is intentionally omitted."
            ),
        },
        "summary": {
            version: {
                key: summarize([case[version] for case in cases], key)
                for key in metric_keys
            }
            for version in ("legacy_fixed_50_50", "auto_dynamic")
        },
        "cases": cases,
    }
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Dynamic Fusion Backtest",
        "",
        "Eight completed matches using stored prematch artifacts. Coefficients were not retuned from these results.",
        "",
        "| Metric | Legacy fixed 50/50 | Auto dynamic |",
        "|---|---:|---:|",
    ]
    labels = {
        "top1_result_hit": "Top-1 result class",
        "top3_exact_hit": "Top-3 exact score",
        "top5_exact_hit": "Top-5 exact score",
        "top1_total_goals_abs_error": "Top-1 total-goals MAE",
        "top1_goal_diff_abs_error": "Top-1 goal-difference MAE",
        "reciprocal_rank": "Mean reciprocal rank",
    }
    for key in metric_keys:
        old = report["summary"]["legacy_fixed_50_50"][key]
        new = report["summary"]["auto_dynamic"][key]
        old_text = f"{old['hits']}/{old['count']} ({old['rate']:.1%})" if "hits" in old else f"{old['mean']:.3f}"
        new_text = f"{new['hits']}/{new['count']} ({new['rate']:.1%})" if "hits" in new else f"{new['mean']:.3f}"
        lines.append(f"| {labels[key]} | {old_text} | {new_text} |")
    lines += [
        "",
        "## Match Detail",
        "",
        "| Match | Actual | Legacy top-1 / rank | Dynamic top-1 / rank | EventFlow weight |",
        "|---|---:|---:|---:|---:|",
    ]
    for case in cases:
        old = case["legacy_fixed_50_50"]
        new = case["auto_dynamic"]
        lines.append(
            f"| {case['match_id']} {case['home']} vs {case['away']} | {case['actual_score']} | "
            f"{old['top1']} / {old['actual_rank'] or '-'} | {new['top1']} / "
            f"{new['actual_rank'] or '-'} | {new['eventflow_weight']:.1%} |"
        )
    lines += [
        "",
        "## Interpretation",
        "",
        "- This comparison tests ranking behavior, not calibrated payout probability.",
        "- Structural anti-overfit gains are reduced user freedom, bounded EventFlow influence, evidence-quality caps, and no duplicate probability injection.",
        "- Performance promotion requires a larger chronological holdout. This eight-match report is diagnostic only.",
        "",
    ]
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT_JSON.relative_to(ROOT)}")
    print(f"Wrote {OUT_MD.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
