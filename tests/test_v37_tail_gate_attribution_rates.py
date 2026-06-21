"""Gate attribution rate definition tests."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from analyze_v37_tail_gate_attribution import analyze  # noqa: E402
from v37_tail_diagnostics_common import gate_interpretation  # noqa: E402


class TestGateRates(unittest.TestCase):
    def test_rate_formula(self):
        blocked_large, blocked_non = 11, 8
        n = blocked_large + blocked_non
        false_rate = blocked_large / n
        true_rate = blocked_non / n
        self.assertAlmostEqual(false_rate, 11 / 19, places=4)
        self.assertAlmostEqual(true_rate, 8 / 19, places=4)

    def test_overblocking_interpretation(self):
        self.assertEqual(
            gate_interpretation(0.55, 0.45),
            "potential_overblocking_large_scores",
        )

    def test_zero_blocked(self):
        rows, _ = analyze(
            ROOT / "database" / "v37" / "backtest" / "tail_backtest_results.csv",
            ROOT / "database" / "v37" / "backtest" / "tail_backtest_case_audit",
        )
        for r in rows:
            self.assertGreaterEqual(float(r["false_block_rate"]), 0.0)
            self.assertGreaterEqual(float(r["true_block_rate"]), 0.0)


if __name__ == "__main__":
    unittest.main()
