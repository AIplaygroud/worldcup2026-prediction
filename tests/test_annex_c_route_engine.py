"""Semantic tests for weighted Annex C route modeling."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from annex_c_route_engine import (  # noqa: E402
    annex_scenario_weights,
    best8_third_probabilities,
    expected_route_for_slot,
)
from competition_route_calibration import evaluate_route_ablation  # noqa: E402


def _states() -> dict[str, dict]:
    out = {}
    for i, group in enumerate("ABCDEFGHIJKL"):
        for finish, suffix in enumerate(("a", "b", "c", "d"), 1):
            out[f"{group}{suffix}"] = {
                "group": group,
                "points": 6 - finish,
                "gd": 3 - finish,
                "p_finish_1": 1.0 if finish == 1 else 0.0,
                "p_finish_2": 1.0 if finish == 2 else 0.0,
                "p_finish_3": 1.0 if finish == 3 else 0.0,
                "p_finish_4": 1.0 if finish == 4 else 0.0,
            }
    return out


class TestAnnexCWeights(unittest.TestCase):
    def test_all_scenarios_normalized(self):
        scenarios = annex_scenario_weights(_states())
        self.assertEqual(len(scenarios), 495)
        self.assertAlmostEqual(sum(s["weight"] for s in scenarios), 1.0, places=9)
        self.assertTrue(all(s["weight"] > 0 for s in scenarios))

    def test_best8_probability_bounded_by_third_probability(self):
        states = _states()
        scenarios = annex_scenario_weights(states)
        probs = best8_third_probabilities(states, scenarios)
        for team, probability in probs.items():
            self.assertLessEqual(probability, states[team]["p_finish_3"] + 1e-9)

    def test_winner_route_covers_annex_scenarios(self):
        states = _states()
        scenarios = annex_scenario_weights(states)
        route = expected_route_for_slot("1A", states, scenarios)
        self.assertEqual(route["annex_scenarios_covered"], 495)
        self.assertGreater(route["uncertainty"], 0.0)
        self.assertGreater(route["difficulty"], 0.0)


class TestRouteCalibrationGate(unittest.TestCase):
    def _rows(self, n: int = 30) -> list[dict]:
        return [
            {"variant": "no_competition_state", "n": n},
            {"variant": "state_only", "n": n},
            {
                "variant": "state_plus_advance", "n": n, "log_loss": 0.72,
                "brier": 0.21, "score_topn_hit_rate": 0.30, "htft_rank_hit_rate": 0.28,
            },
            {
                "variant": "state_plus_advance_plus_route", "n": n, "log_loss": 0.70,
                "brier": 0.205, "score_topn_hit_rate": 0.32, "htft_rank_hit_rate": 0.28,
            },
        ]

    def test_rerank_allowed_only_after_stable_improvement(self):
        report = evaluate_route_ablation(self._rows())
        self.assertTrue(report["rerank_only_allowed"])
        self.assertIn("rerank_only", report["allowed_modes"])

    def test_small_sample_remains_audit_only(self):
        report = evaluate_route_ablation(self._rows(n=8))
        self.assertFalse(report["rerank_only_allowed"])
        self.assertEqual(report["allowed_modes"], ["audit_only"])

    def test_core_metric_regression_blocks_rerank(self):
        rows = self._rows()
        rows[-1]["log_loss"] = 0.75
        report = evaluate_route_ablation(rows)
        self.assertFalse(report["rerank_only_allowed"])


if __name__ == "__main__":
    unittest.main()
