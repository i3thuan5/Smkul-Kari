"""tracker.tracker_row: what the smkul.csv status column ends up saying.

make_all, publish and rebuild all build their rows through this same
function, so a tracker rebuilt from Kari-SRT alone compares byte-for-byte
with the delivered one. Anything that changes the status has to live there
rather than at any of the three call sites.
"""
import unittest

from scripts.news import tracker


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
    "srt_name": "20210210_041_午間_Cou_鄒",
}
DONE = "Claude Vision OCR 已產生 170 行字幕"


class TestVisionStatus(unittest.TestCase):
    def test_the_status_names_the_reader_and_the_delivered_line_count(self):
        # The cue count used to be here too, and was read as a second,
        # smaller line count; it is an internal segmentation number, not
        # anything a reader of the table can act on.
        self.assertEqual(tracker.vision_status(170), DONE)


class TestTrackerRow(unittest.TestCase):
    def test_a_normal_episode_reports_only_its_status(self):
        row = tracker.tracker_row(dict(ENTRY), DONE)
        self.assertEqual(row["字幕srt狀態"], DONE)

    def test_a_short_source_is_said_so_in_the_status(self):
        # The episode is still subtitled -- a partial transcript beats none --
        # but an SRT that simply stops halfway must not read as a whole one.
        entry = dict(ENTRY, partial="來源僅 11:13")
        row = tracker.tracker_row(entry, DONE)
        self.assertTrue(row["字幕srt狀態"].startswith(DONE))
        self.assertIn("來源不完整：來源僅 11:13", row["字幕srt狀態"])

    def test_the_note_is_absent_when_the_field_is(self):
        # every February entry predates the field
        self.assertNotIn("partial", ENTRY)
        row = tracker.tracker_row(dict(ENTRY), DONE)
        self.assertNotIn("來源不完整", row["字幕srt狀態"])

    def test_video_path_is_kept_relative_to_the_corpus_root(self):
        row = tracker.tracker_row(dict(ENTRY), DONE)
        self.assertEqual(row["影片檔案位置"], ENTRY["video"])

    def test_an_absolute_video_path_is_refused(self):
        # inventory 存的是「相對 corpus 根」的路徑。絕對路徑寫進交付表
        # 會讓表變成這台機器專屬的，別台機器 rebuild 不出同樣的內容。
        entry = dict(ENTRY)
        entry["video"] = "/home/vscode/ilrdf-corpus/2月/x.mxf"
        with self.assertRaises(SystemExit):
            tracker.tracker_row(entry, DONE)


if __name__ == "__main__":
    unittest.main()
