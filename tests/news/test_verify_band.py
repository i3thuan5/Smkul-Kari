"""verify_band: telling a graphic's border from the subtitle's own rows.

Both landmarks live in the same profile and the layouts in this corpus put
them within a few pixels of each other, so reading either by height alone
gets it wrong. Two real files proved it, and both are reproduced here as
shapes:

  41午鄒   no lower third on screen. The tallest row is the bottom stroke of
           the glyphs, which is inside the region by construction, so calling
           it a border refused a good file.
  37晚排灣  the full news layout. Its tallest single row is a border 3 px
           BELOW the region, so calling that the dialogue put the plateau
           outside the region and refused a good file the other way round.
"""
import unittest

import numpy as np

from scripts.news import verify_band


def text(rows, top, bottom, height):
    """A broad plateau: a line of subtitle, glyph-body tall."""
    rows[top:bottom] = height


def rule(rows, top, height):
    """A thin bright line: the border along the top of a graphic."""
    rows[top:top + 3] = height


class TestLandmarks(unittest.TestCase):
    def test_border_below_the_text_is_found_as_a_border(self):
        rows = np.full(240, 30.0)
        text(rows, 80, 130, 130)
        rule(rows, 150, 480)
        edge, plateau, ratio = verify_band.landmarks(rows)
        self.assertTrue(150 <= edge <= 152, edge)
        self.assertTrue(80 <= plateau < 130, plateau)
        self.assertGreater(ratio, verify_band.SPIKE)

    def test_the_texts_own_densest_row_is_not_a_border(self):
        # 41午鄒's shape: no graphic anywhere, just one row of the glyphs
        # denser than its neighbours.
        rows = np.full(240, 30.0)
        text(rows, 80, 130, 130)
        rows[126] = 170.0
        edge, plateau, ratio = verify_band.landmarks(rows)
        self.assertIsNone(edge)
        self.assertTrue(80 <= plateau < 130, plateau)
        self.assertLess(ratio, verify_band.SPIKE)

    def test_a_border_does_not_steal_the_plateau_from_the_text(self):
        # 37晚排灣's shape: the border out-inks every single row of the
        # subtitle, but the subtitle is the only broad thing in the profile.
        rows = np.full(240, 20.0)
        text(rows, 80, 130, 130)
        rule(rows, 133, 300)
        _, plateau, _ = verify_band.landmarks(rows)
        self.assertTrue(80 <= plateau < 130, plateau)

    def test_a_border_shown_half_the_window_is_still_a_border(self):
        # Averaged over frames, an intermittent graphic fades towards the
        # picture behind it. The reading is against that neighbourhood, so it
        # weakens rather than disappearing.
        picture = np.full(240, 20.0)
        text(picture, 80, 130, 130)
        with_graphic = picture.copy()
        with_graphic[145:200] = 110.0        # the banner body
        rule(with_graphic, 150, 480)
        rows = (picture + with_graphic) / 2
        edge, _, ratio = verify_band.landmarks(rows)
        self.assertIsNotNone(edge)
        self.assertGreater(ratio, verify_band.SPIKE)

    def test_flat_profile_reports_no_border(self):
        rows = np.full(240, 7.0)
        edge, _, _ = verify_band.landmarks(rows)
        self.assertIsNone(edge)


if __name__ == "__main__":
    unittest.main()
