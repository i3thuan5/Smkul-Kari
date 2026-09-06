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


class TestIsAbnormal(unittest.TestCase):
    """理由非空就是異常集——干焦這一條決定伊落佇佗一張表。"""

    def test_a_reason_makes_it_abnormal(self):
        self.assertTrue(tracker.is_abnormal(entry(理由="無字幕")))

    def test_an_empty_reason_does_not(self):
        self.assertFalse(tracker.is_abnormal(entry(理由="")))

    def test_a_missing_field_does_not(self):
        # 雙語集根本無這隻鍵——「無資料ê欄莫養」。
        self.assertFalse(tracker.is_abnormal(entry()))

    def test_any_wording_counts(self):
        for reason in ("僅華語字幕", "版型不符：槽下跤無帶",
                       "人工判定：sheet_001 兩逝攏空"):
            self.assertTrue(tracker.is_abnormal(entry(理由=reason)), reason)


class TestAbnormalTable(unittest.TestCase):
    """第二張表：`smkul.csv` ê九欄原樣，紲落去加一欄「理由」。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="aiya-abn-")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _abnormal(self, **over):
        over.setdefault("理由", "無字幕")
        over.setdefault("影片長度秒", 2969.967)
        over.setdefault("srt_name", "開會了_088_Atayal_泰雅")
        over.setdefault("集數", "88")
        return entry(**over)

    def test_the_columns_are_the_nine_plus_the_reason(self):
        self.assertEqual(tracker.ABNORMAL_FIELDS, tracker.FIELDS + ["理由"])

    def test_an_abnormal_episode_is_not_in_the_delivered_table(self):
        entries = [entry(), self._abnormal()]
        rows = tracker.tracker_rows(entries, cues_dir=self.tmp)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["成果檔名"], "開會了_068_Amis_阿美")

    def test_it_is_in_the_second_table(self):
        entries = [entry(), self._abnormal()]
        rows = tracker.abnormal_rows(entries)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["成果檔名"], "開會了_088_Atayal_泰雅")
        self.assertEqual(rows[0]["理由"], "無字幕")

    def test_the_key_is_the_name_even_though_no_file_exists(self):
        rows = tracker.abnormal_rows([self._abnormal()])
        self.assertEqual(rows[0]["成果檔名"], rows[0]["成果檔名"].strip())
        self.assertTrue(rows[0]["成果檔名"].startswith("開會了_"))

    def test_the_length_comes_from_the_inventory(self):
        # 這幾集佇 `1-cues/` 無時間軸通推——離線重建嘛袂使開影片。
        rows = tracker.abnormal_rows([self._abnormal()])
        self.assertEqual(rows[0]["影片長度"], "00:49:30")

    def test_a_pending_one_is_not_in_the_delivered_second_table(self):
        rows = tracker.abnormal_rows([self._abnormal(pending=True)])
        self.assertEqual(rows, [])

    def test_the_work_copy_lists_pending_ones_too(self):
        rows = tracker.abnormal_rows([self._abnormal(pending=True)],
                                     include_pending=True)
        self.assertEqual(len(rows), 1)

    def test_the_two_tables_never_share_an_episode(self):
        entries = [entry(), self._abnormal(),
                   entry(srt_name="開會了_083_Rukai_魯凱", 集數="83",
                         理由="僅華語字幕", 影片長度秒=3000.0)]
        delivered = tracker.tracker_rows(entries, cues_dir=self.tmp)
        abnormal = tracker.abnormal_rows(entries)
        names = set()
        for row in delivered:
            names.add(row["成果檔名"])
        for row in abnormal:
            self.assertNotIn(row["成果檔名"], names)
        self.assertEqual(len(delivered) + len(abnormal), 3)

    def test_it_writes_ten_columns(self):
        path = os.path.join(self.tmp, "smkul-字幕版型異常.csv")
        rows = tracker.abnormal_rows([self._abnormal()])
        tracker.write_tracker(rows, path, tracker.ABNORMAL_FIELDS)
        with open(path, encoding="utf-8-sig") as handle:
            header = handle.readline().strip()
        self.assertEqual(header.split(","), tracker.ABNORMAL_FIELDS)

    def test_the_second_table_is_excel_readable_and_stable(self):
        path = os.path.join(self.tmp, "smkul-字幕版型異常.csv")
        rows = tracker.abnormal_rows([self._abnormal()])
        tracker.write_tracker(rows, path, tracker.ABNORMAL_FIELDS)
        with open(path, "rb") as handle:
            raw = handle.read()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
        tracker.write_tracker(rows, path, tracker.ABNORMAL_FIELDS)
        with open(path, "rb") as handle:
            self.assertEqual(handle.read(), raw)


if __name__ == "__main__":
    unittest.main()
