"""blobs: which pixels belong to the same glyph.

Readers need this every batch -- to find where the formosan row's
descenders really end, to census descender glyphs, to tell a real thin
stroke from an anti-aliasing speck -- and the environment has no scipy.
Left to re-implement it themselves, readers get it subtly different each
time: two of them once reimplemented `band_present` as HSV saturation and
agreed with each other on the wrong answer. One implementation, tested,
is the point.
"""
import unittest

import numpy as np

from scripts.aiyalaeho import blobs


def grid(rows):
    """A mask from rows of '.' and '#'."""
    out = []
    for row in rows:
        line = []
        for ch in row:
            line.append(ch == "#")
        out.append(line)
    return np.array(out, dtype=bool)


class TestLabel(unittest.TestCase):
    def test_an_empty_mask_has_no_components(self):
        labels, count = blobs.label(grid(["...", "..."]))
        self.assertEqual(count, 0)
        self.assertEqual(labels.max(), 0)

    def test_two_separated_marks_are_two_components(self):
        labels, count = blobs.label(grid(["#..#",
                                          "#..#"]))
        self.assertEqual(count, 2)
        self.assertNotEqual(labels[0][0], labels[0][3])

    def test_a_diagonal_touch_joins_them(self):
        """8-connected, not 4: glyph strokes touch at corners."""
        labels, count = blobs.label(grid(["#.",
                                          ".#"]))
        self.assertEqual(count, 1)

    def test_a_u_shape_is_one_component(self):
        labels, count = blobs.label(grid(["#.#",
                                          "#.#",
                                          "###"]))
        self.assertEqual(count, 1)

    def test_labels_are_numbered_from_one_with_no_holes(self):
        labels, count = blobs.label(grid(["#.#.#"]))
        self.assertEqual(count, 3)
        self.assertEqual(sorted(set(labels.flatten().tolist())),
                         [0, 1, 2, 3])


class TestBoxes(unittest.TestCase):
    def test_a_box_is_x0_y0_width_height_area(self):
        mask = grid(["....",
                     ".##.",
                     ".##.",
                     "...."])
        labels, count = blobs.label(mask)
        self.assertEqual(blobs.boxes(labels, count), [(1, 1, 2, 2, 4)])

    def test_area_counts_pixels_not_the_box(self):
        """An L is 3 pixels inside a 2x2 box -- the census counts ink."""
        mask = grid(["#.",
                     "##"])
        labels, count = blobs.label(mask)
        self.assertEqual(blobs.boxes(labels, count), [(0, 0, 2, 2, 3)])

    def test_boxes_come_back_in_label_order(self):
        mask = grid(["#..#"])
        labels, count = blobs.label(mask)
        first, second = blobs.boxes(labels, count)
        self.assertLess(first[0], second[0])


class TestDeepestBottom(unittest.TestCase):
    """The measurement the descender question actually needs.

    Two mistakes cost a whole afternoon and had to be caught by readers:
    counting a stray anti-aliasing speck as a descender, and counting the
    Chinese row's ascenders as the formosan row's descenders. Both are
    ruled out here rather than in each reader's own copy.
    """

    def test_it_ignores_a_component_starting_below_the_slot(self):
        """A Chinese glyph's top is not a formosan descender."""
        mask = grid(["..#..",     # y0 -- inside the slot
                     "..#..",
                     ".....",
                     "..#..",     # y3 -- below it: another row's glyph
                     "..#.."])
        got = blobs.deepest_bottom(mask, top=0, floor=3, min_area=1)
        self.assertEqual(got, 1)

    def test_it_ignores_a_one_pixel_speck(self):
        mask = grid(["..#..",
                     "..#..",
                     ".....",
                     "....#"])     # a lone speck, area 1
        got = blobs.deepest_bottom(mask, top=0, floor=4, min_area=2)
        self.assertEqual(got, 1)

    def test_it_keeps_a_thin_tall_stroke(self):
        """Filtering on width would drop a real w=1 stem."""
        mask = grid(["..#..",
                     "..#..",
                     "....#",
                     "....#",
                     "....#"])
        got = blobs.deepest_bottom(mask, top=0, floor=5, min_area=2)
        self.assertEqual(got, 4)

    def test_it_reports_none_when_nothing_starts_in_the_slot(self):
        mask = grid([".....",
                     ".....",
                     "..#.."])
        self.assertIsNone(
            blobs.deepest_bottom(mask, top=0, floor=2, min_area=1))


if __name__ == "__main__":
    unittest.main()
