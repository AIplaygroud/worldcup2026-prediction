"""P4.1 ranking mutation semantics tests."""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from v37_historical_common import payload_from_case  # noqa: E402
from v37_large_score_tail import apply_tail_to_payload  # noqa: E402
from v37_tail_diagnostics_common import is_extreme_tail, is_top3_forbidden  # noqa: E402


class TestRankingSemantics(unittest.TestCase):
    def _case(self, **kw) -> dict[str, str]:
        base = {
            "match_id": "SEM-1", "home_team": "Germany", "away_team": "Curacao",
            "lambda_home": "1.5", "lambda_away": "0.5", "data_quality_score": "0.8",
            "egci_v2": "0.7", "egci_v2_quality": "proxy", "acg_favorite": "0.6",
            "acg_v2_quality": "proxy", "underdog_fragility": "0.5", "chase_pressure": "0.4",
            "cold_guard_active": "false", "must_win_no_convert": "false",
            "deep_handicap_contra": "false", "eventflow_degraded": "false",
            "confirmed_event_timeline": "false",
        }
        base.update(kw)
        return base

    def test_audit_only_unchanged(self):
        payload = payload_from_case(self._case())
        before = copy.deepcopy(payload["final_fusion"]["score_ranking"])
        out = apply_tail_to_payload(payload, mode="audit_only")
        after = out["payload"]["final_fusion"]["score_ranking"]
        self.assertEqual(before, after)
        tail = out["audit"]["v37_large_score_tail"]
        self.assertFalse(tail["ranking_mutation_applied"])

    def test_none_no_safety_demotion_unchanged(self):
        payload = payload_from_case(self._case(lambda_home="1.1", lambda_away="1.0"))
        before = [r["score"] for r in payload["final_fusion"]["score_ranking"][:5]]
        out = apply_tail_to_payload(payload, mode="rerank_only")
        tail = out["audit"]["v37_large_score_tail"]
        if tail["tail_boost_level"] == "none" and not tail["safety_demotion_applied"]:
            after = [r["score"] for r in out["payload"]["final_fusion"]["score_ranking"][:5]]
            self.assertEqual(before, after)
            self.assertEqual(tail["ranking_mutation_reason"], "none")

    def test_safety_demotion_has_reason(self):
        payload = payload_from_case(self._case(lambda_home="4.5", lambda_away="0.3"))
        out = apply_tail_to_payload(payload, mode="rerank_only")
        tail = out["audit"]["v37_large_score_tail"]
        if tail["safety_demotion_applied"]:
            self.assertIn(tail["ranking_mutation_reason"], (
                "five_goal_top3_safety_demotion",
                "tail_boost_and_five_goal_top3_safety_demotion",
            ))

    def test_extreme_tail_not_in_top3(self):
        payload = payload_from_case(self._case(lambda_home="4.5", lambda_away="0.3"))
        out = apply_tail_to_payload(payload, mode="rerank_only")
        top3 = [r["score"] for r in out["payload"]["final_fusion"]["score_ranking"][:3]]
        self.assertFalse(any(is_top3_forbidden(s) for s in top3))

    def test_extreme_tail_classification(self):
        self.assertEqual(is_extreme_tail("7-1"), True)
        self.assertEqual(is_extreme_tail("4-2"), False)


if __name__ == "__main__":
    unittest.main()
