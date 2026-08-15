"""Word -> entry projection (asr-bilingual-srt spec: 整集逐詞辨識結果
落地保存 / 跨界詞歸戶 / 辨識文字忠實輸出).

Max-overlap assignment into the true windows, ties to the earlier entry,
straddling words counted, words outside every window kept aside -- and
the word text itself never altered by any of it.
"""
import unittest

from scripts.asrmt import project
from tests.asrmt import fixtures


def two_entries():
    # [0,2) and [2,4), back to back like the real corpus
    return fixtures.entries_grid(2)


class TestAssignment(unittest.TestCase):
    def test_word_inside_one_window_lands_there(self):
        words = [fixtures.word("roma", 0.5, 1.0)]
        entries, unassigned = project.project(words, two_entries())
        self.assertEqual(entries[0]["word_i"], [0])
        self.assertEqual(entries[1]["word_i"], [])
        self.assertEqual(unassigned, [])

    def test_straddler_goes_to_the_larger_overlap(self):
        # 1.9-2.3: 0.1s in entry 1, 0.3s in entry 2
        words = [fixtures.word("mafanaʼ", 1.9, 2.3)]
        entries, _ = project.project(words, two_entries())
        self.assertEqual(entries[0]["word_i"], [])
        self.assertEqual(entries[1]["word_i"], [0])
        self.assertEqual(entries[1]["straddle"], 1)

    def test_tie_goes_to_the_earlier_entry(self):
        # 1.8-2.2: exactly 0.2s each side
        words = [fixtures.word("ato", 1.8, 2.2)]
        entries, _ = project.project(words, two_entries())
        self.assertEqual(entries[0]["word_i"], [0])
        self.assertEqual(entries[0]["straddle"], 1)

    def test_word_in_a_gap_is_kept_aside_not_dropped(self):
        gapped = [fixtures.entry(1, 0.0, 2.0), fixtures.entry(2, 10.0, 12.0)]
        words = [fixtures.word("radiw", 5.0, 5.5)]
        entries, unassigned = project.project(words, gapped)
        self.assertEqual(entries[0]["word_i"], [])
        self.assertEqual(entries[1]["word_i"], [])
        self.assertEqual(unassigned, [0])

    def test_fully_inside_word_is_not_a_straddler(self):
        words = [fixtures.word("kako", 0.2, 0.8)]
        entries, _ = project.project(words, two_entries())
        self.assertEqual(entries[0]["straddle"], 0)


class TestFormosanLine(unittest.TestCase):
    def test_line_is_words_in_time_order_joined_by_spaces(self):
        words = fixtures.words_evenly("mikeriday anini mihomong", 0.0, 1.8)
        entries, _ = project.project(words, two_entries())
        self.assertEqual(entries[0]["formosan"], "mikeriday anini mihomong")

    def test_word_text_survives_untouched(self):
        # diacritics, apostrophes, casing: presentation clean-ups are the
        # service layer's sin, not ours (spec: 辨識文字忠實輸出)
        words = [fixtures.word("Angcoh", 0.1, 0.5),
                 fixtures.word("ina⌃", 0.6, 0.9),
                 fixtures.word("mafanaʼ", 1.0, 1.4)]
        entries, _ = project.project(words, two_entries())
        self.assertEqual(entries[0]["formosan"], "Angcoh ina⌃ mafanaʼ")


if __name__ == "__main__":
    unittest.main()
