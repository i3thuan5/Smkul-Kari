"""verify_band's landmarks and pass/fail rules, on synthetic profiles.

Pins the loosened edge criterion that had never been field-tested when it
was written: an edge any distance BELOW the region is safe (the January
卑南 layout puts it at y=917 against a region ending at y=844); only an
edge INSIDE the region may stop a batch.
"""
import unittest

import numpy as np

from scripts.news import verify_band

# Mirrors the titv-news probe: region [0,722,1920,122] probed from y=682
# over 242 rows (region grown by 40 above and 120 below).
PROBE_Y = 682
PROBE_H = 242
REGION_LO = 722
REGION_HI = 844


def profile_with(plateau_y=None, edge_y=None):
    """A synthetic row profile: a glyph-height plateau and/or a thin rule."""
    rows = np.zeros(PROBE_H, dtype=np.float64)
    if plateau_y is not None:
        i = plateau_y - PROBE_Y
        rows[i:i + 40] = 100.0          # dialogue: broad, glyph-height
    if edge_y is not None:
        i = edge_y - PROBE_Y
        rows[i] = 600.0                 # graphic border: one thin bright row
    return rows


class TestProbeRegion(unittest.TestCase):
    """量測愛閃過畫面倒爿彼塊**常駐**ê節目台標。

    晨間新聞ê倒下角有一塊「<族語>／晨間新聞」ê圖卡，規集攏佇咧。伊蓋光
    閣蓋定，逐列ê平均予伊拖懸，`landmarks()` 就kā彼塊當做「對白高原」，
    真正ê對白（間歇才出現）反而輸伊。20210220_051_晨間_Thau_邵 就是按呢
    予擋落來ê：量著 y=892（台標），毋是 y=799（對白）。

    實測仝一支母帶，取樣ê倒爿邊界徙開了後：

        x0=0    對白高原 y=892   <- 台標
        x0=300  對白高原 y=799   <- 對白，佇 region 722..844 內底
        x0=400  對白高原 y=799
        x0=500  對白高原 y=799

    午間、晚間彼款無這塊台標，閃這塊袂影響in：判準是「佗一**列**有字」，
    毋是「偌濟字」，倒爿剪掉一塊，列ê位置袂振動。
    """

    def test_the_probe_skips_the_station_bug(self):
        probe = verify_band.probe_region((0, 722, 1920, 122))
        self.assertEqual(probe[0], verify_band.BUG_MARGIN)

    def test_the_probe_keeps_the_rest_of_the_width(self):
        probe = verify_band.probe_region((0, 722, 1920, 122))
        self.assertEqual(probe[0] + probe[2], 1920)

    def test_it_still_looks_above_and_below_the_region(self):
        # 徙開ê是倒爿，懸低愛照原本：版型若徙位，愛看會著伊徙去佗
        probe = verify_band.probe_region((0, 722, 1920, 122))
        self.assertEqual(probe[1], PROBE_Y)
        self.assertEqual(probe[3], PROBE_H)

    def test_a_region_that_already_starts_right_is_not_moved_left(self):
        probe = verify_band.probe_region((900, 722, 1020, 122))
        self.assertEqual(probe[0], 900)
        self.assertEqual(probe[0] + probe[2], 1920)

    def test_a_narrow_region_is_left_alone(self):
        # 若閃了賰無偌闊，就莫閃——寧可量著台標嘛毋通無夠資料通量
        probe = verify_band.probe_region((0, 722, 400, 122))
        self.assertEqual(probe[0], 0)
        self.assertEqual(probe[2], 400)


class TestLandmarks(unittest.TestCase):
    def test_plateau_and_thin_rule_are_told_apart(self):
        rows = profile_with(plateau_y=790, edge_y=848 - PROBE_Y + PROBE_Y)
        edge_i, plateau_i, ratio = verify_band.landmarks(rows)
        self.assertIsNotNone(edge_i)
        self.assertEqual(PROBE_Y + edge_i, 848)
        self.assertTrue(790 <= PROBE_Y + plateau_i <= 830)
        self.assertGreaterEqual(ratio, verify_band.SPIKE)

    def test_no_rule_on_screen_reports_no_edge(self):
        rows = profile_with(plateau_y=790)
        edge_i, plateau_i, _ratio = verify_band.landmarks(rows)
        self.assertIsNone(edge_i)
        self.assertTrue(790 <= PROBE_Y + plateau_i <= 830)


class TestJudge(unittest.TestCase):
    """The spec's two scenarios, as the executable rule."""

    def _verdict(self, plateau_y, edge_y):
        rows = profile_with(plateau_y=plateau_y, edge_y=edge_y)
        edge_i, plateau_i, _ = verify_band.landmarks(rows)
        edge = None if edge_i is None else PROBE_Y + edge_i
        return verify_band.judge(edge, PROBE_Y + plateau_i,
                                 REGION_LO, REGION_HI)

    def test_low_lying_edge_far_below_region_passes(self):
        # the January 卑南 layout: edge at y=917, region ends at y=844
        self.assertEqual(self._verdict(790, 917), [])

    def test_february_edge_just_below_region_passes(self):
        self.assertEqual(self._verdict(790, 848), [])

    def test_edge_inside_region_stops_the_batch(self):
        problems = self._verdict(750, 830)
        self.assertTrue(problems)
        self.assertIn("inside the region", problems[0])

    def test_plateau_outside_region_stops_the_batch(self):
        # dialogue found well above the region: wrong strip entirely
        rows = profile_with(plateau_y=690)
        edge_i, plateau_i, _ = verify_band.landmarks(rows)
        problems = verify_band.judge(None, PROBE_Y + plateau_i,
                                     REGION_LO, REGION_HI)
        self.assertTrue(problems)
        self.assertIn("outside the region", problems[0])

    def test_no_edge_with_good_plateau_passes(self):
        self.assertEqual(self._verdict(790, None), [])


if __name__ == "__main__":
    unittest.main()
