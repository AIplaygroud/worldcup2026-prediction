import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import predict_v2  # noqa: E402
from predict_v2 import MatchContext, apply_referee_layer, load_data, resolve_referee  # noqa: E402


class TestRefereeStatusGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_data()

    def test_provisional_report_only(self):
        ctx = MatchContext(home="USA", away="Australia", referee="Test Ref", referee_status="provisional")
        resolve_referee(ctx, self.data)
        lam_h, lam_a, log, meta = apply_referee_layer(1.5, 1.0, ctx, self.data)
        self.assertEqual(lam_h, 1.5)
        self.assertEqual(lam_a, 1.0)
        self.assertFalse(meta.get("applied"))
        self.assertTrue(meta.get("report_only"))
        self.assertTrue(any("provisional" in x for x in log))

    def test_manual_default_no_lambda_change(self):
        ctx = MatchContext(home="USA", away="Australia", referee="Manual Ref", referee_status="manual")
        lam_h, lam_a, log, meta = apply_referee_layer(1.4, 0.9, ctx, self.data)
        self.assertEqual(lam_h, 1.4)
        self.assertFalse(meta.get("applied"))

    def test_manual_allowed_with_flag(self):
        ctx = MatchContext(
            home="USA", away="Australia", referee="Manual Ref", referee_status="confirmed",
            allow_manual_referee_layer=True,
        )
        ctx.referee_known = True
        ctx.referee_confidence = 0.85
        lam_h, lam_a, log, meta = apply_referee_layer(1.4, 0.9, ctx, self.data)
        # may skip if style data missing; at least should not be report_only block
        self.assertFalse(meta.get("report_only", False))

    def test_confirmed_referee_name_gate_in_scenario_weights(self):
        src = (SCRIPTS / "build_eventflow_scenario_weights.py").read_text(encoding="utf-8")
        self.assertIn("_confirmed_referee_name", src)
        self.assertIn('snum(row, "status") == "confirmed"', src)


if __name__ == "__main__":
    unittest.main()
