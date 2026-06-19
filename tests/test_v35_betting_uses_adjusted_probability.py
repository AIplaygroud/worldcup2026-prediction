import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from apply_realtime_lambda_adjustment import compute_market_snapshot  # noqa: E402
from build_betting_strategy import aggregate_had_prob, load_scoreline_grid  # noqa: E402
from realtime_availability_common import apply_realtime_lambda_adjustments  # noqa: E402


def _core_attacker_out():
    return {
        "match_id": "WC2026-BET-TEST",
        "team": "USA",
        "opponent": "Australia",
        "player": "Core Attacker",
        "signal_type": "injury",
        "status": "out",
        "role_group": "wide_attacker",
        "importance_tier": "core",
        "replacement_quality": "high",
        "evidence_grade": "A",
        "confirmed": "true",
        "source_count": "2",
        "minutes_expected_delta": "-90",
    }


class TestV35BettingUsesAdjustedProbability(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base_h, cls.base_a = 1.60, 1.20
        cls.base_snap = compute_market_snapshot(cls.base_h, cls.base_a)
        cls.result = apply_realtime_lambda_adjustments(
            cls.base_h, cls.base_a, "USA", "Australia", [_core_attacker_out()],
        )
        cls.adj_snap = compute_market_snapshot(
            cls.result.adjusted_lambda_home, cls.result.adjusted_lambda_away,
        )
        cls.payload = {
            "match_id": "WC2026-BET-TEST",
            "match": "USA vs Australia",
            "probability_engine": {
                "probabilities_from": "adjusted_lambda",
                "top_scores": cls.adj_snap["top_scores"],
                "scoreline_probability_grid": cls.adj_snap["scoreline_probability_grid"],
            },
            "final_fusion": {"score_ranking": []},
            "eventflow_engine": {},
        }

    def test_load_scoreline_grid_uses_adjusted_grid(self):
        grid = load_scoreline_grid(self.payload)
        had = aggregate_had_prob(grid)
        self.assertLess(had["home"], self.base_snap["home_win"] + 0.001)

    def test_home_win_prob_lower_than_base_after_adjustment(self):
        grid = load_scoreline_grid(self.payload)
        had = aggregate_had_prob(grid)
        base_had = aggregate_had_prob(self.base_snap["scoreline_probability_grid"])
        self.assertLess(had["home"], base_had["home"])
        self.assertGreater(had["draw"], base_had["draw"])

    def test_31_tail_down_11_up(self):
        grid = {g["score"]: g["probability"] for g in load_scoreline_grid(self.payload)}
        base = {g["score"]: g["probability"] for g in self.base_snap["scoreline_probability_grid"]}
        if "3-1" in grid and "3-1" in base:
            self.assertLess(grid["3-1"], base["3-1"])
        if "1-1" in grid and "1-1" in base:
            self.assertGreater(grid["1-1"], base["1-1"])


if __name__ == "__main__":
    unittest.main()
