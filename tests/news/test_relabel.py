"""relabel：片頭辨識發現目錄語別標毋著，改目錄、改 store ê檔名。

2021-01 片頭辨識：`20210116_016_晚間_Paiwan_排灣` 三格語別牌攏是卑南，
原始檔名是 `卑南語-20210116s1800.mp4`，whisper 紀錄ê主播嘛是卑南主播
Araytay Paregi。目錄一改，成果檔名就換（`_Pinuyumayan_卑南`），store
內底仝一集ê檔愛綴咧改，無就變孤兒檔（`rebuild --verify` 會擋）。

分兩款：
- 佮語別無關ê（時間軸、讀者逐字稿、交付 SRT、段落表、片頭辨識）→ 改名；
- 用毋著ê語言做出來ê（whisper SRT 佮辨識紀錄、平行語料、kaldi 各階段）
  → 刪掉，等重跑。改名留咧就是用排灣語辨識卑南語ê結果冒名頂替。
"""
import csv
import os
import tempfile
import unittest

from scripts.errors import PipelineError
from scripts.news import relabel

OLD = "20210116_016_晚間_Paiwan_排灣"
NEW = "20210116_016_晚間_Pinuyumayan_卑南"

HEAD = ["成果檔名", "節目名稱", "年度", "集數", "播出日期", "族語別(英)",
        "族語別(中)", "語言別", "語言別代號", "原始影片檔案位置", "備註"]


def catalogue_row(**over):
    row = {"成果檔名": OLD, "節目名稱": "晚間族語新聞", "年度": "2021",
           "集數": "16", "播出日期": "2021-01-16", "族語別(英)": "Paiwan",
           "族語別(中)": "排灣", "語言別": "", "語言別代號": "pwn",
           "原始影片檔案位置":
               "ilrdf-corpus/族語新聞/110.1-110.10/1月/卑南語-20210116s1800.mp4",
           "備註": ""}
    row.update(over)
    return row


class TestTheRow(unittest.TestCase):

    def test_language_columns_and_name_follow_the_new_language(self):
        got = relabel.relabel_row(catalogue_row(), "卑南", "片頭語別牌三格攏是卑南")
        self.assertEqual(got["成果檔名"], NEW)
        self.assertEqual((got["族語別(英)"], got["族語別(中)"],
                          got["語言別代號"]), ("Pinuyumayan", "卑南", "pyu"))
        self.assertEqual(got["語言別"], "")
        self.assertIn("排灣", got["備註"])
        self.assertIn("片頭語別牌三格攏是卑南", got["備註"])

    def test_an_existing_note_is_kept(self):
        got = relabel.relabel_row(catalogue_row(備註="檔名寫 18:00"), "卑南",
                                  "片頭")
        self.assertTrue(got["備註"].startswith("檔名寫 18:00"))

    def test_an_unknown_language_is_refused(self):
        with self.assertRaises(PipelineError):
            relabel.relabel_row(catalogue_row(), "卑南語", "x")


class Store(object):
    """合成ê store：逐階段一个檔。"""

    def __init__(self, test):
        tmp = tempfile.TemporaryDirectory()
        test.addCleanup(tmp.cleanup)
        self.root = tmp.name
        self.made = {}
        for label, rel in (("cues", "1-ocr/1-cues/2021-01/%s.json"),
                           ("srt", "1-ocr/3-srt/2021-01/%s.srt"),
                           ("segments", "1-ocr/0-segments/2021-01/%s.csv"),
                           ("whisper",
                            "2-asr-whisper/1-srt-sapolita/2021-01/%s.srt"),
                           ("pairs", "2-asr-whisper/2-平行語料/2021-01/%s.csv"),
                           ("words", "2-asr-kaldi/1-words/2021-01/%s.json")):
            path = os.path.join(self.root, rel % OLD)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(label)
            self.made[label] = path
        vision = os.path.join(self.root, "1-ocr/2-vision/2021-01", OLD)
        os.makedirs(vision)
        with open(os.path.join(vision, "b01.tsv"), "w") as handle:
            handle.write("1\than\t字\n")
        self.opening = os.path.join(self.root, "1-ocr/片頭辨識.csv")
        with open(self.opening, "w", encoding="utf-8", newline="") as handle:
            handle.write("成果檔名,畫面語別牌,主播,與目錄相符,截圖秒數,依據\n"
                         "%s,卑南,,否,20/30/40,Claude Vision\n"
                         "20210117_017_午間_Kanakanavu_卡那卡那富,卡那卡那富,,"
                         "是,20/30/40,Claude Vision\n" % OLD)
        self.log = os.path.join(self.root,
                                "2-asr-whisper/1-srt-sapolita/辨識紀錄.csv")
        with open(self.log, "w", encoding="utf-8", newline="") as handle:
            handle.write("成果檔名,語言別代號,主播名,伺服器,辨識日期,音長秒,段數\n"
                         "%s,pwn-x-pnvn,Araytay Paregi,x,2026-09-18,1,1\n"
                         "20210103_003_晚間_Pinuyumayan_卑南,pyu-x-pym,A,x,"
                         "2026-09-18,1,1\n" % OLD)

    def exists(self, rel):
        return os.path.exists(os.path.join(self.root, rel))


class TestTheStore(unittest.TestCase):

    def setUp(self):
        self.store = Store(self)
        self.report = relabel.move_store(OLD, NEW, "卑南",
                                         store=self.store.root)

    def test_language_free_files_are_renamed(self):
        for rel in ("1-ocr/1-cues/2021-01/%s.json",
                    "1-ocr/3-srt/2021-01/%s.srt",
                    "1-ocr/0-segments/2021-01/%s.csv",
                    "1-ocr/2-vision/2021-01/%s/b01.tsv"):
            self.assertTrue(self.store.exists(rel % NEW), rel)
            self.assertFalse(self.store.exists(rel % OLD), rel)

    def test_what_was_made_in_the_wrong_language_is_removed(self):
        for rel in ("2-asr-whisper/1-srt-sapolita/2021-01/%s.srt",
                    "2-asr-whisper/2-平行語料/2021-01/%s.csv",
                    "2-asr-kaldi/1-words/2021-01/%s.json"):
            self.assertFalse(self.store.exists(rel % OLD), rel)
            self.assertFalse(self.store.exists(rel % NEW), rel)
        self.assertIn("whisper", " ".join(self.report.removed))

    def test_the_whisper_log_loses_the_row_so_it_is_redone(self):
        with open(self.store.log, encoding="utf-8") as handle:
            text = handle.read()
        self.assertNotIn(OLD, text)
        self.assertNotIn(NEW, text)
        self.assertIn("20210103_003_晚間_Pinuyumayan_卑南", text)

    def test_the_opening_row_is_renamed_and_now_matches(self):
        with open(self.store.opening, encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        names = []
        for row in rows:
            names.append(row["成果檔名"])
        self.assertEqual(names, [NEW, "20210117_017_午間_Kanakanavu_卡那卡那富"])
        self.assertEqual(rows[0]["與目錄相符"], "是")

    def test_the_contents_are_untouched(self):
        with open(os.path.join(self.store.root,
                               "1-ocr/1-cues/2021-01/%s.json" % NEW)) as fh:
            self.assertEqual(fh.read(), "cues")

    def test_a_target_that_already_exists_is_refused(self):
        store = Store(self)
        clash = os.path.join(store.root, "1-ocr/3-srt/2021-01/%s.srt" % NEW)
        with open(clash, "w") as handle:
            handle.write("other")
        with self.assertRaises(PipelineError):
            relabel.move_store(OLD, NEW, "卑南", store=store.root)
        self.assertTrue(store.exists("1-ocr/1-cues/2021-01/%s.json" % OLD))


if __name__ == "__main__":
    unittest.main()
