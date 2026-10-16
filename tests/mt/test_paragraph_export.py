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


if __name__ == "__main__":
    unittest.main()
