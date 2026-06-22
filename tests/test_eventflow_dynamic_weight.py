import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from eventflow_dynamic_weight import compute_dynamic_fusion_profile  # noqa: E402


SCENARIOS = [
    {
        "normalized_weight": 0.30,
        "data_confidence": 0.80,
        "raw_tactical_delta": 0.20,
        "raw_source_delta": 0.10,
    },
    {
        "normalized_weight": 0.20,
        "data_confidence": 0.75,
        "raw_tactical_delta": 0.12,
    },
    {
        "normalized_weight": 0.12,
        "data_confidence": 0.70,
        "raw_player_delta": 0.08,
    },
]


class TestDynamicEventFlowWeight(unittest.TestCase):
    def profile(self, source, dq=None, **kwargs):
        return compute_dynamic_fusion_profile(
            data_quality=dq or {
                "real_data_rows": 12,
                "estimated_data_rows": 0,
                "missing_layers": 0,
                "real_data_ratio": 1.0,
            },
            source_fusion=source,
            scenarios=SCENARIOS,
            **kwargs,
        )

    def test_richer_evidence_gets_more_weight(self):
        weak = self.profile({
            "pre_match_evidence_count": 2,
            "grade_A_count": 0,
            "grade_B_count": 0,
            "fused_evidence_rows": 0,
            "conflict_count": 1,
        })
        strong = self.profile({
            "pre_match_evidence_count": 6,
            "grade_A_count": 2,
            "grade_B_count": 1,
            "fused_evidence_rows": 3,
            "conflict_count": 0,
        })
        self.assertLess(weak["eventflow_weight"], strong["eventflow_weight"])
        self.assertLessEqual(weak["eventflow_weight"], 0.20)
        self.assertLessEqual(strong["eventflow_weight"], 0.35)

    def test_legacy_mode_does_not_change_weights(self):
        source = {
            "pre_match_evidence_count": 5,
            "grade_A_count": 1,
            "grade_B_count": 1,
            "fused_evidence_rows": 2,
            "conflict_count": 0,
        }
        safe = self.profile(source, requested_mode="safe")
        hunting = self.profile(source, requested_mode="hit_hunting")
        self.assertEqual(safe["eventflow_weight"], hunting["eventflow_weight"])
        self.assertTrue(safe["legacy_mode_ignored"])
        self.assertTrue(hunting["legacy_mode_ignored"])

    def test_degraded_eventflow_is_probability_only(self):
        p = self.profile(
            {
                "pre_match_evidence_count": 6,
                "grade_A_count": 3,
                "grade_B_count": 2,
                "fused_evidence_rows": 3,
                "conflict_count": 0,
            },
            eventflow_degraded=True,
        )
        self.assertEqual(p["eventflow_weight"], 0.0)
        self.assertEqual(p["probability_weight"], 1.0)


if __name__ == "__main__":
    unittest.main()

