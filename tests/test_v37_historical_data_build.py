"""P4 historical data build tests."""
from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from build_v37_historical_matches import build  # noqa: E402
from v37_historical_common import (  # noqa: E402
    FEATURE_SNAPSHOT_FIELDS,
    HISTORICAL_MATCH_FIELDS,
    label_large_score,
)


class TestHistoricalDataBuild(unittest.TestCase):
    def test_large_score_label(self):
        labels = label_large_score("Germany", "Curacao", 7, 1)
        self.assertEqual(labels["actual_scoreline"], "7-1")
        self.assertEqual(labels["is_large_score"], "true")

    def test_historical_matches_schema(self):
        rows = build(["finished_wc2026"])
        self.assertGreaterEqual(len(rows), 20)
        for field in HISTORICAL_MATCH_FIELDS:
            self.assertIn(field, rows[0])
        self.assertTrue(all(r.get("actual_scoreline") for r in rows))

    def test_feature_snapshot_no_score_leakage(self):
        forbidden = {"actual_scoreline", "home_score", "away_score", "is_large_score"}
        leaked = forbidden & set(FEATURE_SNAPSHOT_FIELDS)
        self.assertEqual(leaked, set())

    def test_statsbomb_ids_prefixed(self):
        rows = build(["statsbomb_open"])
        if not rows:
            self.skipTest("no statsbomb cache")
        for r in rows:
            self.assertTrue(r["historical_match_id"].startswith("SB-"))
            self.assertNotIn("WC2026", r["historical_match_id"])

    def test_event_timeline_flag(self):
        rows = build(["finished_wc2026", "statsbomb_open"])
        with_events = [r for r in rows if r.get("event_timeline_available") == "true"]
        self.assertGreater(len(with_events), 0)


if __name__ == "__main__":
    unittest.main()
