"""add_episodes: naming a fetched video, and the truncated-entry rule."""
import json
import os
import tempfile
import unittest
from unittest import mock

from scripts.news import add_episodes


ROW = {
    "節目名稱": "晚間族語新聞",
    "年度": "2021",
    "集數": "38",
    "播出日期": "2021-02-07",
    "播出時段": "晚間",
    "族語別(英)": "Pinuyumayan",
    "族語別(中)": "卑南",
    "文稿位置": "kithann/tongan/110年2月_族語新聞文稿/1100207 1800原視新聞_卑南",
}
REMOTE = "族語新聞/110.1-110.10/7月/21NL004_38晚間族語新聞.mp4"
CATALOGUE = {"21NL004_38晚間族語新聞.mp4": ROW}


class TestEntry(unittest.TestCase):
    def test_named_the_same_way_as_the_february_batch(self):
        entry, problem = add_episodes.entry_for(REMOTE, CATALOGUE)
        self.assertEqual(problem, "")
        self.assertEqual(entry["srt_name"], "20210207_038_晚間_Pinuyumayan_卑南")
        self.assertEqual(entry["slug"],
                         "2021_038_2021-02-07_晚間_Pinuyumayan_卑南")

    def test_video_is_recorded_where_it_actually_lives(self):
        # The file is deleted as soon as its cues are cut, so an absolute
        # local path would name something that is not there.
        entry, _ = add_episodes.entry_for(REMOTE, CATALOGUE)
        self.assertEqual(entry["video"], "ilrdf-corpus/" + REMOTE)

    def test_transcript_path_is_relative_to_the_corpus_root(self):
        entry, _ = add_episodes.entry_for(REMOTE, CATALOGUE)
        self.assertEqual(entry["文稿位置"],
                         "110年2月_族語新聞文稿/1100207 1800原視新聞_卑南")

    def test_episode_missing_from_the_catalogue_is_reported_not_guessed(self):
        entry, problem = add_episodes.entry_for(REMOTE, {})
        self.assertIsNone(entry)
        self.assertIn("catalogue", problem)


class TestMerge(unittest.TestCase):
    def _inventory(self, entries):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = os.path.join(tmp.name, "inventory.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(entries, handle, ensure_ascii=False)
        return path

    def _add(self, existing):
        path = self._inventory(existing)
        with mock.patch.object(add_episodes.paths, "INVENTORY", path), \
             mock.patch.object(add_episodes.resolve_slug, "load",
                               lambda: CATALOGUE):
            return add_episodes.add([REMOTE])

    def test_new_episode_is_appended(self):
        entries, added, replaced, skipped, errors = self._add([])
        self.assertEqual(len(entries), 1)
        self.assertEqual(len(added), 1)
        self.assertEqual((replaced, skipped, errors), ([], [], []))

    def test_finished_episode_is_left_alone(self):
        old = {"slug": "2021_038_2021-02-07_晚間_Pinuyumayan_卑南",
               "srt_name": "20210207_038_晚間_Pinuyumayan_卑南",
               "truncated": ""}
        entries, added, replaced, skipped, _ = self._add([old])
        self.assertEqual(entries, [old])
        self.assertEqual((added, replaced), ([], []))
        self.assertEqual(len(skipped), 1)

    def test_truncated_episode_is_replaced_by_the_complete_source(self):
        old = {"slug": "2021_038_2021-02-07_晚間_Pinuyumayan_卑南",
               "srt_name": "20210207_038_晚間_Pinuyumayan_卑南",
               "video": "ilrdf-corpus/2月/21NL004_38晚間族語新聞.mxf",
               "truncated": "上傳不完整"}
        entries, added, replaced, skipped, _ = self._add([old])
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["truncated"], "")
        self.assertTrue(entries[0]["video"].endswith(".mp4"))
        self.assertEqual((added, skipped), ([], []))
        self.assertEqual(len(replaced), 1)


if __name__ == "__main__":
    unittest.main()
