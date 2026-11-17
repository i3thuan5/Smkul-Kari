"""news/paragraph_export: the delivery copy and the spot check.

The SRT is now made by pairs_run into Kari-SRT; the export only copies
it with its CSV and counts. The spot check re-pairs a few groups to
show the judge, and refuses when the CSV is not what the pairing makes
-- comparing against the padded time, since that is what the CSV holds:
against the true time every normal CSV would be refused."""
import csv
import os
import tempfile
import unittest

from scripts.errors import PipelineError
from scripts.news import pairs_run
from scripts.news import paragraph_export
from scripts.srtlib import srt
from tests.mt.test_run import LEXICONS, Store

AMIS_NAME = "20210201_032_晚間_Amis_阿美"


def row(start, end, level="高信心", reason=""):
    return {"開始時間": srt.srt_timestamp(start),
            "結束時間": srt.srt_timestamp(end), "族語": "o kawas",
            "華語": "華語", "信心層級": level, "不採用原因": reason}


class TestSummary(unittest.TestCase):
    def test_counts_and_minutes_of_the_csv_time(self):
        # the CSV time carries the padding, like the delivered SRT
        rows = [row(0, 60), row(60, 90, "中信心"),
                row(100, 130, "不採用", reason="幻覺")]
        entry = {"成果檔名": AMIS_NAME, "播出日期": "2021-02-01",
                 "族語別(中)": "阿美", "語言別代號": "ami"}
        got = paragraph_export.summary(entry, rows)
        self.assertEqual((got["雙語字幕條數"], got["高信心"], got["中信心"],
                          got["不採用"]), (2, 1, 1, 1))
        self.assertEqual(got["雙語字幕時長（分）"], "1.5")
        self.assertEqual(got["播出日期"], "2021-02-01")


class TestSpotPick(unittest.TestCase):
    def test_draws_only_high_confidence_and_is_repeatable(self):
        pool = {"a": [row(0, 10), row(10, 20, "中信心"), row(20, 30)],
                "b": [row(0, 10, "不採用", reason="幻覺"), row(10, 20)]}
        first = paragraph_export.spot_pick(pool, 3, seed=1)
        self.assertEqual(sorted(first), [("a", 0), ("a", 2), ("b", 1)])
        self.assertEqual(paragraph_export.spot_pick(pool, 2, seed=7),
                         paragraph_export.spot_pick(pool, 2, seed=7))

    def test_per_tribe_draws_n_of_each_and_reports_the_short_ones(self):
        # 看見族語每族 3 組 × 16 族＝48；某族高信心不足就全收並回報
        pool = {"a1": [row(0, 10), row(10, 20), row(20, 30), row(30, 40)],
                "b1": [row(0, 10), row(10, 20, "中信心")]}
        tribes = {"a1": "阿美", "b1": "邵"}
        chosen, short = paragraph_export.spot_pick_per_tribe(
            pool, tribes, 3, seed=1)
        picked = {}
        for name, _index in chosen:
            picked[tribes[name]] = picked.get(tribes[name], 0) + 1
        self.assertEqual(picked, {"阿美": 3, "邵": 1})
        self.assertEqual(short, {"邵": 1})
        again, _short = paragraph_export.spot_pick_per_tribe(
            pool, tribes, 3, seed=1)
        self.assertEqual(again, chosen)
        for name, index in chosen:
            self.assertEqual(pool[name][index]["信心層級"], "高信心")


class TestWithStore(Store):
    def setUp(self):
        super().setUp()
        self.standard()
        pairs_run.run(recalibrate=True, lexicons=LEXICONS)
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        self.work = work.name

    def test_export_copies_both_layers_and_counts(self):
        rows = paragraph_export.export(["2021-02"],
                                       os.path.join(self.work, "out"))
        self.assertEqual(len(rows), 2)
        out = os.path.join(self.work, "out")
        for rel, stored in (
                (os.path.join("1-雙語字幕", "2021-02", AMIS_NAME + ".srt"),
                 self.srt_out(AMIS_NAME)),
                (os.path.join("2-平行語料", "2021-02", AMIS_NAME + ".csv"),
                 self.out(AMIS_NAME))):
            with open(os.path.join(out, rel), "rb") as a, \
                    open(stored, "rb") as b:
                self.assertEqual(a.read(), b.read())
        with open(os.path.join(out, "3-雙語字幕清單.csv"),
                  encoding="utf-8") as handle:
            listed = list(csv.DictReader(handle))
        self.assertEqual(listed[0]["成果檔名"], AMIS_NAME)

    def test_the_list_covers_everything_delivered_not_just_this_run(self):
        # 清單每 export 一次被覆寫成只剩這次的月份——交件資料夾有 2021-01～02，
        # 清單卻只剩 2021-02（2026-11-16 發現）
        march = "20210301_060_晚間_Amis_阿美"
        self.episode(march, "Amis", "阿美", "ami", "tada ko matini")
        self.write_catalogue()
        pairs_run.run(lexicons=LEXICONS)
        out = os.path.join(self.work, "out")
        paragraph_export.export(["2021-02"], out)
        paragraph_export.export(["2021-03"], out)
        paragraph_export.export(["2021-02"], out)
        with open(os.path.join(out, "3-雙語字幕清單.csv"),
                  encoding="utf-8") as handle:
            names = []
            for r in csv.DictReader(handle):
                names.append(r["成果檔名"])
        self.assertEqual(names, sorted(["20210201_032_晚間_Amis_阿美",
                                        "20210202_033_晚間_Atayal_泰雅",
                                        march]))

    def test_a_month_with_nothing_is_refused(self):
        with self.assertRaises(PipelineError):
            paragraph_export.export(["2021-05"],
                                    os.path.join(self.work, "out"))

    def test_spot_check_accepts_a_csv_holding_the_padded_time(self):
        count = paragraph_export.write_spot(
            ["2021-02"], folder=os.path.join(self.work, "spot"))
        self.assertGreater(count, 0)

    def test_spot_check_refuses_a_csv_out_of_step(self):
        path = self.out(AMIS_NAME)
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        self.assertIn("00:00:19,000", text)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text.replace("00:00:19,000", "00:00:19,500", 1))
        with self.assertRaises(PipelineError) as caught:
            paragraph_export.write_spot(
                ["2021-02"], folder=os.path.join(self.work, "spot"))
        self.assertIn(AMIS_NAME, str(caught.exception))

    def test_a_batch_folder_with_a_request_already_is_refused(self):
        # 第二批會蓋掉 2021-01～02 那批的 request-01／reply-01
        folder = os.path.join(self.work, "spot", "2023")
        paragraph_export.write_spot(["2021-02"], folder=folder)
        request = os.path.join(folder, "request-01-a.tsv")
        with open(request, "rb") as handle:
            before = handle.read()
        with self.assertRaises(PipelineError) as caught:
            paragraph_export.write_spot(["2021-02"], folder=folder)
        self.assertIn("2023", str(caught.exception))
        with open(request, "rb") as handle:
            self.assertEqual(handle.read(), before)

    def test_per_tribe_spot_writes_a_sample(self):
        lines = []
        count = paragraph_export.write_spot(
            ["2021-02"], folder=os.path.join(self.work, "spot", "每族"),
            per_tribe=3, say=lines.append)
        self.assertGreater(count, 0)
        self.assertTrue(lines)   # 合成資料每族不到 3 組，要回報


if __name__ == "__main__":
    unittest.main()
