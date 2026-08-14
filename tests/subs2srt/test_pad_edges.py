"""The 0.5s edge-padding rule from CLAUDE.md, as implemented in assemble."""
import unittest

from scripts.subs2srt import assemble


class TestPadEdges(unittest.TestCase):
    def test_isolated_entry_gets_half_a_second_each_side(self):
        got = assemble.pad_edges([(5.0, 8.0, "獨句")], duration=100.0)
        self.assertEqual(got, [(4.5, 8.5, "獨句")])

    def test_crowded_pair_meets_at_the_gap_midpoint(self):
        # the CLAUDE.md example: 1.0-2.0 and 2.2-3.2 -> 1.0-2.1 and 2.1-3.2
        got = assemble.pad_edges([(1.0, 2.0, "甲"), (2.2, 3.2, "乙")],
                                 duration=100.0)
        self.assertAlmostEqual(got[0][1], 2.1)
        self.assertAlmostEqual(got[1][0], 2.1)
        # touching exactly is allowed; overlapping is not
        self.assertLessEqual(got[0][1], got[1][0])
        # the outer edges still get the full padding
        self.assertAlmostEqual(got[0][0], 0.5)
        self.assertAlmostEqual(got[1][1], 3.7)

    def test_wide_gap_gives_both_sides_full_padding(self):
        got = assemble.pad_edges([(1.0, 2.0, "甲"), (5.0, 6.0, "乙")],
                                 duration=100.0)
        self.assertAlmostEqual(got[0][1], 2.5)
        self.assertAlmostEqual(got[1][0], 4.5)

    def test_start_never_goes_negative(self):
        got = assemble.pad_edges([(0.2, 1.0, "開頭")], duration=100.0)
        self.assertEqual(got[0][0], 0.0)

    def test_end_never_exceeds_the_video(self):
        got = assemble.pad_edges([(99.0, 99.8, "結尾")], duration=100.0)
        self.assertEqual(got[0][1], 100.0)

    def test_touching_entries_stay_touching(self):
        got = assemble.pad_edges([(1.0, 2.0, "甲"), (2.0, 3.0, "乙")],
                                 duration=100.0)
        self.assertAlmostEqual(got[0][1], 2.0)
        self.assertAlmostEqual(got[1][0], 2.0)

    def test_without_duration_the_tail_is_still_padded(self):
        got = assemble.pad_edges([(5.0, 8.0, "x")])
        self.assertEqual(got, [(4.5, 8.5, "x")])

    def test_empty_input(self):
        self.assertEqual(assemble.pad_edges([]), [])


if __name__ == "__main__":
    unittest.main()
