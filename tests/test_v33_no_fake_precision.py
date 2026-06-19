import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


class TestNoFakePrecision(unittest.TestCase):
    def test_tactical_matrix_has_fallback_fields(self):
        src = (SCRIPTS / "build_tactical_matchup_matrix.py").read_text(encoding="utf-8")
        for field in ("fallback_ratio", "is_fallback", "precision_warning"):
            self.assertIn(field, src)

    def test_scenario_weights_fallback_gate(self):
        src = (SCRIPTS / "build_eventflow_scenario_weights.py").read_text(encoding="utf-8")
        self.assertIn("fallback_profile_only_no_tactical_claim", src)
        self.assertIn("fallback_gate_applied", src)

    def test_predict_eventflow_degraded_payload(self):
        src = (SCRIPTS / "predict_eventflow.py").read_text(encoding="utf-8")
        self.assertIn("eventflow_data_degraded", src)
        self.assertIn("precision_warning", src)
        self.assertIn("missing_scenario_rows", src)

    def test_merge_probability_only_on_degradation(self):
        src = (SCRIPTS / "merge_dual_engine_predictions.py").read_text(encoding="utf-8")
        self.assertIn("probability_only_due_to_eventflow_degradation", src)
        self.assertIn("fallback_ratio_too_high", src)


if __name__ == "__main__":
    unittest.main()
