#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V3.5: apply realtime availability adjustments to probability-engine λ and re-export scores."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

from eventflow_common import EVENTFLOW_DB, read_csv, snum, write_csv  # noqa: E402
from realtime_availability_common import apply_realtime_lambda_adjustments  # noqa: E402

RAW_SIGNALS = EVENTFLOW_DB.parent / "realtime_availability_signals.csv"
ADJ_OUT = EVENTFLOW_DB / "realtime_availability_adjustments.csv"
DIAG_PATH = ROOT / "database" / "eventflow" / "raw" / "v2_engine_diagnostics.json"
DEFAULT_PROB_CSV = ROOT / "database" / "eventflow" / "raw" / "probability_engine_scores.csv"

ADJUSTMENT_AUDIT_FIELDS = [
    "match_id", "home", "away", "team", "player", "signal_type", "status",
    "role_group", "importance_tier", "replacement_quality", "evidence_grade",
    "confirmed", "minutes_expected_delta",
    "base_role_adjustment_pct", "replacement_multiplier", "evidence_multiplier",
    "minutes_multiplier", "raw_adjustment_pct", "single_signal_capped_pct",
    "team_total_raw_pct", "team_total_capped_pct", "match_total_lambda_change_pct",
    "final_adjustment_pct", "base_lambda_before", "adjusted_lambda_after",
    "lambda_side", "included_for_lambda", "eventflow_also_uses_signal",
    "eventflow_usage_mode", "exclusion_reason", "generated_at",
]


def _score_result_type(h: int, a: int) -> str:
    if h > a:
        return "胜"
    if h < a:
        return "负"
    return "平"


def compute_market_snapshot(lam_h: float, lam_a: float) -> Dict[str, Any]:
    from predict_v2 import build_ft, markets

    ft, _, _ = build_ft(lam_h, lam_a, 1.0, 1.0)
    m = markets(ft)
    grid: List[Dict[str, Any]] = []
    size = len(ft)
    for i in range(size):
        for j in range(size):
            p = ft[i][j]
            if p < 1e-6:
                continue
            grid.append({
                "home_goals": i,
                "away_goals": j,
                "score": f"{i}-{j}",
                "probability": round(p, 6),
            })
    grid.sort(key=lambda x: -x["probability"])
    return {
        "home_win": round(m["pH"], 4),
        "draw": round(m["pD"], 4),
        "away_win": round(m["pA"], 4),
        "over25": round(m["over25"], 4),
        "over35": round(m["over35"], 4),
        "btts": round(m["btts"], 4),
        "top_scores": [f"{i}-{j}" for i, j, _ in m["scores"][:5]],
        "scoreline_probability_grid": grid,
    }


def recompute_probability_rows(
    lam_h: float,
    lam_a: float,
    match_id: str,
    home: str,
    away: str,
) -> List[Dict[str, str]]:
    snap = compute_market_snapshot(lam_h, lam_a)
    created_at = datetime.now(timezone.utc).isoformat()
    rows: List[Dict[str, str]] = []
    for g in snap["scoreline_probability_grid"]:
        i, j = g["home_goals"], g["away_goals"]
        p = g["probability"]
        rows.append({
            "match_id": match_id,
            "home_team": home,
            "away_team": away,
            "lambda_home": f"{lam_h:.4f}",
            "lambda_away": f"{lam_a:.4f}",
            "score": f"{i}-{j}",
            "home_goals": str(i),
            "away_goals": str(j),
            "probability": f"{p:.6f}",
            "total_goals": str(i + j),
            "result_type": _score_result_type(i, j),
            "created_at": created_at,
        })
    return rows


def update_probability_csv(
    csv_path: Path,
    match_id: str,
    home: str,
    away: str,
    lam_h: float,
    lam_a: float,
) -> int:
    existing = read_csv(csv_path) if csv_path.exists() else []
    if match_id:
        existing = [r for r in existing if snum(r, "match_id") != match_id]
    else:
        existing = [
            r for r in existing
            if not (snum(r, "home_team") == home and snum(r, "away_team") == away)
        ]
    new_rows = recompute_probability_rows(lam_h, lam_a, match_id, home, away)
    fieldnames = [
        "match_id", "home_team", "away_team", "lambda_home", "lambda_away",
        "score", "home_goals", "away_goals", "probability", "total_goals",
        "result_type", "created_at",
    ]
    write_csv(csv_path, existing + new_rows, fieldnames=fieldnames)
    return len(new_rows)


def update_diagnostics(
    match_id: str,
    home: str,
    away: str,
    base_h: float,
    base_a: float,
    result,
    base_snap: Dict[str, Any],
    adj_snap: Dict[str, Any],
) -> Dict[str, Any]:
    diag_all: Dict[str, Any] = {}
    if DIAG_PATH.exists():
        with DIAG_PATH.open(encoding="utf-8") as f:
            diag_all = json.load(f)
    key = match_id or f"{home}_vs_{away}"
    diag = diag_all.get(key, {})
    prob_from = "adjusted_lambda" if result.signals_used else "base_lambda"
    diag.update({
        "match_id": match_id,
        "home": home,
        "away": away,
        "base_lambda_home": round(base_h, 4),
        "base_lambda_away": round(base_a, 4),
        "lambda_home": result.adjusted_lambda_home,
        "lambda_away": result.adjusted_lambda_away,
        "availability_adjustment": result.to_availability_block(),
        "adjusted_lambda": {
            "home": result.adjusted_lambda_home,
            "away": result.adjusted_lambda_away,
        },
        "probabilities_from": prob_from,
        "base_probability_snapshot": {
            "home_win": base_snap["home_win"],
            "draw": base_snap["draw"],
            "away_win": base_snap["away_win"],
            "over25": base_snap["over25"],
            "btts": base_snap["btts"],
            "top_scores": base_snap["top_scores"],
        },
        "adjusted_probability": {
            "home_win": adj_snap["home_win"],
            "draw": adj_snap["draw"],
            "away_win": adj_snap["away_win"],
            "over25": adj_snap["over25"],
            "btts": adj_snap["btts"],
            "top_scores": adj_snap["top_scores"],
        },
        "scoreline_probability_grid": adj_snap["scoreline_probability_grid"],
        "realtime_availability_signals": result.included + result.excluded,
        "realtime_signal_usage": [
            {
                "player": s.get("player", ""),
                "included_for_lambda": bool(s.get("included_for_lambda")),
                "eventflow_usage_mode": s.get("eventflow_usage_mode", ""),
                "eventflow_also_uses_signal": s.get("eventflow_also_uses_signal", False),
                "exclusion_reason": s.get("exclusion_reason", ""),
            }
            for s in result.included + result.excluded
        ],
        "included_lambda_adjustments": result.included,
        "excluded_signals_and_reasons": result.excluded,
    })
    diag_all[key] = diag
    DIAG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with DIAG_PATH.open("w", encoding="utf-8") as f:
        json.dump(diag_all, f, ensure_ascii=False, indent=2)
    return diag


def export_adjustments(result, match_id: str, home: str, away: str) -> None:
    rows = []
    ts = datetime.now(timezone.utc).isoformat()
    for s in result.included + result.excluded:
        rows.append({
            "match_id": match_id,
            "home": home,
            "away": away,
            "team": snum(s, "team"),
            "player": snum(s, "player"),
            "signal_type": snum(s, "signal_type"),
            "status": snum(s, "status"),
            "role_group": snum(s, "role_group"),
            "importance_tier": snum(s, "importance_tier"),
            "replacement_quality": snum(s, "replacement_quality"),
            "evidence_grade": snum(s, "evidence_grade"),
            "confirmed": snum(s, "confirmed"),
            "minutes_expected_delta": snum(s, "minutes_expected_delta"),
            "base_role_adjustment_pct": s.get("base_role_adjustment_pct", ""),
            "replacement_multiplier": s.get("replacement_multiplier", ""),
            "evidence_multiplier": s.get("evidence_multiplier", ""),
            "minutes_multiplier": s.get("minutes_multiplier", ""),
            "raw_adjustment_pct": s.get("raw_adjustment_pct", ""),
            "single_signal_capped_pct": s.get("single_signal_capped_pct", s.get("final_adjustment_pct", "")),
            "team_total_raw_pct": s.get("team_total_raw_pct", ""),
            "team_total_capped_pct": s.get("team_total_capped_pct", ""),
            "match_total_lambda_change_pct": s.get(
                "match_total_lambda_change_pct", result.match_total_lambda_change_pct,
            ),
            "final_adjustment_pct": s.get("final_adjustment_pct", 0),
            "base_lambda_before": s.get("base_lambda_before", ""),
            "adjusted_lambda_after": s.get("adjusted_lambda_after", ""),
            "lambda_side": snum(s, "lambda_side"),
            "included_for_lambda": s.get("included_for_lambda", s.get("eligibility_for_lambda")),
            "eventflow_also_uses_signal": s.get("eventflow_also_uses_signal", False),
            "eventflow_usage_mode": snum(s, "eventflow_usage_mode"),
            "exclusion_reason": snum(s, "exclusion_reason"),
            "generated_at": ts,
        })
    write_csv(ADJ_OUT, rows, fieldnames=ADJUSTMENT_AUDIT_FIELDS)


def apply_for_match(
    match_id: str,
    home: str,
    away: str,
    base_lambda_home: float,
    base_lambda_away: float,
    prob_csv: Path,
) -> Dict[str, Any]:
    signals = read_csv(RAW_SIGNALS)
    signals = [s for s in signals if snum(s, "match_id") == match_id]
    base_snap = compute_market_snapshot(base_lambda_home, base_lambda_away)
    result = apply_realtime_lambda_adjustments(
        base_lambda_home, base_lambda_away, home, away, signals,
    )
    adj_snap = compute_market_snapshot(
        result.adjusted_lambda_home, result.adjusted_lambda_away,
    )
    if result.signals_used:
        n = update_probability_csv(
            prob_csv, match_id, home, away,
            result.adjusted_lambda_home, result.adjusted_lambda_away,
        )
        if (
            base_snap["home_win"] == adj_snap["home_win"]
            and base_snap["top_scores"] == adj_snap["top_scores"]
        ):
            print(
                "WARNING: adjusted_lambda applied but 1X2/top_scores unchanged — "
                "check probability recompute pipeline"
            )
        print(
            f"Adjusted λ {base_lambda_home:.4f}/{base_lambda_away:.4f} -> "
            f"{result.adjusted_lambda_home:.4f}/{result.adjusted_lambda_away:.4f} "
            f"({result.signals_used} signals, match Δλ={result.match_total_lambda_change_pct:.2%}); "
            f"1X2 {base_snap['home_win']:.3f}/{base_snap['draw']:.3f}/{base_snap['away_win']:.3f} -> "
            f"{adj_snap['home_win']:.3f}/{adj_snap['draw']:.3f}/{adj_snap['away_win']:.3f}; "
            f"re-exported {n} score rows"
        )
    else:
        adj_snap = base_snap
        print(f"No lambda-eligible realtime signals for {match_id}; keeping base λ")

    export_adjustments(result, match_id, home, away)
    diag = update_diagnostics(
        match_id, home, away, base_lambda_home, base_lambda_away,
        result, base_snap, adj_snap,
    )
    return {
        "match_id": match_id,
        "base_lambda": {"home": base_lambda_home, "away": base_lambda_away},
        "adjusted_lambda": {
            "home": result.adjusted_lambda_home,
            "away": result.adjusted_lambda_away,
        },
        "availability_adjustment": result.to_availability_block(),
        "base_probability_snapshot": diag.get("base_probability_snapshot"),
        "adjusted_probability": diag.get("adjusted_probability"),
        "probabilities_from": diag.get("probabilities_from"),
        "diagnostics": diag,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Apply V3.5 realtime availability λ adjustments")
    ap.add_argument("--match-id", required=True)
    ap.add_argument("--home", required=True)
    ap.add_argument("--away", required=True)
    ap.add_argument("--base-lambda-home", type=float, required=True)
    ap.add_argument("--base-lambda-away", type=float, required=True)
    ap.add_argument("--prob-csv", default=str(DEFAULT_PROB_CSV))
    ap.add_argument("--export-json", default="")
    args = ap.parse_args()

    out = apply_for_match(
        args.match_id, args.home, args.away,
        args.base_lambda_home, args.base_lambda_away,
        Path(args.prob_csv),
    )
    if args.export_json:
        os.makedirs(os.path.dirname(os.path.abspath(args.export_json)), exist_ok=True)
        with open(args.export_json, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print(f"Wrote {args.export_json}")


if __name__ == "__main__":
    main()
