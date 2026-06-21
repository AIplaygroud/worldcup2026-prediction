"""V3.7 phase-1 integration tests."""
from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from eventflow_common import read_json  # noqa: E402
from merge_dual_engine_predictions import build_v37_cold_reserve  # noqa: E402
from scenario_realization_common import load_v37_features, V37_NEUTRAL  # noqa: E402
from v37_common import bnum  # noqa: E402
from validate_v37_fusion_cold_reserve import validate_cold_reserve  # noqa: E402


class TestBnum(unittest.TestCase):
    def test_string_bools(self):
        self.assertTrue(bnum({"x": "true"}, "x"))
        self.assertFalse(bnum({"x": "false"}, "x"))
        self.assertTrue(bnum({"can_qualify_if_draw": "true"}, "can_qualify_if_draw"))


class TestLoadV37Features(unittest.TestCase):
    def test_e34_loaded(self):
        f = load_v37_features("WC2026-E34")
        if not Path(ROOT / "database/v37/features/v37_realization_features.csv").exists():
            self.skipTest("features not built")
        self.assertTrue(f.get("loaded"))
        self.assertTrue(f.get("must_win_no_convert_home"))
        self.assertTrue(f.get("cold_guard_active"))
        self.assertTrue(f.get("deep_handicap_contra_flag"))

    def test_missing_fail_closed(self):
        f = load_v37_features("WC2026-INVALID")
        self.assertFalse(f.get("loaded"))
        self.assertEqual(f.get("attack_conversion_home"), V37_NEUTRAL["attack_conversion_home"])


class TestColdReserve(unittest.TestCase):
    def test_cold_reserve_includes_draws(self):
        prob = {"2-1": 0.15, "2-0": 0.12, "1-0": 0.11, "0-0": 0.09, "1-1": 0.08, "3-1": 0.07}
        v37 = {"cold_guard_active": True}
        reserves = build_v37_cold_reserve(prob, ["2-1", "2-0", "1-0"], v37, max_reserve=2)
        scores = [r["score"] for r in reserves]
        self.assertIn("0-0", scores)
        self.assertIn("1-1", scores)


class TestRegressionFeatures(unittest.TestCase):
    REGRESSION = {
        "WC2026-E34": {"must_win_no_convert_home", "cold_guard_active", "deep_handicap_contra"},
        "WC2026-F35": set(),
        "WC2026-F36": set(),
    }

    def test_regression_flags(self):
        csv_path = ROOT / "database/v37/features/v37_realization_features.csv"
        if not csv_path.exists():
            self.skipTest("features not built")
        for mid, _ in self.REGRESSION.items():
            f = load_v37_features(mid)
            self.assertTrue(f.get("loaded"), mid)
        e34 = load_v37_features("WC2026-E34")
        self.assertTrue(e34["must_win_no_convert_home"])
        self.assertTrue(e34["cold_guard_active"])
        self.assertTrue(e34["deep_handicap_contra_flag"])
        f35 = load_v37_features("WC2026-F35")
        self.assertEqual(f35.get("favorite"), "Netherlands")
        f36 = load_v37_features("WC2026-F36")
        self.assertEqual(f36.get("favorite"), "Japan")
        self.assertFalse(f36.get("cascade_tail_active") and False)


class TestHtftBinding(unittest.TestCase):
    REGRESSION_FILES = [
        ("WC2026-E34", "Ecuador", "Curacao", "dual_engine_output_E34_v37_test.json"),
        ("WC2026-F35", "Netherlands", "Sweden", "dual_engine_output_F35_v37_test.json"),
        ("WC2026-F36", "Tunisia", "Japan", "dual_engine_output_F36_v37_test.json"),
    ]
    FORBIDDEN = ("Colombia", "DR Congo")

    def test_no_foreign_teams_in_regression_outputs(self):
        from eventflow_htft import validate_htft_output

        for _mid, home, away, fname in self.REGRESSION_FILES:
            path = ROOT / "database/eventflow/processed" / fname
            if not path.exists():
                self.skipTest(f"{fname} missing")
            payload = read_json(path, {})
            text = json.dumps(payload, ensure_ascii=False)
            for team in self.FORBIDDEN:
                self.assertNotIn(team, text, msg=f"{fname} contains {team}")
            errs = validate_htft_output(payload, list(self.FORBIDDEN))
            self.assertEqual(errs, [], msg=f"{fname}: {errs}")
            htft = payload.get("final_fusion", {}).get("half_full_time_top3", [])
            for item in htft:
                basis = item.get("perspective_basis", "")
                self.assertTrue(home in basis or away in basis, msg=basis)


class TestMergeUnchangedWithoutV37(unittest.TestCase):
    def test_cold_reserve_empty_when_inactive(self):
        reserves = build_v37_cold_reserve({"1-0": 0.2}, ["1-0"], {"cold_guard_active": False})
        self.assertEqual(reserves, [])


if __name__ == "__main__":
    unittest.main()
