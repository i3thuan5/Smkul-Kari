"""`pending`: an episode registered but not finished yet.

The inventory has to name an episode before anyone can work on it -- the
batching, the reader hand-off and the import all look each episode's naming
up in it. But the inventory is the store's, and the store's whole claim is
that everything it names can be rebuilt from what it holds. A newly
registered episode has nothing to rebuild from yet.

`pending` is what lets both be true: registered, and not yet claimed as
delivered. Rebuild skips those episodes and leaves them out of the tracker,
so the store stays self-consistent all the way through a batch.

What it must NOT become is a way to make a missing file stop being missing.
An episode with no `pending` flag is a claim that it is delivered, and that
claim is checked.
"""
import json
import os
import tempfile
import unittest
from unittest import mock

from scripts.news import paths
from scripts.news import rebuild
from scripts.news import tracker


def entry(name, **extra):
    base = {
        "節目名稱": "午間族語新聞", "年度": "2021", "集數": "41",
        "播出日期": "2021-02-10", "播出時段": "午間",
        "族語別(英)": "Cou", "族語別(中)": "鄒",
        "video": "ilrdf-corpus/x.mp4", "文稿位置": "",
        "truncated": "", "slug": name, "srt_name": name,
    }
    base.update(extra)
    return base


class TestRebuildSkipsPending(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = tmp.name
        self.cues = os.path.join(self.root, "cues")
        self.srt = os.path.join(self.root, "srt")
        self.vision = os.path.join(self.root, "vision")
        for path in (self.cues, self.srt, self.vision):
            os.makedirs(path)
        self.patches = [
            mock.patch.object(paths, "KARI_CUES", self.cues),
            mock.patch.object(paths, "SRT_DIR", self.srt),
            mock.patch.object(paths, "KARI_VISION", self.vision),
            mock.patch.object(paths, "KARI_VISION_RTF",
                              os.path.join(self.root, "vision-rtf")),
        ]
        for patch in self.patches:
            patch.start()
            self.addCleanup(patch.stop)

    def _delivered(self, name):
        """Everything the store must hold for a delivered episode."""
        with open(os.path.join(self.cues, name + ".json"), "w",
                  encoding="utf-8") as handle:
            json.dump({"cues": [{"index": 1, "start": 1.0, "end": 2.0}]},
                      handle)
        with open(os.path.join(self.srt, name + ".srt"), "w",
                  encoding="utf-8") as handle:
            handle.write("1\n00:00:01,000 --> 00:00:02,000\n測試\n")
        os.makedirs(os.path.join(self.vision, name))
        with open(os.path.join(self.vision, name, "b01.tsv"), "w",
                  encoding="utf-8") as handle:
            handle.write("1\than\t測試\n")

    def test_a_pending_episode_is_not_reported_as_missing(self):
        self._delivered("done")
        problems = rebuild.check_inputs(
            [entry("done"), entry("new", pending=True)])
        self.assertEqual(problems, [])

    def test_a_pending_episode_gets_no_tracker_row(self):
        # Otherwise the store's smkul.csv would gain a row for an episode
        # with no status anyone can derive from the store.
        def status(_entry):
            return tracker.vision_status(1)

        rows = tracker.tracker_rows(
            [entry("done"), entry("new", pending=True)], status)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["集數"], "41")

    def test_a_non_pending_episode_still_has_to_be_there(self):
        # pending is a declaration, not an exemption: drop the flag and the
        # missing files are missing again.
        problems = rebuild.check_inputs([entry("new")])
        self.assertTrue(problems)


if __name__ == "__main__":
    unittest.main()
