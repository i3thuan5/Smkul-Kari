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


class TestTheRenamedProgramme(unittest.TestCase):
    """2024-08-01 起《族語新聞》改名《看見族語》，時段留佇名內底。"""

    def test_the_three_new_names_resolve(self):
        self.assertEqual(checks.slot_of("看見族語（午間）"), "午間")
        self.assertEqual(checks.slot_of("看見族語（晚間）"), "晚間")
        self.assertEqual(checks.slot_of("看見族語（晨間）"), "晨間")

    def test_the_old_names_still_resolve(self):
        # 2024-07-31 以前 2,816 逝猶是用舊名，愛解會出來。
        self.assertEqual(checks.slot_of("晚間族語新聞"), "晚間")

    def test_half_width_parentheses_are_refused_with_a_hint(self):
        # Excel 手拍上濟犯ê毋著：看起來差不多、其實是兩款名。毋是推一个
        # 空字串，是指名彼个名佮講愛全形。
        with self.assertRaises(PipelineError) as caught:
            checks.slot_of("看見族語(晚間)")
        self.assertIn("看見族語(晚間)", str(caught.exception))
        self.assertIn("全形", str(caught.exception))

    def test_the_name_without_a_slot_does_not_resolve(self):
        # 三个時段仝名，推袂出是佗一个。
        with self.assertRaises(PipelineError) as caught:
            checks.slot_of("看見族語")
        self.assertIn("看見族語", str(caught.exception))

    def test_renaming_does_not_change_the_srt_name(self):
        # 改名若連動改成果檔名，3,153 支 SRT 規堆變孤兒檔。
        old = news_row(成果檔名="20241202_337_晚間_Amis_阿美",
                       節目名稱="晚間族語新聞", 年度="2024", 集數="337",
                       播出日期="2024-12-02",
                       **{"族語別(英)": "Amis", "族語別(中)": "阿美"})
        new = dict(old, 節目名稱="看見族語（晚間）")
        self.assertEqual(checks.srt_name_of(old), "20241202_337_晚間_Amis_阿美")
        self.assertEqual(checks.srt_name_of(new), checks.srt_name_of(old))

    def test_programme_for_gives_the_name_that_day_used(self):
        self.assertEqual(checks.programme_for("晚間", "2024-07-31"),
                         "晚間族語新聞")
        self.assertEqual(checks.programme_for("晚間", "2024-08-01"),
                         "看見族語（晚間）")
        self.assertEqual(checks.programme_for("晨間", "2024-12-31"),
                         "看見族語（晨間）")


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


def row_on(date, programme, slot="晚間", episode=214):
    """節目名稱佮播出日期對無對ê實驗用一逝；成果檔名照欄位寫好。"""
    name = "%s_%03d_%s_Amis_阿美" % (date.replace("-", ""), episode, slot)
    return news_row(成果檔名=name, 節目名稱=programme, 年度=date[:4],
                    集數=str(episode), 播出日期=date,
                    **{"族語別(英)": "Amis", "族語別(中)": "阿美",
                       "語言別代號": "ami"})


class TestProgrammeMatchesTheDate(unittest.TestCase):
    """改名生效日 2024-08-01：之前寫族語新聞、之後寫看見族語（時段）。"""

    def test_each_side_of_the_line_with_its_own_name_passes(self):
        self.assertEqual(checks.row_problems(
            [row_on("2024-07-31", "晚間族語新聞")]), [])
        self.assertEqual(checks.row_problems(
            [row_on("2024-08-01", "看見族語（晚間）")]), [])

    def test_the_old_name_on_the_first_day_is_named(self):
        # 界線若寫成 `>` 毋是 `>=`，08-01 彼工就漏。
        problems = checks.row_problems(
            [row_on("2024-08-01", "晚間族語新聞")])
        self.assertEqual(len(problems), 1)
        self.assertIn("第 2 逝", problems[0])
        self.assertIn("節目名稱", problems[0])
        self.assertIn("看見族語（晚間）", problems[0])

    def test_the_new_name_the_day_before_is_named(self):
        problems = checks.row_problems(
            [row_on("2024-07-31", "看見族語（晚間）")])
        self.assertEqual(len(problems), 1)
        self.assertIn("2024-07-31", problems[0])
        self.assertIn("晚間族語新聞", problems[0])
        self.assertNotIn("推袂出來", problems[0])

    def test_both_names_in_one_table_are_legal(self):
        rows = [row_on("2024-07-31", "晚間族語新聞", episode=213),
                row_on("2024-08-01", "看見族語（晚間）", episode=214)]
        self.assertEqual(checks.row_problems(rows), [])

    def test_the_aiyalaeho_table_is_not_touched(self):
        # 開會了ê表無播出日期欄，節目名稱是「開會了」。
        self.assertEqual(checks.row_problems([aiya_row()]), [])

    def test_a_blank_date_does_not_hide_the_other_problem(self):
        # 日期空白ê時成果檔名佮識別欄對袂起來，彼條已經指名矣；日期對照
        # 莫閣加一條「節目名稱毋著」，嘛毋通拋例外。
        problems = checks.row_problems([news_row(播出日期="")])
        self.assertEqual(len(problems), 1)
        self.assertIn("成果檔名", problems[0])

    def test_a_malformed_date_does_not_raise(self):
        problems = checks.row_problems([news_row(播出日期="2024/08/01")])
        self.assertEqual(len(problems), 1)
        self.assertIn("成果檔名", problems[0])


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


def excluded_row(**over):
    row = {"伺服器路徑": "/home/mkv-raw/112/6月/23NL004_174_族語晚間新聞_Paiwan.mkv",
           "排除原因": "重複檔",
           "同一支的保留檔":
               "/home/mkv-raw/112/6月/23NL004_175_族語晚間新聞_Paiwan.mkv",
           "判定依據": "檔案大小相同、影音串流雜湊相同",
           "判定日期": "2026-09-23"}
    row.update(over)
    return row


def server_path(path):
    # 用正式ê換算，毋家己寫一份：目錄寫法 `home/…`、`ilrdf-corpus/…`
    # 佮排除清單 `/home/…`、`/docker/ilrdf-corpus/…` 愛換做仝一个。
    from scripts.news import resolve_slug
    return resolve_slug.server_path(path)


class TestExcludedFiles(unittest.TestCase):
    """`排除影片.csv` 列過ê檔（重複檔、分段檔）袂使閣入目錄。

    2026-09-23：大細相仝ê 4 組整檔 sha256 攏無仝，影音串流雜湊煞攏相仝，
    是仝一支影片囥佇兩个日期。排除了後若是有人照清單閣加轉來，就是
    kā仝一支影片算做兩集。
    """

    def test_a_duplicate_added_back_is_named_with_its_reason(self):
        row = news_row(原始影片檔案位置=(
            "home/mkv-raw/112/6月/23NL004_174_族語晚間新聞_Paiwan.mkv"))
        problems = checks.excluded_problems([row], [excluded_row()],
                                            server_path)
        self.assertEqual(len(problems), 1)
        self.assertIn("第 2 逝", problems[0])
        self.assertIn("重複檔", problems[0])
        self.assertIn("23NL004_175", problems[0])

    def test_the_catalogue_spelling_without_a_slash_still_matches(self):
        # 目錄欄位去掉開頭斜線；清單寫伺服器絕對路徑。字串直接比會漏。
        row = news_row(原始影片檔案位置=(
            "home/mkv-raw/112/6月/23NL004_176_族語晚間新聞_卑南_A.mkv"))
        gone = excluded_row(
            伺服器路徑="/home/mkv-raw/112/6月/23NL004_176_族語晚間新聞_卑南_A.mkv",
            排除原因="分段檔（已接成一支）")
        self.assertEqual(len(checks.excluded_problems([row], [gone],
                                                      server_path)), 1)

    def test_the_old_corpus_root_shorthand_is_expanded(self):
        row = news_row(原始影片檔案位置="ilrdf-corpus/族語新聞/11月/x.mp4")
        gone = excluded_row(
            伺服器路徑="/docker/ilrdf-corpus/族語新聞/11月/x.mp4")
        self.assertEqual(len(checks.excluded_problems([row], [gone],
                                                      server_path)), 1)

    def test_every_path_in_a_semicolon_list_is_checked(self):
        # 63 逝目錄ê素材位置是分號並列；干焦看頭一條會漏後壁彼條。
        row = news_row(原始影片檔案位置=(
            "ilrdf-corpus/族語新聞/2月/a.mxf;"
            "home/mkv-raw/112/6月/23NL004_174_族語晚間新聞_Paiwan.mkv"))
        self.assertEqual(len(checks.excluded_problems([row], [excluded_row()],
                                                      server_path)), 1)

    def test_a_clean_catalogue_passes(self):
        self.assertEqual(checks.excluded_problems([news_row()],
                                                  [excluded_row()],
                                                  server_path), [])

    def test_an_exclusion_without_the_kept_file_is_named(self):
        # 無寫保留彼支，後來ê人就毋知彼个時段是缺檔抑是有另外一支。
        problems = checks.excluded_problems(
            [news_row()], [excluded_row(同一支的保留檔=" ")], server_path)
        self.assertEqual(len(problems), 1)
        self.assertIn("排除影片", problems[0])
        self.assertIn("同一支的保留檔", problems[0])

    def test_a_non_news_programme_needs_no_kept_file(self):
        # 使用者 2026-10-05：22NL004_066 是原視華語新聞《晚安新聞》，毋是
        # 族語新聞，本底就無「同一支」通好保留；袂使為著欲過檢查烏白填一支。
        # （20240930S2000.mkv 本底嘛列佇遮，2026-10-29 更正：《看見族語》
        # 是族語新聞改名，毋是非新聞節目，已經提掉。）
        other = excluded_row(
            伺服器路徑="/home/mkv-raw/111.01-111.05/3月mxf檔/22NL004_066晚間族語新聞.mkv",
            排除原因="非新聞節目", 同一支的保留檔="")
        self.assertEqual(checks.excluded_problems([news_row()], [other],
                                                  server_path), [])

    def test_a_broken_source_mxf_needs_no_kept_file(self):
        # 使用者 2026-10-21：24NL003_190 等 8 支 mxf 大細 19 GB，干焦頭前
        # 幾 MB 有資料、後壁攏是 0，轉出來 0.7 秒。彼个時段無另外一支好
        # 保留，袂使為著欲過檢查烏白填一支。
        broken = excluded_row(
            伺服器路徑="/home/mkv-raw/113/7月/24NL003_190_族語午間新聞_Atayal.mkv",
            排除原因="原始mxf影片損毀", 同一支的保留檔="")
        self.assertEqual(checks.excluded_problems([news_row()], [broken],
                                                  server_path), [])

    def test_a_non_news_programme_listed_in_the_catalogue_is_named(self):
        other = excluded_row(
            伺服器路徑="/home/mkv-raw/112/6月/23NL004_174_族語晚間新聞_Paiwan.mkv",
            排除原因="非新聞節目", 同一支的保留檔="")
        row = news_row(原始影片檔案位置=(
            "home/mkv-raw/112/6月/23NL004_174_族語晚間新聞_Paiwan.mkv"))
        self.assertEqual(len(checks.excluded_problems([row], [other],
                                                      server_path)), 1)


if __name__ == "__main__":
    unittest.main()
