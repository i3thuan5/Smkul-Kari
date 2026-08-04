"""already_read(): never overwrite a work dir somebody has transcribed.

The incident this pins: re-running gap_sheets over a finished vision pass
would write a fresh transcripts.json/verified.json and throw the reading
away -- the most expensive artefact in the pipeline.
"""
import json
import os
import tempfile
import unittest

from scripts.news import gap_sheets


class TestAlreadyRead(unittest.TestCase):
    def _dir_with_verified(self, payload):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        if payload is not None:
            with open(os.path.join(tmp.name, "verified.json"), "w",
                      encoding="utf-8") as handle:
                json.dump(payload, handle)
        return tmp.name

    def test_no_verified_json_is_untouched_territory(self):
        target = self._dir_with_verified(None)
        self.assertFalse(gap_sheets.already_read(target))

    def test_empty_verified_json_does_not_guard(self):
        self.assertFalse(gap_sheets.already_read(self._dir_with_verified({})))

    def test_any_verified_cue_guards_the_dir(self):
        got = gap_sheets.already_read(self._dir_with_verified({"12": True}))
        self.assertTrue(got)


if __name__ == "__main__":
    unittest.main()
