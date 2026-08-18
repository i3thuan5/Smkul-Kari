"""Which smkul.csv is a deliverable, and which is a scratch copy.

Two tables, and mixing them up breaks the one guarantee the store makes.
`make_all` runs while a batch is half done, so its rows say things like
待處理（尚未切cue） -- a state that lives in the work dir. `rebuild` has no
work dir, so it can never reproduce such a row, and a table holding one can
never be verified byte-for-byte again.

So make_all writes to kithann/out/ and publish writes the deliverable, only
once every episode in the batch is finished.
"""
import csv
import json
import os
import tempfile
import unittest
from unittest import mock

from scripts.news import make_all
from scripts.news import paths
from scripts.news import publish


ENTRY = {
    "節目名稱": "午間族語新聞",
    "年度": "2021",
    "集數": "41",
    "播出日期": "2021-02-10",
    "播出時段": "午間",
    "族語別(英)": "Cou",
    "族語別(中)": "鄒",
    "video": "ilrdf-corpus/族語新聞/21NL003_41午間族語新聞.mp4",
    "文稿位置": "",
    "truncated": "",
    "slug": "9999_001_1999-01-01_午間_Test_測試",
    "srt_name": "19990101_001_午間_Test_測試",
}

SRT = "1\n00:00:01,000 --> 00:00:02,000\n測試\n"
CUES = {"cues": [{"index": 1, "start": 1.0, "end": 2.0}]}


class Fixture(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = tmp.name
        # The store is a directory of its own so that the inventory publish
        # reads and the one it writes are still two files, as they are today.
        self.store = self._dir("store")
        self.srt_dir = self._dir("store/srt")
        self.cues_dir = self._dir("store/cues")
        self.work = self._dir("work")
        self.cache = os.path.join(self.root, "cache-smkul.csv")
        self.inventory = os.path.join(self.root, "inventory.json")
        self._json(self.inventory, [dict(ENTRY)])

    def _dir(self, name):
        path = os.path.join(self.root, name)
        os.makedirs(path, exist_ok=True)
        return path

    def _json(self, path, value):
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False)

    def _finished_episode(self):
        """The state publish accepts: cues cut, all checked, SRT built."""
        done = os.path.join(self.work, ENTRY["slug"] + ".B.work")
        os.makedirs(done)
        self._json(os.path.join(done, "cues.json"), CUES)
        self._json(os.path.join(done, "verified.json"), {"1": {"han": True}})
        self._json(os.path.join(self.cues_dir, ENTRY["srt_name"] + ".json"),
                   CUES)
        with open(os.path.join(self.srt_dir, ENTRY["srt_name"] + ".srt"),
                  "w", encoding="utf-8") as handle:
            handle.write(SRT)

    def _rows(self, path):
        with open(path, encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))

    @property
    def store_tracker(self):
        # the delivered table sits at the corpus level of the store, beside
        # inventory.json -- not inside the SRT stage directory
        return os.path.join(self.store, "smkul.csv")


class TestMakeAllWritesTheScratchCopy(Fixture):
    def _run(self):
        with mock.patch.object(paths, "INVENTORY", self.inventory), \
             mock.patch.object(paths, "TRACKER_CACHE", self.cache), \
             mock.patch.object(make_all, "SRT_DIR", self.srt_dir), \
             mock.patch.object(make_all, "WORK", self.work):
            make_all.main()

    def test_writes_the_working_copy(self):
        self._run()
        rows = self._rows(self.cache)
        self.assertEqual(len(rows), 1)
        # Nothing has been cut, so the row names a work-dir state -- exactly
        # the kind of row rebuild could not reproduce.
        self.assertIn("尚未切cue", rows[0]["字幕srt狀態"])

    def test_does_not_touch_the_deliverable(self):
        self._run()
        self.assertFalse(os.path.exists(self.store_tracker))

    def test_lists_pending_episodes_too(self):
        # The working copy is where you look to see how far the batch has
        # got, so it shows the episodes still being worked on. The delivered
        # table is the one that leaves them out.
        self._json(self.inventory, [dict(ENTRY, pending=True)])
        self._run()
        self.assertEqual(len(self._rows(self.cache)), 1)


class TestPublishWritesTheDeliverable(Fixture):
    def _run(self):
        with mock.patch.object(paths, "INVENTORY", self.inventory), \
             mock.patch.object(paths, "SRT_DIR", self.srt_dir), \
             mock.patch.object(paths, "KARI_CUES", self.cues_dir), \
             mock.patch.object(paths, "KARI_FROM_RTF",
                               self._dir("store/from_rtf")), \
             mock.patch.object(paths, "KARI", self.store), \
             mock.patch.object(paths, "TRACKER_STORE",
                               self.store_tracker), \
             mock.patch.object(publish, "WORK", self.work):
            return publish.main([])

    def test_writes_the_deliverable_when_the_batch_is_done(self):
        self._json(self.inventory, [dict(ENTRY, pending=True)])
        self._finished_episode()
        self.assertEqual(self._run(), 0)
        rows = self._rows(self.store_tracker)
        self.assertEqual(len(rows), 1)
        self.assertIn("Claude Vision OCR", rows[0]["字幕srt狀態"])

    def test_clears_the_pending_flag_once_published(self):
        self._json(self.inventory, [dict(ENTRY, pending=True)])
        self._finished_episode()
        self._run()
        with open(self.inventory, encoding="utf-8") as handle:
            written = json.load(handle)
        self.assertNotIn("pending", written[0])

    def test_refuses_while_a_pending_episode_is_unfinished(self):
        # No .B.work at all: registered, but nobody has read it yet.
        self._json(self.inventory, [dict(ENTRY, pending=True)])
        self.assertEqual(self._run(), 1)
        self.assertFalse(os.path.exists(self.store_tracker))

    def test_writes_nothing_at_all_when_blocked(self):
        # All-or-nothing: a second, finished episode must not be published
        # while the first is still being read, or the store ends up holding
        # inputs for a deliverable that is not there.
        other = dict(ENTRY, slug="other", srt_name="other", pending=True)
        self._json(self.inventory, [dict(ENTRY, pending=True), other])
        self._finished_episode()
        self.assertEqual(self._run(), 1)
        self.assertEqual(os.listdir(self.cues_dir), [ENTRY["srt_name"]
                                                     + ".json"])

    def test_a_delivered_episode_needs_no_work_dir(self):
        # Work dirs are caches and get cleared away once published. Nothing
        # pending, nothing to copy -- but the tracker is still written.
        self._json(self.cues_dir + "/" + ENTRY["srt_name"] + ".json", CUES)
        with open(os.path.join(self.srt_dir, ENTRY["srt_name"] + ".srt"),
                  "w", encoding="utf-8") as handle:
            handle.write(SRT)
        self.assertEqual(self._run(), 0)
        self.assertEqual(len(self._rows(self.store_tracker)), 1)


if __name__ == "__main__":
    unittest.main()
