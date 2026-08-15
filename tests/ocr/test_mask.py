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
