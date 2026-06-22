import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_betting_strategy import build_strategy  # noqa: E402

ODDS = ROOT / "database" / "jc-odds" / "processed"
MATCH_GLOB = str(ROOT / "outputs" / "WC2026-*_balanced_v36_v37_final.json")


class TestBettingCompositeExpansion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = build_strategy(
            MATCH_GLOB,
            ODDS / "match_odds_summary.csv",
            ODDS / "match_odds_ttg.csv",
            ODDS / "match_odds_hafu.csv",
            ODDS / "match_odds_crs.csv",
            emit_recommendations=True,
        )

    def test_ttg_composite_keeps_each_price(self):
        rows = [
            c for c in self.result.candidate_pool
            if c.match_id == "WC2026-G40" and c.selection == "总进球2/3/4"
        ]
        self.assertTrue(rows)
        c = rows[0]
        self.assertEqual(c.line_count, 3)
        self.assertEqual(len(c.option_details), 3)
        self.assertIn("3注展开", c.sp_display)
        expected = sum(
            float(o["probability"]) * float(o["sp"]) for o in c.option_details
        ) / 3
        self.assertAlmostEqual(c.expected_return_factor, expected, places=4)

    def test_combo_probability_matches_displayed_legs(self):
        combos = [c for c in self.result.recommended_combos if c.combo_type == "三串一"]
        self.assertTrue(combos)
        combo = combos[0]
        displayed_probability = math.prod(
            float(leg.v2_model_probability) for leg in combo.legs
        )
        self.assertAlmostEqual(combo.combo_probability, displayed_probability, places=4)
        self.assertEqual(combo.line_count, math.prod(leg.line_count for leg in combo.legs))
        self.assertIn("单注合成SP", combo.sp_display)


if __name__ == "__main__":
    unittest.main()

