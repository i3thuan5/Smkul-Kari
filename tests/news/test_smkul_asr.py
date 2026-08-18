"""smkul.csv 的語音側欄：值只由 store 檔案的存在推導，不手填。

srt-data-store spec「語音側進度欄由 store 推導」scenario：任何時點
重算都得到相同內容，rebuild 才能逐 byte 重建含此欄的進度表。

欄位講的是**用哪個模型辨識的**，不是做到哪一版：交付止於
`3-srt-raw/`，有那個檔就是 Kaldi 辨識過，沒有就留白。
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


class TestAsrModel(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.asr = self._tmp.name
        self.name = "20210201_032_晚間_Amis_阿美"

    def tearDown(self):
        self._tmp.cleanup()

    def test_empty_when_store_has_nothing(self):
        self.assertEqual(tracker.asr_model(self.name, self.asr), "")

    def test_missing_dir_reads_as_empty_not_error(self):
        gone = os.path.join(self.asr, "no-such-dir")
        self.assertEqual(tracker.asr_model(self.name, gone), "")

    def test_the_raw_srt_is_what_names_the_model(self):
        touch(self.asr, "3-srt-raw", self.name + ".srt")
        self.assertEqual(tracker.asr_model(self.name, self.asr), "Kaldi")

    def test_stages_before_the_raw_srt_stay_blank(self):
        # 逐詞辨識與投影是半路的中間檔，還不是交付
        touch(self.asr, "1-words", self.name + ".json")
        touch(self.asr, "2-entries", self.name + ".json")
        self.assertEqual(tracker.asr_model(self.name, self.asr), "")

    def test_align_extension_files_alone_do_not_count(self):
        # 4-srt-ai／6-srt-complete 是試點集的 align 延伸產物，語意整併
        # 效果不佳、之後集數不產，所以不再是「比 raw 更高的一版」。
        touch(self.asr, "4-srt-ai", self.name + ".srt")
        touch(self.asr, "6-srt-complete", self.name + ".srt")
        self.assertEqual(tracker.asr_model(self.name, self.asr), "")

    def test_other_episodes_files_do_not_count(self):
        touch(self.asr, "3-srt-raw", "20210208_039_晚間_Amis_阿美.srt")
        self.assertEqual(tracker.asr_model(self.name, self.asr), "")


class TestRowCarriesTheColumn(unittest.TestCase):
    def test_field_exists_and_is_derived(self):
        with tempfile.TemporaryDirectory() as asr:
            touch(asr, "3-srt-raw", entry()["srt_name"] + ".srt")
            row = tracker.tracker_row(entry(), "狀態文字", asr_dir=asr)
        self.assertIn("語音辨識模型", tracker.FIELDS)
        self.assertEqual(row["語音辨識模型"], "Kaldi")

    def test_default_column_is_empty_for_untouched_episode(self):
        with tempfile.TemporaryDirectory() as asr:
            row = tracker.tracker_row(entry(), "狀態文字", asr_dir=asr)
        self.assertEqual(row["語音辨識模型"], "")


if __name__ == "__main__":
    unittest.main()
