"""Region arithmetic: crop chains, normalisation, profile→box."""
import unittest

import numpy as np

from scripts.subs2srt import cli as subs2srt
from scripts.subs2srt import cuelib


class TestCropChain(unittest.TestCase):
    """Every crop must carry exact=1, or ffmpeg re-rounds it behind us."""

    def test_chain_orders_args_as_w_h_x_y(self):
        self.assertEqual(cuelib.crop_chain((10, 20, 300, 40)),
                         "crop=300:40:10:20:exact=1")

    def test_extra_filters_are_appended(self):
        self.assertEqual(cuelib.crop_chain((0, 0, 2, 2), "format=rgb24"),
                         "crop=2:2:0:0:exact=1,format=rgb24")

    def test_exact_flag_is_always_present(self):
        for box in ((0, 0, 1920, 138), (439, 845, 1044, 107)):
            self.assertIn("exact=1", cuelib.crop_chain(box))

    def test_odd_dimensions_are_passed_through_verbatim(self):
        # exact=1 means we may ask for an odd box and get exactly it back
        self.assertEqual(cuelib.crop_chain((1, 3, 1044, 107)),
                         "crop=1044:107:1:3:exact=1")


class TestNormalizeRegion(unittest.TestCase):
    """Belt-and-braces beside exact=1, for older ffmpeg without the flag."""

    def test_odd_values_snap_down_to_even(self):
        self.assertEqual(cuelib.normalize_region((439, 845, 1044, 107)),
                         [438, 844, 1044, 106])

    def test_even_values_are_untouched(self):
        self.assertEqual(cuelib.normalize_region((0, 876, 1920, 138)),
                         [0, 876, 1920, 138])

    def test_clipped_to_frame(self):
        got = cuelib.normalize_region((1900, 1000, 400, 400), 1920, 1080)
        self.assertEqual(got, [1900, 1000, 20, 80])

    def test_never_returns_zero_extent(self):
        got = cuelib.normalize_region((0, 0, 1, 1), 1920, 1080)
        self.assertEqual(got[2] % 2, 0)
        self.assertEqual(got[3] % 2, 0)
        self.assertGreaterEqual(got[2], 2)
        self.assertGreaterEqual(got[3], 2)

    def test_negative_origin_is_clamped(self):
        self.assertEqual(cuelib.normalize_region((-5, -3, 100, 100))[:2],
                         [0, 0])

    def test_all_outputs_are_even(self):
        for box in ((1, 3, 5, 7), (439, 845, 1044, 107), (11, 0, 3, 999)):
            got = cuelib.normalize_region(box, 1920, 1080)
            for value in got:
                self.assertEqual(value % 2, 0, "%s -> %s" % (box, got))


class TestRegionFromProfile(unittest.TestCase):
    """Guard the profile->crop-box arithmetic in detect_band.

    The bug this pins: the candidate loop used `height` for a band's height,
    shadowing the 1080 frame height, so `y1 = min(top + hi + pad, height)`
    clamped the box down to nothing. Detection itself was fine -- the ranked
    candidates printed correctly -- which is exactly why nothing caught it.
    """

    WIDTH = 1920
    HEIGHT = 1080
    TOP = 594

    def _profile(self):
        prof = np.zeros((self.HEIGHT - self.TOP, self.WIDTH),
                        dtype=np.float64)
        # strongest band, but deliberately NOT the last one in row order
        prof[300:350, 100:1800] = 100.0 / 1700
        # a weaker, shorter band below it -- the last loop iteration, and
        # the value that used to leak out and clamp the result
        prof[360:400, 100:1800] = 50.0 / 1700
        return prof

    def test_box_covers_the_strongest_band(self):
        region, _ = subs2srt.region_from_profile(
            self._profile(), self.TOP, self.WIDTH, self.HEIGHT)
        x, y, w, h = region
        self.assertEqual(y, self.TOP + 300 - 6)
        self.assertEqual(h, 50 + 2 * 6)

    def test_box_is_not_clamped_by_a_later_shorter_band(self):
        region, _ = subs2srt.region_from_profile(
            self._profile(), self.TOP, self.WIDTH, self.HEIGHT)
        # the trailing band is 40px tall; a collapsed box would be <= that
        self.assertGreater(region[3], 40)

    def test_ranked_candidates_are_ordered_by_weight(self):
        _, ranked = subs2srt.region_from_profile(
            self._profile(), self.TOP, self.WIDTH, self.HEIGHT)
        self.assertEqual(len(ranked), 2)
        self.assertEqual(ranked[0]["y"], self.TOP + 300)
        self.assertGreater(ranked[0]["weight"], ranked[1]["weight"])

    def test_box_stays_inside_the_frame(self):
        prof = np.zeros((self.HEIGHT - self.TOP, self.WIDTH),
                        dtype=np.float64)
        prof[-40:, :] = 100.0 / self.WIDTH    # band flush with the bottom
        region, _ = subs2srt.region_from_profile(
            prof, self.TOP, self.WIDTH, self.HEIGHT)
        self.assertLessEqual(region[1] + region[3], self.HEIGHT)
        self.assertLessEqual(region[0] + region[2], self.WIDTH)

    def test_collapsed_box_is_refused_rather_than_returned(self):
        with self.assertRaises(RuntimeError):
            # a frame height smaller than the band forces the collapse the
            # shadowing bug used to cause, and it must not pass silently
            subs2srt.region_from_profile(self._profile(), self.TOP,
                                         self.WIDTH, 40)

    def test_width_comes_from_the_chosen_band_only(self):
        """Ink elsewhere in the frame must not set the horizontal extent.

        Measuring columns across the whole search area let a wide band the
        detector did not pick decide where the subtitle starts and ends,
        clipping text off both sides of the band it did pick.
        """
        prof = np.zeros((self.HEIGHT - self.TOP, self.WIDTH),
                        dtype=np.float64)
        prof[300:350, 100:800] = 100.0 / 700     # chosen band: narrow, left
        prof[360:400, 1000:1900] = 50.0 / 900    # other band: wide, right
        region, _ = subs2srt.region_from_profile(
            prof, self.TOP, self.WIDTH, self.HEIGHT)
        x, _, w, _ = region
        self.assertLess(x, 100)                  # starts near the band's ink
        self.assertLess(x + w, 900)              # and stops well before 1000


if __name__ == "__main__":
    unittest.main()
