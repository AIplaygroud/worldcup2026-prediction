"""V3.7 normalized table deduplication tests."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from eventflow_common import read_csv  # noqa: E402
from v37_common import NORMALIZED_TABLES  # noqa: E402
from v37_enrichment_common import MERGE_KEYS, find_duplicates, row_merge_key  # noqa: E402
from validate_v37_normalized_dedup import validate_all  # noqa: E402


class TestNormalizedDedup(unittest.TestCase):
    TABLES = ("match_events", "lineups", "match_stats", "odds_snapshots")

    def test_no_duplicate_merge_keys(self):
        if not NORMALIZED_TABLES["matches"].exists():
            self.skipTest("normalized not built")
        errors = validate_all()
        self.assertEqual(errors, [], msg=errors)

    def test_match_events_event_id_unique(self):
        path = NORMALIZED_TABLES["match_events"]
        if not path.exists():
            self.skipTest("no events")
        rows = read_csv(path)
        dups = find_duplicates("match_events", rows)
        self.assertEqual(dups, [], msg=f"duplicate event keys: {dups[:3]}")

    def test_fulltime_at_most_one(self):
        path = NORMALIZED_TABLES["match_events"]
        if not path.exists():
            self.skipTest("no events")
        ft: dict[str, int] = {}
        for e in read_csv(path):
            if e.get("event_type", "").lower() == "fulltime":
                mid = e["match_id"]
                ft[mid] = ft.get(mid, 0) + 1
        for mid, n in ft.items():
            self.assertLessEqual(n, 1, msg=f"{mid} has {n} fulltime events")

    def test_lineups_key_unique(self):
        path = NORMALIZED_TABLES["lineups"]
        if not path.exists():
            self.skipTest("no lineups")
        dups = find_duplicates("lineups", read_csv(path))
        self.assertEqual(dups, [])

    def test_odds_snapshots_key_unique(self):
        path = NORMALIZED_TABLES["odds_snapshots"]
        if not path.exists():
            self.skipTest("no odds")
        dups = find_duplicates("odds_snapshots", read_csv(path))
        self.assertEqual(dups, [])


if __name__ == "__main__":
    unittest.main()
