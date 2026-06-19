import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from build_betting_strategy import build_strategy  # noqa: E402

ODDS = ROOT / "database" / "jc-odds" / "processed"
MATCH_GLOB = str(ROOT / "database" / "eventflow" / "processed" / "dual_engine_output_*_balanced_v32.json")


class TestV35BettingStrategyOutputSemantics(unittest.TestCase):
    def test_fusion_score_not_reported_as_probability(self):
        text = build_strategy(
            MATCH_GLOB,
            ODDS / "match_odds_summary.csv",
            ODDS / "match_odds_ttg.csv",
            ODDS / "match_odds_hafu.csv",
            ODDS / "match_odds_crs.csv",
            mode="balanced",
        ).to_markdown()
        self.assertNotIn("fusion概率", text)
        self.assertNotIn("融合概率", text)
        self.assertTrue("融合支持" in text or "融合排序" in text)


if __name__ == "__main__":
    unittest.main()
