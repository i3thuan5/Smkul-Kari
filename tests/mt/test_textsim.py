"""textsim: the similarity scores the alignment and the filters use.

Chinese: character n-grams over 漢字／數字／拉丁 only -- the subtitle
writes 「2000晚間新聞」 and the MT writes 「2000 晚間新聞。」, and
punctuation or spacing must not count against them.
Formosan: apostrophes come in three shapes (ASCII, U+02BC, U+2019) and
the ASR lower-cases nothing, so word matching normalises both."""
import unittest

from scripts.mt import textsim


class TestHan(unittest.TestCase):
    def test_punctuation_and_space_are_ignored(self):
        self.assertEqual(textsim.han_chars("大家好，2000 晚間新聞。"),
                         "大家好2000晚間新聞")

    def test_identical_is_one(self):
        self.assertAlmostEqual(textsim.ngram_f1("奇美部落", "奇美部落"), 1.0)

    def test_disjoint_is_zero(self):
        self.assertAlmostEqual(textsim.ngram_f1("奇美部落", "花蓮縣府"), 0.0)

    def test_partial_overlap_between(self):
        score = textsim.ngram_f1("奇美部落的橋", "奇美橋")
        self.assertGreater(score, 0.0)
        self.assertLess(score, 1.0)

    def test_empty_side_is_zero_not_error(self):
        self.assertEqual(textsim.ngram_f1("", "奇美"), 0.0)
        self.assertEqual(textsim.ngram_f1("奇美", ""), 0.0)

    def test_chrf_identical_is_one_and_disjoint_zero(self):
        self.assertAlmostEqual(textsim.chrf("大家好", "大家好"), 1.0)
        self.assertAlmostEqual(textsim.chrf("大家好", "縣政府"), 0.0)

    def test_chrf_recall_weighted(self):
        # beta=2 weights recall: a hypothesis missing half the reference
        # scores lower than one adding half as much extra
        missing = textsim.chrf("奇美部落", "奇美部落的交通要道")
        extra = textsim.chrf("奇美部落的交通要道", "奇美部落")
        self.assertLess(missing, extra)


class TestFormosan(unittest.TestCase):
    def test_words_lowercased_and_apostrophes_normalised(self):
        self.assertEqual(textsim.formosan_words("Ngaʼay ho^ Ci Sera,"),
                         ["nga'ay", "ho", "ci", "sera"])

    def test_length_marks_dropped_on_both_sides(self):
        # gold writes 「Po:long」「ho^」, the recogniser writes polong / ho
        self.assertEqual(textsim.formosan_words("Po:long ho^"),
                         textsim.formosan_words("polong ho"))

    def test_short_function_words_are_kept(self):
        # alignment needs every token; the language check drops <3 letters
        self.assertEqual(textsim.formosan_words("o wawa no mita"),
                         ["o", "wawa", "no", "mita"])

    def test_word_similarity_tolerates_one_letter(self):
        self.assertGreaterEqual(textsim.word_similarity("salikaka",
                                                        "salikaku"), 0.8)
        self.assertLess(textsim.word_similarity("salikaka", "kalingko"),
                        0.75)

    def test_word_f1_counts_fuzzy_matches_once(self):
        score = textsim.word_f1(["salikaka", "ngaʼay", "ho"],
                                ["salikaku", "nga'ay", "ho"])
        self.assertAlmostEqual(score, 1.0)
        self.assertEqual(textsim.word_f1([], ["a"]), 0.0)


if __name__ == "__main__":
    unittest.main()
