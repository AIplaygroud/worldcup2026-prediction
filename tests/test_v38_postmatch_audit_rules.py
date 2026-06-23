import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from eventflow_dynamic_weight import compute_dynamic_fusion_profile  # noqa: E402
from eventflow_htft import halftime_layer_status, summarize_data_quality  # noqa: E402
from predict_eventflow import generate_candidates, score_family_for_match  # noqa: E402
from predict_v2 import open_interval_probabilities  # noqa: E402


class TestV38PostmatchAuditRules(unittest.TestCase):
    def test_away_favorite_score_families_are_mirrored(self):
        row = {
            "scenario_id": "S01_favorite_early_break_open",
            "score_family": "2-0;3-0;3-1",
        }
        self.assertEqual(score_family_for_match(row, favorite_is_home=False), ["0-2", "0-3", "1-3"])

    def test_eventflow_bonus_prefers_away_score_when_away_is_favorite(self):
        scenarios = [
            {
                "scenario_id": "S01_favorite_early_break_open",
                "scenario_name": "强队早球后比赛被打开",
                "score_family": "2-0;3-0;3-1",
                "scenario_ranking_weight": "1.0",
                "data_confidence": "0.9",
            }
        ]
        out = generate_candidates(
            1.2, 1.7, scenarios, scenarios, dynamic_profile={"tail_strength": 0.8}, favorite_is_home=False
        )
        by_score = {r["score"]: r["eventflow_ranking_score"] for r in out}
        self.assertGreater(by_score.get("0-2", 0), by_score.get("2-0", 0))

    def test_no_fixed_85_probability_cap(self):
        p = open_interval_probabilities({"home_win": 0.92, "draw": 0.05, "away_win": 0.03})
        self.assertGreater(p["home_win"], 0.85)
        self.assertLess(p["home_win"], 1.0)
        self.assertAlmostEqual(sum(p.values()), 1.0, places=8)

    def test_eventflow_degraded_goes_probability_only(self):
        profile = compute_dynamic_fusion_profile(
            data_quality={"real_data_rows": 12, "estimated_data_rows": 0, "missing_layers": 0, "real_data_ratio": 1.0},
            source_fusion={"pre_match_evidence_count": 6, "grade_A_count": 2, "grade_B_count": 1, "fused_evidence_rows": 3, "conflict_count": 0},
            scenarios=[{"normalized_weight": 0.5, "data_confidence": 0.9, "raw_tactical_delta": 0.2}],
            eventflow_degraded=True,
        )
        self.assertEqual(profile["eventflow_weight"], 0.0)
        self.assertEqual(profile["probability_weight"], 1.0)

    def test_halftime_layer_is_not_betting_eligible_by_default(self):
        status = halftime_layer_status(
            {"coverage_score": 1.0, "consistency_score": 1.0},
            {"reliability_score": 0.9},
            eventflow_degraded=False,
            htft_top3=[{"label": "平/胜", "score": 0.4}],
        )
        self.assertFalse(status["halftime_betting_eligible"])
        self.assertIn(status["halftime_confidence"], {"low", "medium_reference_only"})
        self.assertEqual(status["halftime_calibration_status"], "not_independently_calibrated")

    def test_data_quality_is_split_not_single_real_ratio(self):
        q = summarize_data_quality("WC2026-C29", "Brazil", "Haiti")
        for key in ("authenticity_score", "coverage_score", "freshness_score", "consistency_score", "overall_data_reliability"):
            self.assertIn(key, q)
        self.assertIn("不等于字段完整", q["note"])


if __name__ == "__main__":
    unittest.main()
