"""External provider cache dry-run tests."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from data_providers.provider_cache_common import load_cache_list  # noqa: E402
from provider_payload_validator import validate_event, validate_fixture  # noqa: E402
from v37_common import V37_RAW_EXTERNAL, V37_TAIL_THRESHOLDS  # noqa: E402
from v37_enrichment_common import ALLOWED_AUDIT_ACTIONS  # noqa: E402


class TestExternalCacheStructure(unittest.TestCase):
    def test_f35_events_cache_exists(self):
        path = V37_RAW_EXTERNAL / "thestatsapi" / "events" / "WC2026-F35.json"
        if not path.exists():
            self.skipTest("F35 cache not present")
        events = load_cache_list("thestatsapi", "events", "WC2026-F35")
        self.assertGreaterEqual(len(events), 2)
        for ev in events:
            self.assertEqual(validate_event(ev, "WC2026-F35"), [])

    def test_invalid_fixture_rejected(self):
        errs = validate_fixture({}, "TEST")
        self.assertTrue(errs)


class TestEnrichmentAuditActions(unittest.TestCase):
    def test_dry_run_action_allowed(self):
        self.assertIn("dry_run_only", ALLOWED_AUDIT_ACTIONS)


class TestMatchConfidence(unittest.TestCase):
    def test_min_confidence(self):
        self.assertGreaterEqual(V37_TAIL_THRESHOLDS["provider_match_confidence_min"], 0.6)


if __name__ == "__main__":
    unittest.main()
