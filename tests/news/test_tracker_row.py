"""make_all.tracker_row: what the smkul.csv status column ends up saying.

rebuild.py builds its rows through this same function, so a tracker rebuilt
from Kari-SRT alone compares byte-for-byte with the delivered one. Anything
that changes the status has to live here rather than at either call site.
"""
import unittest

from scripts.news import make_all


ENTRY = {
    "節目名稱": "午間族語新聞",
    "年度": "2021",
    "集數": "41",
    "播出日期": "2021-02-10",
    "播出時段": "午間",
    "族語別(英)": "Cou",
    "族語別(中)": "鄒",
    "video": "ilrdf-corpus/族語新聞/110.1-110.10/7月/21NL003_41午間族語新聞.mp4",
    "文稿位置": "",
    "truncated": "",
}
DONE = "已產生 170 行；Claude 視覺辨識，237 個 cue 全數校讀"


class TestTrackerRow(unittest.TestCase):
    def test_a_normal_episode_reports_only_its_status(self):
        row = make_all.tracker_row(dict(ENTRY), DONE)
        self.assertEqual(row["字幕srt狀態"], DONE)

    def test_a_short_source_is_said_so_in_the_status(self):
        # The episode is still subtitled -- a partial transcript beats none --
        # but an SRT that simply stops halfway must not read as a whole one.
        entry = dict(ENTRY, partial="來源僅 11:13")
        row = make_all.tracker_row(entry, DONE)
        self.assertTrue(row["字幕srt狀態"].startswith(DONE))
        self.assertIn("來源不完整：來源僅 11:13", row["字幕srt狀態"])

    def test_the_note_is_absent_when_the_field_is(self):
        # every February entry predates the field
        self.assertNotIn("partial", ENTRY)
        row = make_all.tracker_row(dict(ENTRY), DONE)
        self.assertNotIn("來源不完整", row["字幕srt狀態"])

    def test_video_path_is_kept_relative_to_the_corpus_root(self):
        row = make_all.tracker_row(dict(ENTRY), DONE)
        self.assertEqual(row["影片檔案位置"], ENTRY["video"])


if __name__ == "__main__":
    unittest.main()
