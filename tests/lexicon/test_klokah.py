"""E樂園 教材 → 各語別詞表。

辭典一族只收一個語別，E樂園 有 43 個語別逐句標了語言別編號，是手上
唯一分得出語別的族語文本。會錯的地方都是 2026-10-15 解開真檔時量到的：

  族語欄名十種寫法   wordAb、sentenceAAb、lessonAB、con_AB1、Ab_1、
                     article_ab、matchAAbA（Ab 在中間）……只認一種會漏大半
  ch 不是華語的記號  choiceOneAAb 的 ch 是 choice
  兩個編號           句型篇 languageId（族）＋dialectId（語別）
  語別在資料夾名     生活會話篇、閱讀書寫篇的 XML 裡沒有 dialectId
  欄名換一套         文化篇單字表是 dialect_id、word_ab
"""
import os
import tempfile
import unittest

from scripts.errors import PipelineError
from scripts.lexicon import klokah
from tests.lexicon import fixtures


class KlokahCase(unittest.TestCase):
    def setUp(self):
        self.root = fixtures.klokah_tree(tempfile.mkdtemp(prefix="klokah-"))
        self.names = os.path.join(self.root, "E樂園方言編號.txt")

    def vocab(self):
        return klokah.vocabularies(self.root, self.names)


class TestFormosanFields(unittest.TestCase):
    def test_every_spelling_seen_in_the_real_export_counts(self):
        for name in ("wordAb", "sentenceAb", "sentenceAAb", "lessonAB",
                     "lessonAb", "con_AB1", "word_AB12", "Ab_1", "Ab_20",
                     "article_ab", "word_ab", "matchAAbA", "matchCAbB",
                     "choiceOneAAb", "choiceThreeAb", "oralReadingEAb",
                     "recognizeAb", "pictureTalkAb"):
            self.assertTrue(klokah.is_formosan_field(name), name)

    def test_chinese_and_bookkeeping_fields_do_not(self):
        for name in ("wordCh", "sentenceACh", "lessonCH", "con_CH1",
                     "Ch_1", "article_ch", "matchAChA", "choiceOneACh",
                     "dialectId", "classCh", "con_scene1", "vocabularyNum",
                     "lessonNo", "autoId", "sentenceCo", "title_ch"):
            self.assertFalse(klokah.is_formosan_field(name), name)


class TestDialectTable(KlokahCase):
    def test_bom_tabs_and_the_empty_twelve(self):
        names = klokah.dialect_names(self.names)
        self.assertEqual(names["1"], "南勢阿美語")
        self.assertEqual(names["11"], "宜蘭澤敖利泰雅語")
        self.assertNotIn("12", names)

    def test_full_name_is_stripped_to_the_variety(self):
        self.assertEqual(klokah.variety_of("南勢阿美語"),
                         ("阿美", "南勢", "ami-x-iams"))
        self.assertEqual(klokah.variety_of("宜蘭澤敖利泰雅語"),
                         ("泰雅", "宜蘭澤敖利", "tay-x-kls"))
        self.assertEqual(klokah.variety_of("西群卑南語"),
                         ("卑南", "西群", "pyu-x-mkzy"))

    def test_a_variety_listed_under_its_full_name(self):
        # 對照表收的是「東排灣」不是「東」——剝掉族名就查不到。
        self.assertEqual(klokah.variety_of("東排灣語"),
                         ("排灣", "東排灣", "pwn-x-kcdsn"))

    def test_a_language_without_varieties_falls_back_to_its_code(self):
        self.assertEqual(klokah.variety_of("賽夏語"), ("賽夏", "", "xsy"))

    def test_an_unknown_name_stops_and_says_which(self):
        with self.assertRaises(PipelineError) as caught:
            klokah.variety_of("火星阿美語")
        self.assertIn("火星阿美語", str(caught.exception))


class TestVocabularies(KlokahCase):
    def test_dialect_comes_from_dialect_id_not_language_id(self):
        vocab = self.vocab()
        self.assertIn("kiyaumalr", vocab["南王卑南語"])
        for name in vocab:
            self.assertNotEqual(name, "12")

    def test_choice_and_match_columns_are_formosan(self):
        vocab = self.vocab()
        self.assertIn("kiyaumalr", vocab["南王卑南語"])
        self.assertIn("pinaski", vocab["南王卑南語"])
        for words in vocab.values():
            self.assertNotIn("choice華語", words)

    def test_slash_separated_variants_are_separate_words(self):
        vocab = self.vocab()["南王卑南語"]
        self.assertIn("saya", vocab)
        self.assertIn("misasa", vocab)
        self.assertNotIn("sa / saya / misasa", vocab)

    def test_dialect_from_the_folder_when_the_xml_has_none(self):
        vocab = self.vocab()
        self.assertIn("kayzaeh", vocab["賽夏語"])
        self.assertIn("so:o'", vocab["賽夏語"])
        self.assertIn("lokah", vocab["宜蘭澤敖利泰雅語"])
        self.assertIn("masalu", vocab["東排灣語"])

    def test_culture_word_table_uses_other_column_names(self):
        self.assertIn("kaku", self.vocab()["南勢阿美語"])

    def test_sentence_csv(self):
        vocab = self.vocab()
        self.assertIn("harem", vocab["西群卑南語"])
        self.assertIn("garem", vocab["南王卑南語"])
        self.assertNotIn("harem", vocab["南王卑南語"])

    def test_apostrophes_are_normalised_and_case_folded(self):
        vocab = self.vocab()["宜蘭澤敖利泰雅語"]
        self.assertIn("su'", vocab)
        self.assertIn("tayal", vocab)

    def test_chinese_columns_never_reach_a_vocabulary(self):
        for words in self.vocab().values():
            for word in words:
                self.assertTrue(word.isascii() or "ʉ" in word, word)

    def test_a_text_csv_without_a_dialect_column_stops(self):
        fixtures.write_csv(
            os.path.join(self.root, "8.族語短文", "klokah_essay_sentence.csv"),
            ["autoId", "sentenceAb"], [["1", "kaku"]])
        with self.assertRaises(PipelineError) as caught:
            self.vocab()
        self.assertIn("klokah_essay_sentence.csv", str(caught.exception))

    def test_an_unlisted_dialect_number_stops(self):
        fixtures.write_csv(
            os.path.join(self.root, "8.族語短文", "klokah_essay_sentence.csv"),
            ["dialectId", "sentenceAb"], [["99", "kaku"]])
        with self.assertRaises(PipelineError) as caught:
            self.vocab()
        self.assertIn("99", str(caught.exception))


class TestFiles(KlokahCase):
    def test_round_trip_one_word_per_line_sorted(self):
        out = tempfile.mkdtemp(prefix="klokah-out-")
        written = klokah.write_all(self.vocab(), out)
        self.assertIn(os.path.join(out, "西群卑南語.txt"), written)
        with open(os.path.join(out, "西群卑南語.txt"),
                  encoding="utf-8") as handle:
            lines = handle.read().splitlines()
        self.assertEqual(lines, sorted(lines))
        self.assertEqual(klokah.load_all(out), self.vocab())


if __name__ == "__main__":
    unittest.main()
