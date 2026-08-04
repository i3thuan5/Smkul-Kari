"""batches.pending_sheets: only sheets with unverified cues are offered."""
import json
import os
import tempfile
import unittest

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


if __name__ == "__main__":
    unittest.main()
