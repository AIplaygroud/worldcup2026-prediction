"""Missed large-score filter cleanup tests."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from v37_tail_diagnostics_common import is_true_large_score_row, validate_missed_large_score_rows  # noqa: E402


class TestMissedCleanup(unittest.TestCase):
    def test_2_2_excluded(self):
        self.assertFalse(is_true_large_score_row({
            "is_large_score": "true", "large_score_type": "not_large_score",
        }))

    def test_3_0_included(self):
        self.assertTrue(is_true_large_score_row({
            "is_large_score": "true", "large_score_type": "favorite_clean_win_3plus",
        }))

    def test_validate_rejects_pollution(self):
        with self.assertRaises(ValueError):
            validate_missed_large_score_rows([{
                "match_id": "X", "is_large_score": "true",
                "large_score_type": "not_large_score", "primary_miss_reason": "x",
            }])


if __name__ == "__main__":
    unittest.main()
