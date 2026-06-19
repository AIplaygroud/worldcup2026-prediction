import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import predict_v2  # noqa: E402
from predict_v2 import MatchContext, base_lambdas, load_data, clip  # noqa: E402


class TestWcDefBlend(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_data()

    def test_blend_changes_deff_when_adj_present(self):
        team = next(iter(self.data["wc_adj"]), None)
        if not team:
            self.skipTest("no wc_adj data")
        ctx = MatchContext(home=team, away="Brazil")
        if team not in self.data["form"] or "Brazil" not in self.data["form"]:
            self.skipTest("teams missing from form")
        _, _, info = base_lambdas(ctx, self.data)
        if info.get("wc_def_blend_applied_home"):
            self.assertNotEqual(info["raw_deff_h"], info["deff_h"])

    def test_no_wc_team_unchanged_logic(self):
        wc_teams = set(self.data.get("wc", {})) | set(self.data.get("wc_adj", {}))
        team = next((t for t in self.data["form"] if t not in wc_teams), None)
        if not team:
            self.skipTest("all form teams have WC data")
        ctx = MatchContext(home=team, away="Jordan")
        if "Jordan" not in self.data["form"]:
            self.skipTest("Jordan not in form")
        _, _, info = base_lambdas(ctx, self.data)
        self.assertFalse(info.get("wc_def_blend_applied_home", False))

    def test_clip_within_twenty_percent(self):
        raw = 1.0
        blended = clip(raw * 0.5, raw * 0.80, raw * 1.20)
        self.assertGreaterEqual(blended, raw * 0.80)
        self.assertLessEqual(blended, raw * 1.20)

    def test_lam_uses_opponent_blended_defense(self):
        h, a = "USA", "Australia"
        if h not in self.data["form"] or a not in self.data["form"]:
            self.skipTest("teams missing")
        ctx = MatchContext(home=h, away=a)
        lam_h, lam_a, info = base_lambdas(ctx, self.data)
        att_h = info["att_h"]
        att_a = info["att_a"]
        self.assertAlmostEqual(lam_h, predict_v2.ANCHOR * att_h * info["deff_a"], places=4)
        self.assertAlmostEqual(lam_a, predict_v2.ANCHOR * att_a * info["deff_h"], places=4)


if __name__ == "__main__":
    unittest.main()
