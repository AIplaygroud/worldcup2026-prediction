"""V3.7 betting integration: odds lookup + guard score modifiers."""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from build_betting_strategy import (  # noqa: E402
    Candidate,
    _resolve_odds_row,
    _valid_hafu_selection,
    apply_v37_betting_guards,
    build_strategy,
    load_odds,
)
from eventflow_common import read_csv  # noqa: E402
from scenario_realization_common import load_v37_features  # noqa: E402

ODDS_DB = ROOT / "database" / "jc-odds" / "processed"


class TestOddsLookup(unittest.TestCase):
    def test_resolve_by_teams_not_friday_key(self):
        summary = ODDS_DB / "match_odds_summary.csv"
        if not summary.exists():
            self.skipTest("jc odds missing")
        by_key, _ = load_odds(
            summary,
            ODDS_DB / "match_odds_ttg.csv",
            ODDS_DB / "match_odds_hafu.csv",
            ODDS_DB / "match_odds_crs.csv",
        )
        rows = read_csv(summary)
        payload = {"match": "Netherlands vs Sweden", "fifa_match_id": "33", "match_id": "WC2026-F35"}
        row = _resolve_odds_row(payload, by_key, rows)
        self.assertIsNotNone(row)
        self.assertEqual(row.get("homeTeam"), "荷兰")

    def test_e34_ecuador_curacao(self):
        summary = ODDS_DB / "match_odds_summary.csv"
        if not summary.exists():
            self.skipTest("jc odds missing")
        by_key, _ = load_odds(
            summary,
            ODDS_DB / "match_odds_ttg.csv",
            ODDS_DB / "match_odds_hafu.csv",
            ODDS_DB / "match_odds_crs.csv",
        )
        rows = read_csv(summary)
        payload = {"match": "Ecuador vs Curacao", "fifa_match_id": "34", "match_id": "WC2026-E34"}
        row = _resolve_odds_row(payload, by_key, rows)
        self.assertIsNotNone(row)
        self.assertIn("厄瓜多尔", row.get("homeTeam", ""))


class TestHafuParlayValidation(unittest.TestCase):
    def test_valid_hafu_pattern(self):
        self.assertTrue(_valid_hafu_selection("半全场主/主"))
        self.assertTrue(_valid_hafu_selection("半全场平/主"))
        self.assertFalse(_valid_hafu_selection("半全场平/胜"))
        self.assertFalse(_valid_hafu_selection("荷兰半全场主/主"))
        self.assertFalse(_valid_hafu_selection("美国胜"))


class TestV37BettingGuards(unittest.TestCase):
    def _candidate(self, market: str, selection: str) -> Candidate:
        return Candidate(
            match_id="WC2026-E34",
            match="Ecuador vs Curacao",
            market=market,
            selection=selection,
            sp=2.0,
            single_allowed=True,
            parlay_allowed=True,
            v2_model_probability=0.3,
            eventflow_alignment=0.5,
            fusion_alignment=0.5,
            value_proxy=0.6,
            strategy_score_conservative=0.6,
            strategy_score_balanced=0.6,
            strategy_score_aggressive=0.6,
        )

    def test_e34_deep_handicap_contra(self):
        feat_path = ROOT / "database/v37/features/v37_realization_features.csv"
        if not feat_path.exists():
            self.skipTest("features not built")
        feat = load_v37_features("WC2026-E34")
        if not feat.get("deep_handicap_contra_flag"):
            self.skipTest("E34 deep_handicap not active")
        under = self._candidate("HHAD", "厄瓜多尔(-2)让负")
        over = self._candidate("HHAD", "厄瓜多尔(-2)让胜")
        bal_u = under.strategy_score_balanced
        bal_o = over.strategy_score_balanced
        audit = apply_v37_betting_guards(
            [under, over],
            {"match_id": "WC2026-E34"},
            {"homeTeam": "厄瓜多尔", "awayTeam": "库拉索"},
        )
        self.assertTrue(audit.get("applied"))
        self.assertGreater(under.strategy_score_balanced, bal_u)
        self.assertLess(over.strategy_score_balanced, bal_o)
        self.assertIn("boost_hhad_underdog_plus", audit.get("risk_flags", []))

    def test_f35_candidate_pool_nonempty(self):
        json_path = ROOT / "database/eventflow/processed/dual_engine_output_F35_v37_test.json"
        if not json_path.exists():
            self.skipTest("F35 merge output missing")
        res = build_strategy(
            str(json_path),
            ODDS_DB / "match_odds_summary.csv",
            ODDS_DB / "match_odds_ttg.csv",
            ODDS_DB / "match_odds_hafu.csv",
            ODDS_DB / "match_odds_crs.csv",
            use_v37=True,
            emit_recommendations=False,
        )
        self.assertGreater(len(res.candidate_pool), 0, "F35 market guard items should not be empty")
        self.assertEqual(res.recommended_combos, [])


if __name__ == "__main__":
    unittest.main()
