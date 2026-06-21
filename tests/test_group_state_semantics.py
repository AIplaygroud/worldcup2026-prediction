"""Semantic tests for group state / advancement path (P0 fixes)."""
from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from build_match_incentive_features import build_match_row, standings_for_cutoff  # noqa: E402
from group_state_common import (  # noqa: E402
    classify_path_state,
    init_stats,
    kickoff_utc_from_mapping_row,
    local_kickoff_to_utc,
    pre_kickoff_cutoff,
    read_csv,
    remaining_group_matches,
)
from v37_features import compute_group_pressure, pressure_type_from_gpi  # noqa: E402

MAPPING = ROOT / "database" / "competition" / "wc2026_match_id_mapping.csv"


class TestR1NoMustWin(unittest.TestCase):
    def test_all_r1_opening_round(self):
        if not MAPPING.exists():
            self.skipTest("mapping missing")
        r1 = [r for r in read_csv(MAPPING) if r.get("round") == "1"]
        self.assertGreaterEqual(len(r1), 24)
        for m in r1:
            kickoff = kickoff_utc_from_mapping_row(m)
            self.assertIsNotNone(kickoff, m["internal_match_id"])
            cutoff = pre_kickoff_cutoff(kickoff)
            standings = standings_for_cutoff(cutoff)
            rem = remaining_group_matches(cutoff)
            for team in (m["home_team"], m["away_team"]):
                st = next(s for s in standings if s["team"] == team)
                detail = classify_path_state(
                    team, m["group"], st["rank"], standings, rem.get(m["group"], []),
                    round_num=1, cutoff=cutoff,
                )
                self.assertEqual(detail["path_state"], "opening_round", f"{m['internal_match_id']} {team}")
                self.assertNotIn("must_win", detail["path_state"])
                ptype = pressure_type_from_gpi(0.5, 0.3, detail["path_state"], round_num=1)
                self.assertNotEqual(ptype, "must_win")


class TestKickoffUtcConversion(unittest.TestCase):
    def test_us_east_not_treated_as_utc(self):
        ko = local_kickoff_to_utc("2026-06-11", "13:00", "Mexico City")
        self.assertEqual(ko.hour, 19)  # CDT UTC-6 -> 19:00 UTC for 13:00 local

    def test_standings_asof_before_kickoff(self):
        if not MAPPING.exists():
            self.skipTest("mapping missing")
        m = next(r for r in read_csv(MAPPING) if r["internal_match_id"] == "WC2026-F35")
        kickoff = kickoff_utc_from_mapping_row(m)
        cutoff = pre_kickoff_cutoff(kickoff)
        row = build_match_row("test", m, [])
        self.assertIsNotNone(row)
        assert row is not None
        as_of = datetime.fromisoformat(row["as_of_utc"].replace("Z", "+00:00"))
        self.assertLess(as_of, kickoff)


class TestPerMatchSnapshotNoLeak(unittest.TestCase):
    def test_a25_pre_match_points_not_post_global(self):
        if not MAPPING.exists():
            self.skipTest("mapping missing")
        from group_state_common import parse_cutoff

        m = next(r for r in read_csv(MAPPING) if r["internal_match_id"] == "WC2026-A25")
        kickoff = kickoff_utc_from_mapping_row(m)
        self.assertIsNotNone(kickoff)
        cutoff = pre_kickoff_cutoff(kickoff)
        standings = standings_for_cutoff(cutoff)
        home = m["home_team"]
        h = next(s for s in standings if s["team"] == home)
        # Pre-A25: Czechia 0pts after R1 loss; must not include later R2 (A28) results.
        self.assertEqual(h["points"], 0)
        self.assertEqual(h["played"], 1)

        global_standings = standings_for_cutoff(parse_cutoff("2026-06-20T12:00:00Z"))
        h_global = next(s for s in global_standings if s["team"] == home)
        self.assertGreater(h_global["points"], h["points"])


class TestClinchEnumeration(unittest.TestCase):
    def _detail(self, team: str, group: str, standings: list[dict], rem_fixtures: list[dict]) -> dict:
        st = next(s for s in standings if s["team"] == team)
        return classify_path_state(
            team, group, st["rank"], standings, rem_fixtures, round_num=2,
        )

    def test_four_points_not_auto_clinched(self):
        standings = [
            {"group": "X", "team": "A", "rank": 2, "played": 2, "points": 4, "gd": 0, "gf": 3, "ga": 3,
             "wins": 1, "draws": 1, "losses": 0},
            {"group": "X", "team": "B", "rank": 1, "played": 2, "points": 6, "gd": 3, "gf": 5, "ga": 2,
             "wins": 2, "draws": 0, "losses": 0},
            {"group": "X", "team": "C", "rank": 3, "played": 1, "points": 3, "gd": 1, "gf": 2, "ga": 1,
             "wins": 1, "draws": 0, "losses": 0},
            {"group": "X", "team": "D", "rank": 4, "played": 2, "points": 0, "gd": -4, "gf": 0, "ga": 4,
             "wins": 0, "draws": 0, "losses": 2},
        ]
        rem = [
            {"group": "X", "home_team": "A", "away_team": "C"},
            {"group": "X", "home_team": "B", "away_team": "D"},
        ]
        d = self._detail("A", "X", standings, rem)
        self.assertFalse(d["clinched_top2"])
        self.assertIn(d["state_reason_codes"], ("FOUR_POINTS_NOT_CLINCHED", "TOP_SLOT_CHASE"))

    def test_six_points_with_weak_rivals_clinches(self):
        standings = [
            {"group": "Y", "team": "A", "rank": 1, "played": 2, "points": 6, "gd": 4, "gf": 5, "ga": 1,
             "wins": 2, "draws": 0, "losses": 0},
            {"group": "Y", "team": "B", "rank": 2, "played": 2, "points": 1, "gd": 0, "gf": 1, "ga": 1,
             "wins": 0, "draws": 1, "losses": 1},
            {"group": "Y", "team": "C", "rank": 3, "played": 2, "points": 1, "gd": -1, "gf": 1, "ga": 2,
             "wins": 0, "draws": 1, "losses": 1},
            {"group": "Y", "team": "D", "rank": 4, "played": 2, "points": 1, "gd": -3, "gf": 0, "ga": 3,
             "wins": 0, "draws": 1, "losses": 1},
        ]
        rem = [{"group": "Y", "home_team": "A", "away_team": "B"}]
        d = self._detail("A", "Y", standings, rem)
        self.assertTrue(d["clinched_top2"])
        self.assertGreaterEqual(d["p_top2"], 0.99)


class TestPressureTypeGate(unittest.TestCase):
    def test_opening_round_never_must_win_pressure(self):
        row = {
            "win_necessity": 0.72,
            "draw_utility": 0.1,
            "can_qualify_if_draw": "false",
            "elimination_risk_if_loss": "true",
            "rank_before": 3,
            "points_before": 0,
            "gd_before": 0,
            "round_before": 1,
            "path_state": "opening_round",
        }
        out = compute_group_pressure("WC2026-A1", "Mexico", "South Africa", row, "opening_round")
        self.assertNotEqual(out["pressure_type"], "must_win")


if __name__ == "__main__":
    unittest.main()
