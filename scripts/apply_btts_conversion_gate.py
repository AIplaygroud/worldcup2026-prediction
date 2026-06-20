#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V3.6: BTTS conversion gate — conditional BTTS adjustment on probability grid."""
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
    BTTS_AUDIT_CSV,
    RealizationFeatures,
    apply_btts_delta_to_grid,
    compute_realization_features,
    evaluate_btts_gate,
    grid_from_rows,
    load_diagnostics,
    market_snapshot_from_grid,
    update_diagnostics_block,
)

DEFAULT_PROB_CSV = ROOT / "database" / "eventflow" / "raw" / "probability_engine_scores.csv"

AUDIT_FIELDS = [
    "match_id", "home", "away",
    "data_quality_score", "calibration_strength", "adjustment_strength",
    "threat_presence", "conversion_supported", "conversion_supported_by_quality",
    "adjustment_direction",
    "up_signals_count", "down_signals_count",
    "up_reasons", "down_reasons",
    "btts_before", "btts_after",
    "btts_probability_point_delta", "btts_factor_delta_pct",
    "reasons", "diagnostics_only", "generated_at",
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
    gate = evaluate_btts_gate(features, scenario_rows, lam_home, lam_away)

    grid = grid_from_rows(prob_rows)
    btts_before = market_snapshot_from_grid(grid)["btts"]

    if not enabled or gate.diagnostics_only or abs(gate.btts_factor_delta_pct) < 1e-9:
        gate_block = gate.to_dict()
        gate_block["btts_before"] = btts_before
        gate_block["btts_after"] = btts_before
        gate_block["btts_probability_point_delta"] = 0.0
        update_diagnostics_block(match_id, {"btts_conversion_gate": gate_block})
        _write_audit(match_id, home, away, features, gate, btts_before, btts_before)
        print(f"BTTS gate: no adjustment ({gate.adjustment_direction}, diagnostics_only={gate.diagnostics_only})")
        return gate_block

    new_grid = apply_btts_delta_to_grid(grid, gate.btts_factor_delta_pct)
    snap = market_snapshot_from_grid(new_grid)
    btts_after = snap["btts"]

    _write_prob_csv(prob_csv, match_id, home, away, lam_home, lam_away, new_grid)
    gate_block = gate.to_dict()
    gate_block["btts_before"] = btts_before
    gate_block["btts_after"] = btts_after
    gate_block["btts_probability_point_delta"] = round(btts_after - btts_before, 4)
    update_diagnostics_block(match_id, {
        "btts_conversion_gate": gate_block,
        "post_btts_gate_snapshot": {
            "btts": btts_after,
            "top_scores": snap["top_scores"],
        },
        "scoreline_probability_grid_pre_tail": snap["scoreline_probability_grid"],
    })
    _write_audit(match_id, home, away, features, gate, btts_before, btts_after)
    print(
        f"BTTS gate: {gate.adjustment_direction} factor {gate.btts_factor_delta_pct:+.2%} "
        f"({btts_before:.3f} -> {btts_after:.3f}, Δ={btts_after - btts_before:+.4f}) "
        f"reasons={gate.reasons}"
    )
    return gate_block


def _write_audit(
    match_id: str,
    home: str,
    away: str,
    features: RealizationFeatures,
    gate,
    btts_before: float,
    btts_after: float,
) -> None:
    ts = datetime.now(timezone.utc).isoformat()
    row = {
        "match_id": match_id,
        "home": home,
        "away": away,
        "data_quality_score": round(features.data_quality.data_quality_score, 4),
        "calibration_strength": features.data_quality.calibration_strength,
        "adjustment_strength": gate.adjustment_strength,
        "threat_presence": gate.threat_presence,
        "conversion_supported": gate.conversion_supported,
        "conversion_supported_by_quality": gate.conversion_supported_by_quality,
        "adjustment_direction": gate.adjustment_direction,
        "up_signals_count": gate.up_signals_count,
        "down_signals_count": gate.down_signals_count,
        "up_reasons": ";".join(gate.up_reasons),
        "down_reasons": ";".join(gate.down_reasons),
        "btts_before": round(btts_before, 4),
        "btts_after": round(btts_after, 4),
        "btts_probability_point_delta": round(btts_after - btts_before, 4),
        "btts_factor_delta_pct": gate.btts_factor_delta_pct,
        "reasons": ";".join(gate.reasons),
        "diagnostics_only": gate.diagnostics_only,
        "generated_at": ts,
    }
    existing = [r for r in read_csv(BTTS_AUDIT_CSV) if snum(r, "match_id") != match_id]
    write_csv(BTTS_AUDIT_CSV, existing + [row], fieldnames=AUDIT_FIELDS)


def main() -> None:
    ap = argparse.ArgumentParser(description="V3.6 BTTS conversion gate")
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
