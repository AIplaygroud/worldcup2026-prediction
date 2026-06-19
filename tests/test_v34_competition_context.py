import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from eventflow_v32_gates import competition_context_for  # noqa: E402


class TestCompetitionContext(unittest.TestCase):
    def test_d32_context_fields(self):
        ctx = competition_context_for("WC2026-D32")
        self.assertTrue(ctx, "competition_context.csv must contain WC2026-D32")
        self.assertEqual(ctx["group"], "D")
        self.assertEqual(int(ctx["round"]), 2)
        self.assertGreaterEqual(float(ctx["home_draw_acceptance"]), 0.75)
        self.assertGreaterEqual(float(ctx["away_draw_acceptance"]), 0.75)
        self.assertGreaterEqual(float(ctx["mutual_draw_acceptance"]), 0.75)
        self.assertGreater(float(ctx["home_controlled_win_incentive"]), 0.45)
        self.assertGreater(float(ctx["late_draw_control_index"]), 0.50)
        self.assertEqual(ctx["context_quality"], "A")

    def test_r1_no_draw_context(self):
        ctx = competition_context_for("WC2026-D4")
        self.assertTrue(ctx)
        self.assertEqual(float(ctx["mutual_draw_acceptance"]), 0.0)
        self.assertEqual(float(ctx["home_controlled_win_incentive"]), 0.0)

    def test_zero_point_must_win(self):
        ctx = competition_context_for("WC2026-D31")
        self.assertTrue(ctx)
        self.assertGreaterEqual(
            max(float(ctx["home_must_win_pressure"]), float(ctx["away_must_win_pressure"])),
            0.75,
        )
        self.assertLessEqual(float(ctx["mutual_draw_acceptance"]), 0.20)


if __name__ == "__main__":
    unittest.main()
