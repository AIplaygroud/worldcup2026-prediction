#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V3.6: total goals tail calibration via scoreline family re-ranking."""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

from eventflow_common import read_csv, snum, write_csv  # noqa: E402
from scenario_realization_common import (  # noqa: E402
    FAMILY_ADJ_CSV,
    TAIL_AUDIT_CSV,
    apply_family_deltas_to_grid,
    compute_realization_features,
    evaluate_tail_calibration,
    favorite_side,
    grid_from_rows,
    load_diagnostics,
    market_snapshot_from_grid,
    update_diagnostics_block,
)

DEFAULT_PROB_CSV = ROOT / "database" / "eventflow" / "raw" / "probability_engine_scores.csv"

TAIL_AUDIT_FIELDS = [
    "match_id", "home", "away", "data_quality_score", "calibration_strength",
    "four_plus_tail_delta", "boosted_families", "penalized_families",
    "over35_before", "over35_after", "top_scores_before", "top_scores_after",
    "reasons", "diagnostics_only", "generated_at",
]

FAMILY_ADJ_FIELDS = [
    "match_id", "home", "away", "family", "delta", "reason", "generated_at",
]


def _write_prob_csv(
    csv_path: Path,
    match_id: str,
    home: str,
    away: str,
    lam_h: float,
    lam_a: float,
    grid: List[Dict[str, Any]],
) -> int:
    existing = [r for r in read_csv(csv_path) if snum(r, "match_id") != match_id]
    created_at = datetime.now(timezone.utc).isoformat()

    def _result_type(i: int, j: int) -> str:
        if i > j:
            return "胜"
        if i < j:
            return "负"
        return "平"

    rows: List[Dict[str, str]] = []
    for g in grid:
        i, j = g["home_goals"], g["away_goals"]
        rows.append({
            "match_id": match_id,
            "home_team": home,
            "away_team": away,
            "lambda_home": f"{lam_h:.4f}",
            "lambda_away": f"{lam_a:.4f}",
            "score": g["score"],
            "home_goals": str(i),
            "away_goals": str(j),
            "probability": f"{g['probability']:.6f}",
            "total_goals": str(i + j),
            "result_type": _result_type(i, j),
            "created_at": created_at,
        })
    fieldnames = [
        "match_id", "home_team", "away_team", "lambda_home", "lambda_away",
        "score", "home_goals", "away_goals", "probability", "total_goals",
        "result_type", "created_at",
    ]
    write_csv(csv_path, existing + rows, fieldnames=fieldnames)
    return len(rows)


def apply_for_match(
    match_id: str,
    home: str,
    away: str,
    lam_home: float,
    lam_away: float,
    prob_csv: Path,
    enabled: bool = True,
) -> Dict[str, Any]:
    diag = load_diagnostics(match_id)
    prob_rows = [r for r in read_csv(prob_csv) if snum(r, "match_id") == match_id]
    if not prob_rows:
        raise SystemExit(f"No probability rows for {match_id}")

    scenario_rows = [
        r for r in read_csv(ROOT / "database" / "eventflow" / "processed" / "eventflow_scenario_weights.csv")
        if snum(r, "match_id") == match_id
    ]
    features = compute_realization_features(
        match_id, home, away, lam_home, lam_away, scenario_rows, diag,
    )
    tail = evaluate_tail_calibration(features)

    grid = grid_from_rows(prob_rows)
    before = market_snapshot_from_grid(grid)
    fav = favorite_side(lam_home, lam_away)

    if not enabled or tail.diagnostics_only or not tail.family_deltas:
        tail_block = tail.to_dict()
        v36_layer = _build_v36_layer(diag, features, tail, before, before)
        realized = {
            "home_win": before["home_win"],
            "draw": before["draw"],
            "away_win": before["away_win"],
            "over25": before["over25"],
            "over35": before["over35"],
            "btts": before["btts"],
            "top_scores": before["top_scores"],
        }
        update_diagnostics_block(match_id, {
            "total_goals_tail_calibration": tail_block,
            "v36_realization_layer": v36_layer,
            "probabilities_from": "v36_realized",
            "realized_probability": realized,
            "scoreline_probability_grid": before["scoreline_probability_grid"],
            "scenario_realization": diag.get("scenario_realization", {}),
            "btts_conversion_gate": diag.get("btts_conversion_gate", {}),
        })
        _write_audits(match_id, home, away, features, tail, before, before, [])
        print(f"Tail calibration: no adjustment (diagnostics_only={tail.diagnostics_only})")
        return v36_layer

    new_grid = apply_family_deltas_to_grid(grid, tail.family_deltas, fav)
    after = market_snapshot_from_grid(new_grid)

    _write_prob_csv(prob_csv, match_id, home, away, lam_home, lam_away, new_grid)
    tail_block = tail.to_dict()
    v36_layer = _build_v36_layer(diag, features, tail, before, after)
    update_diagnostics_block(match_id, {
        "total_goals_tail_calibration": tail_block,
        "v36_realization_layer": v36_layer,
        "probabilities_from": "v36_realized",
        "realized_probability": {
            "home_win": after["home_win"],
            "draw": after["draw"],
            "away_win": after["away_win"],
            "over25": after["over25"],
            "over35": after["over35"],
            "btts": after["btts"],
            "top_scores": after["top_scores"],
        },
        "scoreline_probability_grid": after["scoreline_probability_grid"],
        "scenario_realization": diag.get("scenario_realization", {}),
        "btts_conversion_gate": diag.get("btts_conversion_gate", {}),
    })
    family_rows = _family_adj_rows(match_id, home, away, tail)
    _write_audits(match_id, home, away, features, tail, before, after, family_rows)
    print(
        f"Tail calibration: over35 {before['over35']:.3f}->{after['over35']:.3f} "
        f"top {before['top_scores'][:3]}->{after['top_scores'][:3]}"
    )
    return v36_layer


def _build_v36_layer(diag, features, tail, before, after) -> Dict[str, Any]:
    btts_gate = diag.get("btts_conversion_gate", {})
    return {
        "data_quality_score": features.data_quality.data_quality_score,
        "calibration_strength": features.data_quality.calibration_strength,
        "diagnostics_only": features.data_quality.diagnostics_only,
        "btts_gate": {
            "direction": btts_gate.get("adjustment_direction", "none"),
            "delta_pct": btts_gate.get("btts_delta_pct", 0.0),
            "reason": btts_gate.get("reasons", []),
        },
        "total_goals_tail": {
            "four_plus_tail_delta": tail.four_plus_tail_delta,
            "boosted_families": tail.boosted_families,
            "penalized_families": tail.penalized_families,
        },
        "scoreline_family_adjustment": tail.family_deltas,
        "top_scores_before": before["top_scores"][:5],
        "top_scores_after": after["top_scores"][:5],
        "conditional_branches": features.conditional_branches,
    }


def _family_adj_rows(match_id: str, home: str, away: str, tail) -> List[Dict[str, Any]]:
    ts = datetime.now(timezone.utc).isoformat()
    rows: List[Dict[str, Any]] = []
    for fam, delta in tail.family_deltas.items():
        rows.append({
            "match_id": match_id,
            "home": home,
            "away": away,
            "family": fam,
            "delta": round(delta, 4),
            "reason": ";".join(tail.reasons),
            "generated_at": ts,
        })
    return rows


def _write_audits(match_id, home, away, features, tail, before, after, family_rows) -> None:
    ts = datetime.now(timezone.utc).isoformat()
    tail_row = {
        "match_id": match_id,
        "home": home,
        "away": away,
        "data_quality_score": round(features.data_quality.data_quality_score, 4),
        "calibration_strength": features.data_quality.calibration_strength,
        "four_plus_tail_delta": tail.four_plus_tail_delta,
        "boosted_families": ";".join(tail.boosted_families),
        "penalized_families": ";".join(tail.penalized_families),
        "over35_before": before["over35"],
        "over35_after": after["over35"],
        "top_scores_before": ";".join(before["top_scores"][:5]),
        "top_scores_after": ";".join(after["top_scores"][:5]),
        "reasons": ";".join(tail.reasons),
        "diagnostics_only": tail.diagnostics_only,
        "generated_at": ts,
    }
    existing_tail = [r for r in read_csv(TAIL_AUDIT_CSV) if snum(r, "match_id") != match_id]
    write_csv(TAIL_AUDIT_CSV, existing_tail + [tail_row], fieldnames=TAIL_AUDIT_FIELDS)

    existing_fam = [r for r in read_csv(FAMILY_ADJ_CSV) if snum(r, "match_id") != match_id]
    write_csv(FAMILY_ADJ_CSV, existing_fam + family_rows, fieldnames=FAMILY_ADJ_FIELDS)


def main() -> None:
    ap = argparse.ArgumentParser(description="V3.6 total goals tail calibration")
    ap.add_argument("--match-id", required=True)
    ap.add_argument("--home", required=True)
    ap.add_argument("--away", required=True)
    ap.add_argument("--lam-home", type=float, required=True)
    ap.add_argument("--lam-away", type=float, required=True)
    ap.add_argument("--prob-csv", default=str(DEFAULT_PROB_CSV))
    ap.add_argument("--disabled", action="store_true")
    args = ap.parse_args()
    apply_for_match(
        args.match_id, args.home, args.away,
        args.lam_home, args.lam_away, Path(args.prob_csv),
        enabled=not args.disabled,
    )


if __name__ == "__main__":
    main()
