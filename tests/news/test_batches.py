"""batches: which sheets are offered, and where their TSVs are told to go."""
import csv
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from scripts import catalogue_checks as checks
from scripts.news import batches
from scripts.news import paths
from scripts.news.vision_tools import prompt
from scripts.errors import PipelineError


class TestPendingSheets(unittest.TestCase):
    def _work(self, sheets, verified):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        os.makedirs(os.path.dirname(paths.sheets_index(tmp.name)))
        with open(paths.sheets_index(tmp.name), "w",
                  encoding="utf-8") as handle:
            json.dump(sheets, handle)
        if verified is not None:
            os.makedirs(os.path.dirname(paths.verified_file(tmp.name)))
            with open(paths.verified_file(tmp.name), "w",
                      encoding="utf-8") as handle:
                json.dump(verified, handle)
        return tmp.name

    SHEETS = {"sheet_001.png": [1, 2], "sheet_002.png": [3, 4]}

    def test_everything_pending_without_verified_json(self):
        got = batches.pending_sheets(self._work(self.SHEETS, None))
        self.assertEqual(len(got), 2)

    def test_fully_verified_sheet_is_not_offered_again(self):
        verified = {"1": True, "2": True, "3": True}
        got = batches.pending_sheets(self._work(self.SHEETS, verified))
        names = []
        for name, cues in got:
            names.append(name)
        self.assertEqual(names, ["sheet_002.png"])

    def test_verified_false_still_counts_as_pending(self):
        verified = {"1": True, "2": False}
        got = batches.pending_sheets(self._work(self.SHEETS, verified))
        self.assertEqual(len(got), 2)

    def test_nothing_pending_when_all_verified(self):
        verified = {"1": True, "2": True, "3": True, "4": True}
        got = batches.pending_sheets(self._work(self.SHEETS, verified))
        self.assertEqual(got, [])


class TestSrtNameOf(unittest.TestCase):
    """The TSV folder must be the srt_name, because that is what ingest.py
    and rebuild.py look under. The slug carries the same fields in another
    order, so a name derived from it lands the reading where nothing reads
    it -- and the only symptom is an episode that assembles empty."""

    ROW = {"成果檔名": "20210210_041_午間_Cou_鄒",
           "節目名稱": "午間族語新聞", "年度": "2021", "集數": "41",
           "播出日期": "2021-02-10", "族語別(英)": "Cou",
           "族語別(中)": "鄒", "語言別": "", "語言別代號": "tsu",
           "原始影片檔案位置":
               "ilrdf-corpus/族語新聞/21NL003_41午間族語新聞.mp4",
           "備註": ""}
    SLUG = "2021_041_2021-02-10_午間_Cou_鄒"

    def _table(self, rows):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = os.path.join(tmp.name, "smkul.csv")
        head = list(checks.head(checks.NEWS_KEYS)) + [
            "原始影片檔案位置", "備註"]
        with open(path, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=head)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
        return path

    def test_name_comes_from_the_catalogue(self):
        path = self._table([self.ROW])
        with mock.patch.object(batches.paths, "TRACKER_STORE", path):
            got = batches.srt_name_of(self.SLUG)
        self.assertEqual(got, self.ROW["成果檔名"])

    def test_unknown_slug_stops_rather_than_guessing_a_folder(self):
        path = self._table([self.ROW])
        with mock.patch.object(batches.paths, "TRACKER_STORE", path):
            with self.assertRaises(PipelineError):
                batches.srt_name_of("2021_999_2021-01-01_午間_Nope_無")


if __name__ == "__main__":
    unittest.main()


class TestOneListForBothTools(unittest.TestCase):
    """`batches` 發 TSV 名、`prompt` 照彼个號碼寫判準——兩爿愛仝一份清單。

    本底 `batches` 對「猶未核實ê圖」切、`prompt.brief()` 對「全部圖」
    切，讀到一半了後兩爿ê第 N 批內容無仝（058晨 51 張彼擺，一爿 3 批、
    一爿 2 批），而且攏對 b01 起算，會kā已經收入 Kari-SRT ê b01.tsv
    蓋掉，無一个所在報錯。
    """

    SLUG = "2021_055_2021-02-24_午間_Cou_鄒"
    NAME = "20210224_055_午間_Cou_鄒"

    def setUp(self):
        from tests.news.test_vision_prompt import sheets_of, write_book
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = tmp.name
        self.work = paths.work_dir(self.SLUG, os.path.join(tmp.name, "w"))
        write_book(self.work, sheets_of(100))
        self.vision = os.path.join(tmp.name, "vision")
        for name, value in (("WORK", os.path.join(tmp.name, "w")),
                            ("KARI_VISION", self.vision)):
            patcher = mock.patch.object(paths, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch.object(batches, "WORK",
                                    os.path.join(tmp.name, "w"))
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = mock.patch.object(batches, "srt_name_of",
                                    return_value=self.NAME)
        patcher.start()
        self.addCleanup(patcher.stop)

    def verify(self, lo, hi):
        path = paths.verified_file(self.work)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        marked = {}
        for cue in range(lo, hi + 1):
            marked[str(cue)] = {"han": True}
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(marked, handle)

    def tsv(self, name, lo, hi):
        folder = paths.stage_path(self.vision, self.NAME)
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, name), "w", encoding="utf-8") as fh:
            for cue in range(lo, hi + 1):
                fh.write("%d\than\t字\n" % cue)

    def listed(self):
        buf = io.StringIO()
        with redirect_stdout(buf), \
                mock.patch("sys.argv", ["batches", self.SLUG]):
            batches.main()
        out = []
        for line in buf.getvalue().splitlines():
            if line.startswith("SHEETS "):
                out.append([line.split()[1:]])
            if line.startswith("TSV "):
                out[-1].append(os.path.basename(line.split()[1]))
        return out

    def test_both_tools_hand_out_the_same_batches(self):
        planned = prompt.batches_of(self.work)
        got = self.listed()
        self.assertEqual(len(got), len(planned))
        for (names, tsv), batch in zip(got, planned):
            self.assertEqual(names, batch)
        self.assertEqual(got[0][1], "b01.tsv")

    def test_a_half_read_episode_numbers_on_from_what_is_in(self):
        self.verify(1, 200)
        self.tsv("b01.tsv", 1, 100)
        self.tsv("b02.tsv", 101, 200)
        got = self.listed()
        names = []
        for _sheets, tsv in got:
            names.append(tsv)
        self.assertEqual(names[0], "b03.tsv")
        self.assertNotIn("b01.tsv", names)
        self.assertNotIn("b02.tsv", names)
        planned = prompt.batches_of(self.work)
        for (sheets, _tsv), batch in zip(got, planned):
            self.assertEqual(sheets, batch)

    def test_the_size_option_is_gone(self):
        with mock.patch("sys.argv", ["batches", self.SLUG, "--size", "4"]):
            with self.assertRaises(SystemExit):
                with redirect_stderr(io.StringIO()):
                    batches.main()
