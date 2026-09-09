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
# `refined` is not decoration: publish only takes a refined timeline into
# the store, so a fixture without it is an episode publish is right to
# refuse. 見 tests/news/test_publish_refined_only.py。
CUES = {"duration": 2880.0, "refined": True,
        "cues": [{"index": 1, "start": 1.0, "end": 2.0}]}


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
        os.makedirs(os.path.join(done, "1-cues"))
        self._json(paths.coarse_cues(done), CUES)
        self._json(os.path.join(done, "verified.json"), {"1": {"han": True}})
        self._staged(self.cues_dir, ".json", json.dumps(CUES))
        self._staged(self.srt_dir, ".srt", SRT)

    def _staged(self, base, suffix, text):
        """A store file where the month layer puts it."""
        path = paths.stage_path(base, ENTRY["srt_name"], suffix)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)

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

    def test_an_unfinished_episode_is_skipped_not_refused(self):
        # No .B.work at all: registered, but nobody has read it yet. It is
        # simply not published -- it is not an error. Returning non-zero
        # here made batch scripts read "not my turn yet" as "something
        # broke" (2026-09-09: gate is per-episode).
        self._json(self.inventory, [dict(ENTRY, pending=True)])
        self.assertEqual(self._run(), 0)
        with open(self.inventory, encoding="utf-8") as handle:
            written = json.load(handle)
        self.assertTrue(written[0]["pending"])
        month = os.path.join(self.cues_dir,
                             paths.month_of(ENTRY["srt_name"]))
        self.assertFalse(os.path.exists(month))

    def test_a_finished_episode_goes_out_beside_an_unread_one(self):
        # Per-episode (2026-09-09): the finished one is published, the one
        # still being read keeps its pending flag and puts nothing in the
        # store. It used to be all-or-nothing, which is what kept 006午 --
        # cut, refined, read and verified -- out of the store because 58
        # other January episodes had not been cut.
        other = dict(ENTRY, slug="9999_002_1999-01-02_午間_Test_測試",
                     srt_name="19990102_002_午間_Test_測試", pending=True)
        self._json(self.inventory, [dict(ENTRY, pending=True), other])
        self._finished_episode()
        self.assertEqual(self._run(), 0)
        month = os.path.join(self.cues_dir,
                             paths.month_of(ENTRY["srt_name"]))
        self.assertEqual(os.listdir(month),
                         [ENTRY["srt_name"] + ".json"])
        with open(self.inventory, encoding="utf-8") as handle:
            written = json.load(handle)
        by = {}
        for one in written:
            by[one["srt_name"]] = one
        self.assertNotIn("pending", by[ENTRY["srt_name"]])
        self.assertTrue(by[other["srt_name"]]["pending"])

    def test_the_store_copy_is_rewritten_readable_not_copied_byte_wise(self):
        """Store ê JSON 愛照〈Kari-SRT/ ê內容愛人讀有〉排版過。

        本底是 `shutil.copy2`，共工作目錄彼份原封不動搬入去。工作目錄
        彼份是切 cue ê時陣寫ê，鍵ê順序是插入順序；store 彼爿ê正本是
        排序過ê。按呢一擺 publish 就共 store 排好ê排版蓋轉去舊款，
        兩爿來回反——2026-09-09 實際踏著：一擺 publish 共 74 份已經
        定版ê檔攏改著，內容一模一樣，干焦鍵序無仝。
        """
        self._json(self.inventory, [dict(ENTRY, pending=True)])
        self._finished_episode()
        self.assertEqual(self._run(), 0)
        target = paths.stage_path(self.cues_dir, ENTRY["srt_name"], ".json")
        with open(target, encoding="utf-8") as handle:
            body = handle.read()
        self.assertEqual(body, json.dumps(CUES, ensure_ascii=False,
                                          indent=2, sort_keys=True) + "\n")
        self.assertEqual(json.loads(body), CUES)

    def test_republishing_does_not_change_the_stored_bytes(self):
        """已經定版ê集閣走一擺 publish，store 內底ê byte 袂使振動。"""
        self._json(self.inventory, [dict(ENTRY, pending=True)])
        self._finished_episode()
        self._run()
        target = paths.stage_path(self.cues_dir, ENTRY["srt_name"], ".json")
        with open(target, "rb") as handle:
            first = handle.read()
        self._run()
        with open(target, "rb") as handle:
            second = handle.read()
        self.assertEqual(first, second)

    def test_a_delivered_episode_needs_no_work_dir(self):
        # Work dirs are caches and get cleared away once published. Nothing
        # pending, nothing to copy -- but the tracker is still written.
        self._staged(self.cues_dir, ".json", json.dumps(CUES))
        self._staged(self.srt_dir, ".srt", SRT)
        self.assertEqual(self._run(), 0)
        self.assertEqual(len(self._rows(self.store_tracker)), 1)


if __name__ == "__main__":
    unittest.main()
