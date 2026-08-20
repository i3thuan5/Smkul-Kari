"""detect: the two independent signals and the anchors.

Content is measured in Chinese with character bigram F1 (word-order
immune, forgiving of small rewrites); time is measured in Formosan with
character LCS after stripping segmentation marks -- the two engines'
tokenisation differs, so words are never the unit. Number and loanword
anchors need no translation at all.
"""
import unittest

from scripts.asrmt.align import detect
from tests.asrmt import fixtures


class TestContentScore(unittest.TestCase):
    def test_small_rewrites_keep_a_high_score(self):
        # 同義改寫仍得高分 scenario
        high = detect.char_bigram_f1("看到熊3件事不要做", "3件事情不要做")
        low = detect.char_bigram_f1("看到熊3件事不要做", "氣象預報明天下雨")
        self.assertGreater(high, 0.5)
        self.assertLess(low, 0.1)
        self.assertGreater(high, low)

    def test_word_order_changes_survive(self):
        a = detect.char_bigram_f1("我在教會牧會", "牧會我在教會")
        self.assertGreater(a, 0.6)


class TestLcs(unittest.TestCase):
    def test_segmentation_marks_do_not_matter(self):
        # 斷詞差異不影響偏移量測 scenario
        self.assertEqual(
            detect.lcs_ratio("mi-牧會 kako", "mi牧會kako"), 1.0)

    def test_case_is_folded(self):
        self.assertEqual(detect.lcs_ratio("Angcoh", "angcoh"), 1.0)

    def test_different_text_scores_low(self):
        self.assertLess(detect.lcs_ratio("mikeriday", "tayni kako"), 0.5)


class TestDeltaScan(unittest.TestCase):
    def test_systematic_lag_shows_up_as_the_best_delta(self):
        # subtitle window [10,12] but the matching speech sits at +1s
        entry = fixtures.entry(1, 10.0, 12.0)
        words = fixtures.words_evenly("mikeriday kako anini", 11.0, 13.0)
        best, _ = detect.delta_scan(entry, "mikeriday kako anini",
                                    words, span=3.0, step=0.5)
        self.assertEqual(best, 1.0)

    def test_aligned_speech_peaks_at_zero(self):
        entry = fixtures.entry(1, 10.0, 12.0)
        words = fixtures.words_evenly("mikeriday kako anini", 10.0, 12.0)
        best, _ = detect.delta_scan(entry, "mikeriday kako anini",
                                    words, span=3.0, step=0.5)
        self.assertEqual(best, 0.0)


class TestRollingMedian(unittest.TestCase):
    def test_a_lone_spike_is_smoothed_away(self):
        got = detect.rolling_median([0.0, 0.0, 3.0, 0.0, 0.0], window=3)
        self.assertEqual(got[2], 0.0)

    def test_a_sustained_shift_survives(self):
        got = detect.rolling_median([0.0, 1.0, 1.0, 1.0, 0.0], window=3)
        self.assertEqual(got[2], 1.0)


class TestAnchors(unittest.TestCase):
    def test_arabic_and_chinese_numbers_are_extracted(self):
        got = detect.find_numbers("上漲3成，約一百二十人，30日截止")
        self.assertIn(3, got)
        self.assertIn(120, got)
        self.assertIn(30, got)

    def test_numeral_anchor_found_in_the_word_stream(self):
        numerals = {"3": ["tolo"], "120": []}
        words = [fixtures.word("tolo", 42.0, 42.5)]
        hits = detect.match_anchors([3, 120], words, numerals)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["value"], 3)
        self.assertEqual(hits[0]["time"], 42.0)

    def test_loanword_matches_within_one_edit(self):
        # 借詞專名以音近命中 scenario
        table = {"台北": ["taypak"]}
        words = [fixtures.word("taypag", 7.0, 7.6)]
        hits = detect.match_loanwords("台北的公司", words, table)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["name"], "台北")

    def test_absent_loanword_reports_nothing(self):
        table = {"花蓮": ["kalingko"]}
        words = [fixtures.word("mikeriday", 1.0, 1.5)]
        self.assertEqual(
            detect.match_loanwords("花蓮的新聞", words, table), [])


if __name__ == "__main__":
    unittest.main()
