"""Large-score labeling cleanup tests."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from v37_historical_common import classify_large_score  # noqa: E402


class TestLargeScoreLabeling(unittest.TestCase):
    def test_3_0_is_large(self):
        c = classify_large_score(3, 0)
        self.assertTrue(c["is_large_score"])
        self.assertEqual(c["large_score_type"], "favorite_clean_win_3plus")

    def test_0_3_is_large(self):
        c = classify_large_score(0, 3)
        self.assertTrue(c["is_large_score"])

    def test_4_2_is_large(self):
        self.assertTrue(classify_large_score(4, 2)["is_large_score"])

    def test_5_1_extreme(self):
        self.assertEqual(classify_large_score(5, 1)["large_score_type"], "extreme_tail_warning")

    def test_2_2_not_large(self):
        c = classify_large_score(2, 2)
        self.assertFalse(c["is_large_score"])
        self.assertEqual(c["large_score_type"], "not_large_score")

    def test_2_1_not_large(self):
        self.assertFalse(classify_large_score(2, 1)["is_large_score"])


if __name__ == "__main__":
    unittest.main()
