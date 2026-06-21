"""Safety demotion rule vs applied semantics."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from v37_historical_common import payload_from_case  # noqa: E402
from v37_large_score_tail import apply_tail_to_payload  # noqa: E402


class TestSafetyDemotionSemantics(unittest.TestCase):
    def _case(self, **kw) -> dict[str, str]:
        base = {
            "match_id": "SD-1", "home_team": "Germany", "away_team": "Curacao",
            "lambda_home": "1.2", "lambda_away": "1.0", "data_quality_score": "0.55",
            "egci_v2": "0.5", "egci_v2_quality": "proxy", "acg_favorite": "0.5",
            "acg_v2_quality": "proxy", "underdog_fragility": "0.4", "chase_pressure": "0.3",
            "cold_guard_active": "false", "must_win_no_convert": "false",
            "deep_handicap_contra": "false", "eventflow_degraded": "false",
            "confirmed_event_timeline": "false",
        }
        base.update(kw)
        return base

    def test_rule_enabled_not_same_as_applied(self):
        payload = payload_from_case(self._case())
        tail = apply_tail_to_payload(payload, mode="rerank_only")["audit"]["v37_large_score_tail"]
        if tail["safety_demotion_rule_enabled"]:
            self.assertIsInstance(tail["safety_demotion_applied"], bool)

    def test_no_five_plus_top3_no_demotion(self):
        payload = payload_from_case(self._case(lambda_home="1.1", lambda_away="1.0"))
        tail = apply_tail_to_payload(payload, mode="rerank_only")["audit"]["v37_large_score_tail"]
        if not tail.get("five_plus_in_top3_before"):
            self.assertFalse(tail["safety_demotion_applied"])

    def test_none_no_demotion_ranking_stable(self):
        payload = payload_from_case(self._case())
        before = payload["final_fusion"]["score_ranking"]
        out = apply_tail_to_payload(payload, mode="rerank_only")
        tail = out["audit"]["v37_large_score_tail"]
        if tail["tail_boost_level"] == "none" and not tail["safety_demotion_applied"]:
            self.assertFalse(tail["ranking_mutation_applied"])


if __name__ == "__main__":
    unittest.main()
