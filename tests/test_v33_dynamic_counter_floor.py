import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import predict_v2  # noqa: E402
from predict_v2 import (  # noqa: E402
    MatchContext,
    COUNTER_FLOOR_MAX,
    COUNTER_FLOOR_MIN,
    dynamic_counter_floor,
    load_data,
    resolve_context,
)


class TestDynamicCounterFloor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_data()

    def _ctx(self, **kwargs):
        ctx = MatchContext(home="Jordan", away="Argentina", **kwargs)
        return resolve_context(ctx, self.data)

    def test_default_floor_below_old_fixed(self):
        ctx = self._ctx()
        fl = dynamic_counter_floor(ctx.away, ctx.home, "away", ctx, self.data, 0.4)
        self.assertLess(fl, 0.85)
        self.assertGreaterEqual(fl, COUNTER_FLOOR_MIN)

    def test_strong_counter_can_raise_but_capped(self):
        ctx = self._ctx(counter_quality_away=1.2, key_att_out_away=0.0)
        fl = dynamic_counter_floor(ctx.away, ctx.home, "away", ctx, self.data, 0.5)
        self.assertLessEqual(fl, COUNTER_FLOOR_MAX)

    def test_key_att_out_lowers_floor(self):
        ctx = self._ctx(counter_quality_away=1.1)
        fl_base = dynamic_counter_floor(ctx.away, ctx.home, "away", ctx, self.data, 0.4)
        ctx2 = self._ctx(counter_quality_away=1.1, key_att_out_away=1.0)
        fl_inj = dynamic_counter_floor(ctx2.away, ctx2.home, "away", ctx2, self.data, 0.4)
        self.assertLess(fl_inj, fl_base)

    def test_low_confidence_caps_floor(self):
        ctx = self._ctx(counter_quality_away=1.2)
        self.data.setdefault("team_model", {}).setdefault(ctx.away, {})["confidence"] = "low"
        fl = dynamic_counter_floor(ctx.away, ctx.home, "away", ctx, self.data, 0.5)
        self.assertLessEqual(fl, predict_v2.COUNTER_FLOOR_CONF_CAP_LOW)


if __name__ == "__main__":
    unittest.main()
