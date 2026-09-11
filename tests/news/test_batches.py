"""batches: which sheets are offered, and where their TSVs are told to go."""
import csv
import json
import os
import tempfile
import unittest
from unittest import mock

from scripts import catalogue_checks as checks
from scripts.news import batches
from scripts.news.vision_tools import prompt
from scripts.errors import PipelineError


class TestPendingSheets(unittest.TestCase):
    def _work(self, sheets, verified):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        with open(os.path.join(tmp.name, "sheets.json"), "w",
                  encoding="utf-8") as handle:
            json.dump(sheets, handle)
        if verified is not None:
            with open(os.path.join(tmp.name, "verified.json"), "w",
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


class TestBatchBoundaries(unittest.TestCase):
    """佗位切批，佮 `prompt` 敢切仝款。

    這兩支愛講仝款ê話：`batches` 發 TSV ê名（b01、b02…），`prompt`
    照彼个號碼寫讀者提示。058晨 壓 2000 了後是 51 張，佇彼个張數，
    遮本底ê `range(0, total, size)` 會生第三批 3 張，`prompt.plan`
    soah kā彼 3 張倂入 b02——**仝一批 cue hőng派兩擺、掛兩个名**，
    `ingest` 就kā規集擋落來（「cue X 佇兩个檔攏有」）。批次大小
    對 24 改做 4 了後，尾批短ê情形變做常態，這條愛先鎖起來。
    """

    def test_a_short_tail_is_folded_the_same_way_prompt_folds_it(self):
        self.assertEqual(batches.spans(51),
                         prompt.plan(51, prompt.SIZE, prompt.MIN_TAIL))

    def test_no_sheet_count_disagrees_with_prompt(self):
        for total in range(1, 200):
            self.assertEqual(
                batches.spans(total),
                prompt.plan(total, prompt.SIZE, prompt.MIN_TAIL),
                "%d 張切法無仝" % total)

    def test_an_explicit_size_is_still_honoured(self):
        self.assertEqual(batches.spans(10, 3),
                         prompt.plan(10, 3, prompt.MIN_TAIL))

    def test_the_default_size_is_prompts_not_a_second_copy(self):
        """遮**無**家己ê預設值。

        本底兩爿各有一个 24，改一爿袂記得改另外一爿就恬恬走精。
        """
        self.assertEqual(batches.spans(51), batches.spans(51, prompt.SIZE))
