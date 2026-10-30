"""redate：目錄那一集的播出日期、集數標毋著，成果檔名跟咧換，store 內底整套改名。

2026-10-29：`20240930_274_晚間_Amis_阿美` 用ê是 `20241001S2000.mkv`，OCR
內容（台9線崇德土石流、山陀兒颱風來襲）佮檔名攏是 10-01，毋是 09-30。
佮 relabel（語別標毋著）無仝：內容猶是仝一集、語言毋曾改，所以 whisper
辨識結果嘛是對ê，**逐階段攏改名，毋刪**；跨月（09 → 10）ê時月份資料夾嘛換。
"""
import csv
import os
import tempfile
import unittest

from scripts import catalogue_checks as checks
from scripts.errors import PipelineError
from scripts.news import redate

OLD = "20240930_274_晚間_Amis_阿美"
NEW = "20241001_275_晚間_Amis_阿美"
NEIGHBOUR = "20240923_267_晚間_Amis_阿美"

STAGES = (("1-ocr/1-cues", ".json"), ("1-ocr/3-srt", ".srt"),
          ("1-ocr/0-segments", ".csv"),
          ("2-asr-whisper/1-srt-sapolita", ".srt"),
          ("2-asr-whisper/2-csv-analysis", ".csv"),
          ("2-asr-whisper/3-srt-paragraph", ".srt"),
          ("2-asr-kaldi/1-words", ".json"))


def catalogue_row(**over):
    row = {"成果檔名": OLD, "節目名稱": "看見族語（晚間）", "年度": "2024",
           "集數": "274", "播出日期": "2024-09-30", "族語別(英)": "Amis",
           "族語別(中)": "阿美", "語言別": "海岸", "語言別代號": "ami-x-pswl",
           "原始影片檔案位置": "home/mkv-raw/113/10月/20241001S2000.mkv",
           "備註": "檔名寫 10-01"}
    row.update(over)
    return row


class TestTheRow(unittest.TestCase):

    def test_the_date_and_episode_change_and_the_name_follows(self):
        got = redate.redate_row(catalogue_row(), "2024-10-01", 275,
                                "OCR 內容是 10-01")
        self.assertEqual(got["成果檔名"], NEW)
        self.assertEqual((got["播出日期"], got["集數"]), ("2024-10-01", "275"))

    def test_everything_else_in_the_row_is_left_alone(self):
        """族語、語言別代號、來源檔都無動——干焦日期佮集數標毋著。"""
        before = catalogue_row()
        got = redate.redate_row(before, "2024-10-01", 275, "x")
        for key in ("節目名稱", "族語別(英)", "族語別(中)", "語言別",
                    "語言別代號", "原始影片檔案位置"):
            self.assertEqual(got[key], before[key], key)

    def test_the_year_follows_when_the_date_crosses_new_year(self):
        got = redate.redate_row(catalogue_row(年度="2024"), "2025-01-01", 1,
                                "x")
        self.assertEqual(got["年度"], "2025")

    def test_the_old_note_is_kept_and_the_reason_added(self):
        got = redate.redate_row(catalogue_row(), "2024-10-01", 275,
                                "OCR 內容是 10-01")
        self.assertTrue(got["備註"].startswith("檔名寫 10-01"))
        self.assertIn("2024-09-30", got["備註"])
        self.assertIn("OCR 內容是 10-01", got["備註"])

    def test_crossing_into_the_renamed_programme_changes_its_name(self):
        """07-31 → 08-01：節目名稱跟咧換成《看見族語（晚間）》。

        無換ê話，剛改好ê這逝會予 `row_problems` ê日期對照擋落來。
        """
        row = catalogue_row(播出日期="2024-07-31", 集數="273",
                            節目名稱="晚間族語新聞")
        got = redate.redate_row(row, "2024-08-01", 274, "x")
        self.assertEqual(got["節目名稱"], "看見族語（晚間）")
        self.assertEqual(checks.row_problems([got]), [])

    def test_crossing_back_before_it_changes_the_name_back(self):
        row = catalogue_row(播出日期="2024-08-01", 集數="274",
                            節目名稱="看見族語（晚間）")
        got = redate.redate_row(row, "2024-07-31", 273, "x")
        self.assertEqual(got["節目名稱"], "晚間族語新聞")
        self.assertEqual(checks.row_problems([got]), [])

    def test_staying_on_one_side_leaves_the_name_alone(self):
        got = redate.redate_row(catalogue_row(), "2024-10-01", 275, "x")
        self.assertEqual(got["節目名稱"], "看見族語（晚間）")

    def test_a_malformed_date_is_refused(self):
        for bad in ("2024/10/01", "20241001", "2024-10-1", ""):
            with self.assertRaises(PipelineError):
                redate.redate_row(catalogue_row(), bad, 275, "x")


class Store(object):
    """合成ê store：逐階段一个檔、兩張紀錄表。"""

    def __init__(self, test):
        tmp = tempfile.TemporaryDirectory()
        test.addCleanup(tmp.cleanup)
        self.root = tmp.name
        for rel, ext in STAGES:
            path = os.path.join(self.root, rel, "2024-09", OLD + ext)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(rel)
        vision = os.path.join(self.root, "1-ocr/2-vision/2024-09", OLD)
        os.makedirs(vision)
        with open(os.path.join(vision, "b01.tsv"), "w") as handle:
            handle.write("1\than\t字\n")
        self.opening = os.path.join(self.root, "1-ocr/片頭辨識.csv")
        with open(self.opening, "w", encoding="utf-8", newline="") as handle:
            handle.write("成果檔名,畫面語別牌,主播,與目錄相符,截圖秒數,依據\n"
                         "%s,阿美,Ohay Sewana,是,20/30/40,Claude Vision\n"
                         "%s,阿美,Ohay Sewana,是,20/30/40,Claude Vision\n"
                         % (NEIGHBOUR, OLD))
        self.log = os.path.join(self.root,
                                "2-asr-whisper/1-srt-sapolita/辨識紀錄.csv")
        with open(self.log, "w", encoding="utf-8", newline="") as handle:
            handle.write("成果檔名,語言別代號,主播名,伺服器,辨識日期,音長秒,段數\n"
                         "%s,ami-x-pswl,Ohay Sewana,x,2026-10-08,2852.04,315\n"
                         "%s,ami-x-pswl,Ohay Sewana,x,2026-10-08,2800.1,300\n"
                         % (NEIGHBOUR, OLD))

    def exists(self, rel):
        return os.path.exists(os.path.join(self.root, rel))

    def names(self, path):
        with open(path, encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        out = []
        for row in rows:
            out.append(row["成果檔名"])
        return out


class TestTheStore(unittest.TestCase):

    def setUp(self):
        self.store = Store(self)
        self.report = redate.move_store(OLD, NEW, store=self.store.root)

    def test_every_stage_is_renamed_into_the_new_month(self):
        """09 → 10：月份資料夾嘛換。whisper、平行語料、kaldi 攏佇內，毋刪。"""
        for rel, ext in STAGES:
            self.assertTrue(self.store.exists("%s/2024-10/%s%s"
                                              % (rel, NEW, ext)), rel)
            self.assertFalse(self.store.exists("%s/2024-09/%s%s"
                                               % (rel, OLD, ext)), rel)

    def test_the_vision_folder_moves_with_its_files(self):
        self.assertTrue(self.store.exists(
            "1-ocr/2-vision/2024-10/%s/b01.tsv" % NEW))
        self.assertFalse(self.store.exists("1-ocr/2-vision/2024-09/%s" % OLD))

    def test_the_contents_are_untouched(self):
        path = os.path.join(
            self.store.root,
            "2-asr-whisper/1-srt-sapolita/2024-10/%s.srt" % NEW)
        with open(path, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "2-asr-whisper/1-srt-sapolita")

    def test_the_two_logs_rename_the_row_and_keep_the_neighbour(self):
        self.assertEqual(sorted(self.store.names(self.store.log)),
                         sorted([NEIGHBOUR, NEW]))
        self.assertEqual(sorted(self.store.names(self.store.opening)),
                         sorted([NEIGHBOUR, NEW]))

    def test_the_log_row_keeps_its_numbers(self):
        with open(self.store.log, encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        for row in rows:
            if row["成果檔名"] == NEW:
                self.assertEqual((row["音長秒"], row["段數"]),
                                 ("2800.1", "300"))

    def test_the_logs_stay_sorted_by_name(self):
        for path in (self.store.log, self.store.opening):
            names = self.store.names(path)
            self.assertEqual(names, sorted(names))

    def test_the_report_lists_what_moved(self):
        # 七個階段檔、一個讀者資料夾、兩張有這集ê紀錄表（訂正紀錄無這集）
        self.assertEqual(len(self.report.renamed), len(STAGES) + 1 + 2)


class TestRefusals(unittest.TestCase):

    def test_a_target_that_already_exists_moves_nothing(self):
        store = Store(self)
        clash = os.path.join(store.root, "1-ocr/3-srt/2024-10/%s.srt" % NEW)
        os.makedirs(os.path.dirname(clash))
        with open(clash, "w") as handle:
            handle.write("other")
        with self.assertRaises(PipelineError):
            redate.move_store(OLD, NEW, store=store.root)
        self.assertTrue(store.exists("1-ocr/1-cues/2024-09/%s.json" % OLD))
        self.assertTrue(store.exists("2-asr-whisper/1-srt-sapolita/2024-09/"
                                     "%s.srt" % OLD))

    def test_the_same_name_is_refused(self):
        store = Store(self)
        with self.assertRaises(PipelineError):
            redate.move_store(OLD, OLD, store=store.root)

    def test_an_episode_with_nothing_in_the_store_still_works(self):
        """猶未切 cue ê集數：目錄改就好，無檔通搬。"""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        report = redate.move_store(OLD, NEW, store=tmp.name)
        self.assertEqual(report.renamed, [])


class TestTheCatalogue(unittest.TestCase):

    HEAD = ["成果檔名", "節目名稱", "年度", "集數", "播出日期", "族語別(英)",
            "族語別(中)", "語言別", "語言別代號", "原始影片檔案位置", "備註"]

    def write(self, rows):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = os.path.join(tmp.name, "smkul.csv")
        with open(path, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, self.HEAD, lineterminator="\r\n")
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
        return path

    def test_the_catalogue_row_and_the_store_change_together(self):
        store = Store(self)
        path = self.write([catalogue_row(成果檔名=NEIGHBOUR, 集數="267",
                                         播出日期="2024-09-23"),
                           catalogue_row()])
        new, report = redate.redate(OLD, "2024-10-01", 275, "OCR 內容是 10-01",
                                    catalogue=path, store=store.root)
        self.assertEqual(new, NEW)
        with open(path, encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        names = []
        for row in rows:
            names.append(row["成果檔名"])
        self.assertEqual(names, [NEIGHBOUR, NEW])
        self.assertTrue(store.exists("1-ocr/3-srt/2024-10/%s.srt" % NEW))
        self.assertTrue(report.renamed)

    def test_a_name_that_is_not_in_the_catalogue_changes_nothing(self):
        store = Store(self)
        path = self.write([catalogue_row(成果檔名=NEIGHBOUR, 集數="267",
                                         播出日期="2024-09-23")])
        with self.assertRaises(PipelineError):
            redate.redate(OLD, "2024-10-01", 275, "x", catalogue=path,
                          store=store.root)
        self.assertTrue(store.exists("1-ocr/3-srt/2024-09/%s.srt" % OLD))

    def test_a_new_name_already_in_the_catalogue_is_refused(self):
        store = Store(self)
        path = self.write([catalogue_row(), catalogue_row(
            成果檔名=NEW, 集數="275", 播出日期="2024-10-01")])
        with self.assertRaises(PipelineError):
            redate.redate(OLD, "2024-10-01", 275, "x", catalogue=path,
                          store=store.root)
        self.assertTrue(store.exists("1-ocr/3-srt/2024-09/%s.srt" % OLD))


if __name__ == "__main__":
    unittest.main()
