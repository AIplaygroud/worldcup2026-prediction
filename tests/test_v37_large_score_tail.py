"""V3.7-P2 large-score tail layer tests."""
from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from eventflow_common import read_json  # noqa: E402
from scenario_realization_common import load_v37_features  # noqa: E402
from v37_large_score_tail import (  # noqa: E402
    apply_tail_to_payload,
    evaluate_tail_level,
    load_p2_context,
)
from validate_v37_large_score_tail import validate_match  # noqa: E402


def _minimal_payload(match_id: str = "WC2026-TEST") -> dict:
    return {
        "match_id": match_id,
        "eventflow_data_degraded": False,
        "probability_engine": {
            "lambda_home": 2.0,
            "lambda_away": 1.0,
            "adjusted_lambda": {"home": 2.0, "away": 1.0},
            "adjusted_probability": {"home_win": 0.6, "draw": 0.2, "away_win": 0.2},
        },
        "final_fusion": {
            "score_ranking": [
                {"score": "2-0", "rank": 1, "v2_scoreline_probability": 0.15, "fusion_ranking_score": 0.15},
                {"score": "3-0", "rank": 5, "v2_scoreline_probability": 0.08, "fusion_ranking_score": 0.08},
                {"score": "3-1", "rank": 6, "v2_scoreline_probability": 0.07, "fusion_ranking_score": 0.07},
                {"score": "4-0", "rank": 8, "v2_scoreline_probability": 0.04, "fusion_ranking_score": 0.04},
            ],
        },
    }


class TestNoLambdaMutation(unittest.TestCase):
    def test_audit_preserves_lambda(self):
        path = ROOT / "database/eventflow/processed/dual_engine_output_F35_v37_test.json"
        if not path.exists():
            self.skipTest("F35 fixture missing")
        payload = read_json(path, {})
        before = copy.deepcopy(payload["probability_engine"])
        result = apply_tail_to_payload(payload, mode="rerank_only")
        after = result["payload"]["probability_engine"]
        self.assertEqual(before.get("lambda_home"), after.get("lambda_home"))
        self.assertEqual(before.get("lambda_away"), after.get("lambda_away"))
        self.assertEqual(before.get("adjusted_probability"), after.get("adjusted_probability"))
        self.assertTrue(result["audit"]["no_lambda_mutation"])


class TestE34NoTailBoost(unittest.TestCase):
    def test_e34_blocked(self):
        path = ROOT / "database/eventflow/processed/dual_engine_output_E34_v37_test.json"
        if not path.exists():
            self.skipTest("E34 fixture missing")
        payload = read_json(path, {})
        payload["match_id"] = "WC2026-E34"
        audit = apply_tail_to_payload(payload, mode="rerank_only")["audit"]
        self.assertEqual(audit["v37_large_score_tail"]["boosted_scores"], [])
        self.assertEqual(audit["v37_large_score_tail"]["tail_boost_level"], "none")
        blockers = audit["evaluation"]["block_reasons"]
        self.assertTrue(
            "cold_guard_active" in blockers or "guard_suppression_enabled" in blockers
        )


class TestColdGuardSuppresses(unittest.TestCase):
    def test_synthetic_cold_guard(self):
        ctx = {
            "data_quality_score": 0.7,
            "cold_guard_active": True,
            "deep_handicap_contra_flag": False,
            "must_win_no_convert_favorite": False,
            "eventflow_degraded": False,
            "egci_proxy_only": False,
            "favorite_acg": 0.75,
            "egci": 0.7,
            "underdog_fragility": 0.7,
            "underdog_chase_pressure": 0.6,
        }
        th = {
            "min_data_quality": 0.55,
            "acg_mild": 0.58,
            "acg_medium": 0.65,
            "acg_strong": 0.72,
            "egci_mild": 0.58,
            "egci_medium": 0.65,
            "egci_strong": 0.72,
            "chase_medium": 0.55,
            "fragility_strong": 0.65,
        }
        ev = evaluate_tail_level(ctx, th)
        self.assertEqual(ev["tail_boost_level"], "none")
        self.assertIn("cold_guard_active", ev["block_reasons"])


class TestMustWinNoConvertSuppresses(unittest.TestCase):
    def test_favorite_must_win_blocks(self):
        ctx = {
            "data_quality_score": 0.7,
            "cold_guard_active": False,
            "deep_handicap_contra_flag": False,
            "must_win_no_convert_favorite": True,
            "eventflow_degraded": False,
            "egci_proxy_only": False,
            "favorite_acg": 0.75,
            "egci": 0.7,
            "underdog_fragility": 0.7,
            "underdog_chase_pressure": 0.6,
        }
        th = {
            "min_data_quality": 0.55,
            "acg_mild": 0.58,
            "acg_medium": 0.65,
            "acg_strong": 0.72,
            "egci_mild": 0.58,
            "egci_medium": 0.65,
            "egci_strong": 0.72,
            "chase_medium": 0.55,
            "fragility_strong": 0.65,
        }
        ev = evaluate_tail_level(ctx, th)
        self.assertIn("must_win_no_convert_favorite", ev["block_reasons"])


class TestAuditReasons(unittest.TestCase):
    def test_audit_json_fields(self):
        path = ROOT / "database/eventflow/processed/dual_engine_output_F36_v37_test.json"
        if not path.exists():
            self.skipTest("F36 fixture missing")
        payload = read_json(path, {})
        payload["match_id"] = "WC2026-F36"
        audit = apply_tail_to_payload(payload, mode="audit_only")["audit"]
        self.assertIn("v37_large_score_tail", audit)
        self.assertIn("evaluation", audit)
        self.assertTrue(audit["v37_large_score_tail"]["no_lambda_mutation"])


class TestDataQualityThreshold(unittest.TestCase):
    def test_low_quality_audit_only(self):
        ctx = {
            "data_quality_score": 0.4,
            "cold_guard_active": False,
            "deep_handicap_contra_flag": False,
            "must_win_no_convert_favorite": False,
            "eventflow_degraded": False,
            "egci_proxy_only": False,
            "favorite_acg": 0.8,
            "egci": 0.8,
            "underdog_fragility": 0.7,
            "underdog_chase_pressure": 0.6,
        }
        th = {"min_data_quality": 0.65, "acg_mild": 0.58, "egci_mild": 0.58,
              "acg_medium": 0.65, "egci_medium": 0.65, "acg_strong": 0.72,
              "egci_strong": 0.72, "fragility_mild": 0.50, "fragility_medium": 0.62,
              "fragility_strong": 0.70, "chase_medium": 0.55, "chase_strong": 0.65}
        ev = evaluate_tail_level(ctx, th)
        self.assertIn("data_quality_below_threshold", ev["block_reasons"])


class TestRegressionValidation(unittest.TestCase):
    FIXTURES = {
        "WC2026-E34": "dual_engine_output_E34_v37_test.json",
        "WC2026-F35": "dual_engine_output_F35_v37_test.json",
        "WC2026-F36": "dual_engine_output_F36_v37_test.json",
    }

    def test_all_regression(self):
        for mid, fname in self.FIXTURES.items():
            path = ROOT / "database/eventflow/processed" / fname
            if not path.exists():
                self.skipTest(f"{fname} missing")
            payload = read_json(path, {})
            payload["match_id"] = mid
            errs = validate_match(mid, payload)
            self.assertEqual(errs, [], msg=f"{mid}: {errs}")


class TestLoadP2Context(unittest.TestCase):
    def test_e34_features_loaded(self):
        csv_path = ROOT / "database/v37/features/v37_realization_features.csv"
        if not csv_path.exists():
            self.skipTest("features not built")
        ctx = load_p2_context("WC2026-E34")
        self.assertTrue(ctx.get("cold_guard_active"))
        self.assertTrue(ctx.get("must_win_no_convert_favorite"))


if __name__ == "__main__":
    unittest.main()
