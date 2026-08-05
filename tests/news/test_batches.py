"""batches: which sheets are offered, and where their TSVs are told to go."""
import json
import os
import tempfile
import unittest
from unittest import mock

from scripts.news import batches


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

    ENTRY = {"slug": "2021_041_2021-02-10_午間_Cou_鄒",
             "srt_name": "20210210_041_午間_Cou_鄒"}

    def _inventory(self, entries):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = os.path.join(tmp.name, "inventory.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(entries, handle, ensure_ascii=False)
        return path

    def test_name_comes_from_the_inventory(self):
        path = self._inventory([self.ENTRY])
        with mock.patch.object(batches.paths, "INVENTORY", path):
            got = batches.srt_name_of(self.ENTRY["slug"])
        self.assertEqual(got, self.ENTRY["srt_name"])

    def test_unknown_slug_stops_rather_than_guessing_a_folder(self):
        path = self._inventory([self.ENTRY])
        with mock.patch.object(batches.paths, "INVENTORY", path):
            with self.assertRaises(SystemExit):
                batches.srt_name_of("2021_999_2021-01-01_午間_Nope_無")


if __name__ == "__main__":
    unittest.main()
