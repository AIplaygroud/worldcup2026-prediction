"""P4.1 candidate coverage tests."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from analyze_v37_tail_candidate_coverage import analyze  # noqa: E402
from v37_tail_diagnostics_common import recommended_bucket, covered_by_tail_pool  # noqa: E402


class TestCandidateCoverage(unittest.TestCase):
    def test_4_2_open_game_bucket(self):
        bucket = recommended_bucket("4-2")
        self.assertIn(bucket, ("open_game_high_total", "favorite_btts_blowout"))
        self.assertTrue(covered_by_tail_pool("4-2"))

    def test_5_1_extreme_warning(self):
        self.assertEqual(recommended_bucket("5-1"), "extreme_tail_warning")

    def test_coverage_rate(self):
        path = ROOT / "database" / "v37" / "backtest" / "tail_backtest_results.csv"
        if not path.exists():
            self.skipTest("run backtest first")
        rows = analyze(path)
        self.assertTrue(rows)
        large_total = sum(int(r["count"]) for r in rows)
        covered = sum(int(r["count"]) for r in rows if r["covered_by_current_tail_pool"] == "true")
        rate = covered / max(large_total, 1)
        self.assertGreaterEqual(rate, 0.0)
        self.assertLessEqual(rate, 1.0)


if __name__ == "__main__":
    unittest.main()
