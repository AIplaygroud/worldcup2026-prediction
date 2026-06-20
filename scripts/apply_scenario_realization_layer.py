#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V3.6: compute scenario realization features (剧本兑现层) after EventFlow."""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

from eventflow_common import EVENTFLOW_DB, read_csv, snum, write_csv  # noqa: E402
from scenario_realization_common import (  # noqa: E402
    REALIZATION_FEATURES_CSV,
    compute_realization_features,
    grid_from_rows,
    load_diagnostics,
    market_snapshot_from_grid,
    update_diagnostics_block,
)

DEFAULT_PROB_CSV = ROOT / "database" / "eventflow" / "raw" / "probability_engine_scores.csv"

FEATURE_FIELDS = [
    "match_id", "home", "away", "scenario_id", "scenario_weight",
    "favorite_leads_early_likelihood", "underdog_leads_early_likelihood",
    "favorite_kill_game_likelihood", "favorite_game_management_likelihood",
    "underdog_btts_conversion_likelihood", "low_block_survival_likelihood",
    "chance_quality_score", "shot_volume_quality_gap", "lead_throttle_score",
    "scoreline_family_boost", "scoreline_family_penalty",
    "data_quality_score", "calibration_strength", "generated_at",
]


def _load_source_fusion_summary(match_id: str) -> Dict[str, Any]:
    events = [r for r in read_csv(EVENTFLOW_DB / "source_signal_events.csv") if snum(r, "match_id") == match_id]
    claims = [r for r in read_csv(EVENTFLOW_DB / "source_signal_claims.csv") if snum(r, "match_id") == match_id]
    grade_a = sum(1 for c in claims if snum(c, "evidence_grade") == "A")
    grade_b = sum(1 for c in claims if snum(c, "evidence_grade") == "B")
    return {
        "pre_match_evidence_count": len(events),
        "grade_A_count": grade_a,
        "grade_B_count": grade_b,
    }


def apply_for_match(
    match_id: str,
    home: str,
    away: str,
    lam_home: float,
    lam_away: float,
) -> Dict[str, Any]:
    diag = load_diagnostics(match_id)
    prob_rows = [r for r in read_csv(DEFAULT_PROB_CSV) if snum(r, "match_id") == match_id]
    if prob_rows:
        baseline_snap = market_snapshot_from_grid(grid_from_rows(prob_rows))
        update_diagnostics_block(match_id, {
            "v35_baseline_probability": {
                "home_win": baseline_snap["home_win"],
                "draw": baseline_snap["draw"],
                "away_win": baseline_snap["away_win"],
                "over25": baseline_snap["over25"],
                "over35": baseline_snap["over35"],
                "btts": baseline_snap["btts"],
                "top_scores": baseline_snap["top_scores"],
            },
            "v35_baseline_scoreline_grid": baseline_snap["scoreline_probability_grid"],
            "probabilities_from_pre_v36": diag.get("probabilities_from", "adjusted_lambda"),
        })
    scenario_rows = [
        r for r in read_csv(EVENTFLOW_DB / "eventflow_scenario_weights.csv")
        if snum(r, "match_id") == match_id
    ]
    source_fusion = _load_source_fusion_summary(match_id)
    features = compute_realization_features(
        match_id, home, away, lam_home, lam_away, scenario_rows, diag, source_fusion,
    )

    ts = datetime.now(timezone.utc).isoformat()
    csv_rows = features.primary_rows_for_csv()
    for row in csv_rows:
        row["generated_at"] = ts

    existing = [r for r in read_csv(REALIZATION_FEATURES_CSV) if snum(r, "match_id") != match_id]
    write_csv(REALIZATION_FEATURES_CSV, existing + csv_rows, fieldnames=FEATURE_FIELDS)

    realization_block = {
        "enabled": True,
        "data_quality_score": features.data_quality.data_quality_score,
        "calibration_strength": features.data_quality.calibration_strength,
        "diagnostics_only": features.data_quality.diagnostics_only,
        "favorite_side": features.favorite_side,
        "favorite_leads_early_likelihood": features.favorite_leads_early_likelihood,
        "underdog_leads_early_likelihood": features.underdog_leads_early_likelihood,
        "favorite_game_management_likelihood": features.favorite_game_management_likelihood,
        "underdog_btts_conversion_likelihood": features.underdog_btts_conversion_likelihood,
        "low_block_survival_likelihood": features.low_block_survival_likelihood,
        "chance_quality_score": features.chance_quality_score,
        "shot_volume_quality_gap": features.shot_volume_quality_gap,
        "lead_throttle_score": features.lead_throttle_score,
        "scoreline_family_boost": features.scoreline_family_boost,
        "scoreline_family_penalty": features.scoreline_family_penalty,
        "conditional_branches": features.conditional_branches,
        "team_style_home": features.team_style_home,
        "team_style_away": features.team_style_away,
        "lineup_function": features.lineup_function,
        "data_quality": features.data_quality.to_dict(),
        "audit_file": str(REALIZATION_FEATURES_CSV.relative_to(ROOT)),
    }
    update_diagnostics_block(match_id, {"scenario_realization": realization_block})

    print(
        f"V3.6 realization features: dq={features.data_quality.data_quality_score:.2f} "
        f"strength={features.data_quality.calibration_strength} "
        f"boost={features.scoreline_family_boost} penalty={features.scoreline_family_penalty}"
    )
    return realization_block


def main() -> None:
    ap = argparse.ArgumentParser(description="V3.6 scenario realization layer")
    ap.add_argument("--match-id", required=True)
    ap.add_argument("--home", required=True)
    ap.add_argument("--away", required=True)
    ap.add_argument("--lam-home", type=float, required=True)
    ap.add_argument("--lam-away", type=float, required=True)
    args = ap.parse_args()
    apply_for_match(args.match_id, args.home, args.away, args.lam_home, args.lam_away)


if __name__ == "__main__":
    main()
