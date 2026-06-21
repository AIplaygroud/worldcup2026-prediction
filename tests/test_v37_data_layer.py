"""V3.7 data layer and feature layer tests."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from eventflow_common import read_csv  # noqa: E402
from v37_common import (  # noqa: E402
    FEATURE_TABLES,
    NORMALIZED_TABLES,
    V37_THRESHOLDS,
    compute_data_quality_score,
    identify_favorite,
    load_team_model_index,
    load_tier_index,
)
from v37_features import (  # noqa: E402
    compute_attack_conversion,
    compute_group_pressure,
    compute_low_block_keeper_guard,
)
from validate_v37_feature_timing import validate_match  # noqa: E402


class TestV37GroupPressure(unittest.TestCase):
    def test_must_win_pressure_type(self):
        row = {
            "win_necessity": 0.72,
            "draw_utility": 0.1,
            "can_qualify_if_draw": "false",
            "elimination_risk_if_loss": "true",
            "rank_before": 3,
            "points_before": 0,
            "gd_before": -1,
        }
        out = compute_group_pressure("WC2026-E34", "Ecuador", "Curacao", row, "must_win")
        self.assertEqual(out["pressure_type"], "must_win")
        self.assertGreaterEqual(out["group_pressure_index"], 0.5)


class TestV37AttackConversion(unittest.TestCase):
    def test_must_win_no_convert_flag(self):
        tactical = {t: {} for t in ("Ecuador", "Curacao")}
        recent = {"xg_for_avg": 0.9, "shots_avg": 10, "sot_avg": 3, "big_chances_avg": 1,
                  "goals_for_avg": 0.5, "matches_played": 1}
        out = compute_attack_conversion(
            "WC2026-E34", "Ecuador", "Curacao", recent, tactical, [], gpi=0.70
        )
        self.assertIn(out["must_win_no_convert_flag"], ("true", "false"))


class TestV37LowBlockKeeper(unittest.TestCase):
    def test_deep_handicap_contra(self):
        tiers = load_tier_index()
        models = load_team_model_index()
        tactical = {t: {} for t in ("Ecuador", "Curacao")}
        odds = [{
            "match_id": "WC2026-E34", "market": "hhad", "selection": "home",
            "handicap": "-2", "sp": "1.85", "pool_status": "open",
        }]
        out = compute_low_block_keeper_guard(
            "WC2026-E34", "Ecuador", "Curacao",
            acg_home=0.48, acg_away=0.45,
            draw_util_home=0.1, draw_util_away=0.3,
            tactical=tactical, tiers=tiers, models=models, odds_rows=odds,
        )
        self.assertEqual(out["deep_handicap_flag"], "true")
        fav = identify_favorite("Ecuador", "Curacao", tiers, models)
        self.assertEqual(fav, "Ecuador")


class TestV37DataTiming(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tables_exist = NORMALIZED_TABLES["matches"].exists()

    def test_prematch_asof_no_score_leak_for_future_match(self):
        if not self._tables_exist:
            self.skipTest("normalized tables not built")
        from datetime import datetime, timezone
        asof = datetime(2026, 6, 20, 12, 0, tzinfo=timezone.utc)
        violations = validate_match("WC2026-F36", asof)
        errors = [v for v in violations if v["severity"] == "error" and v["check"] == "prematch_score_leak"]
        self.assertEqual(errors, [])


class TestV37RegressionCases(unittest.TestCase):
    """E/F R2 cases — regression labels only, not training targets."""

    REGRESSION_MATCHES = ("WC2026-E34", "WC2026-F35", "WC2026-F36", "WC2026-E33")

    @classmethod
    def setUpClass(cls):
        if not FEATURE_TABLES["realization"].exists():
            cls.rows = []
            return
        cls.rows = {r["match_id"]: r for r in read_csv(FEATURE_TABLES["realization"])}

    def test_regression_matches_have_features(self):
        if not self.rows:
            self.skipTest("run build_v37_features first")
        for mid in self.REGRESSION_MATCHES:
            self.assertIn(mid, self.rows, msg=f"missing {mid}")
            row = self.rows[mid]
            self.assertTrue(row.get("group_pressure_home"))
            self.assertTrue(row.get("attack_conversion_home"))

    def test_e34_cold_guard_or_must_win_flag(self):
        if "WC2026-E34" not in self.rows:
            self.skipTest("E34 not built")
        row = self.rows["WC2026-E34"]
        flags = row.get("active_flags", "")
        self.assertTrue(
            "must_win_no_convert" in flags or "cold_guard" in flags or "deep_handicap" in flags,
            msg=f"expected risk flags, got: {flags}",
        )


class TestV37DataQuality(unittest.TestCase):
    def test_quality_score_range(self):
        score = compute_data_quality_score({
            "has_standing": True,
            "has_recent_xg_or_proxy": True,
            "has_lineup": False,
            "has_match_stats": True,
            "has_odds": True,
            "has_tactical_profile": True,
            "has_source_fusion": False,
        })
        self.assertGreaterEqual(score, 0.55)
        self.assertLessEqual(score, 1.0)


if __name__ == "__main__":
    unittest.main()
