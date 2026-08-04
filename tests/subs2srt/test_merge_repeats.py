"""Fusing repeated cues and trimming overlaps before rendering."""
import unittest

from scripts.subs2srt import cli as subs2srt


class TestMergeRepeats(unittest.TestCase):
    def test_identical_neighbours_fuse(self):
        got = subs2srt.merge_repeats(
            [(0.0, 1.0, "耆老表示"), (1.2, 2.4, "耆老表示")], 1.0)
        self.assertEqual(got, [(0.0, 2.4, "耆老表示")])

    def test_far_apart_repeats_stay_separate(self):
        entries = [(0.0, 1.0, "a"), (30.0, 31.0, "a")]
        self.assertEqual(subs2srt.merge_repeats(entries, 1.0), entries)

    def test_different_text_is_untouched(self):
        entries = [(0.0, 1.0, "a"), (1.1, 2.0, "b")]
        self.assertEqual(subs2srt.merge_repeats(entries, 1.0), entries)

    def test_three_in_a_row_fuse_into_one(self):
        got = subs2srt.merge_repeats(
            [(0.0, 1.0, "x"), (1.1, 2.0, "x"), (2.1, 3.0, "x")], 1.0)
        self.assertEqual(got, [(0.0, 3.0, "x")])

    def test_empty_input(self):
        self.assertEqual(subs2srt.merge_repeats([], 1.0), [])


class TestGapRules(unittest.TestCase):
    def test_overlap_is_trimmed(self):
        fixed = subs2srt.apply_gap_rules(
            [(0.0, 2.0, "a"), (1.9, 3.0, "b")], 0.04)
        self.assertLessEqual(fixed[0][1], 1.9 - 0.04 + 1e-9)

    def test_non_overlapping_is_untouched(self):
        entries = [(0.0, 1.0, "a"), (2.0, 3.0, "b")]
        self.assertEqual(subs2srt.apply_gap_rules(entries, 0.04), entries)


if __name__ == "__main__":
    unittest.main()
