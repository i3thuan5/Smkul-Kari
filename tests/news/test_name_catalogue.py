"""name_catalogue：kā `srt_name` 這欄寫入目錄，予外部單位看有。

`srt_name` 本底是**推算**出來的（`resolve_slug.srt_name`），目錄內底無這
欄。毋過交出去的檔案、smkul.csv、佮外部單位講話攏用這个名，所以目錄嘛
愛看會著——若無，人提著目錄一逝，無法度講伊對應佗一支 SRT。

要緊的是：這欄是**產生**的，毋是手寫的。
`name_of()` 是唯一的算法，`check()` 顧著手改了後袂偷偷走精。目錄本身
是 CRLF＋BOM（外部單位用 Excel 開），寫轉去愛照原樣，若無 diff 會歸片紅。

fixture 照真實目錄合成：《開會了》彼款無播出日期ê列，命袂出名，留空。
"""
import csv
import os
import tempfile
import unittest

from scripts.news import name_catalogue


HEAD = ["節目名稱", "年度", "集數", "播出日期", "播出時段",
        "族語別(英)", "族語別(中)", "有無影片", "影片檔案位置"]


def row(**over):
    entry = {"節目名稱": "午間族語新聞", "年度": "2021", "集數": "1",
             "播出日期": "2021-01-01", "播出時段": "午間",
             "族語別(英)": "Rukai", "族語別(中)": "魯凱",
             "有無影片": "是", "影片檔案位置": "ilrdf-corpus/魯凱語.mp4"}
    entry.update(over)
    return entry


def meeting_row():
    """《開會了》：無年度嘛無播出日期，命袂出名。"""
    return row(節目名稱="開會了", 年度="", 集數="79", 播出日期="",
               播出時段="", **{"族語別(英)": "", "族語別(中)": ""})


class TestNameOf(unittest.TestCase):
    def test_it_is_the_same_name_the_pipeline_already_uses(self):
        # 這條若破，表示目錄彼欄佮交出去ê檔名無仝，比無這欄閣較僫。
        self.assertEqual(name_catalogue.name_of(row()),
                         "20210101_001_午間_Rukai_魯凱")

    def test_the_episode_number_is_padded_to_three(self):
        self.assertEqual(name_catalogue.name_of(row(集數="7"))[9:12], "007")

    def test_a_row_the_catalogue_cannot_name_is_empty_not_a_crash(self):
        # 《開會了》46 逝就是按呢。留空，莫烏白掠一个名。
        self.assertEqual(name_catalogue.name_of(meeting_row()), "")

    def test_a_non_numeric_episode_is_empty_too(self):
        self.assertEqual(name_catalogue.name_of(row(集數="待補")), "")


class TestNamed(unittest.TestCase):
    def test_srt_name_goes_first(self):
        # 外部單位掀開就看著，毋免捲到上尾。
        out, head = name_catalogue.named([row()], HEAD)
        self.assertEqual(head[0], "srt_name")

    def test_the_other_columns_keep_their_order(self):
        out, head = name_catalogue.named([row()], HEAD)
        self.assertEqual(head[1:], HEAD)

    def test_the_input_rows_are_not_touched(self):
        original = row()
        name_catalogue.named([original], HEAD)
        self.assertNotIn("srt_name", original)

    def test_running_it_twice_changes_nothing(self):
        once, head = name_catalogue.named([row()], HEAD)
        twice, head2 = name_catalogue.named(once, head)
        self.assertEqual(once, twice)
        self.assertEqual(head, head2)

    def test_a_stale_value_is_overwritten_not_kept(self):
        # 手改過ê值無算數：算法是唯一ê正本。
        stale = row()
        stale["srt_name"] = "亂寫的"
        out, _ = name_catalogue.named([stale], ["srt_name"] + HEAD)
        self.assertEqual(out[0]["srt_name"], "20210101_001_午間_Rukai_魯凱")


class TestCheck(unittest.TestCase):
    def test_a_consistent_catalogue_reports_nothing(self):
        out, head = name_catalogue.named([row(), meeting_row()], HEAD)
        self.assertEqual(name_catalogue.check(out), [])

    def test_a_hand_edited_cell_is_caught(self):
        out, head = name_catalogue.named([row()], HEAD)
        out[0]["srt_name"] = "20210101_001_午間_Rukai_魯凱X"
        bad = name_catalogue.check(out)
        self.assertEqual(len(bad), 1)
        line, stored, wanted = bad[0]
        self.assertEqual(line, 2)          # 表頭是第 1 逝
        self.assertEqual(wanted, "20210101_001_午間_Rukai_魯凱")

    def test_a_missing_column_is_caught(self):
        self.assertEqual(len(name_catalogue.check([row()])), 1)


class TestRoundTrip(unittest.TestCase):
    """目錄是 CRLF＋BOM，寫轉去愛照原樣。"""

    def setUp(self):
        handle, self.path = tempfile.mkstemp(suffix=".csv")
        os.close(handle)
        self.addCleanup(os.unlink, self.path)
        with open(self.path, "w", encoding="utf-8-sig", newline="") as out:
            writer = csv.DictWriter(out, HEAD, lineterminator="\r\n")
            writer.writeheader()
            writer.writerow(row())
            writer.writerow(meeting_row())

    def test_it_keeps_the_bom(self):
        name_catalogue.rewrite(self.path)
        with open(self.path, "rb") as handle:
            self.assertTrue(handle.read(3) == b"\xef\xbb\xbf")

    def test_it_keeps_crlf(self):
        name_catalogue.rewrite(self.path)
        with open(self.path, "rb") as handle:
            body = handle.read()
        self.assertNotIn(b"\n", body.replace(b"\r\n", b""))

    def test_the_column_is_there_after_a_rewrite(self):
        name_catalogue.rewrite(self.path)
        rows, head = name_catalogue.read(self.path)
        self.assertEqual(head[0], "srt_name")
        self.assertEqual(rows[0]["srt_name"],
                         "20210101_001_午間_Rukai_魯凱")
        self.assertEqual(rows[1]["srt_name"], "")

    def test_a_rewrite_is_idempotent_byte_for_byte(self):
        name_catalogue.rewrite(self.path)
        with open(self.path, "rb") as handle:
            first = handle.read()
        name_catalogue.rewrite(self.path)
        with open(self.path, "rb") as handle:
            self.assertEqual(handle.read(), first)

    def test_check_passes_on_a_freshly_written_file(self):
        name_catalogue.rewrite(self.path)
        rows, _ = name_catalogue.read(self.path)
        self.assertEqual(name_catalogue.check(rows), [])


if __name__ == "__main__":
    unittest.main()
