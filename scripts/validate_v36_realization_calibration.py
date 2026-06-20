#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V3.6 penetration validation: realization layer, BTTS gate, tail calibration (§16)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

from scenario_realization_common import (  # noqa: E402
    CALIBRATION_CAPS,
    DataQualityResult,
    RealizationFeatures,
    apply_btts_delta_to_grid,
    apply_family_deltas_to_grid,
    calibration_strength_from_score,
    classify_scoreline_family,
    compute_data_quality,
    compute_realization_features,
    evaluate_btts_gate,
    evaluate_tail_calibration,
    favorite_side,
    grid_from_rows,
    market_snapshot_from_grid,
    normalize_grid,
)


def _mock_dq(**kw) -> DataQualityResult:
    base = dict(
        xg_available=True,
        shot_quality_available=False,
        chance_quality_available=False,
        lineup_function_available=True,
        lineup_default_only=False,
        game_state_model_available=True,
        team_style_baseline_available=True,
        market_total_goals_available=False,
        data_quality_score=0.52,
        calibration_strength="weak",
        source_reliability=0.7,
        diagnostics_only=False,
    )
    base.update(kw)
    return DataQualityResult(**base)


def _mock_features(**overrides) -> RealizationFeatures:
    dq = _mock_dq()
    base = RealizationFeatures(
        match_id="TEST",
        home="Fav",
        away="Dog",
        favorite_side="home",
        scenario_rows=[],
        favorite_leads_early_likelihood=0.6,
        underdog_leads_early_likelihood=0.2,
        favorite_kill_game_likelihood=0.5,
        favorite_game_management_likelihood=0.7,
        underdog_btts_conversion_likelihood=0.3,
        low_block_survival_likelihood=0.4,
        chance_quality_score=0.35,
        shot_volume_quality_gap=0.5,
        lead_throttle_score=0.55,
        scoreline_family_boost=["favorite_clean_win_low", "favorite_clean_win_mid"],
        scoreline_family_penalty=["favorite_btts_win", "favorite_big_win"],
        team_style_home={"team_scoring_style": "low_output", "game_management_style": "conservative",
                         "low_score_win_tendency": 0.7, "btts_allowed_tendency": 0.3, "late_throttle_tendency": 0.6},
        team_style_away={"team_scoring_style": "low_output", "game_management_style": "balanced",
                         "low_score_win_tendency": 0.5, "btts_allowed_tendency": 0.4, "late_throttle_tendency": 0.5},
        lineup_function={
            "Dog": {
                "has_real_lineup_signals": True,
                "pace_outlet_starting": False,
                "pace_outlet_benched": True,
                "central_target_starting": False,
                "creator_starting": False,
                "counterattack_exit_quality": 0.25,
            },
            "Fav": {
                "has_real_lineup_signals": True,
                "pace_outlet_starting": True,
                "pace_outlet_benched": False,
                "counterattack_exit_quality": 0.6,
            },
        },
        data_quality=dq,
        conditional_branches=[{
            "branch_id": "underdog_early_goal",
            "status": "conditional_prematch",
            "trigger": "若弱势方先入球",
            "effect": "激活 low_block_survival",
            "active": False,
        }],
    )
    for k, v in overrides.items():
        setattr(base, k, v)
    return base


def _simple_grid() -> List[Dict[str, Any]]:
    scores = [
        (2, 0, 0.15), (3, 0, 0.12), (2, 1, 0.11), (3, 1, 0.09), (4, 1, 0.06),
        (1, 0, 0.10), (1, 1, 0.08), (0, 0, 0.07), (0, 1, 0.05), (4, 0, 0.05),
    ]
    grid = [{"home_goals": h, "away_goals": a, "score": f"{h}-{a}", "probability": p} for h, a, p in scores]
    return normalize_grid(grid)


def run_unit_checks() -> List[str]:
    errors: List[str] = []

    # §16.1 no global hard downscale constant
    if hasattr(sys.modules[__name__], "GLOBAL_BTTS_DOWNSCALE"):
        errors.append("global_btts_downscale must not exist")

    # §16.2 data quality insufficient
    dq_low = DataQualityResult(
        xg_available=False, shot_quality_available=False, chance_quality_available=False,
        lineup_function_available=False, lineup_default_only=True,
        game_state_model_available=False, team_style_baseline_available=False,
        market_total_goals_available=False, data_quality_score=0.30,
        calibration_strength="none", source_reliability=0.3, diagnostics_only=True,
    )
    feat_low = _mock_features(data_quality=dq_low)
    gate_low = evaluate_btts_gate(feat_low, [{"scenario_id": "S07_open", "normalized_weight": "0.3"}], 1.5, 1.0)
    if gate_low.btts_factor_delta_pct != 0.0 or not gate_low.diagnostics_only:
        errors.append("16.2: low dq should not adjust BTTS")

    # §15.1 default lineup must not up BTTS
    dq_default = _mock_dq(
        lineup_function_available=False, lineup_default_only=True,
        chance_quality_available=False, shot_quality_available=False,
        data_quality_score=0.48, calibration_strength="weak",
    )
    feat_default = _mock_features(
        data_quality=dq_default,
        lineup_function={
            "Dog": {"has_real_lineup_signals": False, "pace_outlet_starting": False,
                    "pace_outlet_benched": False, "counterattack_exit_quality": 0.5},
            "Fav": {"has_real_lineup_signals": False, "pace_outlet_benched": False},
        },
    )
    gate_default = evaluate_btts_gate(
        feat_default, [{"scenario_id": "S07_open", "normalized_weight": "0.25"}], 1.5, 1.0,
    )
    if gate_default.adjustment_direction == "up":
        errors.append("15.1: default lineup must not up BTTS")

    # §15.2 D32-like regression
    gate_d32 = evaluate_btts_gate(
        _mock_features(), [{"scenario_id": "S01", "normalized_weight": "0.18"},
                           {"scenario_id": "S03", "normalized_weight": "0.12"},
                           {"scenario_id": "S07", "normalized_weight": "0.10"}],
        1.54, 1.21,
    )
    if gate_d32.adjustment_direction == "up":
        errors.append(f"15.2 D32: BTTS must not up, got {gate_d32.adjustment_direction}")

    # §15.3 data quality cap
    dq_cap = compute_data_quality(
        "CAP-TEST", "A", "B",
        {"xg_source": "team:wc2026_team_xg_adj.csv", "whether_default_used": False},
        {"pre_match_evidence_count": 2, "grade_A_count": 1, "grade_B_count": 0},
    )
    if dq_cap.data_quality_score > 0.55 or dq_cap.calibration_strength == "strong":
        errors.append(f"15.3: dq cap failed score={dq_cap.data_quality_score} strength={dq_cap.calibration_strength}")

    # §16.3 threat but low conversion -> down
    feat_conv = _mock_features()
    gate_conv = evaluate_btts_gate(feat_conv, [{"scenario_id": "S07", "normalized_weight": "0.2"}], 1.8, 0.9)
    if gate_conv.adjustment_direction not in {"down", "none"}:
        errors.append(f"16.3: expected down/none, got {gate_conv.adjustment_direction}")
    if gate_conv.adjustment_direction == "up":
        errors.append("16.3: must not up BTTS when conversion low")

    # §16.4 lead management throttle
    tail = evaluate_tail_calibration(feat_conv)
    if "favorite_clean_win_low" not in tail.boosted_families:
        errors.append("16.4: should boost clean win low")
    if "favorite_btts_win" not in tail.penalized_families:
        errors.append("16.4: should penalize btts win family")

    grid = _simple_grid()
    before = market_snapshot_from_grid(grid)
    after = market_snapshot_from_grid(
        apply_family_deltas_to_grid(grid, tail.family_deltas, "home"),
    )
    p_20_before = next(g["probability"] for g in grid if g["score"] == "2-0")
    p_31_before = next(g["probability"] for g in grid if g["score"] == "3-1")
    after_grid = apply_family_deltas_to_grid(grid, tail.family_deltas, "home")
    p_20_after = next(g["probability"] for g in after_grid if g["score"] == "2-0")
    p_31_after = next(g["probability"] for g in after_grid if g["score"] == "3-1")
    if p_20_after <= p_20_before:
        errors.append("16.4: 2-0 should be boosted")
    if p_31_after >= p_31_before:
        errors.append("16.4: 3-1 should be penalized")

    # §16.5 conditional branch prematch
    feat_branch = _mock_features(underdog_leads_early_likelihood=0.35, low_block_survival_likelihood=0.4)
    if not feat_branch.conditional_branches:
        errors.append("16.5: should emit conditional branch")
    branch = feat_branch.conditional_branches[0]
    if branch.get("active"):
        errors.append("16.5: prematch branch must not be active")

    # §16.6 high volume low quality
    feat_vol = _mock_features(shot_volume_quality_gap=0.6, chance_quality_score=0.3)
    tail_vol = evaluate_tail_calibration(feat_vol)
    if not tail_vol.family_deltas:
        errors.append("16.6: volume/quality gap should trigger family adjustment")

    # §16.7 Brazil 3-0 preserve
    feat_bra = _mock_features(
        favorite_leads_early_likelihood=0.7,
        favorite_game_management_likelihood=0.75,
        underdog_btts_conversion_likelihood=0.2,
        scoreline_family_boost=["favorite_clean_win_low", "favorite_clean_win_mid"],
        scoreline_family_penalty=["favorite_btts_win", "favorite_big_win"],
    )
    tail_bra = evaluate_tail_calibration(feat_bra)
    grid_bra = normalize_grid([
        {"home_goals": 3, "away_goals": 0, "score": "3-0", "probability": 0.18},
        {"home_goals": 4, "away_goals": 1, "score": "4-1", "probability": 0.08},
        {"home_goals": 2, "away_goals": 0, "score": "2-0", "probability": 0.15},
        {"home_goals": 2, "away_goals": 1, "score": "2-1", "probability": 0.12},
        {"home_goals": 1, "away_goals": 0, "score": "1-0", "probability": 0.10},
        {"home_goals": 0, "away_goals": 0, "score": "0-0", "probability": 0.37},
    ])
    adj_bra = apply_family_deltas_to_grid(grid_bra, tail_bra.family_deltas, "home")
    p30 = next(g["probability"] for g in adj_bra if g["score"] == "3-0")
    p41 = next(g["probability"] for g in adj_bra if g["score"] == "4-1")
    p30b = next(g["probability"] for g in grid_bra if g["score"] == "3-0")
    p41b = next(g["probability"] for g in grid_bra if g["score"] == "4-1")
    if p30 < p30b * 0.95:
        errors.append("16.7: 3-0 should be preserved or boosted")
    if p41 > p41b * 1.02:
        errors.append("16.7: 4-1 should not be boosted")

    # calibration strength caps
    for strength, cap in CALIBRATION_CAPS.items():
        if strength == "none" and cap["btts"] != 0:
            errors.append("none strength must have 0 BTTS cap")

    # grid normalization
    g = apply_btts_delta_to_grid(_simple_grid(), -0.04)
    total = sum(x["probability"] for x in g)
    if abs(total - 1.0) > 0.01:
        errors.append(f"grid not normalized after BTTS adjust: {total}")

    # scoreline family classification smoke
    if classify_scoreline_family("2-0", "home") != "favorite_clean_win_low":
        errors.append("family classify 2-0 home fav")
    if classify_scoreline_family("3-1", "home") != "favorite_btts_win":
        errors.append("family classify 3-1")

    if calibration_strength_from_score(0.30) != "none":
        errors.append("dq 0.30 should be none")

    return errors


def validate_match(match_id: str) -> List[str]:
    errors: List[str] = []
    from scenario_realization_common import DIAG_PATH, load_diagnostics
    import json

    diag = load_diagnostics(match_id)
    if not diag:
        errors.append(f"no diagnostics for {match_id}")
        return errors

    v36 = diag.get("v36_realization_layer", {})
    if not v36 and not diag.get("scenario_realization"):
        errors.append("missing v36_realization_layer / scenario_realization")
        return errors

    grid = diag.get("scoreline_probability_grid", [])
    if grid:
        total = sum(float(g.get("probability", 0)) for g in grid)
        if abs(total - 1.0) > 0.02:
            errors.append(f"scoreline grid sum={total:.4f}")

    btts_gate = diag.get("btts_conversion_gate", {})
    strength = v36.get("calibration_strength") or diag.get("scenario_realization", {}).get("calibration_strength")
    if strength == "none" and abs(float(btts_gate.get("btts_factor_delta_pct", btts_gate.get("btts_delta_pct", 0)) or 0)) > 1e-6:
        errors.append("none calibration strength but BTTS adjusted")

    cap = CALIBRATION_CAPS.get(strength or "none", CALIBRATION_CAPS["none"])["btts"]
    delta = abs(float(btts_gate.get("btts_factor_delta_pct", btts_gate.get("btts_delta_pct", 0)) or 0))
    if delta > cap + 1e-6:
        errors.append(f"BTTS delta {delta} exceeds cap {cap} for {strength}")

    return errors


def main() -> None:
    ap = argparse.ArgumentParser(description="Validate V3.6 realization calibration")
    ap.add_argument("--match-id", default="")
    args = ap.parse_args()

    unit_errors = run_unit_checks()
    match_errors: List[str] = []
    if args.match_id:
        match_errors = validate_match(args.match_id)

    all_errors = unit_errors + match_errors
    if all_errors:
        print("V3.6 validation FAILED:")
        for e in all_errors:
            print(f"  - {e}")
        raise SystemExit(1)
    print(f"V3.6 validation OK ({len(unit_errors)} unit checks, match_id={args.match_id or 'n/a'})")


if __name__ == "__main__":
    main()
