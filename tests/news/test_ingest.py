"""ingest: TSV normalisation and the whole-batch rejection rule."""
import json
import os
import tempfile
import unittest
from unittest import mock

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


if __name__ == "__main__":
    unittest.main()
