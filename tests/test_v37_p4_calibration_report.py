"""P4 calibration report tests."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from report_v37_p4_tail_calibration import ci_gate, evaluate  # noqa: E402
from v37_common import V37_AUDIT  # noqa: E402


class TestP4CalibrationReport(unittest.TestCase):
    def test_small_sample_performance_false(self):
        report = evaluate({"sample_size": 3, "large_score_cases": 1}, [])
        self.assertFalse(report["performance_pass"])
        self.assertFalse(report["rerank_only_allowed"])

    def test_rerank_only_blocked_below_20(self):
        report = evaluate({
            "sample_size": 15,
            "large_score_cases": 5,
            "large_score_top5_recall_delta": 0.10,
            "tail_false_positive_delta": 0.0,
            "avg_rank_improvement": 1.0,
        }, [])
        self.assertFalse(report["rerank_only_allowed"])

    def test_safety_not_equal_performance(self):
        report = evaluate({"sample_size": 30, "large_score_cases": 8}, [])
        self.assertNotEqual(report["safety_pass"], report["performance_pass"])

    def test_rerank_default_false(self):
        report = evaluate({
            "sample_size": 60,
            "large_score_cases": 15,
            "large_score_top5_recall_delta": 0.15,
            "tail_false_positive_delta": 0.01,
            "avg_rank_improvement": 2.0,
        }, [], manual_approval=False)
        self.assertFalse(report["rerank_default_allowed"])

    def test_guard_violation_fails_safety(self):
        report = evaluate({
            "sample_size": 30,
            "large_score_cases": 8,
            "five_goal_top3_violation_count": 1,
        }, [])
        self.assertFalse(report["safety_pass"])

    def test_p4_report_files_exist(self):
        jpath = V37_AUDIT / "v37_p4_tail_calibration_report.json"
        mpath = V37_AUDIT / "v37_p4_tail_calibration_report.md"
        if not jpath.exists():
            self.skipTest("run report_v37_p4_tail_calibration.py after backtest")
        self.assertTrue(mpath.exists())
        report = json.loads(jpath.read_text(encoding="utf-8"))
        self.assertEqual(report["version"], "v37_p4_tail_calibration")
        self.assertIn("decision", report)

    def test_ci_gate_default_allowed(self):
        report = evaluate({"sample_size": 60, "large_score_cases": 15}, [])
        report["rerank_default_allowed"] = True
        errors = ci_gate(report)
        self.assertTrue(any("manual approval" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
