"""reread：kā一條失敗ê cue 切做「一句一段」，予視覺辨識重讀。

`blind_cues` 講會出佗幾條 cue 著愛閣看，這支講會出**彼條內底愛按怎切**。

## 為啥物袂使閣用 `mask_distance` 直接比相鄰兩格

切 cue 就是按呢失敗ê。背景若會振動（碎石、水面、白衫），逐格ê遮罩攏
無仝——20210220_051 cue 735 實測相鄰兩格ê Jaccard 中位數 0.726，門檻
0.35，等於逐格攏「換句」。訊號淹佇雜訊內底。

## 時間中位數先kā會振動ê洗掉

雜訊逐格走位，字幕停佇原所在。一个視窗內底逐像素取多數，會振動ê
點仔就無去，賰ê差不多就是字。實測 cue 735：原本遮罩 ink 中位數
12751（字幕才 2000-4000），三格交集了賰 3964。

洗過才比，兩組就分會開——實測真正換句 ≥0.68，雜訊 ≤0.33，中央
彼逝縫真闊。這是補查 agent 手動做ê法，這改kā伊寫做程式。

## 限制（寫佇遮，免閣重試一擺）

中位數干焦洗會掉**會振動**ê雜訊，洗袂掉**無振動**ê亮背景。
20210220_051 cue 125 是一張白紙文件（ink 38076），字幕才佔 2500，
換句ê時遮罩振動無到 7%——洗了猶原看無。彼型愛用別ê法。
"""
import unittest

import numpy as np

from scripts.news import reread


def mask(*spans, h=8, w=100):
    """一塊遮罩：spans 是 (x0, x1) 幾塊白ê。"""
    m = np.zeros((h, w), dtype=bool)
    for x0, x1 in spans:
        m[:, x0:x1] = True
    return m


def noisy(text_span, seed, h=8, w=100):
    """字幕固定，雜訊逐格走位——就是碎石背景彼款。"""
    m = mask(text_span, h=h, w=w)
    rng = np.random.RandomState(seed)
    for _ in range(30):
        x = rng.randint(0, w - 2)
        y = rng.randint(0, h - 1)
        m[y:y + 1, x:x + 2] = True
    return m


class TestMedian(unittest.TestCase):
    """視窗內逐像素取多數，會振動ê點仔就無去。"""

    def test_it_keeps_what_every_frame_agrees_on(self):
        frames = [noisy((10, 30), seed) for seed in range(5)]
        got = reread.median(frames)
        # 字幕彼塊逐格攏有，愛留咧
        self.assertTrue(got[:, 10:30].all())

    def test_it_drops_what_only_one_frame_had(self):
        frames = [mask((10, 30)), mask((10, 30)), mask((10, 30))]
        frames[1] = mask((10, 30), (60, 70))       # 干焦中央彼格有雜訊
        got = reread.median(frames)
        self.assertFalse(got[:, 60:70].any())

    def test_a_single_frame_is_itself(self):
        one = mask((10, 30))
        self.assertTrue((reread.median([one]) == one).all())

    def test_no_frames_is_reported_not_guessed(self):
        with self.assertRaises(Exception):
            reread.median([])


class TestWindows(unittest.TestCase):
    """逐格ê遮罩，先照時間切做視窗才做中位數。"""

    def test_it_groups_by_the_span_asked_for(self):
        frames = [mask((10, 30)) for _ in range(12)]
        got = reread.windows(frames, frame_dt=0.2, span=0.6)
        self.assertEqual(len(got), 4)          # 12 格 × 0.2 ＝ 2.4 秒 ÷ 0.6

    def test_a_short_tail_still_becomes_a_window(self):
        frames = [mask((10, 30)) for _ in range(8)]
        got = reread.windows(frames, frame_dt=0.2, span=0.6)
        self.assertEqual(len(got), 3)          # 3+3+2

    def test_each_window_carries_where_it_starts(self):
        frames = [mask((10, 30)) for _ in range(6)]
        got = reread.windows(frames, frame_dt=0.2, span=0.6)
        self.assertEqual([w["first"] for w in got], [0, 3])


class TestBoundaries(unittest.TestCase):
    """洗過ê視窗兩兩相比，超過門檻才算換句。"""

    def _win(self, spans_per_window, frames_each=3):
        frames = []
        for spans in spans_per_window:
            for _ in range(frames_each):
                frames.append(mask(*spans))
        return reread.windows(frames, frame_dt=0.2, span=0.6)

    def test_a_real_change_is_a_boundary(self):
        w = self._win([[(10, 30)], [(10, 30)], [(60, 90)], [(60, 90)]])
        self.assertEqual(reread.boundaries(w), [2])

    def test_no_change_is_no_boundary(self):
        w = self._win([[(10, 30)], [(10, 30)], [(10, 30)]])
        self.assertEqual(reread.boundaries(w), [])

    def test_moving_noise_does_not_make_a_boundary(self):
        # 逐格ê雜訊攏無仝，毋過字幕仝款——洗過就袂當做換句
        frames = []
        for seed in range(12):
            frames.append(noisy((10, 30), seed))
        w = reread.windows(frames, frame_dt=0.2, span=0.6)
        self.assertEqual(reread.boundaries(w), [])

    def test_two_changes_give_two_boundaries(self):
        w = self._win([[(10, 30)], [(40, 55)], [(70, 95)]])
        self.assertEqual(reread.boundaries(w), [1, 2])


class TestSegments(unittest.TestCase):
    """切出來ê段，時間愛落佇原本彼條 cue 內底。"""

    CUE = {"index": 735, "start": 100.0, "end": 102.4}

    def _frames(self):
        frames = []
        for spans in ([(10, 30)], [(10, 30)], [(60, 90)], [(60, 90)]):
            for _ in range(3):
                frames.append(mask(*spans))
        return frames

    def test_it_splits_at_the_boundary(self):
        got = reread.segments(self.CUE, self._frames(),
                              frame_dt=0.2, span=0.6)
        self.assertEqual(len(got), 2)

    def test_the_first_segment_starts_where_the_cue_starts(self):
        got = reread.segments(self.CUE, self._frames(),
                              frame_dt=0.2, span=0.6)
        self.assertAlmostEqual(got[0]["start"], 100.0)

    def test_the_last_segment_ends_where_the_cue_ends(self):
        got = reread.segments(self.CUE, self._frames(),
                              frame_dt=0.2, span=0.6)
        self.assertAlmostEqual(got[-1]["end"], 102.4)

    def test_the_segments_join_up_with_no_hole(self):
        got = reread.segments(self.CUE, self._frames(),
                              frame_dt=0.2, span=0.6)
        self.assertAlmostEqual(got[0]["end"], got[1]["start"])

    def test_a_cue_with_one_sentence_stays_one_segment(self):
        frames = [mask((10, 30)) for _ in range(12)]
        got = reread.segments(self.CUE, frames, frame_dt=0.2, span=0.6)
        self.assertEqual(len(got), 1)
        self.assertAlmostEqual(got[0]["start"], 100.0)
        self.assertAlmostEqual(got[0]["end"], 102.4)

    def test_each_segment_says_which_cue_it_came_from(self):
        got = reread.segments(self.CUE, self._frames(),
                              frame_dt=0.2, span=0.6)
        for seg in got:
            self.assertEqual(seg["cue"], 735)

    def test_segments_are_numbered_in_order(self):
        got = reread.segments(self.CUE, self._frames(),
                              frame_dt=0.2, span=0.6)
        self.assertEqual([s["part"] for s in got], [1, 2])


class TestPack(unittest.TestCase):
    """段落分張：一張 sheet 囥幾條，佮伊ê編號。

    視覺辨識ê讀者是照 gutter 印ê編號抄ê，所以編號愛**家己講會出**
    伊是佗一條 cue ê第幾段——`735.03` 按呢。若干焦印流水號，讀轉來
    ê時陣無法度知影愛併轉去佗一格。
    """

    SEGS = [{"cue": 735, "part": n + 1, "start": 0.0, "end": 1.0}
            for n in range(7)]

    def test_it_fills_a_sheet_before_starting_the_next(self):
        got = reread.pack(self.SEGS, per=3)
        self.assertEqual([len(s) for s in got], [3, 3, 1])

    def test_every_segment_lands_somewhere(self):
        got = reread.pack(self.SEGS, per=3)
        total = 0
        for sheet in got:
            total += len(sheet)
        self.assertEqual(total, len(self.SEGS))

    def test_nothing_to_pack_is_no_sheets(self):
        self.assertEqual(reread.pack([], per=3), [])

    def test_the_label_names_the_cue_and_the_part(self):
        self.assertEqual(reread.label(self.SEGS[2]), "735.03")

    def test_the_label_pads_so_they_sort(self):
        seg = {"cue": 7, "part": 12}
        self.assertEqual(reread.label(seg), "7.12")


class TestFold(unittest.TestCase):
    """讀轉來ê段落文字，愛併轉去原本彼格 cue。

    一格 cue 切做幾若段，讀者逐段各讀一逝字。beh入 TSV ê時愛照
    `part` ê順序接倒轉去——接毋著順序，話就顛倒反。

    空ê段（彼段無字幕）愛跳過，莫留空縫。
    """

    def test_it_joins_the_parts_in_order(self):
        got = reread.fold([
            {"cue": 735, "part": 2, "text": "比較深根的一個"},
            {"cue": 735, "part": 1, "text": "它會先種芋頭"},
            {"cue": 735, "part": 3, "text": "種植法"},
        ])
        self.assertEqual(got[735], "它會先種芋頭比較深根的一個種植法")

    def test_blank_parts_leave_no_gap(self):
        got = reread.fold([
            {"cue": 9, "part": 1, "text": "頭一句"},
            {"cue": 9, "part": 2, "text": ""},
            {"cue": 9, "part": 3, "text": "第三句"},
        ])
        self.assertEqual(got[9], "頭一句第三句")

    def test_several_cues_stay_apart(self):
        got = reread.fold([
            {"cue": 1, "part": 1, "text": "甲"},
            {"cue": 2, "part": 1, "text": "乙"},
        ])
        self.assertEqual(got, {1: "甲", 2: "乙"})

    def test_a_cue_whose_parts_are_all_blank_is_blank(self):
        got = reread.fold([
            {"cue": 5, "part": 1, "text": ""},
            {"cue": 5, "part": 2, "text": "  "},
        ])
        self.assertEqual(got[5], "")


class TestHasText(unittest.TestCase):
    """段落洗過猶原無墨ê，莫送去讀——彼段本底就無字幕。

    片頭動畫是上明ê例：伊真光、ink 真懸，所以用「ink 大細」篩袂掉。
    毋過伊逐格攏咧振動，中位數洗了就賰無偌濟。實測
    20210215_046_晚間_Amis_阿美：

        cue 有字ê 64 段   中位數 ink 6481
        cue 空白ê 26 段   中位數 ink   63

    兩組差兩个數量級。門檻 400 留 58/64 有字段、擋掉 22/26 空白段；
    予伊擋掉ê彼 6 段有字段，本身mā是無字幕ê空縫（cue 有字，毋過彼
    一段拄好無）——擋著是著ê，毋是漏。

    這集若無篩，90 段內底 26 段（29%）是白做ê，其中 19 段是 cue 1
    彼个片頭動畫。
    """

    def test_a_line_of_text_passes(self):
        m = mask((10, 30), h=8, w=100)          # 8×20 ＝ 160 點
        self.assertTrue(reread.has_text(m, floor=100))

    def test_an_empty_mask_does_not(self):
        m = mask(h=8, w=100)
        self.assertFalse(reread.has_text(m, floor=100))

    def test_a_few_stray_pixels_do_not(self):
        m = mask((10, 12), h=8, w=100)          # 8×2 ＝ 16 點
        self.assertFalse(reread.has_text(m, floor=100))

    def test_the_floor_is_what_decides(self):
        m = mask((10, 30), h=8, w=100)
        self.assertFalse(reread.has_text(m, floor=1000))


class TestSlivers(unittest.TestCase):
    """尾溜彼塊碎片愛併轉去，袂使家己做一段。

    `stream_region` 回ê格數會比「時長×fps」加一格（實測 cue 234 長
    6.48 秒、5fps，回 33 格＝6.6 秒份）。按呢上尾彼个視窗ê起點就
    落佇 cue 結束前 0.08 秒，切出一段 0.08 秒ê碎片。

    0.08 秒囥袂落一句話——彼格影像實際上已經是**後一條 cue** ê句矣。
    實測 20210215_046：

        段 234.02  986.66–986.74（0.08s）→ 讀著「像ferfer一樣可以飛黃騰達」
        cue 235    986.74 起            → TSV 就是彼句
        段 311.02  1245.22–1245.30      → 讀著「蛋白質來源」
        cue 312    1245.30 起           → TSV 就是彼句

    收落去就是kā厝邊ê句囥入毋著格——補查著愛改ê就是這類。所以傷短ê
    段愛併轉去頂一段，莫家己成一段。
    """

    CUE = {"index": 234, "start": 980.26, "end": 986.74}

    def test_a_sliver_at_the_end_is_merged_back(self):
        # 33 格：頭 32 格一句，上尾一格是後一條 cue ê句
        frames = [mask((10, 30)) for _ in range(32)] + [mask((60, 90))]
        got = reread.segments(self.CUE, frames, frame_dt=0.2, span=0.8)
        self.assertEqual(len(got), 1)
        self.assertAlmostEqual(got[0]["end"], 986.74)

    def test_a_real_second_sentence_is_not_merged(self):
        # 兩句各 16 格＝3.2 秒，遠遠超過門檻
        frames = ([mask((10, 30))] * 16) + ([mask((60, 90))] * 17)
        got = reread.segments(self.CUE, frames, frame_dt=0.2, span=0.8)
        self.assertEqual(len(got), 2)

    def test_segments_still_cover_the_cue_end_to_end(self):
        frames = [mask((10, 30)) for _ in range(32)] + [mask((60, 90))]
        got = reread.segments(self.CUE, frames, frame_dt=0.2, span=0.8)
        self.assertAlmostEqual(got[0]["start"], 980.26)
        self.assertAlmostEqual(got[-1]["end"], 986.74)


class TestFoldRepeats(unittest.TestCase):
    """切傷細ê時，相連兩段會是仝一句——莫kā伊接兩擺。

    實測 20210215_046 段 210.01／210.02 兩段畫面攏是「學校有限制一星期
    26節」（210.02 才 0.28 秒）。若照接，TSV 彼格就變「學校有限制一星期
    26節學校有限制一星期26節」——畫面上從來無出現過ê字串。
    """

    def test_a_part_repeating_the_one_before_is_dropped(self):
        got = reread.fold([
            {"cue": 210, "part": 1, "text": "學校有限制一星期26節"},
            {"cue": 210, "part": 2, "text": "學校有限制一星期26節"},
        ])
        self.assertEqual(got[210], "學校有限制一星期26節")

    def test_a_repeat_that_is_not_adjacent_is_kept(self):
        # 仝一句講兩擺，中央有別句——彼是真ê重複，愛留
        got = reread.fold([
            {"cue": 9, "part": 1, "text": "甲"},
            {"cue": 9, "part": 2, "text": "乙"},
            {"cue": 9, "part": 3, "text": "甲"},
        ])
        self.assertEqual(got[9], "甲乙甲")

    def test_a_blank_between_two_repeats_still_counts_as_adjacent(self):
        got = reread.fold([
            {"cue": 9, "part": 1, "text": "甲"},
            {"cue": 9, "part": 2, "text": ""},
            {"cue": 9, "part": 3, "text": "甲"},
        ])
        self.assertEqual(got[9], "甲")


class TestFoldNeighbours(unittest.TestCase):
    """尾段若讀著後一條 cue ê句，莫接——彼是 cue 邊界劃了傷晏。

    切 cue ê邊界若劃傷晏，後一句ê頭就予切入前一條 cue ê尾溜。實測
    20210215_046：

        cue 31  116.00–119.00  TSV「今天我們暫時離開電腦」
        段 31.03  118.40–119.00  讀著「放下手機」
        cue 32  119.00 起       TSV 就是「放下手機」

    接落去會變「今天我們暫時離開電腦放下手機」——畫面頂懸這兩句
    毋捌做伙出現過。

    ## 判準ài有方向、有位置

    頭起先我寫做「文字若佮厝邊仝款就擲掉」，**大錯**：一句字幕停佇
    畫面跨幾若个 cue 是這个語料ê**常態寫法**（全批 12351 處相鄰 cue
    文字完全相同）。彼條規矩kā下面四條ê內容全部清空去：

        cue 30 ＝ cue 31 ＝ 今天我們暫時離開電腦
        cue 106 ＝ cue 107 ＝ 只懂皮毛而已
        cue 143 ＝ cue 144 ＝ 好像都隨身帶著彈弓
        cue 148 ＝ cue 149 ＝ 我才知道彈弓是父親的獵鳥器具

    所以判準是：**干焦「切做兩段以上」ê cue ê「上尾彼段」，而且伊
    佮「後一條」cue 仝款，才擲掉**。單段ê cue 一律莫振動——伊若真正
    裝著厝邊ê句，彼是改寫，愛換掉，毋是擲掉（擲掉就變空格）。
    """

    def test_a_tail_repeating_the_next_cue_is_dropped(self):
        got = reread.fold(
            [{"cue": 31, "part": 1, "text": "今天我們暫時離開電腦"},
             {"cue": 31, "part": 2, "text": ""},
             {"cue": 31, "part": 3, "text": "放下手機"}],
            after={31: "放下手機"})
        self.assertEqual(got[31], "今天我們暫時離開電腦")

    def test_a_line_spanning_two_cues_is_left_alone(self):
        # cue 30 佮 cue 31 仝款——彼是正常寫法，袂使擲
        got = reread.fold(
            [{"cue": 31, "part": 1, "text": "今天我們暫時離開電腦"}],
            after={31: "放下手機"}, before={31: "今天我們暫時離開電腦"})
        self.assertEqual(got[31], "今天我們暫時離開電腦")

    def test_a_single_part_cue_is_never_emptied(self):
        # 單段ê cue 就算佮後一條仝款嘛莫擲——擲了就變空格
        got = reread.fold(
            [{"cue": 144, "part": 1, "text": "好像都隨身帶著彈弓"}],
            after={144: "好像都隨身帶著彈弓"})
        self.assertEqual(got[144], "好像都隨身帶著彈弓")

    def test_a_middle_part_matching_the_next_cue_is_kept(self):
        # 干焦上尾彼段才有「後一句ê頭予切入來」ê問題
        got = reread.fold(
            [{"cue": 9, "part": 1, "text": "甲"},
             {"cue": 9, "part": 2, "text": "乙"},
             {"cue": 9, "part": 3, "text": "丙"}],
            after={9: "乙"})
        self.assertEqual(got[9], "甲乙丙")

    def test_without_the_neighbour_list_nothing_is_dropped(self):
        got = reread.fold(
            [{"cue": 31, "part": 1, "text": "甲"},
             {"cue": 31, "part": 2, "text": "乙"}])
        self.assertEqual(got[31], "甲乙")

    def test_the_match_is_whole_cell_not_substring(self):
        got = reread.fold(
            [{"cue": 5, "part": 1, "text": "老人家"},
             {"cue": 5, "part": 2, "text": "老人家就會跟我們講說"}],
            after={5: "老人家"})
        self.assertEqual(got[5], "老人家老人家就會跟我們講說")


class TestStaticBackground(unittest.TestCase):
    """**無**振動ê亮背景，愛用「減背景」才切會開。

    時間中位數洗會掉會振動ê雜訊，洗袂掉靜態ê。20210222_053 cue 111
    ê背景是一版**直排中文報紙**——規版攏是筆畫、閣一動都無動，遮罩
    ink 57126。字幕佇 21.4 秒內底換至少 5 擺，一擺都無予偵測著
    （`frames=106`，等於逐格攏「無變」）。

    靜態ê物件有一个對稱ê解法：**規條 cue ê中位數就是背景**，kā伊
    對逐格減掉，賰ê就是會變ê字幕。實測：

        cue 111  1 段 → 9 段
        cue 125  2 段 → 8 段（白紙文件，實際 6 句）
        cue 735 20 段 → 21 段（會振動彼型，無影響）

    ## 毋過袂使逐條攏減

    字幕若規條 cue 攏無變（正常ê cue 就是按呢），伊家己就變做「背景」
    予減掉，賰ê是雜訊——20210220_051 cue 27（17.2 秒一句）減了炸做
    **14 段**。

    所以愛看**減了賰偌濟墨**：

        愛切ê   cue 111  8164    cue 125  5504
        袂使切ê cue  27    24    cue 960   234   cue 144  1933

    3000 佇中央，兩爿分會清。一逝字幕ê筆畫大約 2000-4000，所以這
    條ê意思是「至少有一逝字ê份量咧變」。
    """

    def _masks(self, bg_span, lines, per=6, h=8, w=200):
        """靜態背景 ＋ 換來換去ê字幕。"""
        out = []
        for span in lines:
            for _ in range(per):
                out.append(mask(bg_span, span, h=h, w=w))
        return out

    def test_a_static_background_hides_the_change_without_subtraction(self):
        # 背景佔規塊，字幕振動看袂出
        got = self._masks((0, 150), [(160, 180), (160, 180)])
        plain = reread.boundaries(reread.windows(got, frame_dt=0.2, span=0.8))
        self.assertEqual(plain, [])

    def test_subtracting_it_brings_the_change_back(self):
        got = self._masks((0, 150), [(160, 175), (180, 195)])
        fg = reread.foreground(got)
        self.assertTrue(reread.boundaries(
            reread.windows(fg, frame_dt=0.2, span=0.8)))

    def test_the_background_is_what_every_frame_shares(self):
        got = self._masks((0, 150), [(160, 175), (180, 195)])
        bg = reread.median(got)
        self.assertTrue(bg[:, 0:150].all())
        self.assertFalse(bg[:, 160:195].any())

    def test_a_moving_background_is_not_worth_subtracting(self):
        """字幕無振動、**背景**咧振動ê時，減背景會kā字幕減掉。

        20210215_046 cue 148：規條 2.54 秒攏是「我才知道彈弓是父親的
        獵鳥器具」一句，鏡頭佇樹林內底橫搖。字幕是靜態ê，所以伊落佇
        中位數內底變做「背景」；減了賰ê是咧振動ê樹葉，切做 3 段——
        假ê。

        前景 ink 4511 過門檻，光靠 ink 擋袂牢。愛閣看**遮罩ê穩定度**：

            愛減ê   cue 111  0.205   cue 125  0.174
            莫減ê   cue 148  0.572   cue 735  0.982

        0.35 就是 `Segmenter` 家己ê `change`——意思是「遮罩佮規條 cue
        ê中位數夠倚，切 cue 機制會判做無變」。
        """
        moving = []
        for k in range(12):
            # 字幕固定，背景一逝一逝徙位
            moving.append(mask((160, 180), (k * 8, k * 8 + 40), h=8, w=200))
        self.assertFalse(reread.worth_subtracting(moving, 0.2, floor=50))

    def test_a_steady_subtitle_is_not_worth_subtracting(self):
        # 字幕規條 cue 攏無變：減了賰無物，莫用減背景
        got = [mask((0, 150), (160, 180), h=8, w=200) for _ in range(12)]
        self.assertFalse(reread.worth_subtracting(got, 0.2, floor=100))

    def test_a_changing_subtitle_is_worth_subtracting(self):
        got = self._masks((0, 150), [(160, 175), (180, 195)])
        self.assertTrue(reread.worth_subtracting(got, 0.2, floor=50))

    def test_segments_uses_it_only_when_it_helps(self):
        cue = {"index": 111, "start": 0.0, "end": 2.4}
        steady = [mask((0, 150), (160, 180), h=8, w=200) for _ in range(12)]
        self.assertEqual(len(reread.segments(cue, steady, frame_dt=0.2)), 1)


if __name__ == "__main__":
    unittest.main()
