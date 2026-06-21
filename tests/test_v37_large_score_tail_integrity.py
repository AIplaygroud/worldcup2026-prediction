"""V3.7-P2.1 large-score tail integrity tests."""
from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from eventflow_common import read_json  # noqa: E402
from v37_common import TAIL_LAYER_VERSION  # noqa: E402
from v37_large_score_tail import TOP3_FORBIDDEN, apply_tail_to_payload  # noqa: E402


REGRESSION = {
    "WC2026-E34": "dual_engine_output_E34_v37_test.json",
    "WC2026-F35": "dual_engine_output_F35_v37_test.json",
    "WC2026-F36": "dual_engine_output_F36_v37_test.json",
}


def _load(mid: str) -> dict:
    path = ROOT / "database/eventflow/processed" / REGRESSION[mid]
    payload = read_json(path, {})
    payload["match_id"] = mid
    return payload


class TestLambdaUnchanged(unittest.TestCase):
    def test_rerank_lambda(self):
        for mid in REGRESSION:
            p = _load(mid)
            before = copy.deepcopy(p["probability_engine"])
            out = apply_tail_to_payload(p, mode="rerank_only")["payload"]
            after = out["probability_engine"]
            self.assertEqual(before.get("lambda_home"), after.get("lambda_home"), mid)
            self.assertEqual(before.get("lambda_away"), after.get("lambda_away"), mid)
            self.assertEqual(before.get("adjusted_lambda"), after.get("adjusted_lambda"), mid)


class TestV2ProbabilityUnchanged(unittest.TestCase):
    def test_scoreline_probs_unchanged(self):
        for mid in REGRESSION:
            p = _load(mid)
            orig = {r["score"]: r["v2_scoreline_probability"] for r in p["final_fusion"]["score_ranking"]}
            out = apply_tail_to_payload(p, mode="rerank_only")["payload"]
            for r in out["final_fusion"]["score_ranking"]:
                self.assertEqual(r["v2_scoreline_probability"], orig.get(r["score"]), mid)


class TestAuditOnlyNoRankingChange(unittest.TestCase):
    def test_ranking_unchanged(self):
        for mid in REGRESSION:
            p = _load(mid)
            before = [(r["score"], r["rank"]) for r in p["final_fusion"]["score_ranking"][:5]]
            apply_tail_to_payload(p, mode="audit_only")
            after = [(r["score"], r["rank"]) for r in p["final_fusion"]["score_ranking"][:5]]
            self.assertEqual(before, after, mid)


class TestE34AlwaysNone(unittest.TestCase):
    def test_e34(self):
        audit = apply_tail_to_payload(_load("WC2026-E34"), mode="rerank_only")["audit"]
        self.assertEqual(audit["v37_large_score_tail"]["tail_boost_level"], "none")
        self.assertEqual(audit["v37_large_score_tail"]["boosted_scores"], [])


class TestColdGuardBlock(unittest.TestCase):
    def test_e34_cold_guard(self):
        audit = apply_tail_to_payload(_load("WC2026-E34"), mode="audit_only")["audit"]
        self.assertTrue(audit["eligibility"]["guard_suppression"])


class TestDegradedEventflowBlock(unittest.TestCase):
    def test_f35_degraded(self):
        p = _load("WC2026-F35")
        self.assertTrue(p.get("eventflow_data_degraded"))
        audit = apply_tail_to_payload(p, mode="rerank_only")["audit"]
        self.assertEqual(audit["v37_large_score_tail"]["boosted_scores"], [])


class TestTop3Forbidden(unittest.TestCase):
    def test_no_5_goal_in_top3(self):
        for mid in REGRESSION:
            out = apply_tail_to_payload(_load(mid), mode="rerank_only")["payload"]
            top3 = [r["score"] for r in out["final_fusion"]["score_ranking"][:3]]
            for s in top3:
                self.assertNotIn(s, TOP3_FORBIDDEN, mid)


class TestAuditStructure(unittest.TestCase):
    def test_p2_1_fields(self):
        audit = apply_tail_to_payload(_load("WC2026-F35"), mode="audit_only")["audit"]
        self.assertEqual(audit["tail_layer_version"], "v37_p4_1")
        self.assertTrue(audit.get("no_v2_probability_mutation"))
        self.assertIn("eligibility", audit)
        self.assertIn("block_reasons", audit)
        self.assertIn("scoreline_before", audit)
        self.assertIn("forbidden_top3_scorelines", audit)
        self.assertTrue(audit["block_reasons"])


class TestRerankWritesAudit(unittest.TestCase):
    def test_delta_summary(self):
        audit = apply_tail_to_payload(_load("WC2026-F35"), mode="rerank_only")["audit"]
        self.assertIn("delta_summary", audit)
        self.assertTrue(audit["no_lambda_mutation"])


if __name__ == "__main__":
    unittest.main()
