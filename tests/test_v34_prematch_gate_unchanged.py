import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from eventflow_source_common import prematch_eligibility  # noqa: E402
from cross_source_validate_signals import grade_claim  # noqa: E402


class TestPrematchGateUnchanged(unittest.TestCase):
    def _row(self, **kwargs):
        base = {
            "evidence_usage": "pre_match_prediction",
            "available_before_kickoff": "true",
            "published_at": "2026-06-22 10:00",
            "kickoff_time": "2026-06-22 12:00",
            "timezone_assumption": "UTC",
            "source_url": "https://example.com/a",
            "source_type": "test",
            "evidence_snippet": "snippet",
            "source_authority": 0.8,
            "tactical_specificity": 0.3,
        }
        base.update(kwargs)
        return base

    def test_available_false_still_excluded(self):
        elig = prematch_eligibility(self._row(available_before_kickoff="false"))
        self.assertEqual(elig["evidence_partition"], "excluded_non_prematch")
        grade, _, use_w, use_p, _ = grade_claim(2, 0.7, ["a", "b"], 0.8, "", self._row(available_before_kickoff="false"))
        self.assertEqual(grade, "C")
        self.assertFalse(use_w)
        self.assertFalse(use_p)
