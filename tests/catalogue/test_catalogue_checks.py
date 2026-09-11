"""節目目錄ê不變量：成果檔名、語言欄、素材位置、列序、孤兒檔。

`smkul.csv` 這馬是輸入毋是產出，逐 byte 重算比對無意義矣，所以
`rebuild --verify` 對伊ê把關換做這幾條。逐 byte 干焦會講「對袂起來」，
這爿會講是佗一逝、佗一欄、按怎毋著。
"""
import unittest

from scripts import catalogue_checks as checks
from scripts.errors import PipelineError


def news_row(**over):
    row = {"成果檔名": "20210201_032_午間_Atayal_泰雅",
           "節目名稱": "午間族語新聞", "年度": "2021", "集數": "32",
           "播出日期": "2021-02-01", "族語別(英)": "Atayal",
           "族語別(中)": "泰雅", "語言別": "", "語言別代號": "tay",
           "原始影片檔案位置": "ilrdf-corpus/2月/x.mxf", "備註": ""}
    row.update(over)
    return row


def aiya_row(**over):
    row = {"成果檔名": "開會了_068_Amis_阿美", "節目名稱": "開會了",
           "集數": "68", "族語別(英)": "Amis", "族語別(中)": "阿美",
           "語言別": "秀姑巒", "語言別代號": "ami-x-skl",
           "原始影片檔案位置": "ilrdf-corpus/族語節目/開會了/068.mp4",
           "備註": ""}
    row.update(over)
    return row


class TestSlotComesFromTheProgramme(unittest.TestCase):
    """播出時段由節目名稱決定，983 逝零例外，所以無彼一欄。"""

    def test_the_three_news_programmes_resolve(self):
        self.assertEqual(checks.slot_of("午間族語新聞"), "午間")
        self.assertEqual(checks.slot_of("晚間族語新聞"), "晚間")
        self.assertEqual(checks.slot_of("晨間族語新聞"), "晨間")

    def test_an_unknown_programme_is_named_not_blanked(self):
        # 推一个空字串傳落去ê話，會去組出一个無人揣會著ê成果檔名。
        with self.assertRaises(PipelineError) as caught:
            checks.slot_of("特別節目")
        self.assertIn("特別節目", str(caught.exception))


class TestSrtNameDerivation(unittest.TestCase):
    def test_news_name_is_date_episode_slot_language(self):
        self.assertEqual(checks.srt_name_of(news_row()),
                         "20210201_032_午間_Atayal_泰雅")

    def test_the_episode_number_is_padded_to_three(self):
        # `2021_32_…` 佮 `2021_032_…` 排起來無仝位，而且揣無檔。
        got = checks.srt_name_of(news_row(集數="6",
                                          播出日期="2021-01-06"))
        self.assertIn("_006_", got)

    def test_aiyalaeho_name_has_no_date(self):
        self.assertEqual(checks.srt_name_of(aiya_row()),
                         "開會了_068_Amis_阿美")

    def test_an_unprocessed_episode_still_has_a_name(self):
        # 猶未切 cue ê集數嘛推會出來——一逝一建立就有名。
        row = news_row(成果檔名="")
        self.assertTrue(checks.srt_name_of(row))


class TestNameSpec(unittest.TestCase):
    def test_a_three_digit_episode_passes(self):
        self.assertTrue(checks.name_is_legal("20210201_032_午間_Atayal_泰雅"))

    def test_a_two_digit_episode_fails(self):
        self.assertFalse(checks.name_is_legal("20210201_32_午間_Atayal_泰雅"))

    def test_aiyalaeho_form_passes(self):
        self.assertTrue(checks.name_is_legal("開會了_068_Amis_阿美"))

    def test_a_name_with_a_date_where_開會了_goes_fails(self):
        self.assertFalse(checks.name_is_legal("開會了_68_Amis_阿美"))


class TestRowProblems(unittest.TestCase):
    def test_a_clean_table_has_none(self):
        self.assertEqual(checks.row_problems([news_row()]), [])

    def test_a_name_that_does_not_match_its_columns_is_named(self):
        rows = [news_row(成果檔名="20210201_033_午間_Atayal_泰雅")]
        problems = checks.row_problems(rows)
        self.assertTrue(problems)
        self.assertIn("第 2 逝", problems[0])

    def test_a_duplicate_name_is_named(self):
        problems = checks.row_problems([news_row(), news_row()])
        self.assertTrue(any("重複" in p for p in problems))

    def test_an_unknown_language_code_is_named(self):
        problems = checks.row_problems([news_row(語言別代號="amis")])
        self.assertTrue(any("amis" in p for p in problems))

    def test_a_mismatched_english_spelling_is_named(self):
        rows = [news_row()]
        rows[0]["族語別(英)"] = "Tayal"
        problems = checks.row_problems(rows)
        self.assertTrue(any("族語別(英)" in p for p in problems))

    def test_an_empty_source_path_is_named(self):
        problems = checks.row_problems([news_row(原始影片檔案位置="")])
        self.assertTrue(any("原始影片檔案位置" in p for p in problems))

    def test_the_text_corpus_names_its_own_source_column(self):
        row = aiya_row()
        del row["原始影片檔案位置"]
        row["來源文字檔檔案位置"] = "開會001_賽夏族/ok.txt"
        self.assertEqual(
            checks.row_problems([row],
                                source_column="來源文字檔檔案位置"), [])


class TestRowOrder(unittest.TestCase):
    """列序照 `成果檔名` 排——加一批才袂規檔重寫。"""

    def test_sorted_rows_pass(self):
        rows = [news_row(成果檔名="20210106_006_午間_Cou_鄒",
                         集數="6", 播出日期="2021-01-06"),
                news_row()]
        rows[0]["族語別(英)"] = "Cou"
        rows[0]["族語別(中)"] = "鄒"
        rows[0]["語言別代號"] = "tsu"
        self.assertEqual(checks.row_problems(rows), [])

    def test_january_after_february_is_named(self):
        # 舊表就是按呢：第一逝是 2021-02-01、上尾逝是 2021-01-06。
        rows = [news_row()]
        later = news_row(成果檔名="20210106_006_午間_Cou_鄒",
                         集數="6", 播出日期="2021-01-06")
        later["族語別(英)"] = "Cou"
        later["族語別(中)"] = "鄒"
        later["語言別代號"] = "tsu"
        rows.append(later)
        problems = checks.row_problems(rows)
        self.assertTrue(any("列序" in p for p in problems))


class TestOrphanFiles(unittest.TestCase):
    def test_a_file_the_table_does_not_know_is_named(self):
        problems = checks.orphan_problems(
            [news_row()],
            [("3-srt", {"20210201_032_午間_Atayal_泰雅", "20210299_099_x_y_z"})])
        self.assertEqual(len(problems), 1)
        self.assertIn("20210299_099_x_y_z", problems[0])

    def test_a_row_with_no_file_is_not_an_orphan(self):
        # 表有 969 逝、階段目錄才 75 集——彼是猶未做，毋是錯。
        self.assertEqual(
            checks.orphan_problems([news_row()], [("3-srt", set())]), [])


class TestHeader(unittest.TestCase):
    def test_the_news_head_is_eleven_columns(self):
        want = checks.head(checks.NEWS_KEYS)
        self.assertEqual(want[0], "成果檔名")
        self.assertEqual(want[1], "節目名稱")
        self.assertEqual(want[-1], "語言別代號")

    def test_the_two_corpora_share_everything_but_the_keys(self):
        news = checks.head(checks.NEWS_KEYS)
        other = checks.head(checks.EPISODE_KEYS)
        self.assertEqual(news[:2], other[:2])
        self.assertEqual(news[-4:], other[-4:])

    def test_a_wrong_head_is_named(self):
        problems = checks.header_problems(
            ["節目名稱", "成果檔名", "集數", "族語別(英)", "族語別(中)",
             "語言別", "語言別代號"], checks.EPISODE_KEYS)
        self.assertEqual(len(problems), 1)

    def test_the_right_head_passes(self):
        self.assertEqual(
            checks.header_problems(list(checks.head(checks.EPISODE_KEYS))
                                   + ["原始影片檔案位置", "備註"],
                                   checks.EPISODE_KEYS), [])


if __name__ == "__main__":
    unittest.main()
