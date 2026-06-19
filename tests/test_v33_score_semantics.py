import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


class TestScoreSemantics(unittest.TestCase):
    def test_merge_module_fields(self):
        src = (SCRIPTS / "merge_dual_engine_predictions.py").read_text(encoding="utf-8")
        self.assertIn("fusion_ranking_score", src)
        self.assertIn("display_fusion_score", src)
        self.assertNotIn('f"{fusion_ranking_score*100', src)
        self.assertNotIn("% ranking score (not calibrated joint prob)", src)

    def test_data_dictionary(self):
        text = (ROOT / "docs" / "data_dictionary.md").read_text(encoding="utf-8")
        self.assertIn("fusion_ranking_score", text)
        self.assertNotIn("final_weight | 双引擎融合权重", text)

    def test_skill_md(self):
        text = (ROOT / "skill.md").read_text(encoding="utf-8")
        self.assertIn("fusion_ranking_score", text)
        self.assertNotIn("按 `final_weight`", text)


if __name__ == "__main__":
    unittest.main()
