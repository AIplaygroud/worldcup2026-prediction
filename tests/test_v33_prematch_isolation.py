import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from eventflow_source_common import prematch_eligibility  # noqa: E402
from cross_source_validate_signals import grade_claim  # noqa: E402


class TestPrematchIsolation(unittest.TestCase):
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

    def test_eligible_prematch(self):
        elig = prematch_eligibility(self._row())
        self.assertEqual(elig["evidence_partition"], "eligible_prematch")
        grade, _, use_w, use_p, _ = grade_claim(2, 0.7, ["a", "b"], 0.8, "", self._row())
        self.assertEqual(grade, "A")
        self.assertTrue(use_w)
        self.assertTrue(use_p)

    def test_post_match_review_excluded(self):
        row = self._row(evidence_usage="post_match_review")
        elig = prematch_eligibility(row)
        self.assertEqual(elig["evidence_partition"], "excluded_non_prematch")
        grade, _, use_w, use_p, elig2 = grade_claim(1, 0.9, ["a"], 0.9, "", row)
        self.assertEqual(grade, "C")
        self.assertFalse(use_w)
        self.assertFalse(use_p)
        self.assertEqual(elig2["evidence_partition"], "excluded_non_prematch")

    def test_available_false_excluded(self):
        elig = prematch_eligibility(self._row(available_before_kickoff="false"))
        self.assertEqual(elig["evidence_partition"], "excluded_non_prematch")

    def test_published_after_kickoff_excluded(self):
        elig = prematch_eligibility(self._row(published_at="2026-06-22 15:30"))
        self.assertEqual(elig["evidence_partition"], "excluded_non_prematch")
        self.assertIn(elig["exclusion_reason"], {"published_at_not_before_kickoff", "missing_or_unparseable_time"})

    def test_missing_time_excluded(self):
        elig = prematch_eligibility(self._row(published_at="", kickoff_time=""))
        self.assertEqual(elig["evidence_partition"], "excluded_non_prematch")
        self.assertEqual(elig["exclusion_reason"], "missing_or_unparseable_time")

    def test_c_grade_prematch_summary_only(self):
        row = self._row()
        grade, _, use_w, use_p, elig = grade_claim(1, 0.46, ["low_auth"], 0.4, "", row)
        self.assertEqual(grade, "C")
        self.assertFalse(use_w)
        self.assertFalse(use_p)
        self.assertEqual(elig["evidence_partition"], "prematch_summary_only")


if __name__ == "__main__":
    unittest.main()
