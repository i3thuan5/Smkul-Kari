"""辭典 xlsx → 詞庫 txt。

會出代誌ê所在有三个，攏是量過ê：

  欄位靠位置    真檔 16 欄，欄序若換一擺規份就歪去。愛靠表頭名。
  彎撇無正規化  辭典寫 `ngaʼay`（U+02BC），字幕寫 `nga'ay`（ASCII）。
                無正規化ê話，喉塞音彼款詞逐个攏對袂著。
  干焦收單字    068 ê涵蓋率會對 81% 落到 75%——例句原文內底彼款
                變化形才是實際講出來ê。
"""
import os
import tempfile
import unittest

from scripts.aiyalaeho.langcheck import dictionary
from tests.aiyalaeho.langcheck import fixtures


class DictionaryCase(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="aiya-dict-")
        self.path = os.path.join(self.folder, "d.xlsx")

    def write(self, rows, header=None):
        table = [header or fixtures.DICT_HEADER]
        table.extend(rows)
        return fixtures.write_xlsx(self.path, table)


class TestColumnsAreFoundByName(DictionaryCase):
    def test_the_three_columns_are_collected(self):
        self.write([fixtures.dict_row(word="koleto", stem="leto",
                                      sentence="maolah kako")])
        got = dictionary.words_of(self.path)
        self.assertEqual(got, {"koleto", "leto", "maolah", "kako"})

    def test_a_shuffled_column_order_still_works(self):
        # 欄位靠位置取ê話，這條會規份歪去。
        header = list(reversed(fixtures.DICT_HEADER))
        row = list(reversed(fixtures.dict_row(word="koleto",
                                              sentence="maolah kako")))
        self.write([row], header=header)
        self.assertEqual(dictionary.words_of(self.path),
                         {"koleto", "maolah", "kako"})

    def test_a_missing_column_is_named_not_guessed(self):
        header = list(fixtures.DICT_HEADER)
        header[header.index("例句原文")] = "例句"
        self.write([["x"] * len(header)], header=header)
        with self.assertRaises(Exception) as caught:
            dictionary.words_of(self.path)
        self.assertIn("例句原文", str(caught.exception))


class TestApostrophes(DictionaryCase):
    def test_the_modifier_letter_apostrophe_is_normalised(self):
        # 辭典用 U+02BC，字幕用 ASCII。無正規化ê話喉塞音彼款詞
        # 對袂著，而且是規類詞攏對袂著，毋是一兩个。
        self.write([fixtures.dict_row(word="ngaʼay")])
        self.assertEqual(dictionary.words_of(self.path), {"nga'ay"})

    def test_the_curly_apostrophe_is_normalised_too(self):
        self.write([fixtures.dict_row(word="nga’ay")])
        self.assertEqual(dictionary.words_of(self.path), {"nga'ay"})


class TestWhatCountsAsAWord(DictionaryCase):
    def test_chinese_glosses_do_not_enter_the_lexicon(self):
        # 中文釋義彼欄無收，毋過例句原文內底若有漢字嘛袂使入詞庫。
        self.write([fixtures.dict_row(sentence="malalitin 山藥 kako")])
        self.assertEqual(dictionary.words_of(self.path),
                         {"malalitin", "kako"})

    def test_two_letter_words_are_dropped(self):
        # 傷短ê詞逐族攏有，鑑別力等於零，留咧是雜訊。
        self.write([fixtures.dict_row(sentence="to ko nipalomaan")])
        self.assertEqual(dictionary.words_of(self.path), {"nipalomaan"})

    def test_case_is_folded(self):
        self.write([fixtures.dict_row(word="Talampo")])
        self.assertEqual(dictionary.words_of(self.path), {"talampo"})


class TestLexiconFile(DictionaryCase):
    def test_one_word_a_line_sorted(self):
        self.write([fixtures.dict_row(word="tolos"),
                    fixtures.dict_row(word="cakelis"),
                    fixtures.dict_row(word="falocoʼ")])
        out = os.path.join(self.folder, "阿美.txt")
        dictionary.distil(self.path, out)
        with open(out, encoding="utf-8") as handle:
            lines = handle.read().splitlines()
        self.assertEqual(lines, ["cakelis", "falocoʼ".replace("ʼ", "'"),
                                 "tolos"])

    def test_writing_twice_gives_the_same_bytes(self):
        self.write([fixtures.dict_row(word="tolos"),
                    fixtures.dict_row(word="cakelis")])
        first = os.path.join(self.folder, "a.txt")
        second = os.path.join(self.folder, "b.txt")
        dictionary.distil(self.path, first)
        dictionary.distil(self.path, second)
        with open(first, "rb") as handle:
            one = handle.read()
        with open(second, "rb") as handle:
            two = handle.read()
        self.assertEqual(one, two)

    def test_loading_a_lexicon_gives_back_the_words(self):
        self.write([fixtures.dict_row(word="tolos"),
                    fixtures.dict_row(word="cakelis")])
        out = os.path.join(self.folder, "阿美.txt")
        dictionary.distil(self.path, out)
        self.assertEqual(dictionary.load(out), {"tolos", "cakelis"})


if __name__ == "__main__":
    unittest.main()
