import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from build_betting_strategy import build_strategy  # noqa: E402

ODDS = ROOT / "database" / "jc-odds" / "processed"
MATCH_GLOB = str(ROOT / "database" / "eventflow" / "processed" / "dual_engine_output_*_balanced_v36.json")


class TestV35BettingStrategyFusionSelection(unittest.TestCase):
    def test_turkey_eventflow_lifts_ttg3(self):
        recs = build_strategy(
            MATCH_GLOB,
            ODDS / "match_odds_summary.csv",
            ODDS / "match_odds_ttg.csv",
            ODDS / "match_odds_hafu.csv",
            ODDS / "match_odds_crs.csv",
            mode="balanced",
        )
        tur_candidates = [c for c in recs.candidate_pool if c.match_id == "WC2026-D31"]
        self.assertTrue(
            any(c.market == "TTG" and c.selection in ("总进球3", "总进球3/4") for c in tur_candidates),
            f"expected TTG3 in pool, got {[c.selection for c in tur_candidates if c.market == 'TTG']}",
        )
        self.assertTrue(
            any("融合首选2-1" in c.reason or "EventFlow开放" in c.reason for c in tur_candidates),
            f"reasons: {[c.reason for c in tur_candidates[:5]]}",
        )


if __name__ == "__main__":
    unittest.main()
