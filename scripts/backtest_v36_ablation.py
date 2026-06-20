#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V3.6 ablation backtest: V3.5 baseline vs Full V3.6 on R2 review matches."""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys_path = str(SCRIPTS)
import sys

sys.path.insert(0, sys_path)

from eventflow_common import EVENTFLOW_DB, fnum, snum  # noqa: E402
from scenario_realization_common import (  # noqa: E402
    DIAG_PATH,
    classify_scoreline_family,
    favorite_side,
    load_diagnostics,
)

PROCESSED = EVENTFLOW_DB
RAW = ROOT / "database" / "eventflow" / "raw"

DEFAULT_MATCHES = [
    ("WC2026-D32", "USA", "Australia", "2-0", "database/eventflow/processed/dual_engine_output_D32_USA_AUS_balanced_v36.json"),
    ("WC2026-C29", "Brazil", "Haiti", "3-0", "database/eventflow/processed/dual_engine_output_C29_BRA_HTI_balanced_v36.json"),
    ("WC2026-C30", "Scotland", "Morocco", "0-1", "database/eventflow/processed/dual_engine_output_C30_SCO_MAR_balanced_v36.json"),
    ("WC2026-D31", "Turkey", "Paraguay", "0-1", "database/eventflow/processed/dual_engine_output_D31_TUR_PAR_balanced_v36.json"),
]

DETAIL_FIELDS = [
    "match_id", "home", "away", "version", "actual_score", "actual_result",
    "actual_btts", "actual_total_goals", "top1_score", "top3_scores",
    "top1_hit", "top3_hit", "pred_home_win", "pred_draw", "pred_away_win",
    "pred_btts", "pred_over25", "pred_over35", "actual_score_probability",
    "btts_log_loss", "btts_brier", "total_goals_bucket_log_loss",
    "scoreline_family_hit",
]

METRIC_FIELDS = [
    "version", "n", "one_x_two_accuracy", "top1_scoreline_hit_rate",
    "top3_scoreline_hit_rate", "btts_log_loss", "btts_brier",
    "over25_log_loss", "over35_log_loss", "total_goals_bucket_log_loss",
    "mean_actual_score_probability",
]


def _parse_score(score: str) -> Tuple[int, int]:
    h, a = score.split("-")
    return int(h), int(a)


def _result(h: int, a: int) -> str:
    if h > a:
        return "H"
    if h < a:
        return "A"
    return "D"


def _total_bucket(total: int) -> str:
    if total <= 1:
        return "0-1"
    if total == 2:
        return "2"
    if total == 3:
        return "3"
    if total == 4:
        return "4"
    return "5+"


def _grid_probs(grid: Sequence[Dict[str, Any]]) -> Dict[str, float]:
    return {snum(g, "score"): fnum(g, "probability") for g in grid}


def _aggregate_markets(grid: Sequence[Dict[str, Any]]) -> Dict[str, float]:
    p_h = p_d = p_a = over25 = over35 = btts = 0.0
    for g in grid:
        p = fnum(g, "probability")
        h = int(g.get("home_goals", 0))
        a = int(g.get("away_goals", 0))
        r = _result(h, a)
        if r == "H":
            p_h += p
        elif r == "D":
            p_d += p
        else:
            p_a += p
        t = h + a
        if t >= 3:
            over25 += p
        if t >= 4:
            over35 += p
        if h >= 1 and a >= 1:
            btts += p
    return {
        "home_win": p_h, "draw": p_d, "away_win": p_a,
        "over25": over25, "over35": over35, "btts": btts,
    }


def _top_scores(grid: Sequence[Dict[str, Any]], n: int = 3) -> List[str]:
    ranked = sorted(grid, key=lambda g: -fnum(g, "probability"))
    return [snum(g, "score") for g in ranked[:n]]


def _bucket_probs(grid: Sequence[Dict[str, Any]]) -> Dict[str, float]:
    out = {k: 0.0 for k in ("0-1", "2", "3", "4", "5+")}
    for g in grid:
        h = int(g.get("home_goals", 0))
        a = int(g.get("away_goals", 0))
        out[_total_bucket(h + a)] += fnum(g, "probability")
    return out


def _log_loss(p: float) -> float:
    return -math.log(max(min(p, 1.0 - 1e-12), 1e-12))


def _brier(p: float, actual: bool) -> float:
    return (p - (1.0 if actual else 0.0)) ** 2


def load_grid_for_version(match_id: str, version: str, json_rel: str) -> List[Dict[str, Any]]:
    diag = load_diagnostics(match_id)
    if version == "v35_baseline":
        grid = diag.get("v35_baseline_scoreline_grid") or []
        if not grid:
            grid = diag.get("scoreline_probability_grid_pre_tail") or []
        if grid:
            return grid
        adj = diag.get("adjusted_probability", {})
        if diag.get("scoreline_probability_grid") and diag.get("probabilities_from") == "adjusted_lambda":
            return diag["scoreline_probability_grid"]
        pe = {}
        path = ROOT / json_rel
        if path.exists():
            pe = json.loads(path.read_text(encoding="utf-8")).get("probability_engine", {})
        grid = pe.get("scoreline_probability_grid") or []
        if grid and pe.get("probabilities_from") != "v36_realized":
            return grid
        snap = diag.get("adjusted_probability", {})
        if snap and diag.get("base_probability_snapshot"):
            pass
        return grid
    if version == "full_v36":
        path = ROOT / json_rel
        if path.exists():
            pe = json.loads(path.read_text(encoding="utf-8")).get("probability_engine", {})
            grid = pe.get("scoreline_probability_grid") or []
            if grid:
                return grid
        return diag.get("scoreline_probability_grid") or []
    raise ValueError(f"unknown version {version}")


def evaluate_match(
    match_id: str,
    home: str,
    away: str,
    actual_score: str,
    version: str,
    json_rel: str,
) -> Dict[str, Any]:
    grid = load_grid_for_version(match_id, version, json_rel)
    if not grid:
        raise SystemExit(f"No grid for {match_id} version={version}")

    ah, aa = _parse_score(actual_score)
    actual_result = _result(ah, aa)
    actual_btts = ah >= 1 and aa >= 1
    actual_total = ah + aa
    actual_bucket = _total_bucket(actual_total)

    markets = _aggregate_markets(grid)
    top3 = _top_scores(grid, 3)
    top1 = top3[0] if top3 else ""
    probs = _grid_probs(grid)
    p_actual = probs.get(actual_score, 0.0)
    bucket_probs = _bucket_probs(grid)
    p_bucket = bucket_probs.get(actual_bucket, 0.0)

    lam_h = fnum(load_diagnostics(match_id), "lambda_home") or 1.5
    lam_a = fnum(load_diagnostics(match_id), "lambda_away") or 1.0
    fav = favorite_side(lam_h, lam_a)
    fam = classify_scoreline_family(actual_score, fav)
    fam_scores = [s for s in probs if classify_scoreline_family(s, fav) == fam]
    fam_mass = sum(probs[s] for s in fam_scores)
    fam_top3 = sorted(fam_scores, key=lambda s: -probs[s])[:3]
    family_hit = 1 if actual_score in fam_top3 else 0

    pred_result = max(
        [("H", markets["home_win"]), ("D", markets["draw"]), ("A", markets["away_win"])],
        key=lambda x: x[1],
    )[0]

    return {
        "match_id": match_id,
        "home": home,
        "away": away,
        "version": version,
        "actual_score": actual_score,
        "actual_result": actual_result,
        "actual_btts": int(actual_btts),
        "actual_total_goals": actual_total,
        "top1_score": top1,
        "top3_scores": ";".join(top3),
        "top1_hit": int(top1 == actual_score),
        "top3_hit": int(actual_score in top3),
        "pred_home_win": round(markets["home_win"], 4),
        "pred_draw": round(markets["draw"], 4),
        "pred_away_win": round(markets["away_win"], 4),
        "pred_btts": round(markets["btts"], 4),
        "pred_over25": round(markets["over25"], 4),
        "pred_over35": round(markets["over35"], 4),
        "actual_score_probability": round(p_actual, 6),
        "btts_log_loss": round(_log_loss(markets["btts"] if actual_btts else 1 - markets["btts"]), 6),
        "btts_brier": round(_brier(markets["btts"], actual_btts), 6),
        "total_goals_bucket_log_loss": round(_log_loss(p_bucket), 6),
        "scoreline_family_hit": family_hit,
        "result_hit": int(pred_result == actual_result),
        "over25_log_loss": round(
            _log_loss(markets["over25"] if actual_total >= 3 else 1 - markets["over25"]), 6,
        ),
        "over35_log_loss": round(
            _log_loss(markets["over35"] if actual_total >= 4 else 1 - markets["over35"]), 6,
        ),
        "scoreline_family_mass": round(fam_mass, 4),
    }


def aggregate_metrics(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_ver: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        by_ver.setdefault(r["version"], []).append(r)
    out: List[Dict[str, Any]] = []
    for ver, rs in by_ver.items():
        n = len(rs)
        out.append({
            "version": ver,
            "n": n,
            "one_x_two_accuracy": round(sum(r["result_hit"] for r in rs) / n, 4),
            "top1_scoreline_hit_rate": round(sum(r["top1_hit"] for r in rs) / n, 4),
            "top3_scoreline_hit_rate": round(sum(r["top3_hit"] for r in rs) / n, 4),
            "btts_log_loss": round(sum(r["btts_log_loss"] for r in rs) / n, 6),
            "btts_brier": round(sum(r["btts_brier"] for r in rs) / n, 6),
            "over25_log_loss": round(sum(r["over25_log_loss"] for r in rs) / n, 6),
            "over35_log_loss": round(sum(r["over35_log_loss"] for r in rs) / n, 6),
            "total_goals_bucket_log_loss": round(
                sum(r["total_goals_bucket_log_loss"] for r in rs) / n, 6,
            ),
            "mean_actual_score_probability": round(
                sum(r["actual_score_probability"] for r in rs) / n, 6,
            ),
        })
    return out


def write_summary_md(metrics: List[Dict[str, Any]], details: List[Dict[str, Any]], path: Path) -> None:
    lines = [
        "# V3.6 Ablation Summary",
        "",
        "## Aggregate metrics",
        "",
        "| version | n | 1X2 acc | top1 | top3 | BTTS LL | BTTS Brier | O2.5 LL | bucket LL |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for m in metrics:
        lines.append(
            f"| {m['version']} | {m['n']} | {m['one_x_two_accuracy']:.2f} | "
            f"{m['top1_scoreline_hit_rate']:.2f} | {m['top3_scoreline_hit_rate']:.2f} | "
            f"{m['btts_log_loss']:.4f} | {m['btts_brier']:.4f} | "
            f"{m['over25_log_loss']:.4f} | {m['total_goals_bucket_log_loss']:.4f} |"
        )
    lines.extend(["", "## Match details", ""])
    for d in details:
        lines.append(
            f"- **{d['match_id']}** `{d['version']}` actual={d['actual_score']} "
            f"top1={d['top1_score']} hit1={d['top1_hit']} hit3={d['top3_hit']} "
            f"BTTS pred={d['pred_btts']:.3f} actual={d['actual_btts']}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description="V3.6 ablation backtest")
    ap.add_argument("--matches", default=",".join(m[0] for m in DEFAULT_MATCHES))
    args = ap.parse_args()
    wanted = {x.strip() for x in args.matches.split(",") if x.strip()}

    details: List[Dict[str, Any]] = []
    for mid, home, away, actual, json_rel in DEFAULT_MATCHES:
        if mid not in wanted:
            continue
        for version in ("v35_baseline", "full_v36"):
            details.append(evaluate_match(mid, home, away, actual, version, json_rel))

    metrics = aggregate_metrics(details)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    detail_path = PROCESSED / "v36_ablation_match_details.csv"
    metric_path = PROCESSED / "v36_ablation_metrics.csv"
    summary_path = PROCESSED / "v36_ablation_summary.md"

    with detail_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=DETAIL_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(details)
    with metric_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=METRIC_FIELDS)
        w.writeheader()
        w.writerows(metrics)
    write_summary_md(metrics, details, summary_path)
    print(f"Wrote {detail_path}")
    print(f"Wrote {metric_path}")
    print(f"Wrote {summary_path}")
    for m in metrics:
        print(
            f"{m['version']}: 1X2={m['one_x_two_accuracy']:.0%} "
            f"top3={m['top3_scoreline_hit_rate']:.0%} BTTS_LL={m['btts_log_loss']:.4f}"
        )


if __name__ == "__main__":
    main()
