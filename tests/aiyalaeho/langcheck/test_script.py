"""字元分類：族語列內底有偌濟拉丁字母、偌濟漢字、偌濟注音。

這是四級標籤前三个ê全部依據，所以伊會錯ê所在攏是「按算 a-z 就是
拉丁字母」這款：語料內底有 `ʉ`（737 擺）、`ē`、`è`，攏是拉丁字母
毋過無佇 a-z；注音 `ㄅㄆㄇㄈ` 有 4 條族語列出現過，是第三種書寫
系統，毋是漢字。
"""
import unittest

from scripts.aiyalaeho.langcheck import script


class TestLatinLetters(unittest.TestCase):
    def test_plain_ascii_letters_count(self):
        self.assertEqual(script.counts("kako").latin, 4)

    def test_letters_with_diacritics_are_still_latin(self):
        # 用 'a' <= c <= 'z' 分類ê話，這三个會落厝——`ʉ` 佇語料內底
        # 出現 737 擺，規列會去予判做「無拉丁字母」，煞變做華語。
        for word in ("ʉ", "ē", "è"):
            got = script.counts(word)
            self.assertEqual(got.latin, 1, word)
            self.assertEqual(got.han, 0, word)

    def test_uppercase_counts_too(self):
        self.assertEqual(script.counts("Sera").latin, 4)


class TestHan(unittest.TestCase):
    def test_han_ideographs_count(self):
        self.assertEqual(script.counts("投資").han, 2)

    def test_bopomofo_is_not_han(self):
        # 122 布農、093 阿美攏有「micodad to ㄅㄆㄇㄈ」這款列。注音
        # 若算做漢字，規列就變做「夾華語」，其實彼是講著注音符號。
        got = script.counts("micodad to ㄅㄆㄇㄈ")
        self.assertEqual(got.han, 0)
        self.assertEqual(got.bopomofo, 4)


class TestWhatDoesNotCount(unittest.TestCase):
    def test_digits_and_punctuation_count_as_neither(self):
        got = script.counts("1000 ... '^: -")
        self.assertEqual(got.latin, 0)
        self.assertEqual(got.han, 0)
        self.assertEqual(got.bopomofo, 0)

    def test_a_row_of_only_digits_is_not_han(self):
        # 「5 to ko nipalomaan niyam」愛照拉丁字母判，數字免插伊。
        got = script.counts("5 to ko nipalomaan niyam")
        self.assertGreater(got.latin, 0)
        self.assertEqual(got.han, 0)


class TestMixedRows(unittest.TestCase):
    def test_a_code_switched_row_has_both(self):
        # 082 第 49 條。有拉丁嘛有漢字 → 夾華語，毋是華語。
        got = script.counts("1000 kamini ni 投資")
        self.assertGreater(got.latin, 0)
        self.assertGreater(got.han, 0)

    def test_a_swapped_row_has_han_only(self):
        # 114 布農 cue 714：兩逝激反去，族語列規列漢字。
        got = script.counts("母親的語言 母語")
        self.assertEqual(got.latin, 0)
        self.assertGreater(got.han, 0)

    def test_a_plain_formosan_row_has_no_han(self):
        got = script.counts("Tangasa to matini maafo to")
        self.assertGreater(got.latin, 0)
        self.assertEqual(got.han, 0)


class TestEmpty(unittest.TestCase):
    def test_nothing_at_all(self):
        got = script.counts("")
        self.assertEqual((got.latin, got.han, got.bopomofo), (0, 0, 0))


class TestWords(unittest.TestCase):
    """切詞。詞庫佮字幕愛用仝一支——無仝ê切法會hőng看做「辭典涵蓋
    無夠」，其實是尺無仝。"""

    def test_han_and_digits_separate_words_and_do_not_enter(self):
        self.assertEqual(script.words("1000 kamini ni 投資"), ["kamini"])

    def test_orthographic_marks_stay_inside_the_word(self):
        # ' 是喉塞音、^ 是長音，攏是詞ê一部份，毋是分界。
        self.assertEqual(script.words("nga'ay ho^"), ["nga'ay", "ho^"])

    def test_apostrophes_are_normalised_to_ascii(self):
        for text in ("ngaʼay", "nga’ay", "nga'ay"):
            self.assertEqual(script.words(text), ["nga'ay"], text)

    def test_short_words_are_dropped(self):
        self.assertEqual(script.words("to ko nipalomaan"), ["nipalomaan"])

    def test_case_is_folded(self):
        self.assertEqual(script.words("Ci Sera kako"), ["sera", "kako"])

    def test_marks_alone_are_not_a_word(self):
        self.assertEqual(script.words("--- ^^^"), [])


if __name__ == "__main__":
    unittest.main()
