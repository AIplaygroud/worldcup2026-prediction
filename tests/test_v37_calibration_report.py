"""P4 calibration report structure tests."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from v37_common import V37_AUDIT  # noqa: E402


class TestCalibrationReport(unittest.TestCase):
    def test_report_has_safety_and_performance(self):
        path = V37_AUDIT / "v37_p2_p3_calibration_report.json"
        if not path.exists():
            self.skipTest("run report_v37_p2_p3_calibration.py")
        report = json.loads(path.read_text(encoding="utf-8"))
        self.assertIn("safety_pass", report)
        self.assertIn("performance_pass", report)
        self.assertIn("rerank_only_allowed", report)
        self.assertIn("rerank_default_allowed", report)
        self.assertFalse(report["rerank_default_allowed"])

    def test_safety_not_equal_performance(self):
        path = V37_AUDIT / "v37_p2_p3_calibration_report.json"
        if not path.exists():
            self.skipTest("no report")
        report = json.loads(path.read_text(encoding="utf-8"))
        if report.get("historical_matches_with_scores", 0) < 5:
            self.assertFalse(report.get("performance_pass", True))


if __name__ == "__main__":
    unittest.main()
