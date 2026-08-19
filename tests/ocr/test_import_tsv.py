"""Importing text read off the contact sheets, end to end.

This is where a reader's work enters the pipeline, and the two ways it can
go wrong both go wrong quietly. A cue number that belongs to a different
episode puts a whole stretch of subtitle on the wrong lines -- worse than a
misread character, because nothing downstream looks wrong. A partial import
is worse still: the rows that landed are indistinguishable from the rows
that did not, so afterwards nobody can tell which half was read.

So: nothing is written unless everything checks out, and every imported row
is marked human-verified, which is what export-gt trusts when deciding what
may become training data.
"""
import json
import os
import tempfile
import unittest

from scripts.ocr import transcripts


MANIFEST = {
    "lines": [{"name": "han"}],
    "cues": [{"index": 1, "start": 1.0, "end": 2.0},
             {"index": 2, "start": 3.0, "end": 4.0},
             {"index": 3, "start": 5.0, "end": 6.0}],
}


class TestImportTsv(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.work = tmp.name
        self._write("cues.json", json.dumps(MANIFEST, ensure_ascii=False))

    def _write(self, name, text):
        path = os.path.join(self.work, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path

    def _read(self, name):
        path = os.path.join(self.work, name)
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)

    def _tsv(self, text):
        return self._write("batch.tsv", text)

    def test_rows_land_on_their_own_cues(self):
        got = transcripts.import_tsv(self.work, self._tsv("1\t第一句\n3\t第三句\n"))
        self.assertEqual(got, (2, 2, 3))
        self.assertEqual(self._read("transcripts.json"),
                         {"1": {"han": "第一句"}, "3": {"han": "第三句"}})

    def test_imported_rows_are_marked_human_verified(self):
        transcripts.import_tsv(self.work, self._tsv("1\t第一句\n"))
        self.assertEqual(self._read("verified.json"), {"1": {"han": True}})

    def test_a_blank_cue_is_recorded_as_blank(self):
        # A reader confirming "there is no subtitle here" is information, and
        # it is what stops the cue being read again on the next pass.
        transcripts.import_tsv(self.work, self._tsv("1\than\t\n"))
        self.assertEqual(self._read("transcripts.json"), {"1": {"han": ""}})
        self.assertEqual(self._read("verified.json"), {"1": {"han": True}})

    def test_a_second_batch_merges(self):
        transcripts.import_tsv(self.work, self._tsv("1\t第一句\n"))
        transcripts.import_tsv(self.work, self._tsv("2\t第二句\n"))
        self.assertEqual(sorted(self._read("transcripts.json")), ["1", "2"])

    def test_replace_discards_what_was_there(self):
        transcripts.import_tsv(self.work, self._tsv("1\t第一句\n"))
        transcripts.import_tsv(self.work, self._tsv("2\t第二句\n"), replace=True)
        self.assertEqual(sorted(self._read("transcripts.json")), ["2"])

    def test_a_cue_from_another_episode_is_refused(self):
        tsv = self._tsv("1\t第一句\n99\t漂走了\n")
        with self.assertRaises(SystemExit):
            transcripts.import_tsv(self.work, tsv)

    def test_nothing_is_written_when_a_row_is_refused(self):
        # The whole batch or none of it -- a half-imported file leaves no
        # trace of which rows made it.
        tsv = self._tsv("1\t第一句\n99\t漂走了\n")
        with self.assertRaises(SystemExit):
            transcripts.import_tsv(self.work, tsv)
        self.assertIsNone(self._read("transcripts.json"))
        self.assertIsNone(self._read("verified.json"))

    def test_an_unknown_line_name_is_refused(self):
        tsv = self._tsv("1\tamis\tnot a line\n")
        with self.assertRaises(SystemExit):
            transcripts.import_tsv(self.work, tsv)

    def test_a_row_with_no_index_is_refused(self):
        tsv = self._tsv("x\t第一句\n")
        with self.assertRaises(SystemExit):
            transcripts.import_tsv(self.work, tsv)

    def test_coverage_counts_cues_not_rows(self):
        _imported, covered, total = transcripts.import_tsv(
            self.work, self._tsv("1\t第一句\n2\t第二句\n"))
        self.assertEqual((covered, total), (2, 3))


if __name__ == "__main__":
    unittest.main()
