"""ingest: TSV normalisation and the whole-batch rejection rule."""
import json
import os
import tempfile
import unittest
from unittest import mock

from scripts.news import paths
from scripts.news import ingest
from scripts.errors import PipelineError


class TestNormalise(unittest.TestCase):
    def _roundtrip(self, content):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "b01.tsv")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(content)
            rows = ingest.normalise(path)
            with open(path, encoding="utf-8") as handle:
                written = handle.read()
        return rows, written

    def test_blank_cue_gets_its_tab_back(self):
        # the Write tool trims the trailing tab off confirmed-blank rows;
        # ingest restores it instead of asking agents to fix it themselves
        rows, written = self._roundtrip("5\than\n")
        self.assertEqual(rows, ["5\than\t"])
        self.assertEqual(written, "5\than\t\n")

    def test_full_rows_pass_through(self):
        rows, _ = self._roundtrip("7\than\t大家好\n")
        self.assertEqual(rows, ["7\than\t大家好"])

    def test_empty_lines_are_dropped(self):
        rows, _ = self._roundtrip("1\than\t甲\n\n  \n2\than\t乙\n")
        self.assertEqual(len(rows), 2)

    def test_rows_come_out_in_cue_order(self):
        # The sheets are packed widest-with-widest, so one sheet carries
        # 703, 612, 699... and a reader writes them down in the order it
        # sees them. `Kari-SRT/` has to be readable by a person, and a
        # TSV whose numbers jump about is not.
        rows, written = self._roundtrip(
            "703\than\t丙\n612\than\t甲\n699\than\t乙\n")
        self.assertEqual(rows, ["612\than\t甲", "699\than\t乙",
                                "703\than\t丙"])
        self.assertEqual(written,
                         "612\than\t甲\n699\than\t乙\n703\than\t丙\n")

    def test_the_two_lines_of_one_cue_keep_their_order(self):
        # 開會了 puts the formosan line above the han one and the reader
        # writes them in that order; sorting must not swap them, and
        # `12` must not sort before `9` as text would.
        rows, _ = self._roundtrip("12\tformosan\tA\n12\than\t乙\n"
                                  "9\tformosan\tB\n9\than\t甲\n")
        self.assertEqual(rows, ["9\tformosan\tB", "9\than\t甲",
                                "12\tformosan\tA", "12\than\t乙"])

    def test_a_blank_row_is_sorted_like_any_other(self):
        rows, _ = self._roundtrip("8\than\n3\than\t甲\n")
        self.assertEqual(rows, ["3\than\t甲", "8\than\t"])

    def test_an_unnumbered_row_is_kept_for_the_audit_to_reject(self):
        # A row with no cue number is a rejected batch, not a crash:
        # `_audit_row` is the one place that decides that.
        rows, _ = self._roundtrip("5\than\t甲\nxx\than\t乙\n")
        self.assertEqual(len(rows), 2)
        self.assertIn("xx\than\t乙", rows)


class TestBatchRejection(unittest.TestCase):
    """A TSV naming a cue that was on no sheet must sink the whole batch."""

    def _run(self, sheet_cues, tsv_body):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        work = os.path.join(tmp.name, "ep.B.work")
        os.makedirs(work)
        with open(os.path.join(work, "sheets.json"), "w",
                  encoding="utf-8") as handle:
            json.dump({"sheet_001.png": sheet_cues}, handle)
        tsvdir = os.path.join(tmp.name, "tsv")
        os.makedirs(tsvdir)
        with open(os.path.join(tsvdir, "b01.tsv"), "w",
                  encoding="utf-8") as handle:
            handle.write(tsv_body)
        argv = ["ingest", "ep", tsvdir]
        with mock.patch.object(ingest, "WORK", tmp.name):
            with mock.patch("sys.argv", argv):
                ingest.main()

    def test_cue_not_on_any_sheet_rejects_the_batch(self):
        with self.assertRaises(PipelineError):
            self._run([1, 2, 3], "1\than\t甲\n99\than\t亂入\n")

    def test_bad_index_rejects_the_batch(self):
        with self.assertRaises(PipelineError):
            self._run([1, 2, 3], "x\than\t甲\n")


class TestOnlyBatchFiles(unittest.TestCase):
    """`b*.tsv` ê 才是視覺辨識ê批，其他 TSV 莫提。

    Store 內底 644 个 TSV，643 个是 `b<N>.tsv`；賰彼一个是
    20210209_040 ê `sample.tsv`——逐 72 條抽 4 條ê抽查檔，內容本底
    就是對 `b*.tsv` 抄ê，ingest 伊嘛加無半字。

    毋過伊坐佇 ingest ê路頂：`_audit_row` 看著仝一个 cue 編號出現
    佇兩个檔就報錯，所以彼集ê ingest **本底就走袂過**（進前無走
    過，才無人發現）。重新編號了後閣較歹——`sample.tsv` 是照舊編號
    索引ê，這馬指去別條 cue。

    收斂 glob 是上細ê改法：合約本底就是 `b*.tsv`，而且store 內底
    若閣有別款附屬檔，管線袂閣予人絆倒。
    """

    def _dir(self, *files):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        work = os.path.join(tmp.name, "ep.B.work")
        os.makedirs(work)
        with open(os.path.join(work, "sheets.json"), "w",
                  encoding="utf-8") as handle:
            json.dump({"sheet_001.png": [1, 2]}, handle)
        cues = []
        for n in (1, 2):
            cues.append({"index": n, "start": n * 1.0, "end": n * 1.0 + 0.8})
        os.makedirs(os.path.join(work, "1-cues"), exist_ok=True)
        with open(paths.coarse_cues(work), "w",
                  encoding="utf-8") as handle:
            json.dump({"cues": cues,
                       "lines": [{"name": "han"}]}, handle)
        with open(os.path.join(work, "transcripts.json"), "w",
                  encoding="utf-8") as handle:
            json.dump({"1": {"han": ""}, "2": {"han": ""}}, handle)
        tsvdir = os.path.join(tmp.name, "tsv")
        os.makedirs(tsvdir)
        for name, body in files:
            with open(os.path.join(tsvdir, name), "w",
                      encoding="utf-8") as handle:
                handle.write(body)
        return tmp.name, tsvdir

    def test_a_stray_tsv_does_not_collide(self):
        root, tsvdir = self._dir(("b01.tsv", "1\than\t甲\n2\than\t乙\n"),
                                 ("sample.tsv", "1\than\t舊ê甲\n"))
        with mock.patch.object(ingest, "WORK", root):
            with mock.patch("sys.argv", ["ingest", "ep", tsvdir]):
                ingest.main()          # 莫掔錯

    def test_batch_files_are_still_audited(self):
        root, tsvdir = self._dir(("b01.tsv", "1\than\t甲\n"),
                                 ("b02.tsv", "1\than\t重耽\n"))
        with mock.patch.object(ingest, "WORK", root):
            with mock.patch("sys.argv", ["ingest", "ep", tsvdir]):
                with self.assertRaises(PipelineError):
                    ingest.main()


if __name__ == "__main__":
    unittest.main()
