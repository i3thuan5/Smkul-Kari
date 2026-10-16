"""送 Claude 判定的分批檔，與判定結果的匯入驗證。

判定是這條線唯一花錢、不能重跑出同樣結果的步驟，所以：存檔、重跑
不重判；匯入時少列、多列、類別寫錯都要指名中止，不能恬恬吞掉——
news ingest 驗 sheets 編號就是因為這樣才擋下過一次舊檔。
"""
import os
import tempfile
import unittest

from scripts.aiyalaeho.cleaning import candidates
from scripts.aiyalaeho.cleaning import verdicts
from scripts.aiyalaeho.cleaning.source import Entry
from scripts.aiyalaeho.langcheck.report import write_table
from scripts.errors import PipelineError

E087 = "開會了_087_Pinuyumayan_卑南"


def built(*texts):
    entries = []
    for number, text in enumerate(texts, start=1):
        entries.append(Entry(number, "00:00:01,000", "00:00:02,000", text,
                             "華語%d" % number))
    episode = candidates.EpisodeText(E087, "卑南", ("西群", "知本"), entries)
    evidence = candidates.Evidence(
        dictionary={"garem"}, klokah={"西群": {"likavung", "harem"}},
        kaldi=set(), corpus={}, transcripts={}, dict_variety="南王")
    return candidates.build([episode], evidence), entries


def texts_of(entries):
    out = {}
    for entry in entries:
        out[(E087, entry.number)] = entry
    return out


class TextCase(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="verdict-")
        self.built, self.entries = built(
            "ay harem i Likavungg nanta", "kemazu i Likavungg",
            "zi pukatelu mawnanta kazu", "Likavung")

    def export(self, size=300):
        return verdicts.export_text(self.built, texts_of(self.entries),
                                    {E087: ("西群", "知本")}, self.folder,
                                    size)

    def answer(self, batch, rows):
        path = os.path.join(self.folder, "%s.csv" % batch)
        write_table(path, verdicts.TEXT_RESULT_HEADER, rows)


class TestTextExport(TextCase):
    def test_only_words_sent_for_judging_go_out(self):
        paths = self.export()
        self.assertEqual(len(paths), 1)
        self.assertEqual(os.path.basename(paths[0]), "待判-b01.csv")
        sent = verdicts.read_rows(paths[0])
        words = []
        for row in sent:
            words.append(row["詞形"])
        self.assertIn("Likavungg", words)
        self.assertNotIn("harem", words)
        self.assertNotIn("Likavung", words)

    def test_context_carries_both_rows_and_the_entry_number(self):
        sent = verdicts.read_rows(self.export()[0])
        for row in sent:
            if row["詞形"] == "Likavungg":
                self.assertIn("087#1 族語：ay harem i Likavungg nanta／"
                              "華語：華語1", row["上下文"])
                self.assertIn("087#2", row["上下文"])
                self.assertEqual(row["該集語別"], "西群;知本")
                self.assertIn("Likavung", row["相近寫法"])

    def test_batches_are_split_by_size(self):
        paths = self.export(size=2)
        self.assertGreater(len(paths), 1)
        self.assertEqual(os.path.basename(paths[1]), "待判-b02.csv")

    def test_a_rerun_sends_only_what_was_not_sent(self):
        self.export()
        self.assertEqual(self.export(), [])


class TestTextImport(TextCase):
    def rows_for(self, batch_path, kind="不同詞", suggestion=""):
        rows = []
        for row in verdicts.read_rows(batch_path):
            rows.append([row["詞形"], kind, suggestion, "理由"])
        return rows

    def test_a_complete_answer_is_read_back_by_word(self):
        path = self.export()[0]
        rows = self.rows_for(path)
        for row in rows:
            if row[0] == "Likavungg":
                row[1:3] = ["錯字", "Likavung"]
        self.answer("b01", rows)
        got = verdicts.load_text(self.folder)
        self.assertEqual(got["likavungg"].kind, "錯字")
        self.assertEqual(got["likavungg"].suggestion, "Likavung")

    def test_a_missing_row_names_the_word_and_batch(self):
        path = self.export()[0]
        rows = self.rows_for(path)
        dropped = rows.pop()
        self.answer("b01", rows)
        with self.assertRaises(PipelineError) as caught:
            verdicts.load_text(self.folder)
        self.assertIn("b01", str(caught.exception))
        self.assertIn(dropped[0], str(caught.exception))

    def test_an_extra_row_is_refused(self):
        path = self.export()[0]
        rows = self.rows_for(path)
        rows.append(["kaku", "語言別差異", "", "多出來的"])
        self.answer("b01", rows)
        with self.assertRaises(PipelineError) as caught:
            verdicts.load_text(self.folder)
        self.assertIn("kaku", str(caught.exception))

    def test_an_unknown_class_is_refused(self):
        path = self.export()[0]
        self.answer("b01", self.rows_for(path, kind="錯誤"))
        with self.assertRaises(PipelineError) as caught:
            verdicts.load_text(self.folder)
        self.assertIn("錯誤", str(caught.exception))

    def test_a_typo_without_a_suggestion_is_refused(self):
        path = self.export()[0]
        self.answer("b01", self.rows_for(path, kind="錯字"))
        with self.assertRaises(PipelineError):
            verdicts.load_text(self.folder)

    def test_an_unanswered_batch_is_named(self):
        self.export()
        with self.assertRaises(PipelineError) as caught:
            verdicts.load_text(self.folder)
        self.assertIn("待判-b01.csv", str(caught.exception))


class TestImage(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="verdict-img-")
        self.items = [
            verdicts.ImageItem(E087, 188, "Likavungg", "Likavung",
                               "ay harem Likavungg", "介紹利嘉部落",
                               ["/w/2-strips/t00819000_formosan.png"]),
            verdicts.ImageItem(E087, 376, "mena’   u", "mena'u",
                               "zi mena’   u kana", "放眼看",
                               ["/w/2-strips/a.png", "/w/2-strips/b.png"]),
        ]

    def answer(self, rows):
        write_table(os.path.join(self.folder, "b01.csv"),
                    verdicts.IMAGE_RESULT_HEADER, rows)

    def test_every_strip_of_the_entry_is_sent(self):
        path = verdicts.export_image(self.items, self.folder, 60)[0]
        rows = verdicts.read_rows(path)
        self.assertEqual(rows[1]["圖條"],
                         "/w/2-strips/a.png;/w/2-strips/b.png")

    def test_round_trip_and_rerun(self):
        verdicts.export_image(self.items, self.folder, 60)
        self.answer([[E087, "188", "Likavungg", "播出端錯字", "Likavungg",
                      "畫面兩個 g"],
                     [E087, "376", "mena’   u", "播出端錯字", "mena'u",
                      "同一詞"]])
        got = verdicts.load_image(self.folder)
        self.assertEqual(got[(E087, 376, "mena’   u")].screen, "mena'u")
        self.assertEqual(verdicts.export_image(self.items, self.folder, 60),
                         [])

    def test_image_classes_are_closed(self):
        verdicts.export_image(self.items, self.folder, 60)
        self.answer([[E087, "188", "Likavungg", "錯字", "Likavungg", ""],
                     [E087, "376", "mena’   u", "看不出來", "", ""]])
        with self.assertRaises(PipelineError) as caught:
            verdicts.load_image(self.folder)
        self.assertIn("錯字", str(caught.exception))

    def test_ocr_misread_needs_what_the_screen_shows(self):
        verdicts.export_image(self.items, self.folder, 60)
        self.answer([[E087, "188", "Likavungg", "OCR 讀錯", "", ""],
                     [E087, "376", "mena’   u", "看不出來", "", ""]])
        with self.assertRaises(PipelineError):
            verdicts.load_image(self.folder)


if __name__ == "__main__":
    unittest.main()
