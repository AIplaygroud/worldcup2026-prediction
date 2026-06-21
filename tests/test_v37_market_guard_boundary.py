"""Market guard audit-only boundary tests."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from eventflow_common import read_json  # noqa: E402


class TestMarketGuardBoundary(unittest.TestCase):
    def setUp(self):
        self.path = ROOT / "database/eventflow/processed/market_guard_report.json"
        if not self.path.exists():
            self.skipTest("market_guard_report missing")
        self.report = read_json(self.path, {})

    def test_emit_recommendations_false(self):
        self.assertFalse(self.report.get("meta", {}).get("emit_recommendations", True))

    def test_report_type_market_guard(self):
        self.assertEqual(self.report.get("meta", {}).get("report_type"), "market_guard")

    def test_recommended_combos_empty(self):
        self.assertEqual(self.report.get("recommended_combos", []), [])

    def test_no_stake_in_report(self):
        text = json.dumps(self.report, ensure_ascii=False).lower()
        self.assertNotIn('"stake"', text)

    def test_no_sure_pick(self):
        text = json.dumps(self.report, ensure_ascii=False).lower()
        self.assertNotIn("sure pick", text)
        self.assertNotIn("sure_pick", text)


if __name__ == "__main__":
    unittest.main()
