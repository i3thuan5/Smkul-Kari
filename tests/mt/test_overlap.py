"""overlap: grouping sapolita segments with subtitle entries by time.

Each subtitle goes to the one segment it overlaps most. The rule it
replaced -- anything that overlaps anything is one group -- was measured
on the real corpus (656 episodes): it chained 31,249 groups across more
than one segment, the longest 495 s, because a subtitle that spills
0.1 s into the next VAD segment welds the two paragraphs together."""
import unittest

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


class TestSpan(unittest.TestCase):
    def test_span_covers_segments_and_entries(self):
        segs = [seg(0, 5.0, 10.0)]
        ents = [ent(0, 4.0, 6.0), ent(1, 9.0, 12.0)]
        group = {"segs": [0], "entries": [0, 1]}
        self.assertEqual(overlap.span(group, segs, ents), (4.0, 12.0))


if __name__ == "__main__":
    unittest.main()
