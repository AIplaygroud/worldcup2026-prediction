"""P4 tail backtest tests."""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from backtest_v37_tail_layer import backtest_case, summarize  # noqa: E402
from v37_historical_common import payload_from_case, rank_of_score  # noqa: E402
from v37_large_score_tail import TOP3_FORBIDDEN, apply_tail_to_payload  # noqa: E402


class TestTailBacktest(unittest.TestCase):
    def _case(self, **kw) -> dict[str, str]:
        base = {
            "match_id": "TEST-1",
            "historical_match_id": "TEST-1",
            "source": "test",
            "competition": "test",
            "home_team": "Germany",
            "away_team": "Curacao",
            "actual_scoreline": "7-1",
            "is_large_score": "true",
            "lambda_home": "4.0",
            "lambda_away": "0.4",
            "data_quality_score": "0.80",
            "egci_v2": "0.72",
            "egci_v2_quality": "real",
            "acg_favorite": "0.70",
            "acg_v2_quality": "real",
            "underdog_fragility": "0.6",
            "chase_pressure": "0.5",
            "cold_guard_active": "false",
            "must_win_no_convert": "false",
            "deep_handicap_contra": "false",
            "eventflow_degraded": "false",
            "confirmed_event_timeline": "true",
            "eligible_for_tail_backtest": "true",
        }
        base.update(kw)
        return base

    def test_baseline_and_rerank_top5(self):
        result, _ = backtest_case(self._case())
        self.assertIn("baseline_top5", result)
        self.assertIn("rerank_top5", result)
        self.assertTrue(result["baseline_top5"])
        self.assertTrue(result["rerank_top5"])

    def test_no_lambda_mutation(self):
        payload = payload_from_case(self._case())
        before = copy.deepcopy(payload["probability_engine"])
        apply_tail_to_payload(payload, mode="rerank_only")
        after = payload["probability_engine"]
        self.assertEqual(before["lambda_home"], after["lambda_home"])
        self.assertEqual(before["lambda_away"], after["lambda_away"])

    def test_no_v2_probability_mutation(self):
        payload = payload_from_case(self._case())
        ranking = payload["final_fusion"]["score_ranking"]
        probs = {r["score"]: r["v2_scoreline_probability"] for r in ranking}
        out = apply_tail_to_payload(payload, mode="rerank_only")["payload"]
        for r in out["final_fusion"]["score_ranking"]:
            self.assertEqual(r["v2_scoreline_probability"], probs[r["score"]])

    def test_rank_improvement_sign(self):
        result = backtest_case(self._case())[0]
        b = int(result["baseline_actual_rank"])
        r = int(result["rerank_actual_rank"])
        self.assertEqual(int(result["rank_improvement"]), b - r)

    def test_false_positive_non_large(self):
        result = backtest_case(self._case(actual_scoreline="1-0", is_large_score="false", lambda_home="1.2", lambda_away="1.0"))[0]
        self.assertIn(result["tail_false_positive"], ("true", "false"))

    def test_five_goal_top3_violation_detected(self):
        payload = payload_from_case(self._case())
        ranking = payload["final_fusion"]["score_ranking"]
        for r in ranking:
            if r["score"] in TOP3_FORBIDDEN:
                r["fusion_ranking_score"] = 0.99
        payload["final_fusion"]["score_ranking"] = sorted(
            ranking, key=lambda x: -x["fusion_ranking_score"],
        )
        for i, r in enumerate(payload["final_fusion"]["score_ranking"], 1):
            r["rank"] = i
        out = apply_tail_to_payload(payload, mode="rerank_only")
        top3 = [r["score"] for r in out["payload"]["final_fusion"]["score_ranking"][:3]]
        self.assertFalse(any(s in TOP3_FORBIDDEN for s in top3))

    def test_summarize_metrics(self):
        results = [backtest_case(self._case())[0], backtest_case(self._case(match_id="TEST-2", actual_scoreline="1-0", is_large_score="false"))[0]]
        summary = summarize(results)
        self.assertIn("large_score_top5_recall_delta", summary)
        self.assertEqual(summary["sample_size"], 2)


if __name__ == "__main__":
    unittest.main()
