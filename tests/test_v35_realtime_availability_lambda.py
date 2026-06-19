import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from apply_realtime_lambda_adjustment import apply_for_match  # noqa: E402
from realtime_availability_common import (  # noqa: E402
    apply_realtime_lambda_adjustments,
    check_lambda_eligibility,
    compute_signal_adjustment,
)


class TestV35RealtimeAvailabilityLambda(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._apply_out = apply_for_match(
            "WC2026-D32", "USA", "Australia", 1.581, 1.2083,
            ROOT / "database" / "eventflow" / "raw" / "probability_engine_scores.csv",
        )

    def _pulisic_out(self, **kw):
        base = {
            "match_id": "WC2026-D32",
            "team": "USA",
            "opponent": "Australia",
            "player": "Christian Pulisic",
            "signal_type": "injury",
            "status": "out",
            "role_group": "wide_attacker",
            "importance_tier": "core",
            "replacement": "Ricardo Pepi",
            "replacement_quality": "high",
            "evidence_grade": "A",
            "confirmed": "true",
            "source_count": "2",
            "minutes_expected_delta": "-80",
        }
        base.update(kw)
        return base

    def test_core_attacker_out_adjusts_usa_lambda_down(self):
        res = apply_realtime_lambda_adjustments(
            1.581, 1.2083, "USA", "Australia", [self._pulisic_out()],
        )
        self.assertEqual(res.signals_used, 1)
        self.assertLess(res.adjusted_lambda_home, res.base_lambda_home)
        self.assertAlmostEqual(res.adjusted_lambda_away, res.base_lambda_away)
        pct = (res.adjusted_lambda_home / res.base_lambda_home) - 1
        self.assertGreaterEqual(pct, -0.05)
        self.assertLessEqual(pct, -0.02)

    def test_doubtful_unconfirmed_excluded(self):
        ok, reason, ef = check_lambda_eligibility(self._pulisic_out(
            status="doubtful", evidence_grade="C", confirmed="false",
        ))
        self.assertFalse(ok)
        self.assertEqual(reason, "unconfirmed")
        self.assertTrue(ef)

    def test_goalkeeper_out_raises_opponent_lambda(self):
        sig = self._pulisic_out(
            player="Mathew Ryan",
            team="Australia",
            opponent="USA",
            role_group="goalkeeper",
            replacement_quality="low",
        )
        row = compute_signal_adjustment(sig)
        self.assertGreater(float(row["opponent_attack_delta_pct"]), 0.04)

    def test_probabilities_from_adjusted_lambda_in_apply(self):
        out = self._apply_out
        self.assertEqual(out["probabilities_from"], "adjusted_lambda")
        self.assertIn("availability_adjustment", out)
        self.assertLess(
            out["adjusted_lambda"]["home"],
            out["base_lambda"]["home"],
        )

    def test_fusion_input_fields_present_after_merge_import(self):
        diag_path = ROOT / "database" / "eventflow" / "raw" / "v2_engine_diagnostics.json"
        if not diag_path.exists():
            self.skipTest("no diagnostics yet")
        diag = json.loads(diag_path.read_text(encoding="utf-8")).get("WC2026-D32", {})
        self.assertEqual(diag.get("probabilities_from"), "adjusted_lambda")
        self.assertIn("base_lambda_home", diag)
        self.assertIn("availability_adjustment", diag)


if __name__ == "__main__":
    unittest.main()
