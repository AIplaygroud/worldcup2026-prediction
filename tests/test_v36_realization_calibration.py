import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from scenario_realization_common import (  # noqa: E402
    CALIBRATION_CAPS,
    DataQualityResult,
    RealizationFeatures,
    apply_btts_delta_to_grid,
    apply_family_deltas_to_grid,
    calibration_strength_from_score,
    evaluate_btts_gate,
    evaluate_tail_calibration,
    normalize_grid,
)
from validate_v36_realization_calibration import run_unit_checks  # noqa: E402


class TestV36RealizationCalibration(unittest.TestCase):
    def test_unit_checks_pass(self):
        errors = run_unit_checks()
        self.assertEqual(errors, [], msg="\n".join(errors))

    def test_no_global_btts_downscale(self):
        import scenario_realization_common as src
        self.assertFalse(hasattr(src, "GLOBAL_BTTS_DOWNSCALE"))

    def test_low_dq_diagnostics_only(self):
        dq = DataQualityResult(
            xg_available=False, shot_quality_available=False, chance_quality_available=False,
            lineup_function_available=False, lineup_default_only=True,
            game_state_model_available=False, team_style_baseline_available=False,
            market_total_goals_available=False, data_quality_score=0.30,
            calibration_strength="none", source_reliability=0.2, diagnostics_only=True,
        )
        feat = RealizationFeatures(
            match_id="T", home="A", away="B", favorite_side="home", scenario_rows=[],
            favorite_leads_early_likelihood=0.5, underdog_leads_early_likelihood=0.3,
            favorite_kill_game_likelihood=0.4, favorite_game_management_likelihood=0.5,
            underdog_btts_conversion_likelihood=0.3, low_block_survival_likelihood=0.3,
            chance_quality_score=0.4, shot_volume_quality_gap=0.5, lead_throttle_score=0.4,
            scoreline_family_boost=[], scoreline_family_penalty=[],
            team_style_home={}, team_style_away={},
            lineup_function={}, data_quality=dq,
        )
        gate = evaluate_btts_gate(feat, [{"scenario_id": "S07", "normalized_weight": "0.25"}], 1.5, 1.0)
        self.assertEqual(gate.btts_factor_delta_pct, 0.0)
        self.assertTrue(gate.diagnostics_only)

    def test_btts_cap_by_strength(self):
        for strength, caps in CALIBRATION_CAPS.items():
            self.assertLessEqual(caps["btts"], 0.10)

    def test_grid_stays_normalized(self):
        grid = normalize_grid([
            {"home_goals": 1, "away_goals": 1, "score": "1-1", "probability": 0.2},
            {"home_goals": 2, "away_goals": 0, "score": "2-0", "probability": 0.3},
            {"home_goals": 0, "away_goals": 0, "score": "0-0", "probability": 0.5},
        ])
        adj = apply_btts_delta_to_grid(grid, -0.03)
        total = sum(g["probability"] for g in adj)
        self.assertAlmostEqual(total, 1.0, places=4)

    def test_calibration_strength_thresholds(self):
        self.assertEqual(calibration_strength_from_score(0.30), "none")
        self.assertEqual(calibration_strength_from_score(0.45), "weak")
        self.assertEqual(calibration_strength_from_score(0.65), "medium")
        self.assertEqual(calibration_strength_from_score(0.80), "strong")


if __name__ == "__main__":
    unittest.main()
