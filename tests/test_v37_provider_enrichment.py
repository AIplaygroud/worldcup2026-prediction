"""V3.7-P3 provider enrichment tests."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from eventflow_common import read_csv  # noqa: E402
from v37_common import FEATURE_TABLES, NORMALIZED_TABLES, V37_AUDIT, V37_TAIL_THRESHOLDS  # noqa: E402
from v37_enrichment_common import ALLOWED_AUDIT_ACTIONS  # noqa: E402


class TestProviderMatchMap(unittest.TestCase):
    def test_map_exists_with_confidence(self):
        path = NORMALIZED_TABLES["provider_match_map"]
        if not path.exists():
            self.skipTest("run build_v37_provider_match_map.py first")
        rows = read_csv(path)
        self.assertGreater(len(rows), 0)
        min_conf = V37_TAIL_THRESHOLDS["provider_match_confidence_min"]
        for r in rows[:5]:
            self.assertGreaterEqual(float(r["match_confidence"]), min_conf)
            self.assertIn("internal_home", r)
            self.assertIn("provider_home", r)


class TestEnrichmentAudit(unittest.TestCase):
    def test_audit_actions_allowed(self):
        path = V37_AUDIT / "provider_enrichment_audit.csv"
        if not path.exists():
            self.skipTest("run enrich_v37_normalized_tables.py first")
        rows = read_csv(path)
        self.assertGreater(len(rows), 0)
        for r in rows:
            self.assertIn(r.get("action", ""), ALLOWED_AUDIT_ACTIONS)
            self.assertTrue(r.get("audit_id"))
            self.assertTrue(r.get("run_id"))

    def test_has_dedup_or_skip_actions(self):
        path = V37_AUDIT / "provider_enrichment_audit.csv"
        if not path.exists():
            self.skipTest("no audit")
        actions = {r.get("action") for r in read_csv(path)}
        self.assertTrue(
            actions & {"duplicate_removed", "skip_duplicate", "keep_local", "conflict_keep_local", "fill_missing"},
            msg=f"actions={actions}",
        )


class TestV2Features(unittest.TestCase):
    def test_egci_v2_built(self):
        path = FEATURE_TABLES["egci_v2"]
        if not path.exists():
            self.skipTest("run build_v37_egci_v2_features.py first")
        rows = read_csv(path)
        self.assertGreaterEqual(len(rows), 72)
        self.assertIn("egci_v2_quality", rows[0])
        self.assertIn("early_goal_cascade_index_v2", rows[0])

    def test_acg_v2_built(self):
        path = FEATURE_TABLES["acg_v2"]
        if not path.exists():
            self.skipTest("run build_v37_acg_v2_features.py first")
        rows = read_csv(path)
        self.assertGreaterEqual(len(rows), 72)
        self.assertIn("acg_v2_quality", rows[0])
        self.assertIn("conversion_proxy_ratio", rows[0])


if __name__ == "__main__":
    unittest.main()
