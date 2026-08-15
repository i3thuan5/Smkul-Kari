"""smkul.csv 的語音側欄：值只由 store 檔案的存在推導，不手填。

srt-data-store spec「語音側進度欄由 store 推導」scenario：任何時點
重算都得到相同內容，rebuild 才能逐 byte 重建含此欄的進度表。
"""
import os
import tempfile
import unittest

from scripts.news import tracker


def touch(root, folder, name):
    os.makedirs(os.path.join(root, folder), exist_ok=True)
    handle = open(os.path.join(root, folder, name), "w")
    handle.close()


def entry(srt_name="20210201_032_晚間_Amis_阿美"):
    return {
        "節目名稱": "晚間族語新聞", "年度": "2021", "集數": "32",
        "播出日期": "2021-02-01", "播出時段": "晚間",
        "族語別(英)": "Amis", "族語別(中)": "阿美",
        "video": "/somewhere/20NL004_32晚間族語新聞.mxf",
        "文稿位置": "", "srt_name": srt_name,
    }


class TestAsrStatus(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.asr = self._tmp.name
        self.name = "20210201_032_晚間_Amis_阿美"

    def tearDown(self):
        self._tmp.cleanup()

    def test_empty_when_store_has_nothing(self):
        self.assertEqual(tracker.asr_status(self.name, self.asr), "")

    def test_missing_dir_reads_as_empty_not_error(self):
        gone = os.path.join(self.asr, "no-such-dir")
        self.assertEqual(tracker.asr_status(self.name, gone), "")

    def test_words_alone_reads_as_transcribed(self):
        touch(self.asr, "1-words", self.name + ".json")
        self.assertEqual(tracker.asr_status(self.name, self.asr), "逐詞辨識")

    def test_raw_srt_beats_earlier_stages(self):
        touch(self.asr, "1-words", self.name + ".json")
        touch(self.asr, "2-entries", self.name + ".json")
        touch(self.asr, "4-srt-ai", self.name + ".srt")
        self.assertEqual(tracker.asr_status(self.name, self.asr), "審查版")

    def test_complete_wins_over_raw(self):
        touch(self.asr, "4-srt-ai", self.name + ".srt")
        touch(self.asr, "6-srt-complete", self.name + ".srt")
        self.assertEqual(tracker.asr_status(self.name, self.asr), "正式版")

    def test_other_episodes_files_do_not_count(self):
        touch(self.asr, "4-srt-ai", "20210208_039_晚間_Amis_阿美.srt")
        self.assertEqual(tracker.asr_status(self.name, self.asr), "")


class TestRowCarriesTheColumn(unittest.TestCase):
    def test_field_exists_and_is_derived(self):
        with tempfile.TemporaryDirectory() as asr:
            touch(asr, "4-srt-ai", entry()["srt_name"] + ".srt")
            row = tracker.tracker_row(entry(), "狀態文字", asr_dir=asr)
        self.assertIn("語音辨識狀態", tracker.FIELDS)
        self.assertEqual(row["語音辨識狀態"], "審查版")

    def test_default_column_is_empty_for_untouched_episode(self):
        with tempfile.TemporaryDirectory() as asr:
            row = tracker.tracker_row(entry(), "狀態文字", asr_dir=asr)
        self.assertEqual(row["語音辨識狀態"], "")


if __name__ == "__main__":
    unittest.main()
