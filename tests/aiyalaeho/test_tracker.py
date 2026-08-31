"""tracker: the nine columns of aiyalaeho/smkul.csv, and one row of it.

Three programs build this table -- the batch assembly, the publish step
and the offline rebuild -- and `rebuild --verify` compares the result byte
for byte, so the column set and every derived value live here rather than
in any of them.
"""
import json
import os
import shutil
import tempfile
import unittest

from scripts.aiyalaeho import tracker


def entry(**over):
    row = {
        "file": "068-阿美語-秀姑巒-雙語字幕.mp4",
        "video": "ilrdf-corpus/族語節目/開會了/068-阿美語-秀姑巒-雙語字幕.mp4",
        "srt_name": "開會了_068_Amis_阿美",
        "節目名稱": "開會了",
        "集數": "68",
        "族語別(英)": "Amis",
        "族語別(中)": "阿美",
        "語言別": "秀姑巒",
        "語言代號": "ami-x-skl",
    }
    row.update(over)
    return row


class TestColumns(unittest.TestCase):
    def test_the_nine_columns_in_order(self):
        self.assertEqual(tracker.FIELDS, [
            "節目名稱", "集數", "族語別(英)", "族語別(中)", "語言別",
            "語言代號", "影片檔案位置", "影片長度", "成果檔名"])

    def test_there_is_no_column_with_nothing_to_put_in_it(self):
        # 播出日期／時段／年度查無，語音側無這條線，字幕狀態看 SRT 本身
        # 就知——無資料ê欄莫養。
        for gone in ("年度", "播出日期", "播出時段", "字幕srt狀態",
                     "語音辨識模型", "文稿位置"):
            self.assertNotIn(gone, tracker.FIELDS)


class TestRow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="aiya-tracker-")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _cues(self, name, duration):
        path = os.path.join(self.tmp, name + ".json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"duration": duration, "cues": []}, handle)
        return self.tmp

    def test_the_deliverable_name_is_a_column(self):
        row = tracker.tracker_row(entry(), cues_dir=self.tmp)
        self.assertEqual(row["成果檔名"], "開會了_068_Amis_阿美")

    def test_the_columns_come_from_the_inventory(self):
        row = tracker.tracker_row(entry(), cues_dir=self.tmp)
        self.assertEqual(row["節目名稱"], "開會了")
        self.assertEqual(row["集數"], "68")
        self.assertEqual(row["語言別"], "秀姑巒")
        self.assertEqual(row["語言代號"], "ami-x-skl")
        self.assertEqual(row["影片檔案位置"],
                         "ilrdf-corpus/族語節目/開會了/"
                         "068-阿美語-秀姑巒-雙語字幕.mp4")

    def test_the_length_is_read_off_the_stored_timeline(self):
        cues = self._cues("開會了_068_Amis_阿美", 3150.014)
        row = tracker.tracker_row(entry(), cues_dir=cues)
        self.assertEqual(row["影片長度"], "00:52:30")

    def test_an_episode_with_no_timeline_yet_has_no_length(self):
        row = tracker.tracker_row(entry(), cues_dir=self.tmp)
        self.assertEqual(row["影片長度"], "")

    def test_an_absolute_video_path_is_refused(self):
        # 絕對路徑會予交付ê表綁佇一台機器頂懸。
        self.assertRaises(Exception, tracker.tracker_row,
                          entry(video="/home/me/068.mp4"), cues_dir=self.tmp)


class TestRows(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="aiya-tracker-")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_pending_episodes_are_not_in_the_delivered_table(self):
        # 進行中ê狀態干焦佇 work dir，重建無 work dir，就重建袂出來。
        entries = [entry(), entry(srt_name="開會了_082_Amis_阿美",
                                  集數="82", pending=True)]
        rows = tracker.tracker_rows(entries, cues_dir=self.tmp)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["成果檔名"], "開會了_068_Amis_阿美")

    def test_the_work_copy_lists_everybody(self):
        entries = [entry(), entry(srt_name="開會了_082_Amis_阿美",
                                  集數="82", pending=True)]
        rows = tracker.tracker_rows(entries, cues_dir=self.tmp,
                                    include_pending=True)
        self.assertEqual(len(rows), 2)


class TestFile(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="aiya-tracker-")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_the_file_is_excel_readable_and_stable(self):
        path = os.path.join(self.tmp, "smkul.csv")
        rows = tracker.tracker_rows([entry()], cues_dir=self.tmp)
        tracker.write_tracker(rows, path)
        with open(path, "rb") as handle:
            raw = handle.read()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))   # BOM，予 Excel 用
        self.assertIn(b"\r\n", raw)
        tracker.write_tracker(rows, path)
        with open(path, "rb") as handle:
            self.assertEqual(handle.read(), raw)


if __name__ == "__main__":
    unittest.main()
