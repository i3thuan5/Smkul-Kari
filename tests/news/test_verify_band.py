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
