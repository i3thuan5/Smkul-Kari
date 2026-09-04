"""ingest: check a batch of two-row TSVs, then import it or refuse it all.

The audit here is the one that catches a reader drifting off the sheet it
was given. A misread character is visible; text landing on the wrong
subtitle is not, and nothing downstream can tell afterwards.
"""
import json
import os
import shutil
import tempfile
import unittest

from scripts import datadirs
from scripts.aiyalaeho import ingest
from scripts.ocr import transcripts
from scripts.errors import PipelineError


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="aiya-ingest-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.work = os.path.join(self.tmp, "work")
        self.tsvdir = os.path.join(self.tmp, "tsv")
        os.makedirs(self.work)
        os.makedirs(self.tsvdir)
        cues = []
        for index in (1, 2, 3, 4):
            cues.append({"index": index, "start": index * 10.0,
                         "end": index * 10.0 + 4.0})
        manifest = {
            "lines": [{"name": "formosan", "y": 12, "h": 60},
                      {"name": "han", "y": 72, "h": 64}],
            "cues": cues,
        }
        os.makedirs(os.path.join(self.work, "1-cues"), exist_ok=True)
        self._write_json(datadirs.coarse_cues(self.work), manifest)
        self._write_json(os.path.join(self.work, "sheets.json"),
                         {"sheet_001.png": [1, 2], "sheet_002.png": [3, 4]})
        self._write_json(os.path.join(self.work, "transcripts.json"), {})
        self._write_json(os.path.join(self.work, "verified.json"), {})

    def _write_json(self, path, value):
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False)

    def _tsv(self, name, text):
        path = os.path.join(self.tsvdir, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path

    def _texts(self):
        return transcripts.load_transcripts(self.work)


class TestImport(Fixture):
    def test_two_rows_per_cue_land_on_the_right_lines(self):
        self._tsv("b01.tsv",
                  "1\tformosan\tNga'ay ho^\n"
                  "1\than\t大家好\n"
                  "2\tformosan\tCi Sera kako\n"
                  "2\than\t我是Sera\n")
        ingest.run(self.work, self.tsvdir)
        got = self._texts()
        self.assertEqual(got["1"]["formosan"], "Nga'ay ho^")
        self.assertEqual(got["1"]["han"], "大家好")
        self.assertEqual(got["2"]["han"], "我是Sera")

    def test_a_blank_row_keeps_its_line_and_stays_empty(self):
        # 族語彼逝無字幕ê時，讀者寫 `3<TAB>formosan<TAB>`，尾溜彼个 tab
        # 定定予編輯工具剪掉——補轉去才袂當做「這逝欠一欄」。
        self._tsv("b01.tsv", "1\tformosan\n1\than\t大家好\n")
        ingest.run(self.work, self.tsvdir)
        got = self._texts()
        self.assertEqual(got["1"]["formosan"], "")
        self.assertEqual(got["1"]["han"], "大家好")

    def test_the_import_is_recorded_as_verified(self):
        self._tsv("b01.tsv", "1\tformosan\tx\n1\than\ty\n")
        ingest.run(self.work, self.tsvdir)
        verified = transcripts.load_verified(self.work)
        self.assertTrue(verified["1"]["formosan"])
        self.assertTrue(verified["1"]["han"])

    def test_only_b_files_are_read(self):
        # `b*.tsv` 才是視覺辨識ê批。別ê檔（抽查、筆記）莫食入去——news
        # 彼爿就是予一个 sample.tsv 蓋去，四個月無人看出來。
        self._tsv("b01.tsv", "1\tformosan\tgood\n")
        self._tsv("sample.tsv", "1\tformosan\tstale\n")
        ingest.run(self.work, self.tsvdir)
        self.assertEqual(self._texts()["1"]["formosan"], "good")


class TestRefusals(Fixture):
    def test_a_cue_that_was_not_on_any_sheet_stops_the_batch(self):
        self._tsv("b01.tsv", "1\tformosan\tx\n9\tformosan\ty\n")
        self.assertRaises(PipelineError, ingest.run, self.work, self.tsvdir)
        self.assertEqual(self._texts(), {})

    def test_an_unknown_line_name_stops_the_batch(self):
        # 舊 preset 彼个 `ami` 已經改做 `formosan`：讀者若寫舊名，
        # 規批擋落來，莫予伊恬恬掉落無人看ê所在。
        self._tsv("b01.tsv", "1\tami\tx\n")
        self.assertRaises(PipelineError, ingest.run, self.work, self.tsvdir)
        self.assertEqual(self._texts(), {})

    def test_the_same_cue_in_two_batches_stops_the_batch(self):
        self._tsv("b01.tsv", "1\tformosan\tx\n")
        self._tsv("b02.tsv", "1\tformosan\ty\n")
        self.assertRaises(PipelineError, ingest.run, self.work, self.tsvdir)

    def test_nothing_is_written_when_a_batch_is_refused(self):
        self._tsv("b01.tsv", "1\tformosan\tfine\n")
        ingest.run(self.work, self.tsvdir)
        self._tsv("b02.tsv", "2\tformosan\tok\n3\tformosan\tok\n"
                             "77\tformosan\tstray\n")
        self.assertRaises(PipelineError, ingest.run, self.work, self.tsvdir)
        got = self._texts()
        self.assertIn("1", got)
        self.assertNotIn("2", got)


class TestReport(Fixture):
    def test_with_no_tsv_at_all_it_still_knows_the_episode_size(self):
        # 一批若一个 TSV 都無，猶原愛講規集偌濟條，莫報 0。
        report = ingest.run(self.work, self.tsvdir)
        self.assertEqual(report["files"], 0)
        self.assertEqual(report["cues"], 4)
        self.assertEqual(report["read"], 0)

    def test_it_says_how_much_of_the_episode_is_read(self):
        self._tsv("b01.tsv", "1\tformosan\tx\n1\than\ty\n")
        report = ingest.run(self.work, self.tsvdir)
        self.assertEqual(report["cues"], 4)
        self.assertEqual(report["read"], 1)
        self.assertEqual(sorted(report["unread"]), [2, 3, 4])


if __name__ == "__main__":
    unittest.main()
