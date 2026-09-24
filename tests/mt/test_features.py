"""features: the per-group numbers a filter can threshold on.

Everything here must be computable on the news corpus, where there is
no gold -- so only the two ASR rows, the subtitle text, the times and
the dictionary go in."""
import unittest

from scripts.mt import features


def seg(index, start, end, formosan, han):
    return {"index": index, "start": start, "end": end,
            "formosan": formosan, "han": han}


def ent(index, start, end, han):
    return {"index": index, "true_start": start, "true_end": end,
            "han": han, "formosan": "", "cues": [index]}


SEGS = [seg(0, 0.0, 10.0, "o kayakay no kiwit a niyaroʼ", "奇美部落的橋"),
        seg(1, 10.0, 20.0, "ʼa ʼa ʼa ʼa ʼa ʼa ʼa ʼa", "一、二、三、四、五、六")]
ENTS = [ent(0, 1.0, 4.0, "花蓮原山奇美橋"),
        ent(1, 4.0, 8.0, "是奇美部落的交通要道"),
        ent(2, 12.0, 15.0, "自由時報")]
LEXICON = {"kayakay", "kiwit", "niyaro'"}


class TestGroupFeatures(unittest.TestCase):
    def test_similarity_between_mt_and_subtitle_text(self):
        got = features.group_features({"segs": [0], "entries": [0, 1]},
                                      SEGS, ENTS, LEXICON)
        # recall-weighted: the MT is much shorter than the two subtitles,
        # so the score is low but clearly not zero
        self.assertGreater(got["chrf"], 0.1)
        self.assertGreater(got["ngram_f1"], 0.0)
        self.assertEqual(got["n_segs"], 1)
        self.assertEqual(got["n_entries"], 2)

    def test_lexicon_rate_counts_only_words_in_the_dictionary(self):
        got = features.group_features({"segs": [0], "entries": [0, 1]},
                                      SEGS, ENTS, LEXICON)
        # kayakay, kiwit, niyaroʼ hit; o, no, a do not
        self.assertAlmostEqual(got["lexicon_rate"], 0.5)

    def test_hallucinated_group_is_flagged(self):
        got = features.group_features({"segs": [1], "entries": [2]},
                                      SEGS, ENTS, LEXICON)
        self.assertTrue(got["suspicious"])
        self.assertEqual(got["chrf"], 0.0)

    def test_time_coverage_both_ways(self):
        got = features.group_features({"segs": [0], "entries": [0, 1]},
                                      SEGS, ENTS, LEXICON)
        # entries cover 7 of the segment's 10 s; the segment covers all
        # 7 s of the entries
        self.assertAlmostEqual(got["cover_seg"], 0.7)
        self.assertAlmostEqual(got["cover_entries"], 1.0)

    def test_length_ratio_words_per_han_char(self):
        got = features.group_features({"segs": [0], "entries": [0, 1]},
                                      SEGS, ENTS, LEXICON)
        self.assertAlmostEqual(got["asr_words"], 6)
        self.assertAlmostEqual(got["han_chars"], 17)
        self.assertAlmostEqual(got["len_ratio"], 6 / 17)

    def test_speech_rate_and_compression(self):
        got = features.group_features({"segs": [0], "entries": [0, 1]},
                                      SEGS, ENTS, LEXICON)
        # 6 words over a 10 s segment
        self.assertAlmostEqual(got["wps"], 0.6)
        # ordinary text hardly compresses; a loop compresses a lot
        self.assertLess(got["compression"], 1.6)
        loop = features.group_features({"segs": [1], "entries": [2]},
                                       SEGS, ENTS, LEXICON)
        self.assertGreater(loop["compression"], 2.0)

    def test_all_dictionaries_name_the_language_actually_spoken(self):
        lexicons = {"阿美": LEXICON,
                    "泰雅": {"tayal", "qani", "kawas", "miru", "nqrqes"}}
        atayal = [seg(0, 0.0, 10.0, "miru squ zega nqrqes tayal qani kawas",
                      "畫人物")]
        got = features.group_features({"segs": [0], "entries": [0]},
                                      atayal, ENTS, LEXICON,
                                      lexicons=lexicons, tribe="阿美")
        self.assertEqual(got["best_tribe"], "泰雅")
        self.assertTrue(got["foreign"])
        self.assertTrue(got["suspicious"])

    def test_hallucinated_is_only_loops_numbers_and_blanks(self):
        # a real sentence with few dictionary words is 命中率 business,
        # judged against the tribe's own baseline -- not a hallucination
        sparse = [seg(0, 0.0, 10.0, "tada ko tatiih a romi'ad i tini",
                      "奇美部落的橋")]
        got = features.group_features({"segs": [0], "entries": [0]},
                                      sparse, ENTS, LEXICON)
        self.assertFalse(got["hallucinated"])
        loop = features.group_features({"segs": [1], "entries": [2]},
                                       SEGS, ENTS, LEXICON)
        self.assertTrue(loop["hallucinated"])


if __name__ == "__main__":
    unittest.main()
