"""resplit：kā一條切毋著ê cue 換做幾若條，時間軸綴咧改。

`reread` 講會出一條 cue 內底實際有幾句、逐句佇佗位。這支kā彼寡段
真正寫入時間軸——彼條 cue 無去，換做 N 條，後壁ê編號綴咧徙。

## 為啥物愛動時間軸

補查干焦補文字：13 句接佇仝一格後壁，變做一條 27.58 秒ê字幕。
內容有轉來，毋過音檔佮文字對袂起來——這批語料是欲提去訓練語音
辨識ê，一條 27.58 秒內底 16 句ê條目，比缺漏閣較歹，因為伊看起來
是完整ê。

## 編號徙位是這步上危險ê所在

TSV 是照 cue 編號做索引ê。一條 cue 換做 16 條，後壁逐條攏愛加 15。
若時間軸改矣、TSV 無綴咧改，逐格ê字就會歪去——而且 `ingest` 掠
會著（伊會比對編號），毋過彼是走了才發現。所以兩爿愛做伙改。
"""
import unittest

from scripts.news import resplit


def cue(index, start, end, frames=5):
    return {"index": index, "start": start, "end": end, "frames": frames}


class TestReplace(unittest.TestCase):
    """一條換做幾若條，前後ê編號愛對。"""

    CUES = [cue(1, 0.0, 1.0), cue(2, 1.0, 5.0), cue(3, 5.0, 6.0)]
    PARTS = [{"cue": 2, "part": 1, "start": 1.0, "end": 3.0},
             {"cue": 2, "part": 2, "start": 3.0, "end": 5.0}]

    def test_the_cue_becomes_as_many_as_it_has_parts(self):
        got = resplit.replace(self.CUES, 2, self.PARTS)
        self.assertEqual(len(got), 4)

    def test_the_new_cues_carry_the_parts_times(self):
        got = resplit.replace(self.CUES, 2, self.PARTS)
        self.assertAlmostEqual(got[1]["start"], 1.0)
        self.assertAlmostEqual(got[1]["end"], 3.0)
        self.assertAlmostEqual(got[2]["start"], 3.0)
        self.assertAlmostEqual(got[2]["end"], 5.0)

    def test_everything_is_renumbered_from_one(self):
        got = resplit.replace(self.CUES, 2, self.PARTS)
        self.assertEqual([c["index"] for c in got], [1, 2, 3, 4])

    def test_the_cues_after_keep_their_times(self):
        got = resplit.replace(self.CUES, 2, self.PARTS)
        self.assertAlmostEqual(got[3]["start"], 5.0)
        self.assertAlmostEqual(got[3]["end"], 6.0)

    def test_the_timeline_still_has_no_holes(self):
        got = resplit.replace(self.CUES, 2, self.PARTS)
        for a, b in zip(got, got[1:]):
            self.assertLessEqual(a["end"], b["start"] + 1e-9)

    def test_one_part_changes_nothing(self):
        one = [{"cue": 2, "part": 1, "start": 1.0, "end": 5.0}]
        got = resplit.replace(self.CUES, 2, one)
        self.assertEqual([c["index"] for c in got], [1, 2, 3])

    def test_an_unknown_cue_is_reported_not_ignored(self):
        with self.assertRaises(Exception):
            resplit.replace(self.CUES, 99, self.PARTS)


class TestShift(unittest.TestCase):
    """TSV ê編號愛綴時間軸徙，兩爿袂使走精。"""

    def test_rows_before_the_split_are_untouched(self):
        got = resplit.shift({1: "甲", 2: "乙", 3: "丙"}, at=2, extra=2)
        self.assertEqual(got[1], "甲")

    def test_rows_after_move_up_by_the_number_added(self):
        got = resplit.shift({1: "甲", 2: "乙", 3: "丙"}, at=2, extra=2)
        self.assertEqual(got[5], "丙")

    def test_the_split_cue_itself_is_dropped(self):
        # 彼格ê內容由新ê逐段各自提供，舊ê無路用矣
        got = resplit.shift({1: "甲", 2: "乙", 3: "丙"}, at=2, extra=2)
        self.assertNotIn(2, got)

    def test_nothing_added_still_drops_the_old_row(self):
        got = resplit.shift({1: "甲", 2: "乙"}, at=2, extra=0)
        self.assertEqual(got, {1: "甲"})


class TestPlace(unittest.TestCase):
    """新切ê逐段，文字各自入去家己彼格。"""

    def test_each_part_lands_on_its_own_index(self):
        got = resplit.place({1: "甲", 4: "丁"}, at=2,
                            texts=["乙一", "乙二"])
        self.assertEqual(got[2], "乙一")
        self.assertEqual(got[3], "乙二")

    def test_the_rows_around_it_are_kept(self):
        got = resplit.place({1: "甲", 4: "丁"}, at=2,
                            texts=["乙一", "乙二"])
        self.assertEqual(got[1], "甲")
        self.assertEqual(got[4], "丁")


class TestSurvives(unittest.TestCase):
    """切開進前ê把關：這條 cue ê字敢會無去。

    這條判準是規个操作ê安全性所在——伊若判毋著，已經交付ê字會恬恬
    仔無去，而且無一个所在會報錯（`ingest`、`rebuild --verify` 攏
    袂掠著，因為兩爿是一致ê，干焦內容較少）。

    ## 方向愛顧予好

    頭起先寫做雙向子字串 `piece in t or t in piece`，**大錯**：厝邊
    若干焦有一塊片段，`t in piece` 就成立，規句話煞予人當做「有承接」
    放行。20210221_052 cue 60 就是按呢漏過去ê——既有是「就是一位難
    求搶搶搶下手(預定)手刀要快」，重讀切了賰頭尾兩段（中央「搶搶搶」
    才三个字，予 `has_text` 濾掉），厝邊 cue 61 是「下手(預定)手刀要
    快」，片段爾，煞予把關認做涵蓋。

    正確ê方向：**短去ê彼段愛出現佇厝邊**（`piece in t`），毋是顛倒。

    ## 字形更正愛先正規化

    無按呢做，把關會kā**刻意ê更正**當做落字擋落來。20210215_046 有
    七條按呢——既有kā「牠」認做「牝」，重讀改轉來，把關看著舊字揣無
    就擋。彼字本底就是錯ê。
    """

    NEAR = {"下手(預定)手刀要快", "厝邊別句"}

    def test_text_fully_rebuilt_survives(self):
        self.assertTrue(resplit.survives("甲乙丙", "甲乙丙", set()))

    def test_text_inside_the_new_join_survives(self):
        self.assertTrue(resplit.survives("甲乙", "甲乙丙", set()))

    def test_a_neighbour_holding_the_lost_part_survives(self):
        self.assertTrue(resplit.survives("甲乙", "甲", {"乙"}))

    def test_a_neighbour_holding_only_a_fragment_does_not(self):
        # 這是彼个方向錯誤：厝邊ê「乙」是短去彼段ê片段，袂使算涵蓋
        self.assertFalse(resplit.survives("甲乙丙", "甲", {"乙"}))

    def test_the_020210221_052_case(self):
        old = "就是一位難求搶搶搶下手(預定)手刀要快"
        new = "就是一位難求下手(預定)手刀要快"
        self.assertFalse(resplit.survives(old, new, self.NEAR))

    def test_a_known_glyph_fix_is_not_read_as_a_loss(self):
        # 既有「牝」，重讀改做「牠」——彼是更正，毋是落字
        self.assertTrue(
            resplit.survives("牝絆在這裡", "牠絆在這裡", set()))

    def test_the_20210208_039_case(self):
        """既有寫 `耆老`、讀者讀著畫面ê `者老`，把關掠做落字。

        彼條擋牢一條 cue，連紲害著兩句新句（`啊呀漢人今天都休息`、
        `準備吃團圓飯了`）入袂了正本。本底無囥入 FIXES 是因為兩種
        寫法佇語料庫攏實在有；2026-08-31 使用者裁定「錯字愛訂正做
        臺灣正體字」了後，`耆老` 才是對ê，這條就會使規則化。
        """
        self.assertTrue(
            resplit.survives("聽部落耆老早期的說法",
                             "聽部落者老早期的說法", set()))

    def test_simplified_forms_are_normalised_too(self):
        """簡體佮正體並排ê時，把關嘛袂使掠做落字。"""
        self.assertTrue(
            resplit.survives("根據统計", "根據統計", set()))
        self.assertTrue(
            resplit.survives("在宅醫療带進台灣", "在宅醫療帶進台灣", set()))

    def test_normalise_does_not_touch_what_gets_written(self):
        """FIXES 干焦是**比對**ê時用ê。寫入去ê是讀者寫ê彼字。"""
        self.assertEqual(resplit.normalise("者老"), resplit.normalise("耆老"))

    def test_an_empty_old_cell_always_survives(self):
        self.assertTrue(resplit.survives("", "隨便啥", set()))


class TestSurvivesAcrossTheBatch(unittest.TestCase):
    """厝邊ê**新**內容嘛算數——毋是干焦看舊ê。

    一句字幕跨過 cue ê界線ê時，重讀會kā伊判予真正佔多數彼爿，也就是
    **搬去厝邊ê段**。彼句無不見，是徙位。

    毋過把關本底是提「新ê這格」佮「**舊ê**厝邊」比，看袂著仝一批kā
    伊搬去佗。20210206_037 cue 498 就是按呢予擋落來ê：

        既有 cue 497 古琉璃珠的圖騰 ／ cue 498 樣式來製作
        畫面：498 彼 2.38 秒內底有 2.00 秒是「很像古琉璃珠」，
              「樣式來製作」是 497 ê尾溜跨界 0.34 秒
        重讀：497.01 古琉璃珠的圖騰、497.02 樣式來製作
              498.01/498.02 很像古琉璃珠

    照擋ê話，「樣式來製作」會佇 497.02 佮 498 出現兩擺，「很像古琉璃
    珠」永遠入袂了正本——**擋伊顛倒害著**。

    所以厝邊愛提**新ê**（若彼條嘛切過），無才提舊ê。
    """

    # 20210206_037 彼齣ê資料
    OLD = {496: "因此我們仿照", 497: "古琉璃珠的圖騰",
           498: "樣式來製作", 499: "不過不是真正的古琉璃珠"}
    NEW = {497: "古琉璃珠的圖騰樣式來製作", 498: "很像古琉璃珠"}

    def test_a_sentence_moved_into_a_neighbour_is_admitted(self):
        self.assertEqual(resplit.admit(self.OLD, self.NEW), {497, 498})

    def test_a_real_loss_is_still_blocked(self):
        # 497 無切開ê時，「樣式來製作」真正就是無去
        self.assertEqual(resplit.admit(self.OLD, {498: "很像古琉璃珠"}), set())

    def test_a_blocked_neighbour_cannot_vouch(self):
        # 497 家己嘛予擋ê時，伊ê新內容袂寫入去，就袂使替 498 作保。
        # 遮予 497 讀著一句厝邊揣無ê物件，逼伊予人擋。
        old = dict(self.OLD)
        old[497] = "古琉璃珠的圖騰另外一句厝邊無ê"
        self.assertEqual(resplit.admit(old, self.NEW), set())

    def test_unsplit_neighbours_still_vouch_with_their_old_text(self):
        self.assertEqual(
            resplit.admit({1: "甲乙", 2: "甲"}, {1: "乙"}), {1})


class TestUnsplitButChanged(unittest.TestCase):
    """切段器切無開、毋過讀者讀著無仝款——這款愛講出來，莫恬恬放捒。

    `reread` ê切段器佮交付管線是仝一路，所以**仝一款情形伊嘛會卡牢**：
    亮閣無振動ê背景（氣象圖、白紙）換句ê時遮罩變無到 7%，切袂開。
    彼時讀者看著兩句，煞干焦一格通好寫，只好kā兩句相黏做一格。

    `safe_resplit` 看著「單段」就跳過（無切開，免動），按呢讀者揣著ê
    彼句**規句無去**，而且無一个所在會講。

    20210219_050 cue 1115（11.1 秒）就是按呢：畫面 2753.8–2760.2 是
    「今日氣溫北部8至23度」、2761.0–2764.2 是「中部9至26度」，既有
    干焦記頭一句，讀者兩句攏讀著，寫做「今日氣溫北部8至23度中部9至
    26度」一格，紲落來規个予人擲捒。仝一集 cue 1116 仝款。

    分別著愛掠會準：讀者讀毋著字（「邊波」／「邊坡」）佮讀者看著
    較濟句，兩種佇資料頂懸生做仝款。所以這支**干焦報**，無家己改。
    """

    def test_it_reports_a_reader_that_saw_more(self):
        old = {1115: "今日氣溫北部8至23度"}
        single = {1115: "今日氣溫北部8至23度中部9至26度"}
        self.assertEqual(resplit.unsplit_but_changed(old, single), [1115])

    def test_it_stays_quiet_when_the_reader_agrees(self):
        old = {1115: "今日氣溫北部8至23度"}
        self.assertEqual(resplit.unsplit_but_changed(old, dict(old)), [])

    def test_a_reader_that_saw_less_is_not_reported(self):
        # 讀者讀較少ê時，既有有涵蓋，無新物件
        old = {180: "再重複再講一次"}
        self.assertEqual(resplit.unsplit_but_changed(old, {180: "再講"}), [])

    def test_a_blank_read_is_not_reported(self):
        self.assertEqual(
            resplit.unsplit_but_changed({7: "有字"}, {7: "  "}), [])


if __name__ == "__main__":
    unittest.main()
