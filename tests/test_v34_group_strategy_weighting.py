import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from eventflow_common import read_csv, snum, fnum  # noqa: E402
from eventflow_v32_gates import parse_gates_json  # noqa: E402
from predict_eventflow import generate_candidates, pick_activated  # noqa: E402

WEIGHTS_PATH = ROOT / "database" / "eventflow" / "processed" / "eventflow_scenario_weights.csv"
MATCH_ID = "WC2026-D32"


def scenario_weight(match_id: str, scenario_id: str) -> dict:
    for row in read_csv(WEIGHTS_PATH):
        if snum(row, "match_id") == match_id and snum(row, "scenario_id") == scenario_id:
            gates = parse_gates_json(snum(row, "weight_gates"))
            return {
                "raw_tactical_delta": fnum(row, "raw_tactical_delta"),
                "triggered_by": snum(row, "triggered_by"),
                "weight_gates": gates,
            }
    return {}


def top_scores(match_id: str, lam_home: float = 1.45, lam_away: float = 1.05) -> list[str]:
    rows = [
        r for r in read_csv(WEIGHTS_PATH)
        if snum(r, "match_id") == match_id and snum(r, "home") == "USA" and snum(r, "away") == "Australia"
    ]
    activated = pick_activated(rows)
    cand = generate_candidates(lam_home, lam_away, rows, activated, "balanced", degraded=False)
    return [c["score"] for c in cand[:5]]


class TestGroupStrategyWeighting(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not WEIGHTS_PATH.exists():
            raise unittest.SkipTest("Run build_eventflow_scenario_weights.py first")

    def test_s11_s17_weights(self):
        s11 = scenario_weight(MATCH_ID, "S11_group_state_draw_control")
        s17 = scenario_weight(MATCH_ID, "S17_group_top_spot_controlled_win")
        s07 = scenario_weight(MATCH_ID, "S07_late_chase_open_game")

        self.assertGreaterEqual(s11["raw_tactical_delta"], 0.10)
        self.assertGreaterEqual(s17["raw_tactical_delta"], 0.08)
        self.assertIn("structured_competition_context", s11["triggered_by"])
        self.assertIn("structured_competition_context", s17["triggered_by"])
        self.assertIn("competition_late_chase_cap", s07["weight_gates"])

    def test_low_risk_scores_in_top5(self):
        top5 = top_scores(MATCH_ID)
        self.assertTrue("1-1" in top5 or "1-0" in top5)
        if "1-1" in top5:
            self.assertLessEqual(top5.index("1-1"), 4)


if __name__ == "__main__":
    unittest.main()
