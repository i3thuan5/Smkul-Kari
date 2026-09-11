"""兩張 smkul 表讀出來ê逐集條目。

`aiyalaeho/inventory.json` 提掉矣——彼 44 筆對兩張表逐欄對會起來、
零處無仝。兩張表欄位完全相仝，分別干焦佇「這一逝佇佗一个檔」。
"""
import csv
import os
import tempfile
import unittest

from scripts import catalogue_checks as checks
from scripts.aiyalaeho import episodes

HEAD = list(checks.head(checks.EPISODE_KEYS)) + ["原始影片檔案位置",
                                                 "備註"]


def row(**over):
    one = {"成果檔名": "開會了_068_Amis_阿美", "節目名稱": "開會了",
           "集數": "68", "族語別(英)": "Amis", "族語別(中)": "阿美",
           "語言別": "秀姑巒", "語言別代號": "ami-x-skl",
           "原始影片檔案位置": "ilrdf-corpus/族語節目/開會了/068.mp4",
           "備註": ""}
    one.update(over)
    return one


class Fixture(unittest.TestCase):
    def _tables(self, normal, abnormal, head=None):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        made = []
        for name, rows in (("smkul.csv", normal), ("abnormal.csv", abnormal)):
            path = os.path.join(tmp.name, name)
            with open(path, "w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=head or HEAD)
                writer.writeheader()
                for one in rows:
                    writer.writerow(one)
            made.append(path)
        return made


class TestBothTablesAreRead(Fixture):
    def test_rows_from_both_tables_come_back(self):
        bad = row(成果檔名="開會了_083_Rukai_魯凱", 集數="83",
                  備註="僅華語字幕")
        bad["族語別(英)"] = "Rukai"
        bad["族語別(中)"] = "魯凱"
        bad["語言別"] = "非霧台"
        bad["語言別代號"] = "dru"
        table, abnormal = self._tables([row()], [bad])
        got = episodes.load(table, abnormal, srt_dir=set())
        self.assertEqual(len(got), 2)

    def test_which_table_a_row_came_from_is_recorded(self):
        """欄位完全相仝，所以「佇佗一張表」是唯一ê分別。"""
        bad = row(成果檔名="開會了_088_Atayal_泰雅", 集數="88",
                  備註="無字幕")
        bad["族語別(英)"] = "Atayal"
        bad["族語別(中)"] = "泰雅"
        bad["語言別"] = ""
        bad["語言別代號"] = "tay"
        table, abnormal = self._tables([row()], [bad])
        got = episodes.load(table, abnormal, srt_dir=set())
        marks = {}
        for one in got:
            marks[one["srt_name"]] = one["abnormal"]
        self.assertFalse(marks["開會了_068_Amis_阿美"])
        self.assertTrue(marks["開會了_088_Atayal_泰雅"])

    def test_rows_come_back_sorted_by_name(self):
        second = row(成果檔名="開會了_082_Amis_阿美", 集數="82",
                     語言別="", 語言別代號="ami")
        table, abnormal = self._tables([second, row()], [])
        got = episodes.load(table, abnormal, srt_dir=set())
        self.assertEqual([one["srt_name"] for one in got],
                         ["開會了_068_Amis_阿美", "開會了_082_Amis_阿美"])


class TestPendingComesFromTheFileSystem(Fixture):
    def test_an_episode_with_no_srt_is_pending(self):
        table, abnormal = self._tables([row()], [])
        got = episodes.load(table, abnormal, srt_dir=set())
        self.assertTrue(got[0]["pending"])

    def test_an_episode_with_an_srt_is_not(self):
        table, abnormal = self._tables([row()], [])
        got = episodes.load(table, abnormal,
                            srt_dir={"開會了_068_Amis_阿美"})
        self.assertFalse(got[0]["pending"])


class TestTheAbnormalTableMustExplainItself(Fixture):
    """異常表逐逝ê `備註` 愛非空。

    兩張表欄位一模一樣了後，`備註` 非空是彼張表唯一ê自我宣告——有人
    kā一逝徙毋著檔ê話，對欄位看袂出來。
    """

    def test_a_blank_note_in_the_abnormal_table_is_named(self):
        bad = row(成果檔名="開會了_083_Rukai_魯凱", 集數="83", 備註="")
        bad["族語別(英)"] = "Rukai"
        bad["族語別(中)"] = "魯凱"
        bad["語言別"] = ""
        bad["語言別代號"] = "dru"
        table, abnormal = self._tables([row()], [bad])
        problems = episodes.header_problems(table, abnormal)
        self.assertTrue(any("開會了_083_Rukai_魯凱" in p for p in problems))

    def test_a_filled_note_passes(self):
        bad = row(成果檔名="開會了_083_Rukai_魯凱", 集數="83",
                  備註="僅華語字幕")
        bad["族語別(英)"] = "Rukai"
        bad["族語別(中)"] = "魯凱"
        bad["語言別"] = ""
        bad["語言別代號"] = "dru"
        table, abnormal = self._tables([row()], [bad])
        self.assertEqual(episodes.header_problems(table, abnormal), [])

    def test_a_wrong_header_is_named(self):
        head = ["節目名稱", "成果檔名"] + HEAD[2:]
        table, abnormal = self._tables([], [], head=head)
        self.assertTrue(episodes.header_problems(table, abnormal))


if __name__ == "__main__":
    unittest.main()
