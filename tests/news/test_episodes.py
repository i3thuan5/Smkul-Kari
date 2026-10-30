"""節目目錄讀出來ê逐集條目：slug、file、pending 攏是推導ê。

`news/inventory.json` 提掉矣。伊ê逐一欄對節目目錄推導會出來，驗過
133 筆零例外，所以「這集是啥」問目錄、「這集做到佗」問階段目錄。
"""
import csv
import os
import tempfile
import unittest

from scripts.news import episodes
from scripts.errors import PipelineError

HEAD = ["成果檔名", "節目名稱", "年度", "集數", "播出日期",
        "族語別(英)", "族語別(中)", "語言別", "語言別代號",
        "原始影片檔案位置", "備註"]


def row(**over):
    one = {"成果檔名": "20210201_032_午間_Atayal_泰雅",
           "節目名稱": "午間族語新聞", "年度": "2021", "集數": "32",
           "播出日期": "2021-02-01", "族語別(英)": "Atayal",
           "族語別(中)": "泰雅", "語言別": "", "語言別代號": "tay",
           "原始影片檔案位置": "ilrdf-corpus/2月/20NL003_32午間族語新聞.mxf",
           "備註": ""}
    one.update(over)
    return one


class Fixture(unittest.TestCase):
    def _table(self, *rows):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = os.path.join(tmp.name, "smkul.csv")
        with open(path, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=HEAD)
            writer.writeheader()
            for one in rows:
                writer.writerow(one)
        return path


class TestSlug(Fixture):
    def test_the_episode_number_is_padded_to_three(self):
        # `2021_32_…` 佮 `2021_032_…` 排起來無仝位，而且揣無彼跡。
        got = episodes.slug_of(row(集數="32"))
        self.assertEqual(got, "2021_032_2021-02-01_午間_Atayal_泰雅")

    def test_a_single_digit_episode_too(self):
        got = episodes.slug_of(row(集數="6", 播出日期="2021-01-06"))
        self.assertIn("_006_", got)

    def test_the_slot_comes_from_the_programme(self):
        got = episodes.slug_of(row(節目名稱="晚間族語新聞"))
        self.assertIn("_晚間_", got)

    def test_the_renamed_programme_keeps_the_same_work_dir_name(self):
        # 節目名稱改成《看見族語（晚間）》，work dir 名若跟咧變，切好ê工作區
        # 就揣袂著。
        old = row(節目名稱="晚間族語新聞", 年度="2024", 集數="337",
                  播出日期="2024-12-02",
                  **{"族語別(英)": "Amis", "族語別(中)": "阿美"})
        new = dict(old, 節目名稱="看見族語（晚間）")
        self.assertEqual(episodes.slug_of(old),
                         "2024_337_2024-12-02_晚間_Amis_阿美")
        self.assertEqual(episodes.slug_of(new), episodes.slug_of(old))

    def test_an_unknown_programme_stops_instead_of_blanking_the_slot(self):
        # 空時段會組出一个無人揣會著ê work dir 名。
        with self.assertRaises(PipelineError):
            episodes.slug_of(row(節目名稱="特別節目"))


class TestFileName(Fixture):
    def test_it_is_the_basename_of_the_source(self):
        self.assertEqual(episodes.file_of(row()),
                         "20NL003_32午間族語新聞.mxf")

    def test_a_semicolon_candidate_list_is_split_first(self):
        """`原始影片檔案位置` 是候選清單，122 逝黏幾若條。

        規格直接 basename ê話，提著ê是**上尾**彼條ê檔名（抑是規串
        帶分號ê垃圾字串），揣無檔嘛對袂著目錄。
        """
        cell = "ilrdf-corpus/a/母帶.mxf;ilrdf-corpus/b/轉檔.mp4"
        self.assertEqual(episodes.file_of(row(原始影片檔案位置=cell)),
                         "母帶.mxf")


class TestPendingComesFromTheFileSystem(Fixture):
    """某一集做到佗一步，答案佇階段目錄，毋是佇任何一欄宣告。"""

    def test_an_episode_with_no_srt_is_pending(self):
        got = episodes.load(self._table(row()), srt_dir=set())
        self.assertTrue(got[0]["pending"])

    def test_an_episode_with_an_srt_is_not(self):
        got = episodes.load(self._table(row()),
                            srt_dir={"20210201_032_午間_Atayal_泰雅"})
        self.assertFalse(got[0]["pending"])

    def test_the_table_may_be_far_ahead_of_the_files(self):
        # 表 969 逝、階段目錄才 75 集——彼是猶未做，毋是錯。
        second = row(成果檔名="20210202_033_午間_Kavalan_噶瑪蘭",
                     集數="33", 播出日期="2021-02-02")
        second["族語別(英)"] = "Kavalan"
        second["族語別(中)"] = "噶瑪蘭"
        second["語言別代號"] = "ckv"
        rows = [row(), second]
        got = episodes.load(self._table(*rows),
                            srt_dir={"20210201_032_午間_Atayal_泰雅"})
        self.assertEqual([one["pending"] for one in got], [False, True])


class TestEntryShape(Fixture):
    """條目ê形狀佮舊 inventory 相仝——十八支程式ê索引攏免改。"""

    def test_the_keys_the_callers_index_are_all_there(self):
        got = episodes.load(self._table(row()), srt_dir=set())[0]
        for name in ("srt_name", "slug", "file", "video", "remote", "節目名稱",
                     "年度", "集數", "播出日期", "播出時段",
                     "族語別(英)", "族語別(中)"):
            self.assertIn(name, got)

    def test_remote_is_the_canonical_location_of_the_name(self):
        # 全流程取遠端路徑ê唯一出口：由成果檔名推導，毋是讀原始欄。
        got = episodes.load(self._table(row()), srt_dir=set())[0]
        self.assertEqual(
            got["remote"],
            "/home/news/mkv/2021-02/20210201_032_午間_Atayal_泰雅.mkv")

    def test_remote_does_not_depend_on_the_original_column(self):
        # 原始欄空白抑是有幾若條候選，正規位置攏仝；video／file 兩欄猶原
        # 是原始欄ê值，留作紀錄佮退路。
        plain = episodes.load(self._table(row()), srt_dir=set())[0]
        for cell in ("", "ilrdf-corpus/a/母帶.mxf;ilrdf-corpus/b/轉檔.mp4"):
            got = episodes.load(self._table(row(原始影片檔案位置=cell)),
                                srt_dir=set())[0]
            self.assertEqual(got["remote"], plain["remote"])
            self.assertEqual(got["video"], cell)

    def test_the_three_retired_keys_are_gone(self):
        """`truncated`／`partial`／`文稿位置` 無矣。

        無影片ê集數這馬根本無入表（新聞 983 → 969），所以「來源殘缺
        到根本做袂出字幕」彼个旗標無物件通指；`partial` 收入 `備註`；
        文稿路線裁掉矣。留一个永遠空ê鍵，比提掉較害——彼會予人閣寫
        新ê守衛去問伊。
        """
        got = episodes.load(self._table(row()), srt_dir=set())[0]
        for name in ("truncated", "partial", "文稿位置"):
            self.assertNotIn(name, got)

    def test_srt_name_is_the_delivery_key(self):
        got = episodes.load(self._table(row()), srt_dir=set())[0]
        self.assertEqual(got["srt_name"], "20210201_032_午間_Atayal_泰雅")


if __name__ == "__main__":
    unittest.main()
