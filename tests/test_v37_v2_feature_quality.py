"""EGCI v2 / ACG v2 quality gating tests."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from eventflow_common import read_csv  # noqa: E402
from v37_common import FEATURE_TABLES  # noqa: E402
from v37_large_score_tail import EGCI_V2_OK, evaluate_tail_level, load_p2_context  # noqa: E402


class TestEgciQuality(unittest.TestCase):
    def test_proxy_blocks_boost(self):
        ctx = {
            "data_quality_score": 0.7,
            "cold_guard_active": False,
            "deep_handicap_contra_flag": False,
            "must_win_no_convert_favorite": False,
            "eventflow_degraded": False,
            "egci_v2_quality": "proxy",
            "acg_v2_quality": "partial",
            "favorite_acg": 0.7,
            "egci": 0.7,
            "underdog_fragility": 0.6,
            "underdog_chase_pressure": 0.6,
            "confirmed_event_timeline": False,
        }
        th = {
            "min_data_quality": 0.65, "acg_mild": 0.58, "egci_mild": 0.58,
            "acg_medium": 0.65, "egci_medium": 0.65, "acg_strong": 0.72,
            "egci_strong": 0.72, "fragility_mild": 0.50, "fragility_medium": 0.62,
            "fragility_strong": 0.70, "chase_medium": 0.55, "chase_strong": 0.65,
        }
        ev = evaluate_tail_level(ctx, th)
        self.assertEqual(ev["tail_boost_level"], "none")

    def test_real_egci_has_goal_minute(self):
        path = FEATURE_TABLES["egci_v2"]
        if not path.exists():
            self.skipTest("egci v2 not built")
        real = [r for r in read_csv(path) if r.get("egci_v2_quality") == "real"]
        for r in real:
            self.assertTrue(r.get("first_goal_minute"))


class TestAcgQuality(unittest.TestCase):
    def test_acg_v2_fields(self):
        path = FEATURE_TABLES["acg_v2"]
        if not path.exists():
            self.skipTest("acg v2 not built")
        row = read_csv(path)[0]
        self.assertIn("conversion_proxy_ratio", row)
        self.assertIn("must_win_no_convert_v2", row)


if __name__ == "__main__":
    unittest.main()
