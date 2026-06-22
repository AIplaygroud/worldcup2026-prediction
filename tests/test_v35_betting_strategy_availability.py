import sys
import unittest
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from build_betting_strategy import build_strategy  # noqa: E402

ODDS = ROOT / "database" / "jc-odds" / "processed"
MATCH_GLOB = str(ROOT / "database" / "eventflow" / "processed" / "dual_engine_output_*_balanced_v36.json")


def _build():
    return build_strategy(
        MATCH_GLOB,
        ODDS / "match_odds_summary.csv",
        ODDS / "match_odds_ttg.csv",
        ODDS / "match_odds_hafu.csv",
        ODDS / "match_odds_crs.csv",
        mode="auto",
        emit_recommendations=True,
    )


class TestV35BettingStrategyAvailability(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with (ODDS / "match_odds_summary.csv").open(encoding="utf-8-sig", newline="") as handle:
            teams = {(row["homeTeam"], row["awayTeam"]) for row in csv.DictReader(handle)}
        if ("巴西", "海地") not in teams:
            raise unittest.SkipTest("historical Brazil-Haiti odds snapshot not active")

    def test_brazil_had_unavailable_filtered(self):
        recs = _build()
        text = recs.to_markdown()
        self.assertNotIn("巴西胜", text)
        self.assertIn("HAD 市场未开售", text)
        brz = [c for c in recs.candidate_pool if c.match_id == "WC2026-C29"]
        self.assertTrue(any(c.market in ("TTG", "HAFU", "CRS", "HHAD") for c in brz))

    def test_hhad_single_false_not_in_single_banker(self):
        recs = _build()
        single_section = recs.sections["single_banker"]
        self.assertNotIn("巴西(-2)", single_section)

    def test_no_fake_over_under_market(self):
        text = _build().to_markdown()
        self.assertNotIn("大2.5", text)
        self.assertNotIn("小2.5", text)
        self.assertTrue("总进球3" in text or "总进球3/4" in text)


if __name__ == "__main__":
    unittest.main()
