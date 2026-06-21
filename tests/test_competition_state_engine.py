"""P1 semantic tests for canonical state and runtime route consumption."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from build_match_incentive_features import build_match_row  # noqa: E402
from competition_state_engine import evaluate_match_state  # noqa: E402
from eventflow_v32_gates import competition_context_for  # noqa: E402
from group_state_common import kickoff_utc_from_mapping_row, read_csv  # noqa: E402
from run_phase06B_bracket_route_analysis import build_runtime_incentive  # noqa: E402
from v37_common import runtime_incentive_for  # noqa: E402

MAPPING = ROOT / "database" / "competition" / "wc2026_match_id_mapping.csv"


class TestCanonicalStateEngine(unittest.TestCase):
    def test_phase06_reason_matches_engine(self):
        match = next(r for r in read_csv(MAPPING) if r["internal_match_id"] == "WC2026-A25")
        kickoff = kickoff_utc_from_mapping_row(match)
        self.assertIsNotNone(kickoff)
        state = evaluate_match_state(
            match["home_team"], match["away_team"], match["group"], kickoff,
            round_num=int(match["round"]),
        )
        row = build_match_row("test", match, [])
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["home_state_reason_code"], state["home"]["state_reason_code"])
        self.assertEqual(row["away_state_reason_code"], state["away"]["state_reason_code"])


class TestRouteFieldSemantics(unittest.TestCase):
    def test_home_away_utilities_are_symmetric_and_directional(self):
        incentive = [{
            "match_id": "M1", "home": "H", "away": "A",
            "home_path_state": "top_slot_chase", "away_path_state": "must_win",
            "home_state_reason_code": "H_REASON", "away_state_reason_code": "A_REASON",
        }]
        bracket = [
            {
                "team": "H", "route_avoidance_applicable": "true",
                "best_route_position": "second", "route_avoidance_strength": "medium",
                "route_score_first": 0.70, "route_score_second": 0.40,
                "qualification_secure_prob": 0.9, "route_preference_delta": 0.3,
            },
            {
                "team": "A", "route_avoidance_applicable": "false",
                "best_route_position": "first", "route_avoidance_strength": "none",
                "route_score_first": 0.30, "route_score_second": 0.65,
                "qualification_secure_prob": 0.5, "route_preference_delta": 0.0,
            },
        ]
        row = build_runtime_incentive("snap", incentive, bracket)[0]
        self.assertAlmostEqual(row["home_first_place_utility"], 0.30)
        self.assertAlmostEqual(row["away_first_place_utility"], 0.70)
        self.assertAlmostEqual(row["home_second_place_utility"], 0.60)
        self.assertAlmostEqual(row["away_second_place_utility"], 0.35)
        self.assertEqual(row["home_state_reason_code"], "H_REASON")
        self.assertEqual(row["away_state_reason_code"], "A_REASON")
        self.assertNotEqual(row["home_late_push_modifier"], row["away_late_push_modifier"])
        self.assertEqual(row["home_route_utility_first"], row["home_first_place_utility"])
        self.assertEqual(row["away_route_utility_second"], row["away_second_place_utility"])


class TestRuntimeReadOnlyConsumption(unittest.TestCase):
    def test_eventflow_and_v37_load_runtime_row(self):
        rows = read_csv(ROOT / "database" / "competition" / "runtime" / "match_incentive_runtime_R2.csv")
        if not rows:
            self.skipTest("runtime incentive table missing")
        mid = rows[0]["match_id"]
        self.assertEqual(runtime_incentive_for(mid)["match_id"], mid)
        ctx = competition_context_for(mid)
        self.assertTrue(ctx)
        self.assertEqual(ctx["runtime_incentive_used"], "true")
        self.assertLess(ctx["as_of_utc"], ctx["kickoff_utc"])


if __name__ == "__main__":
    unittest.main()
