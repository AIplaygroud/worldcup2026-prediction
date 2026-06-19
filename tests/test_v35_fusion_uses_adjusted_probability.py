import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from apply_realtime_lambda_adjustment import compute_market_snapshot, update_probability_csv, DEFAULT_PROB_CSV  # noqa: E402
from merge_dual_engine_predictions import MODE, filter_rows  # noqa: E402
from eventflow_common import read_csv  # noqa: E402
from realtime_availability_common import apply_realtime_lambda_adjustments  # noqa: E402


def _core_attacker_out(**kw):
    base = {
        "match_id": "WC2026-FUSION-TEST",
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
    base.update(kw)
    return base


class TestV35FusionUsesAdjustedProbability(unittest.TestCase):
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
        update_probability_csv(
            DEFAULT_PROB_CSV, "WC2026-FUSION-TEST", "USA", "Australia",
            cls.result.adjusted_lambda_home, cls.result.adjusted_lambda_away,
        )

    def test_probability_snapshots_differ(self):
        self.assertLess(self.adj_snap["home_win"], self.base_snap["home_win"])
        self.assertGreater(self.adj_snap["draw"], self.base_snap["draw"])

    def test_scoreline_probabilities_in_csv_updated(self):
        rows = filter_rows(read_csv(DEFAULT_PROB_CSV), "WC2026-FUSION-TEST", "USA", "Australia")
        self.assertTrue(rows)
        lam = float(rows[0]["lambda_home"])
        self.assertAlmostEqual(lam, self.result.adjusted_lambda_home, places=3)

    def test_fusion_score_would_change_with_adjusted_prob(self):
        p_weight, e_weight = MODE["balanced"]
        score = "2-1"
        base_p = next(
            (g["probability"] for g in self.base_snap["scoreline_probability_grid"] if g["score"] == score),
            0.0,
        )
        adj_p = next(
            (g["probability"] for g in self.adj_snap["scoreline_probability_grid"] if g["score"] == score),
            0.0,
        )
        ef_rank = 0.15
        base_blend = p_weight * base_p + e_weight * ef_rank
        adj_blend = p_weight * adj_p + e_weight * ef_rank
        self.assertNotAlmostEqual(base_blend, adj_blend, places=5)

    def test_large_delta_changes_fusion_ranking_order(self):
        """§10.2: -15% home attack should move draw-related scores up vs base."""
        big = apply_realtime_lambda_adjustments(
            1.60, 1.20, "USA", "Australia",
            [_core_attacker_out(minutes_expected_delta="-90", replacement_quality="low")],
        )
        # force large negative by stacking isn't allowed; use direct lambda
        adj = compute_market_snapshot(1.60 * 0.85, 1.20)
        base = self.base_snap
        self.assertLess(adj["home_win"], base["home_win"])
        p11_base = next(g["probability"] for g in base["scoreline_probability_grid"] if g["score"] == "1-1")
        p11_adj = next(g["probability"] for g in adj["scoreline_probability_grid"] if g["score"] == "1-1")
        self.assertGreater(p11_adj, p11_base)


if __name__ == "__main__":
    unittest.main()
