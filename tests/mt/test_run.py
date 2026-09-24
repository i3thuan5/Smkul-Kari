"""news/pairs_run: the 2021-01～10 batch into 2-平行語料.

A synthetic store (two tribes, three episodes); the dictionaries are
passed in, so nothing reaches the SFTP.
"""
import csv
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from scripts.errors import PipelineError
from scripts.mt import tier
from scripts.news import pairs_run
from scripts.news import paths

HEADER = ["成果檔名", "節目名稱", "年度", "集數", "播出日期", "族語別(英)",
          "族語別(中)", "語言別", "語言別代號", "原始影片檔案位置", "備註"]
LEXICONS = {
    "阿美": {"salikaka", "niyaro'", "kayakay", "kiwit", "lalan",
           "tanosok", "matini", "kalingko", "sowal", "romi'ad"},
    "泰雅": {"tayal", "qani", "kawas", "miru", "nqrqes", "squliq",
           "lokah", "balay", "yaba'", "kmayal"},
}


def read_bytes(path):
    with open(path, "rb") as handle:
        return handle.read()


AMIS = ("o tanosok a lalan no salikaka no kiwit a niyaroʼ i kalingko "
        "matini sowal no romiʼad")
ATAYAL = "lokah balay squliq tayal qani kawas miru nqrqes kmayal yabaʼ"


class Store(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="pairs-run-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        news = os.path.join(self.tmp, "news")
        self.dirs = {
            "KARI_CUES": os.path.join(news, "1-ocr", "1-cues"),
            "KARI_VISION": os.path.join(news, "1-ocr", "2-vision"),
            "SRT_DIR": os.path.join(news, "1-ocr", "3-srt"),
            "SAPOLITA_SRT": os.path.join(news, "2-asr-whisper",
                                         "1-srt-sapolita"),
            "PAIRS_DIR": os.path.join(news, "2-asr-whisper", "2-平行語料"),
        }
        for name, value in self.dirs.items():
            patcher = mock.patch.object(paths, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.table = os.path.join(self.dirs["PAIRS_DIR"], "校正基準.csv")
        self.catalogue = os.path.join(news, "smkul.csv")
        for name, value in (("PAIRS_CALIBRATION", self.table),
                            ("TRACKER_STORE", self.catalogue)):
            patcher = mock.patch.object(paths, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.rows = []

    def episode(self, name, tribe_en, tribe, code, formosan,
                ocr=True, whisper=True):
        date = name[:8]
        self.rows.append({
            "成果檔名": name, "節目名稱": "晚間族語新聞", "年度": date[:4],
            "集數": name[9:12], "播出日期": "%s-%s-%s" % (
                date[:4], date[4:6], date[6:]),
            "族語別(英)": tribe_en, "族語別(中)": tribe, "語言別": "",
            "語言別代號": code, "原始影片檔案位置": "x/%s.mp4" % name,
            "備註": ""})
        month = paths.month_of(name)
        cues = [{"index": 1, "start": 20.0, "end": 24.0},
                {"index": 2, "start": 24.0, "end": 28.0},
                {"index": 3, "start": 120.0, "end": 124.0}]
        folder = os.path.join(self.dirs["KARI_CUES"], month)
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, name + ".json"), "w",
                  encoding="utf-8") as handle:
            json.dump({"cues": cues, "duration": 200.0}, handle)
        vision = os.path.join(self.dirs["KARI_VISION"], month, name)
        os.makedirs(vision, exist_ok=True)
        with open(os.path.join(vision, "b01.tsv"), "w",
                  encoding="utf-8") as handle:
            handle.write("1\than\t奇美部落的道路\n2\than\t花蓮縣的族人\n"
                         "3\than\t節目最後\n")
        if ocr:
            folder = os.path.join(self.dirs["SRT_DIR"], month)
            os.makedirs(folder, exist_ok=True)
            open(os.path.join(folder, name + ".srt"), "w").close()
        if whisper:
            folder = os.path.join(self.dirs["SAPOLITA_SRT"], month)
            os.makedirs(folder, exist_ok=True)
            with open(os.path.join(folder, name + ".srt"), "w",
                      encoding="utf-8") as handle:
                handle.write("1\n00:00:19,500 --> 00:00:28,200\n族語：%s\n"
                             "華語：奇美部落的道路\n\n2\n00:02:00,000 --> "
                             "00:02:04,000\n族語：ʼa ʼa ʼa ʼa ʼa ʼa ʼa ʼa\n"
                             "華語：一、二、三、四、五、六\n" % formosan)

    def write_catalogue(self):
        with open(self.catalogue, "w", encoding="utf-8-sig",
                  newline="") as handle:
            writer = csv.DictWriter(handle, HEADER, lineterminator="\r\n")
            writer.writeheader()
            for row in sorted(self.rows, key=lambda r: r["成果檔名"]):
                writer.writerow(row)

    def out(self, name):
        return os.path.join(self.dirs["PAIRS_DIR"], paths.month_of(name),
                            name + ".csv")

    def standard(self):
        self.episode("20210201_032_晚間_Amis_阿美", "Amis", "阿美", "ami", AMIS)
        self.episode("20210202_033_晚間_Atayal_泰雅", "Atayal", "泰雅", "tay",
                     ATAYAL)
        self.write_catalogue()


class TestScope(Store):
    def test_only_2021_01_to_10(self):
        self.standard()
        self.episode("20211101_305_晚間_Amis_阿美", "Amis", "阿美", "ami", AMIS)
        self.write_catalogue()
        pairs_run.run(recalibrate=True, lexicons=LEXICONS)
        self.assertTrue(os.path.exists(self.out("20210201_032_晚間_Amis_阿美")))
        self.assertFalse(os.path.exists(
            self.out("20211101_305_晚間_Amis_阿美")))

    def test_one_side_missing_is_listed_not_an_error(self):
        self.standard()
        self.episode("20210703_184_晚間_Amis_阿美", "Amis", "阿美", "ami", AMIS,
                     ocr=False)
        self.write_catalogue()
        written, skipped = pairs_run.run(recalibrate=True, lexicons=LEXICONS)
        self.assertEqual(len(written), 2)
        self.assertEqual([name for name, _why in skipped],
                         ["20210703_184_晚間_Amis_阿美"])


class TestCalibration(Store):
    def test_no_table_without_recalibrate_is_refused(self):
        self.standard()
        with self.assertRaises(PipelineError):
            pairs_run.run(lexicons=LEXICONS)

    def test_new_month_leaves_table_and_old_files_alone(self):
        self.standard()
        pairs_run.run(recalibrate=True, lexicons=LEXICONS)
        table = read_bytes(self.table)
        old = read_bytes(self.out("20210201_032_晚間_Amis_阿美"))
        self.episode("20210301_060_晚間_Amis_阿美", "Amis", "阿美", "ami",
                     "tada ko matini")
        self.write_catalogue()
        pairs_run.run(lexicons=LEXICONS)
        self.assertEqual(read_bytes(self.table), table)
        self.assertEqual(read_bytes(self.out("20210201_032_晚間_Amis_阿美")),
                         old)
        self.assertTrue(os.path.exists(self.out("20210301_060_晚間_Amis_阿美")))

    def test_recalibrate_rewrites_the_table(self):
        self.standard()
        pairs_run.run(recalibrate=True, lexicons=LEXICONS)
        with open(self.table, "w", encoding="utf-8") as handle:
            handle.write("族語別,開場組數,辭典命中率中位數\n阿美,1,0.9000\n"
                         "泰雅,1,0.9000\n")
        pairs_run.run(recalibrate=True, lexicons=LEXICONS)
        self.assertNotIn(b"0.9000", read_bytes(self.table))


class TestContent(Store):
    def test_rows_are_tiered_with_reasons(self):
        self.standard()
        pairs_run.run(recalibrate=True, lexicons=LEXICONS)
        with open(self.out("20210201_032_晚間_Amis_阿美"),
                  encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 2)
        self.assertNotEqual(rows[0]["信心層級"], "不採用")
        self.assertEqual((rows[1]["信心層級"], rows[1]["不採用原因"]),
                         ("不採用", "幻覺"))
        self.assertEqual(rows[0]["語言別代號"], "ami")

    def test_no_model_is_called(self):
        self.standard()
        with mock.patch("scripts.asrmt.gradio.Client",
                        side_effect=AssertionError("model call")):
            pairs_run.run(recalibrate=True, lexicons=LEXICONS)

    def test_merge_threshold_is_read_from_tier(self):
        self.standard()
        seen = []
        real = pairs_run.overlap.max_overlap_groups

        def spy(segments, entries, straddle_frac=None):
            seen.append(straddle_frac)
            return real(segments, entries, straddle_frac=straddle_frac)
        with mock.patch.object(pairs_run.overlap, "max_overlap_groups", spy):
            pairs_run.run(recalibrate=True, lexicons=LEXICONS)
        self.assertEqual(set(seen), {tier.MERGE_FRACTION})


if __name__ == "__main__":
    unittest.main()
