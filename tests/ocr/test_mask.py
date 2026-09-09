"""Masking: morphology, mask distance, text_mask, band presence."""
import unittest

import numpy as np

from scripts.ocr import cuelib


class TestMorphology(unittest.TestCase):
    def test_dilate_grows_by_radius(self):
        mask = np.zeros((9, 9), dtype=bool)
        mask[4, 4] = True
        grown = cuelib.dilate(mask, 5)
        self.assertEqual(int(grown.sum()), 25)
        self.assertTrue(grown[2:7, 2:7].all())

    def test_dilate_noop_for_size_below_three(self):
        mask = np.zeros((4, 4), dtype=bool)
        mask[1, 1] = True
        self.assertTrue((cuelib.dilate(mask, 1) == mask).all())

    def test_erode_removes_thin_strokes(self):
        mask = np.zeros((11, 11), dtype=bool)
        mask[5, :] = True            # a 1px horizontal stroke
        self.assertEqual(int(cuelib.erode(mask, 3).sum()), 0)

    def test_erode_keeps_blob_interior(self):
        mask = np.zeros((11, 11), dtype=bool)
        mask[2:9, 2:9] = True
        eroded = cuelib.erode(mask, 3)
        self.assertTrue(eroded[3:8, 3:8].all())
        self.assertFalse(eroded[2, 2])

    def test_dilate_does_not_wrap_edges(self):
        mask = np.zeros((5, 5), dtype=bool)
        mask[0, 0] = True
        grown = cuelib.dilate(mask, 3)
        self.assertFalse(grown[4, 4])
        self.assertEqual(int(grown.sum()), 4)


class TestMaskDistance(unittest.TestCase):
    def test_identical_is_zero(self):
        mask = np.zeros((8, 8), dtype=bool)
        mask[2:5, 2:5] = True
        self.assertEqual(cuelib.mask_distance(mask, mask.copy()), 0.0)

    def test_disjoint_is_one(self):
        a = np.zeros((8, 8), dtype=bool)
        b = np.zeros((8, 8), dtype=bool)
        a[0:3, 0:3] = True
        b[5:8, 5:8] = True
        self.assertEqual(cuelib.mask_distance(a, b), 1.0)

    def test_both_empty_is_zero(self):
        empty = np.zeros((4, 4), dtype=bool)
        self.assertEqual(cuelib.mask_distance(empty, empty), 0.0)

    def test_half_overlap(self):
        a = np.zeros((1, 4), dtype=bool)
        b = np.zeros((1, 4), dtype=bool)
        a[0, 0:2] = True
        b[0, 1:3] = True
        # union 3, symmetric difference 2
        self.assertAlmostEqual(cuelib.mask_distance(a, b), 2.0 / 3.0)


class TestTextMask(unittest.TestCase):
    def _canvas(self, colour, size=(60, 60)):
        return np.full((size[0], size[1], 3), colour, dtype=np.uint8)

    def test_outlined_glyph_is_kept(self):
        frame = self._canvas(30)                 # dark background
        frame[28:32, 10:50] = 255                # white stroke on it
        spec = cuelib.MaskSpec()
        mask = cuelib.text_mask(frame, spec)
        self.assertGreater(int(mask.sum()), 100)

    def test_large_flat_white_is_rejected(self):
        frame = self._canvas(255)                # nothing but white
        spec = cuelib.MaskSpec()
        self.assertEqual(int(cuelib.text_mask(frame, spec).sum()), 0)

    def test_yellow_band_is_rejected_but_glyph_is_not(self):
        frame = np.zeros((60, 60, 3), dtype=np.uint8)
        frame[:, :] = (255, 220, 40)             # saturated yellow band
        spec = cuelib.MaskSpec(outline=False)
        self.assertEqual(int(cuelib.text_mask(frame, spec).sum()), 0)
        frame[28:32, 10:50] = 255
        self.assertEqual(int(cuelib.text_mask(frame, spec).sum()), 4 * 40)

    def test_luma_matches_bt601(self):
        frame = np.zeros((1, 1, 3), dtype=np.uint8)
        frame[0, 0] = (255, 255, 255)
        self.assertGreaterEqual(int(cuelib.luma_of(frame)[0, 0]), 250)
        frame[0, 0] = (0, 0, 0)
        self.assertEqual(int(cuelib.luma_of(frame)[0, 0]), 0)


class TestBandPresence(unittest.TestCase):
    """Titles and credit rolls must not be mistaken for subtitles."""

    PROBE = {"x": 0, "w": 60, "min_saturation": 60}

    def _band(self):
        frame = np.zeros((40, 200, 3), dtype=np.uint8)
        frame[:, :] = (247, 190, 117)          # the orange/yellow bar
        return frame

    def _footage(self):
        frame = np.zeros((40, 200, 3), dtype=np.uint8)
        frame[:, :] = (75, 77, 100)            # a dull, near-grey shot
        return frame

    def test_saturated_band_counts_as_present(self):
        self.assertTrue(cuelib.band_present(self._band(), self.PROBE))

    def test_desaturated_footage_counts_as_absent(self):
        self.assertFalse(cuelib.band_present(self._footage(), self.PROBE))

    def test_no_probe_always_present(self):
        self.assertTrue(cuelib.band_present(self._footage(), None))

    def test_mask_is_empty_when_band_is_gone(self):
        frame = self._footage()
        frame[18:24, 80:160] = 255             # white credit text
        spec = cuelib.MaskSpec(outline=False, band_probe=self.PROBE)
        self.assertEqual(int(cuelib.text_mask(frame, spec).sum()), 0)

    def test_same_text_is_kept_when_band_is_there(self):
        frame = self._band()
        frame[18:24, 80:160] = 255
        spec = cuelib.MaskSpec(outline=False, band_probe=self.PROBE)
        self.assertEqual(int(cuelib.text_mask(frame, spec).sum()), 6 * 80)

    def test_probe_survives_round_trip_through_dict(self):
        spec = cuelib.MaskSpec.from_dict({"band_probe": self.PROBE})
        self.assertEqual(spec.to_dict()["band_probe"], self.PROBE)


if __name__ == "__main__":
    unittest.main()


class TestFrameMask(unittest.TestCase):
    """`frame_mask` is what the segmenter compares: sampled, then windowed.

    The first test is the regression anchor for the whole change. Cutting a
    cue used to call `text_mask` directly; if `frame_mask` at scale 1 with no
    window ever stops matching it bit for bit, every timeline cut before the
    change and every one cut after stop being comparable, and nothing else
    in the pipeline would notice -- `rebuild --verify` rebuilds SRTs from
    stored timelines and never touches a mask.
    """

    def _lit(self, size=(120, 120)):
        """A dark frame with one white stroke across it."""
        frame = np.full((size[0], size[1], 3), 30, dtype=np.uint8)
        frame[52:60, 20:100] = 255
        return frame

    def test_unscaled_unwindowed_matches_text_mask_bit_for_bit(self):
        frame = self._lit()
        spec = cuelib.MaskSpec()
        self.assertTrue(np.array_equal(cuelib.frame_mask(frame, spec),
                                       cuelib.text_mask(frame, spec)))

    def test_half_scale_keeps_the_glyph_and_about_a_quarter_of_the_ink(self):
        frame = self._lit()
        full = int(cuelib.text_mask(frame, cuelib.MaskSpec()).sum())
        half = int(cuelib.frame_mask(frame, cuelib.MaskSpec(scale=2)).sum())
        self.assertGreater(half, 0, "the glyph vanished at half scale")
        self.assertGreater(half, full * 0.15)
        self.assertLess(half, full * 0.45)

    def test_window_blanks_outside_and_leaves_inside_alone(self):
        frame = self._lit()
        plain = cuelib.text_mask(frame, cuelib.MaskSpec())
        spec = cuelib.MaskSpec(compare_cols=(40, 80), compare_rows=(50, 62))
        got = cuelib.frame_mask(frame, spec)
        self.assertEqual(int(got[:, :40].sum()), 0)
        self.assertEqual(int(got[:, 80:].sum()), 0)
        self.assertEqual(int(got[:50, :].sum()), 0)
        self.assertEqual(int(got[62:, :].sum()), 0)
        self.assertTrue(np.array_equal(got[50:62, 40:80],
                                       plain[50:62, 40:80]))

    def test_a_glyph_wholly_outside_the_window_reads_as_blank(self):
        """The mechanism behind the 0.1% of cues the window drops.

        Measured on four episodes: 5 subtitles out of 2,669 sit entirely
        outside the compare window (a graphic covering the band, or a
        detection so faint its ink is 437 against a subtitle's 2000-4000).
        The segmenter then never opens a cue there. That is a deliberate
        trade -- the same window cuts swallowed sentences from 87 to 43 on
        one episode -- so it is locked down here rather than left to be
        rediscovered as a surprise.
        """
        frame = self._lit()
        spec = cuelib.MaskSpec(compare_cols=(0, 15))
        self.assertEqual(int(cuelib.frame_mask(frame, spec).sum()), 0)


class TestMaskSpecScaled(unittest.TestCase):
    """Every length in the spec has to shrink together with the pixels.

    Two of these have teeth. Leaving `band_probe` at full-frame coordinates
    points 開會了's band test at the wrong columns, so a whole episode reads
    as having no band at all. Leaving `band_rows` unscaled crops the wrong
    rows, which is the very failure `band_rows` was added to fix.
    """

    def test_lengths_halve_and_thresholds_do_not(self):
        spec = cuelib.MaskSpec(
            outline_size=9, thin_size=7,
            band_probe={"x": 60, "w": 40, "min_saturation": 60},
            band_rows=(24, 114), compare_cols=(1250, 1790),
            compare_rows=(4, 114), scale=2)
        small = spec.scaled(2)
        self.assertEqual(small.outline_size, 5)
        self.assertEqual(small.band_probe["x"], 30)
        self.assertEqual(small.band_probe["w"], 20)
        self.assertEqual(small.band_probe["min_saturation"], 60)
        self.assertEqual(tuple(small.band_rows), (12, 57))
        self.assertEqual(tuple(small.compare_cols), (625, 895))
        self.assertEqual(tuple(small.compare_rows), (2, 57))
        # intensities are not lengths
        self.assertEqual(small.white_min, spec.white_min)
        self.assertEqual(small.max_spread, spec.max_spread)
        self.assertEqual(small.dark_max, spec.dark_max)
        # already applied, so the copy must not scale a second time
        self.assertEqual(small.scale, 1)

    def test_none_fields_stay_none(self):
        small = cuelib.MaskSpec().scaled(2)
        self.assertIsNone(small.band_probe)
        self.assertIsNone(small.band_rows)
        self.assertIsNone(small.compare_cols)
        self.assertIsNone(small.compare_rows)

    def test_factor_one_is_a_no_op(self):
        spec = cuelib.MaskSpec(outline_size=9, compare_cols=(10, 20))
        same = spec.scaled(1)
        self.assertEqual(same.outline_size, 9)
        self.assertEqual(tuple(same.compare_cols), (10, 20))


class TestMaskSpecStaysOutOfTheManifest(unittest.TestCase):
    """The three new fields are deliberately NOT serialised.

    Ruled 2026-09-09: the timeline gains no new keys. These three are
    declared by the layout preset, so the preset is where they live; only
    values that are *measured* per episode (`band_rows`) have nowhere else
    to go and are written to the timeline. Anyone who "tidies up" by adding
    them to the key tables breaks that split, so the key set is asserted.
    """

    KEYS = {"white_min", "max_spread", "dark_max", "outline", "outline_size",
            "thin", "thin_size", "band_probe", "band_rows"}

    def test_to_dict_carries_exactly_the_old_keys(self):
        spec = cuelib.MaskSpec(scale=2, compare_cols=(1250, 1790),
                               compare_rows=(4, 114))
        self.assertEqual(set(spec.to_dict().keys()), self.KEYS)

    def test_from_dict_ignores_the_three(self):
        spec = cuelib.MaskSpec.from_dict(
            {"scale": 2, "compare_cols": [1250, 1790],
             "compare_rows": [4, 114], "white_min": 200})
        self.assertEqual(spec.white_min, 200)
        self.assertEqual(spec.scale, 1)
        self.assertIsNone(spec.compare_cols)
        self.assertIsNone(spec.compare_rows)
