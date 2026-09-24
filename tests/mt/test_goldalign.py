"""goldalign: the text-based truth for 開會了.

The gold subtitles carry the Formosan text of every cue, so which cues
an ASR segment really covers can be read off the words, independent of
timing. The ASR is noisy -- letters substituted, words dropped, whole
hallucinated segments -- and the truth must survive that or say it
cannot tell."""
import unittest

from scripts.mt import goldalign


def ent(index, start, end, formosan):
    return {"index": index, "true_start": start, "true_end": end,
            "formosan": formosan, "han": "", "cues": [index]}


def seg(start, end, formosan):
    return {"index": 0, "start": start, "end": end,
            "formosan": formosan, "han": ""}


ENTRIES = [
    ent(0, 0.0, 3.0, "Po:long no miki'arawaty to 'a'iyalaeho: a kamok a"),
    ent(1, 3.0, 6.0, "finawlan ina^ mama^ salikaka^ nga'ay ho^"),
    ent(2, 6.0, 7.0, "Nga'ay ho^"),
    ent(3, 7.0, 10.0, "Ci Sera kako"),
    ent(4, 10.0, 15.0, "mikeriday anini mihomong to Angcoh a demak"),
]


class TestAlignWords(unittest.TestCase):
    def test_exact_words_align_in_order(self):
        asr = ["ci", "sera", "kako"]
        gold = ["nga'ay", "ho^", "ci", "sera", "kako", "mikeriday"]
        self.assertEqual(goldalign.align_words(asr, gold), [2, 3, 4])

    def test_one_letter_error_still_aligns(self):
        asr = ["ci", "sira", "kako"]
        gold = ["nga'ay", "ho^", "ci", "sera", "kako"]
        self.assertEqual(goldalign.align_words(asr, gold), [2, 3, 4])

    def test_dropped_word_leaves_a_gap_not_a_shift(self):
        asr = ["ci", "kako"]
        gold = ["ci", "sera", "kako", "mikeriday"]
        self.assertEqual(goldalign.align_words(asr, gold), [0, 2])

    def test_hallucination_matches_nothing(self):
        asr = ["ʼa", "ʼa", "ʼa", "ʼa"]
        gold = ["ci", "sera", "kako", "mikeriday"]
        self.assertEqual(goldalign.align_words(asr, gold),
                         [None, None, None, None])


class TestGoldCues(unittest.TestCase):
    def test_segment_maps_to_the_cues_its_words_came_from(self):
        segment = seg(2.5, 9.0, "salikaka nga'ay ho nga'ay ho ci sera kako")
        truth = goldalign.gold_cues(segment, ENTRIES, window=20.0)
        self.assertEqual(sorted(truth["entries"]), [1, 2, 3])
        # cue 1 has 6 words, 3 matched; cue 3 fully matched
        self.assertEqual(truth["entries"][3], (3, 3))
        self.assertEqual(truth["entries"][1][1], 6)
        self.assertGreaterEqual(truth["match_rate"], 0.9)

    def test_time_window_limits_the_candidates(self):
        # same words also exist far away; the window keeps it local
        far = ENTRIES + [ent(9, 500.0, 503.0, "Ci Sera kako")]
        segment = seg(7.0, 10.0, "ci sera kako")
        truth = goldalign.gold_cues(segment, far, window=20.0)
        self.assertEqual(sorted(truth["entries"]), [3])

    def test_hallucinated_segment_has_low_match_rate(self):
        segment = seg(2.0, 9.0, "ʼa ʼa ʼa ʼa ʼa ʼa ʼa ʼa")
        truth = goldalign.gold_cues(segment, ENTRIES, window=20.0)
        self.assertEqual(truth["entries"], {})
        self.assertEqual(truth["match_rate"], 0.0)

    def test_entries_without_formosan_row_are_never_truth(self):
        chinese_only = ENTRIES + [ent(5, 15.0, 18.0, "")]
        segment = seg(10.0, 18.0, "mikeriday anini mihomong")
        truth = goldalign.gold_cues(segment, chinese_only, window=20.0)
        self.assertNotIn(5, truth["entries"])


if __name__ == "__main__":
    unittest.main()
