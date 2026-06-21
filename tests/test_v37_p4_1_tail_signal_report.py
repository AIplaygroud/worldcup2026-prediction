"""P4.1 tail signal improvement report tests."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from report_v37_p4_1_tail_signal_improvement import build_report, ci_gate  # noqa: E402
from v37_common import V37_AUDIT  # noqa: E402


class TestP41Report(unittest.TestCase):
    def test_report_structure(self):
        report = build_report(
            {"sample_size": 33, "large_score_cases": 15, "large_score_top5_recall_delta": 0.0},
            [{"primary_miss_reason": "egci_quality_insufficient", "is_large_score": "true",
              "large_score_type": "favorite_btts_blowout"}],
            [{"gate_name": "egci_quality", "blocked_count": "5", "true_block_rate": "0.8", "false_block_rate": "0.2"}],
            [{"actual_scoreline": "4-2", "count": "2", "covered_by_current_tail_pool": "true"}],
            {}, [], {},
        )
        self.assertTrue(report["diagnostics_complete"])
        self.assertFalse(report["rerank_only_allowed"])
        self.assertIn("audit_only", report["decision"]["allowed_modes"])
        self.assertTrue(report["recommendations"])

    def test_performance_false_blocks_rerank(self):
        report = build_report({}, [], [], [], {}, [], {})
        report["performance_pass"] = False
        report["rerank_only_allowed"] = True
        self.assertTrue(ci_gate(report))

    def test_files_exist(self):
        jpath = V37_AUDIT / "v37_p4_1_tail_signal_improvement_report.json"
        if not jpath.exists():
            self.skipTest("run report script")
        report = json.loads(jpath.read_text(encoding="utf-8"))
        self.assertEqual(report["version"], "v37_p4_1_tail_diagnostics_clean")
        for key in (
            "diagnostic_semantics_clean", "missed_case_filter_valid",
            "large_score_labeling_valid", "ranking_semantics_valid",
        ):
            self.assertIn(key, report)
        self.assertTrue(report["diagnostic_semantics_clean"])
        self.assertFalse(report["rerank_only_allowed"])
        self.assertEqual(ci_gate(report), [])


if __name__ == "__main__":
    unittest.main()
