"""overlap: grouping sapolita segments with subtitle entries by time.

Each subtitle goes to the one segment it overlaps most. The rule it
replaced -- anything that overlaps anything is one group -- was measured
on the real corpus (656 episodes): it chained 31,249 groups across more
than one segment, the longest 495 s, because a subtitle that spills
0.1 s into the next VAD segment welds the two paragraphs together."""
import unittest

from scripts.errors import PipelineError
from scripts.mt import overlap


def seg(index, start, end):
    return {"index": index, "start": start, "end": end,
            "formosan": "w%d" % index, "han": ""}


def ent(index, start, end):
    return {"index": index, "true_start": start, "true_end": end,
            "han": "c%d" % index, "formosan": "", "cues": [index]}


class TestLinks(unittest.TestCase):
    def test_link_carries_overlap_and_both_fractions(self):
        found = overlap.links([seg(0, 0.0, 10.0)], [ent(0, 8.0, 12.0)])
        self.assertEqual(len(found), 1)
        link = found[0]
        self.assertEqual((link["seg"], link["entry"]), (0, 0))
        self.assertAlmostEqual(link["seconds"], 2.0)
        self.assertAlmostEqual(link["frac_entry"], 0.5)
        self.assertAlmostEqual(link["frac_seg"], 0.2)

    def test_touching_is_not_overlapping(self):
        found = overlap.links([seg(0, 0.0, 10.0)], [ent(0, 10.0, 12.0)])
        self.assertEqual(found, [])

    def test_min_frac_drops_the_sliver(self):
        # 0.1 s of a 4 s subtitle: 2.5% -- below a 10% floor
        segs = [seg(0, 0.0, 10.0), seg(1, 10.0, 20.0)]
        ents = [ent(0, 9.9, 13.9)]
        both = overlap.links(segs, ents)
        self.assertEqual([link["seg"] for link in both], [0, 1])
        floored = overlap.links(segs, ents, min_frac=0.1)
        self.assertEqual([link["seg"] for link in floored], [1])


class TestMaxOverlap(unittest.TestCase):
    def test_entry_goes_to_the_larger_overlap_only(self):
        segs = [seg(0, 0.0, 10.0), seg(1, 10.0, 20.0)]
        ents = [ent(0, 9.0, 13.0)]   # 1 s in seg 0, 3 s in seg 1
        groups, lone_s, _ = overlap.max_overlap_groups(segs, ents)
        self.assertEqual([g["segs"] for g in groups], [[1]])
        self.assertEqual([g["entries"] for g in groups], [[0]])
        self.assertEqual(lone_s, [0])

    def test_tie_goes_to_the_earlier_segment(self):
        segs = [seg(0, 0.0, 10.0), seg(1, 10.0, 20.0)]
        ents = [ent(0, 8.0, 12.0)]
        groups, lone_s, _ = overlap.max_overlap_groups(segs, ents)
        self.assertEqual([g["segs"] for g in groups], [[0]])
        self.assertEqual(lone_s, [1])

    def test_true_straddler_merges_the_two_segments(self):
        # 40% / 60%: the subtitle genuinely spans both VAD segments
        segs = [seg(0, 0.0, 10.0), seg(1, 10.0, 20.0)]
        ents = [ent(0, 8.0, 13.0), ent(1, 15.0, 18.0)]
        groups, _, _ = overlap.max_overlap_groups(segs, ents,
                                                  straddle_frac=0.3)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["segs"], [0, 1])
        self.assertEqual(groups[0]["entries"], [0, 1])

    def test_share_exactly_at_the_threshold_merges(self):
        # 1.2 s of a 4 s subtitle is exactly 30%
        segs = [seg(0, 0.0, 10.0), seg(1, 10.0, 20.0)]
        ents = [ent(0, 8.8, 12.8)]
        groups, _, _ = overlap.max_overlap_groups(segs, ents,
                                                  straddle_frac=0.3)
        self.assertEqual([g["segs"] for g in groups], [[0, 1]])

    def test_sliver_does_not_merge(self):
        segs = [seg(0, 0.0, 10.0), seg(1, 10.0, 20.0)]
        ents = [ent(0, 9.9, 13.9)]
        groups, lone_s, _ = overlap.max_overlap_groups(segs, ents,
                                                       straddle_frac=0.3)
        self.assertEqual([g["segs"] for g in groups], [[1]])
        self.assertEqual(lone_s, [0])

    def test_groups_keep_time_order(self):
        segs = [seg(0, 0.0, 10.0), seg(1, 10.0, 20.0), seg(2, 20.0, 30.0)]
        ents = [ent(0, 1.0, 3.0), ent(1, 11.0, 13.0), ent(2, 21.0, 23.0)]
        groups, _, _ = overlap.max_overlap_groups(segs, ents)
        self.assertEqual([g["segs"] for g in groups], [[0], [1], [2]])


class TestHoles(unittest.TestCase):
    """拉阿魯哇 20210103_003 晨間: a 13.2 s subtitle covers segments
    184-188; 185-187 are about 1 s each, under 10% of it, so no entry
    picks them -- yet they sit inside the group's time (133 episodes:
    91 groups, 123 segments)."""

    def setUp(self):
        self.segs = [seg(0, 0.0, 4.0), seg(1, 5.0, 6.0), seg(2, 7.0, 8.0),
                     seg(3, 9.0, 10.0), seg(4, 11.0, 14.0),
                     seg(5, 30.0, 31.0), seg(6, 40.0, 44.0)]
        # the 15 s subtitle holds 13% of itself in seg 0 and 20% in seg 4,
        # so it fuses them; segs 1-3 get 1 s each (7%), below 10%
        self.ents = [ent(0, 0.5, 1.9), ent(1, 2.0, 17.0),
                     ent(2, 40.5, 43.5)]

    def groups(self):
        return overlap.max_overlap_groups(self.segs, self.ents,
                                          straddle_frac=0.1)

    def test_segments_between_the_first_and_last_are_filled_in(self):
        groups, _, _ = self.groups()
        self.assertEqual(groups[0]["segs"], [0, 1, 2, 3, 4])

    def test_filled_segments_leave_the_lonely_list(self):
        _, lone_s, _ = self.groups()
        self.assertEqual(lone_s, [5])

    def test_a_lonely_segment_outside_any_group_stays_out(self):
        groups, _, _ = self.groups()
        self.assertEqual([g["segs"] for g in groups], [[0, 1, 2, 3, 4], [6]])


class TestTrueBoundaries(unittest.TestCase):
    def test_a_subtitle_in_the_gap_is_judged_on_the_true_edges(self):
        # padded 0.5 s each, the two segments would meet at 10.4 and the
        # subtitle would reach into the first; on true edges it does not
        segs = [seg(0, 0.0, 10.0), seg(1, 10.8, 20.0)]
        ents = [ent(0, 10.1, 12.0)]
        groups, lone_s, _ = overlap.max_overlap_groups(segs, ents,
                                                       straddle_frac=0.1)
        self.assertEqual([g["segs"] for g in groups], [[1]])
        self.assertEqual(lone_s, [0])


class TestSpan(unittest.TestCase):
    def test_span_is_the_speech_not_the_subtitles(self):
        # 20210224_055 撒奇萊雅: 「對於醫療能有更多的選擇」 hangs 27.6 s over
        # the music and starts 5 s before the speech it was given to
        segs = [seg(0, 1719.914, 1747.302)]
        ents = [ent(0, 1714.78, 1742.4)]
        groups, _, _ = overlap.max_overlap_groups(segs, ents)
        self.assertEqual(groups[0]["entries"], [0])
        self.assertEqual(overlap.span(groups[0], segs), (1719.914, 1747.302))

    def test_a_spilling_subtitle_no_longer_makes_neighbours_overlap(self):
        segs = [seg(0, 0.0, 10.0), seg(1, 10.3, 20.0)]
        ents = [ent(0, 6.0, 10.6), ent(1, 12.0, 15.0)]   # 0 spills 0.3 s
        groups, _, _ = overlap.max_overlap_groups(segs, ents,
                                                  straddle_frac=0.1)
        first = overlap.span(groups[0], segs)
        second = overlap.span(groups[1], segs)
        self.assertLessEqual(first[1], second[0])

    def test_touching_speech_gives_touching_spans(self):
        segs = [seg(0, 0.0, 10.0), seg(1, 10.0, 20.0)]
        ents = [ent(0, 1.0, 9.0), ent(1, 11.0, 19.0)]
        groups, _, _ = overlap.max_overlap_groups(segs, ents)
        self.assertEqual(overlap.span(groups[0], segs)[1],
                         overlap.span(groups[1], segs)[0])


def one(index, start, end):
    """A group of one segment, `index`, with one subtitle."""
    return {"segs": [index], "entries": [index]}


class TestPaddedSpans(unittest.TestCase):
    """The CSV's time: the true speech padded 0.5 s a side, every VAD
    segment of the episode a neighbour (CLAUDE.md, SRT 產出規定)."""

    def test_far_apart_groups_each_get_half_a_second(self):
        segs = [seg(0, 30.0, 40.0)]
        self.assertEqual(overlap.padded_spans([one(0, 30, 40)], segs, 100.0),
                         [(29.5, 40.5)])

    def test_a_dropped_group_still_limits_the_padding(self):
        # the caller passes every group, dropped ones too: 10.0 / 10.4
        segs = [seg(0, 5.0, 10.0), seg(1, 10.4, 15.0)]
        spans = overlap.padded_spans([one(0, 5, 10), one(1, 10.4, 15)],
                                     segs, 100.0)
        self.assertAlmostEqual(spans[0][1], 10.2)
        self.assertAlmostEqual(spans[1][0], 10.2)

    def test_a_lonely_segment_limits_the_padding(self):
        # 1,258 lonely segments in 133 episodes; 244 kept edges would
        # pad into one if only the groups counted
        segs = [seg(0, 15.0, 19.8), seg(1, 20.0, 25.0)]
        spans = overlap.padded_spans([one(1, 20, 25)], segs, 100.0)
        self.assertAlmostEqual(spans[0][0], 19.9)

    def test_touching_speech_gets_no_padding_between(self):
        segs = [seg(0, 20.0, 30.0), seg(1, 30.0, 40.0)]
        spans = overlap.padded_spans([one(0, 20, 30), one(1, 30, 40)],
                                     segs, 100.0)
        self.assertEqual(spans[0][1], 30.0)
        self.assertEqual(spans[1][0], 30.0)

    def test_clamped_to_zero_and_to_the_audio_length(self):
        segs = [seg(0, 0.2, 5.0), seg(1, 90.0, 99.9)]
        spans = overlap.padded_spans([one(0, 0.2, 5), one(1, 90, 99.9)],
                                     segs, 100.0)
        self.assertEqual(spans[0][0], 0.0)
        self.assertEqual(spans[1][1], 100.0)

    def test_a_group_spanning_several_segments_pads_its_outer_edges(self):
        segs = [seg(0, 10.0, 12.0), seg(1, 12.5, 14.0), seg(2, 30.0, 31.0)]
        group = {"segs": [0, 1], "entries": [0]}
        spans = overlap.padded_spans([group], segs, 100.0)
        self.assertEqual(spans, [(9.5, 14.5)])

    def test_overlapping_spans_are_refused_not_stitched(self):
        # the old spans did overlap; padding them would hide that
        segs = [seg(0, 0.0, 10.0), seg(1, 9.0, 20.0)]
        with self.assertRaises(PipelineError):
            overlap.padded_spans([one(0, 0, 10), one(1, 9, 20)], segs, 100.0)


if __name__ == "__main__":
    unittest.main()
