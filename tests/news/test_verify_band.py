"""verify_band's landmarks and pass/fail rules, on synthetic profiles.

Pins the loosened edge criterion that had never been field-tested when it
was written: an edge any distance BELOW the region is safe (the January
卑南 layout puts it at y=917 against a region ending at y=844); only an
edge INSIDE the region may stop a batch.
"""
import unittest

import numpy as np

from scripts.news import verify_band
from scripts.ocr import cuelib

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


class TestLandmarkReport(unittest.TestCase):
    """判「無紅帶」ê時，量著ê數字愛留佇輸出予人覆核。

    「無紅帶」這个判定會**kā「紅帶袂使落佇 region 內」彼道檢查
    閬過**——失敗ê方向是放過歹檔案，毋是擋著好ê。所以伊袂使恬恬
    仔閬過：比值佮門檻攏愛講出來，人才有法度看這个判定是量著ê抑是
    量無ê。門檻本身改過幾擺，數字留咧才有法度轉頭校。
    """

    def test_no_rule_line_carries_the_ratio_and_the_threshold(self):
        line = verify_band.landmark_lines(None, 1.78)[0]
        self.assertIn("1.78", line)
        self.assertIn("%.2f" % verify_band.SPIKE, line)

    def test_the_rule_line_carries_where_and_how_tall(self):
        line = verify_band.landmark_lines(849, 2.15)[0]
        self.assertIn("849", line)
        self.assertIn("2.15", line)


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


class TestRightCliff(unittest.TestCase):
    """Where the ink stops on the right, off the column profile.

    News subtitles are flush right: measured over 27 episodes the ink's
    right edge sits at x=1735-1737 with a standard deviation of 31-70 px,
    against 460-470 for the left edge. So the column profile climbs from the
    left and falls off a cliff at the text's right edge, and that cliff is
    what says whether this batch's layout is the one the preset describes.
    """

    def _profile(self, lo, hi, width=1440):
        cols = np.zeros(width)
        cols[lo:hi] = 40.0
        return cols

    def test_the_cliff_lands_at_the_right_edge_of_the_ink(self):
        got = verify_band.right_cliff(self._profile(200, 1264))
        self.assertIsNotNone(got)
        self.assertLess(abs(got - 1264), 16)

    def test_a_shifted_layout_moves_the_cliff(self):
        near = verify_band.right_cliff(self._profile(200, 1264))
        far = verify_band.right_cliff(self._profile(100, 1160))
        self.assertLess(far, near - 80)

    def test_a_blank_profile_has_no_cliff(self):
        self.assertIsNone(verify_band.right_cliff(np.zeros(1440)))


class TestJudgeColumns(unittest.TestCase):
    """The window has to contain the text, with room to compare.

    Deliberately NOT "is the cliff where we expected it": 046晚 puts its
    right edge at 1631 against the usual 1736, and the fixed window still
    works on it (measured: repeated cues 48 -> 27, nothing dropped), because
    1631 is inside the window with 390px of line to its left. A tolerance
    around an expected value would have refused a batch that cuts perfectly
    well.

    The 200px floor comes from the shortest subtitles measured: the 10th
    percentile of line width is 420-546px, so half of that inside the window
    is a floor with room to spare.
    """

    WINDOW = (1250, 1790)

    def test_the_usual_layout_passes(self):
        self.assertEqual(verify_band.judge_columns(1744, self.WINDOW), [])

    def test_the_measured_outlier_still_passes(self):
        self.assertEqual(verify_band.judge_columns(1640, self.WINDOW), [])

    def test_text_shifted_off_the_left_of_the_window_is_refused(self):
        problems = verify_band.judge_columns(1300, self.WINDOW)
        self.assertEqual(len(problems), 1)
        self.assertIn("1300", problems[0])
        self.assertIn("1250", problems[0])

    def test_text_running_past_the_right_of_the_window_is_refused(self):
        problems = verify_band.judge_columns(1850, self.WINDOW)
        self.assertEqual(len(problems), 1)
        self.assertIn("1850", problems[0])

    def test_no_window_declared_means_nothing_to_check(self):
        self.assertEqual(verify_band.judge_columns(900, None), [])

    def test_no_ink_at_all_is_refused_rather_than_passed(self):
        problems = verify_band.judge_columns(None, self.WINDOW)
        self.assertEqual(len(problems), 1)


class TestColumnGuardIsNotAnInkShareTest(unittest.TestCase):
    """The share of ink inside the window cannot tell the layouts apart.

    Measured: the three normal episodes put 53%, 69% and 62% of their band
    ink inside the window, and the odd one out puts 58% -- squarely among
    them, because that share moves with sentence length and with how bright
    the picture behind the band happens to be. The cliff separates them
    cleanly (1744/1745/1744 against 1640). This is pinned so nobody
    "simplifies" the guard into the measure that does not work.
    """

    def test_same_ink_share_different_verdicts(self):
        good = np.zeros(1440)
        good[1000:1264] = 40.0                  # ends at the usual place
        bad = np.zeros(1440)
        bad[556:820] = 40.0                     # same width, far left
        self.assertAlmostEqual(float(good.sum()), float(bad.sum()))
        window = (1250, 1790)
        good_cliff = verify_band.right_cliff(good) + 480
        bad_cliff = verify_band.right_cliff(bad) + 480
        self.assertEqual(verify_band.judge_columns(good_cliff, window), [])
        self.assertEqual(len(verify_band.judge_columns(bad_cliff, window)), 1)


class TestColumnProfileIgnoresTheLowerThird(unittest.TestCase):
    """The column half must not count the supers under the band.

    `probe_region` reaches 120 rows below the region on purpose, so that a
    lower third that intrudes can be seen at all. But the lower third's
    keyword and reporter-name supers run further right than the dialogue:
    summed over the whole probe, 032午 measured its right edge at x=1801 and
    the guard refused an ordinary episode. Over the region's own rows the
    same episode measures 1744.
    """

    def _frames(self):
        """A dialogue line ending early, a super below it ending later."""
        frame = np.full((240, 1440, 3), 20, dtype=np.uint8)
        frame[60:100, 700:1264] = 255      # dialogue, inside the band rows
        frame[160:190, 700:1360] = 255     # super, below the band
        return frame

    def test_summing_the_whole_probe_finds_the_super(self):
        mask = cuelib.text_mask(self._frames(), cuelib.MaskSpec())
        whole = verify_band.right_cliff(mask.sum(axis=0).astype(float))
        self.assertGreater(whole, 1300)

    def test_summing_the_band_rows_finds_the_dialogue(self):
        mask = cuelib.text_mask(self._frames(), cuelib.MaskSpec())
        band = verify_band.right_cliff(mask[40:140, :].sum(axis=0)
                                       .astype(float))
        self.assertLess(band, 1300)
