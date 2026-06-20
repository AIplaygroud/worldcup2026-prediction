import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from scenario_realization_common import DIAG_PATH, load_diagnostics, sync_v36_diagnostics_from_merge_json  # noqa: E402

R2 = [
    ("WC2026-D32", "database/eventflow/processed/dual_engine_output_D32_USA_AUS_balanced_v36.json"),
    ("WC2026-C29", "database/eventflow/processed/dual_engine_output_C29_BRA_HTI_balanced_v36.json"),
    ("WC2026-C30", "database/eventflow/processed/dual_engine_output_C30_SCO_MAR_balanced_v36.json"),
    ("WC2026-D31", "database/eventflow/processed/dual_engine_output_D31_TUR_PAR_balanced_v36.json"),
]


class TestV36DiagnosticsSync(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for mid, rel in R2:
            path = ROOT / rel
            if path.exists():
                sync_v36_diagnostics_from_merge_json(path)

    def test_raw_diagnostics_has_v36_layer(self):
        for mid, rel in R2:
            path = ROOT / rel
            if not path.exists():
                self.skipTest(f"missing {rel}")
            diag = load_diagnostics(mid)
            data = json.loads(path.read_text(encoding="utf-8"))
            pe = data.get("probability_engine", {})
            self.assertTrue(diag.get("v36_realization_layer"), f"{mid} raw missing v36_realization_layer")
            self.assertTrue(diag.get("scenario_realization"), f"{mid} raw missing scenario_realization")
            self.assertEqual(diag.get("probabilities_from"), "v36_realized")
            self.assertEqual(pe.get("probabilities_from"), "v36_realized")

    def test_btts_matches_between_json_and_raw(self):
        for mid, rel in R2:
            path = ROOT / rel
            if not path.exists():
                continue
            pe = json.loads(path.read_text(encoding="utf-8"))["probability_engine"]
            diag = load_diagnostics(mid)
            json_btts = pe.get("realized_probability", {}).get("btts")
            raw_btts = diag.get("realized_probability", {}).get("btts")
            if json_btts is not None and raw_btts is not None:
                self.assertAlmostEqual(float(json_btts), float(raw_btts), places=4, msg=mid)

    def test_d32_btts_direction_down(self):
        diag = load_diagnostics("WC2026-D32")
        if not diag:
            self.skipTest("no D32 diagnostics")
        gate = diag.get("btts_conversion_gate", {})
        self.assertEqual(gate.get("adjustment_direction"), "down")
        v36 = diag.get("v36_realization_layer", {})
        self.assertLessEqual(float(v36.get("data_quality_score", 1)), 0.75)


if __name__ == "__main__":
    unittest.main()
