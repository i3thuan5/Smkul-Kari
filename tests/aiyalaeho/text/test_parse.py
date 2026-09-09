"""一個檔（decode.py 吐出來的文字）→ 一串列（行號,類型,族語,華語,開始,結束）。

四種排版型混在同一批資料裡：同行雙語、時碼＋同行雙語、隔行雙語、短片段。
每個 scenario 的樣本都取自真實盤點量到的樣子（見 design.md 的量測結果），
不是憑空編的字串。
"""
import unittest

from scripts.aiyalaeho.text import parse


class TestSameLineBilingual(unittest.TestCase):
    def test_double_slash_separator(self):
        rows = parse.parse_lines("ka:i' na pi ka laro'//唱起山柿之歌\n")
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["類型"], "雙語")
        self.assertEqual(row["族語"], "ka:i' na pi ka laro'")
        self.assertEqual(row["華語"], "唱起山柿之歌")
        self.assertEqual(row["行號"], 1)

    def test_double_backslash_separator(self):
        line = "qani ga 'a'iyalaeho:\\\\這是'a'iyalaeho:開會了節目\n"
        rows = parse.parse_lines(line)
        self.assertEqual(rows[0]["類型"], "雙語")
        self.assertEqual(rows[0]["族語"], "qani ga 'a'iyalaeho:")
        self.assertEqual(rows[0]["華語"], "這是'a'iyalaeho:開會了節目")


class TestTimecodeLines(unittest.TestCase):
    def test_timecode_pair_splits_into_four_columns(self):
        line = "00:00:14;15 00:00:17;09 族語\\\\華語\n"
        rows = parse.parse_lines(line)
        row = rows[0]
        self.assertEqual(row["開始時間"], "00:00:14;15")
        self.assertEqual(row["結束時間"], "00:00:17;09")
        self.assertEqual(row["族語"], "族語")
        self.assertEqual(row["華語"], "華語")

    def test_no_timecode_leaves_both_columns_blank(self):
        rows = parse.parse_lines("族語//華語\n")
        self.assertEqual(rows[0]["開始時間"], "")
        self.assertEqual(rows[0]["結束時間"], "")

    def test_single_timecode_line_fills_only_the_start_column(self):
        # 開會031、開會032 有幾個檔整份都是這個格式：一個時碼、沒有
        # 結束時間（下一條的開始隱含就是這一條的結束）。一開始漏了這
        # 條分支，1,130 列的族語欄開頭黏著原始時碼字串——真實資料抓到
        # 的，不是憑空想的。
        line = "00:00:16;06 djavaidjavai a tja sikataqaljan\\\\所有的部落族人大家好\n"
        rows = parse.parse_lines(line)
        row = rows[0]
        self.assertEqual(row["開始時間"], "00:00:16;06")
        self.assertEqual(row["結束時間"], "")
        self.assertEqual(row["族語"], "djavaidjavai a tja sikataqaljan")
        self.assertEqual(row["華語"], "所有的部落族人大家好")

    def test_timecode_pair_with_no_dialogue_is_a_marker_not_mixed_content(
            self):
        # 真實資料裡有的窗口沒有話要說（兩個時碼中間只有空白）——這是
        # 製作事實，不是漏譯；一開始沒接住，整串時碼字串掉進「混合」
        # 欄位裡（開會044 播出檔 line 83 就是這樣被抓到的）。
        rows = parse.parse_lines("00:04:47;14 00:04:47;16 \n")
        row = rows[0]
        self.assertEqual(row["類型"], "註記")
        self.assertEqual(row["開始時間"], "00:04:47;14")
        self.assertEqual(row["結束時間"], "00:04:47;16")
        self.assertEqual(row["族語"], "")
        self.assertEqual(row["華語"], "")


class TestMultipleSeparators(unittest.TestCase):
    """158 行有兩個以上分隔符，是四種病：分隔符打兩次、開頭就是分隔符、
    族語內部自己有分隔符、兩條字幕黏成一行。查無切法表就切最後一個。
    """

    def test_separator_doubled(self):
        rows = parse.parse_lines("maelranenga////謝謝\n")
        row = rows[0]
        self.assertEqual(row["類型"], "雙語（多重分隔符，規則切割）")
        # 切最後一個：族語留下多餘的分隔符，這是規則切割的已知代價，
        # AI 切割存在的理由正是修正這種情形。
        self.assertEqual(row["華語"], "謝謝")

    def test_line_starts_with_separator(self):
        rows = parse.parse_lines(
            "//mina nakhini honaehnge: ila ka pinaehrarangan//"
            "距離上次我們的討論也有一段時間了 \n")
        row = rows[0]
        self.assertEqual(row["類型"], "雙語（多重分隔符，規則切割）")
        self.assertEqual(row["華語"], "距離上次我們的討論也有一段時間了")

    def test_separator_used_inside_the_formosan_text(self):
        rows = parse.parse_lines(
            "imi ni ga pagluw ta//kumaal ci yogi na alang//"
            "\"聚在一起討論重要事務\"的意思\n")
        row = rows[0]
        self.assertEqual(row["類型"], "雙語（多重分隔符，規則切割）")
        self.assertEqual(row["族語"],
                         "imi ni ga pagluw ta//kumaal ci yogi na alang")
        self.assertEqual(row["華語"], "\"聚在一起討論重要事務\"的意思")

    def test_two_subtitles_glued_together_needs_the_split_table(self):
        # 這種病規則切最後一個一定切錯（族語會吃到華語1），必須靠切法
        # 表；沒有切法表時仍然退回規則切割並標明，不可以假裝規則對了。
        content = ("na semalji a'en uta//我也很好奇uri 'ivadaq a'en ta "
                   "aicu ti ina audra ui//想問問秋梅長老")
        rows = parse.parse_lines(content + "\n")
        row = rows[0]
        self.assertEqual(row["類型"], "雙語（多重分隔符，規則切割）")

    def test_split_table_entry_is_used_when_present_and_marked_ai(self):
        # 多重分隔符（至少兩個）才會查切法表；這裡先看「切法表只給
        # 一組族語華語」的情形——真正的兩句黏一行處理見
        # TestGluedSubtitles。
        content = "族語A//族語B//華語A"
        split_table = {content: [("族語A（AI校正）", "華語A（AI校正）")]}
        rows = parse.parse_lines(content + "\n", split_table=split_table)
        row = rows[0]
        self.assertEqual(len(rows), 1)
        self.assertEqual(row["類型"], "雙語（多重分隔符，AI切割）")
        self.assertEqual(row["族語"], "族語A（AI校正）")
        self.assertEqual(row["華語"], "華語A（AI校正）")


class TestGluedSubtitles(unittest.TestCase):
    """158 行裡有 3 行是真的兩句字幕黏成一行，不是分隔符打錯——規則
    切割會把後一句的族語整段吃進前一句的華語欄，唯一放得下兩句話的
    辦法是輸出兩列。真實案例：開會011_排灣族 第 8 行。
    """

    def test_a_line_that_is_really_two_glued_subtitles_becomes_two_rows(self):
        content = ("na semalji a'en uta//我也很好奇uri 'ivadaq a'en ta "
                   "aicu ti ina audra ui//想問問秋梅長老")
        split_table = {
            content: [
                ("na semalji a'en uta", "我也很好奇"),
                ("uri 'ivadaq a'en ta aicu ti ina audra ui", "想問問秋梅長老"),
            ],
        }
        rows = parse.parse_lines(content + "\n", split_table=split_table)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["類型"], "雙語（多重分隔符，AI切割）")
        self.assertEqual(rows[0]["族語"], "na semalji a'en uta")
        self.assertEqual(rows[0]["華語"], "我也很好奇")
        self.assertEqual(rows[1]["類型"], "雙語（多重分隔符，AI切割）")
        self.assertEqual(rows[1]["族語"],
                         "uri 'ivadaq a'en ta aicu ti ina audra ui")
        self.assertEqual(rows[1]["華語"], "想問問秋梅長老")

    def test_both_rows_share_the_same_line_number(self):
        content = "族語1//華語1//族語2//華語2"
        split_table = {content: [("族語1", "華語1"), ("族語2", "華語2")]}
        rows = parse.parse_lines("開頭\n" + content + "\n",
                                 split_table=split_table)
        self.assertEqual(rows[1]["行號"], rows[2]["行號"])
        self.assertEqual(rows[1]["行號"], 2)

    def test_no_extra_ordering_column_order_is_just_list_order(self):
        content = "族語1//華語1//族語2//華語2"
        split_table = {content: [("族語1", "華語1"), ("族語2", "華語2")]}
        rows = parse.parse_lines(content + "\n", split_table=split_table)
        self.assertNotIn("序", rows[0])
        self.assertEqual([r["族語"] for r in rows], ["族語1", "族語2"])


class TestInterleavedPairing(unittest.TestCase):
    def test_formosan_line_then_chinese_line_pair_up(self):
        text = "'ita' saboeh kayzaeh \n大家好\n"
        rows = parse.parse_lines(text)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["類型"], "隔行配對")
        self.assertEqual(row["族語"], "'ita' saboeh kayzaeh")
        self.assertEqual(row["華語"], "大家好")
        self.assertEqual(row["行號"], 1)

    def test_a_formosan_line_not_followed_by_chinese_stands_alone(self):
        # 卑南族歌謠的襯字，本來就沒有華語譯文——不可以跳過去抓後面的
        # 漢字行來配對。
        text = ("hoiyanahiyuin ho~yanahiyaoyan~nahiyaohayyan\n"
                "salawvulay ta inuwazukan na wadiyan an temuwamuwan \n"
                "族人及子孫們 我們相聚多美好\n")
        rows = parse.parse_lines(text)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["類型"], "僅族語")
        self.assertEqual(rows[0]["族語"],
                         "hoiyanahiyuin ho~yanahiyaoyan~nahiyaohayyan")
        self.assertEqual(rows[0]["華語"], "")
        self.assertEqual(rows[1]["類型"], "隔行配對")
        self.assertEqual(rows[1]["族語"],
                         "salawvulay ta inuwazukan na wadiyan an "
                         "temuwamuwan")
        self.assertEqual(rows[1]["華語"], "族人及子孫們 我們相聚多美好")


class TestTimecodedStandaloneLine(unittest.TestCase):
    """一個時碼前綴接著一句**只有單語**的話（沒有分隔符、不成對、不是
    註記）——這是真實資料才踩到的坑：`_classify_content` 對這種內容判
    不出類型會回傳 None，外層原本拿**還帶著時碼的原始行**去判斷隔行
    配對／落單，時碼字串就整串掉進族語或華語欄。開會004 有一整段
    Chinese-only 的旁白，逐行各自帶時碼、彼此不隔行配對，就是這樣
    被抓到的。
    """

    def test_timecoded_han_only_line_keeps_its_timecode_separate(self):
        rows = parse.parse_lines(
            "00:01:41:12 00:01:43:25 新竹縣五峰鄉桃山國小合唱團\n")
        row = rows[0]
        self.assertEqual(row["類型"], "僅華語")
        self.assertEqual(row["開始時間"], "00:01:41:12")
        self.assertEqual(row["結束時間"], "00:01:43:25")
        self.assertEqual(row["華語"], "新竹縣五峰鄉桃山國小合唱團")
        self.assertNotIn("00:01:41:12", row["族語"])

    def test_two_consecutive_timecoded_han_only_lines_do_not_pair(self):
        text = ("00:01:41:12 00:01:43:25 新竹縣五峰鄉桃山國小合唱團\n"
                "00:01:43:25 00:01:50:09 自30年前成立以來就頗負盛名\n")
        rows = parse.parse_lines(text)
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertEqual(row["類型"], "僅華語")
            self.assertTrue(row["開始時間"])


class TestMixedNoSeparator(unittest.TestCase):
    def test_formosan_and_chinese_on_one_line_without_separator(self):
        rows = parse.parse_lines(
            "ya:o tawtawazay 'itih ka kalih Say Sa:wi'我是豆家的 "
            "'itih a kalih 來自獅潭\n")
        row = rows[0]
        self.assertEqual(row["類型"], "混合")
        self.assertEqual(row["華語"], "")
        self.assertIn("我是豆家的", row["族語"])


class TestMarkerLines(unittest.TestCase):
    def test_os_marker(self):
        rows = parse.parse_lines("OS1\n")
        self.assertEqual(rows[0]["類型"], "註記")

    def test_bite_marker(self):
        rows = parse.parse_lines("Bite\n")
        self.assertEqual(rows[0]["類型"], "註記")

    def test_bare_digit_timecode_marker(self):
        rows = parse.parse_lines("035101\n")
        self.assertEqual(rows[0]["類型"], "註記")

    def test_deletion_instruction_marker(self):
        rows = parse.parse_lines("刪除 113208~\n")
        self.assertEqual(rows[0]["類型"], "註記")

    def test_marker_line_still_appears_in_output(self):
        rows = parse.parse_lines("OS1\n族語//華語\n")
        self.assertEqual(len(rows), 2)


class TestBlankLines(unittest.TestCase):
    def test_blank_lines_produce_no_rows(self):
        rows = parse.parse_lines("族語//華語\n\n   \n另一句//另一句華語\n")
        self.assertEqual(len(rows), 2)

    def test_line_numbers_count_the_original_blank_lines(self):
        rows = parse.parse_lines("族語//華語\n\n另一句//另一句華語\n")
        self.assertEqual(rows[0]["行號"], 1)
        self.assertEqual(rows[1]["行號"], 3)


if __name__ == "__main__":
    unittest.main()
