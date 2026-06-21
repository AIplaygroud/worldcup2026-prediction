"""P4.1 missed large-score analysis tests."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from analyze_v37_missed_large_scores import analyze  # noqa: E402
from v37_tail_diagnostics_common import covered_by_tail_pool, primary_miss_reason  # noqa: E402


class TestMissedLargeScore(unittest.TestCase):
    def test_missed_definition(self):
        rows = analyze(
            ROOT / "database" / "v37" / "backtest" / "tail_backtest_results.csv",
            ROOT / "database" / "v37" / "historical" / "historical_tail_backtest_cases.csv",
            ROOT / "database" / "v37" / "backtest" / "tail_backtest_case_audit",
            ROOT / "database" / "v37" / "historical" / "historical_matches.csv",
        )
        for r in rows:
            self.assertGreater(int(r.get("rerank_actual_rank", 0)), 5)
            self.assertTrue(r.get("primary_miss_reason"))

    def test_primary_miss_reason_nonempty(self):
        case = {
            "actual_scoreline": "7-1", "egci_v2_quality": "proxy", "acg_v2_quality": "proxy",
            "cold_guard_active": "false", "must_win_no_convert": "false",
            "deep_handicap_contra": "false", "data_quality_score": "0.8",
            "egci_v2": "0.5", "acg_favorite": "0.5", "baseline_actual_rank": "20",
        }
        primary, _ = primary_miss_reason(case, {"block_reasons": []})
        self.assertTrue(primary)

    def test_candidate_pool_4_2(self):
        self.assertTrue(covered_by_tail_pool("4-2"))


if __name__ == "__main__":
    unittest.main()
