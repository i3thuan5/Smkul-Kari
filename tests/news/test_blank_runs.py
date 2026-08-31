"""blank_runs: the offline half of finding subtitles printed outside the band.

A stretch of programme whose subtitles sit outside `REGION` reaches the
reader as blank strips, so it lands in the store as a long run of empty
vision text. Ordinary gaps -- an establishing shot, a graphic card -- run
a handful of cues; 056晚 ran 147. Telling those apart needs no video,
which is the point: it screens every episode ever delivered for free.

Length alone does not tell them apart, though: 006 ê病灶干焦 **12 條**，
仝彼集良性ê空鏡連紲 **13 條**，比病灶較長。分會開ê證據是圖條**頂端
予切掉ê墨**——字幕印佇帶頂懸，region 干焦切著字ê下半截。
"""
import json
import os
import tempfile
import unittest
from unittest import mock

import numpy as np

from scripts.news import blank_runs
from scripts.news import paths
from scripts.ocr import cuelib


class TestRunsOfBlank(unittest.TestCase):
    def test_no_blanks_is_no_runs(self):
        rows = {1: "有", 2: "有", 3: "有"}
        self.assertEqual(blank_runs.runs_of_blank(rows), [])

    def test_one_blank_is_a_run_of_one(self):
        rows = {1: "有", 2: "", 3: "有"}
        self.assertEqual(blank_runs.runs_of_blank(rows), [(2, 2)])

    def test_neighbouring_blanks_join_into_one_run(self):
        rows = {1: "有", 2: "", 3: "", 4: "", 5: "有"}
        self.assertEqual(blank_runs.runs_of_blank(rows), [(2, 4)])

    def test_a_gap_of_text_splits_two_runs(self):
        rows = {1: "", 2: "", 3: "有", 4: "", 5: ""}
        self.assertEqual(blank_runs.runs_of_blank(rows), [(1, 2), (4, 5)])

    def test_a_run_reaching_the_last_cue_is_closed(self):
        """尾溜彼段上要緊——片尾ê空白就是按呢，袂使落勾。"""
        rows = {1: "有", 2: "", 3: ""}
        self.assertEqual(blank_runs.runs_of_blank(rows), [(2, 3)])

    def test_whitespace_only_counts_as_blank(self):
        rows = {1: "有", 2: "   ", 3: "有"}
        self.assertEqual(blank_runs.runs_of_blank(rows), [(2, 2)])

    def test_cue_order_not_insertion_order(self):
        """TSV 是逐批讀ê，dict 內底ê順序毋是 cue ê順序。"""
        rows = {3: "", 1: "有", 2: ""}
        self.assertEqual(blank_runs.runs_of_blank(rows), [(2, 3)])

    def test_numbering_with_holes_does_not_merge_across_them(self):
        """Cue 號碼會跳；跳過去彼幾條無算佇連紲內底。"""
        rows = {1: "", 2: "", 9: "", 10: ""}
        self.assertEqual(blank_runs.runs_of_blank(rows), [(1, 10)])


def strip(white=None, dark=None, shape=(20, 40)):
    """A synthetic contact-sheet strip: mid-grey picture, optional glyph.

    Mid-grey is neither white (`white_min` 185) nor dark (`dark_max` 95),
    so an empty strip carries no ink at all. `white` and `dark` are row
    slices: a glyph body and the black outline that proves it is a glyph
    rather than a bright piece of picture.
    """
    rgb = np.full(shape + (3,), 120, dtype=np.uint8)
    if white is not None:
        rgb[white[0]:white[1]] = 255
    if dark is not None:
        rgb[dark[0]:dark[1]] = 0
    return rgb


class TestEdgeInk(unittest.TestCase):
    """圖條頂端予切掉ê墨——字幕印佇 region 頂懸ê證據。

    Region 對 y=722 起。字幕若印佇頂懸，切出來ê圖條干焦食著字ê下半
    截，墨會**貼著上頂彼逝**。字幕若好好仔佇帶內底，字ê頂懸離圖條
    邊猶有空縫，頂逝就是清氣ê。
    """

    SPEC = cuelib.MaskSpec()

    def test_a_glyph_cut_by_the_top_edge_is_measured(self):
        rgb = strip(white=(0, 3), dark=(3, 7))
        self.assertGreater(blank_runs.edge_ink(rgb, self.SPEC), 0)

    def test_an_empty_strip_has_no_edge_ink(self):
        self.assertEqual(blank_runs.edge_ink(strip(), self.SPEC), 0)

    def test_a_subtitle_in_its_proper_place_has_no_edge_ink(self):
        # 字幕佇帶內底：墨佇中央，頂逝清氣
        rgb = strip(white=(9, 12), dark=(12, 16))
        self.assertEqual(blank_runs.edge_ink(rgb, self.SPEC), 0)

    def test_bright_picture_without_an_outline_is_not_ink(self):
        """白衫、天光嘛是光ê，毋過無烏邊——判準愛分會開。"""
        rgb = strip(white=(0, 3))
        self.assertEqual(blank_runs.edge_ink(rgb, self.SPEC), 0)

    def test_how_deep_the_edge_reaches_is_adjustable(self):
        rgb = strip(white=(4, 6), dark=(6, 10))
        self.assertEqual(blank_runs.edge_ink(rgb, self.SPEC, rows=3), 0)
        self.assertGreater(blank_runs.edge_ink(rgb, self.SPEC, rows=6), 0)


class TestCutEvidence(unittest.TestCase):
    """Edge ink alone flags the wrong things, so the shape counts too.

    Measured on 006: a full-screen graphic card (資料畫面, dark text on a
    pale field) puts as much ink against the top edge as a cut-off
    subtitle does -- the pale field is white, the dark lettering supplies
    the outline, and `text_mask` cannot tell them apart from three rows.

    什麼分會開ê是**墨khǹg佇佗位**。字幕印佇帶頂懸，圖條干焦食著字ê
    下半截,墨規陣khû佇頂逝,下底是畫面;圖卡ê墨是規條攏有。實測ê比
    值：真病灶 0.099 佮 0.320，圖卡佮良性ê攏 ≤0.029。
    """

    SPEC = cuelib.MaskSpec()

    def test_it_reports_the_edge_and_the_whole_strip(self):
        rgb = strip(white=(0, 3), dark=(3, 7))
        edge, total = blank_runs.cut_evidence(rgb, self.SPEC)
        self.assertGreater(edge, 0)
        self.assertGreaterEqual(total, edge)

    def test_a_cut_off_subtitle_concentrates_its_ink_at_the_edge(self):
        rgb = strip(white=(0, 3), dark=(3, 7))
        edge, total = blank_runs.cut_evidence(rgb, self.SPEC)
        self.assertGreater(edge / total, 0.5)

    def test_a_graphic_card_spreads_its_ink_down_the_strip(self):
        """整面圖卡：頂懸嘛有墨，毋過規條攏是墨——毋是予切掉ê字。

        淺底烏字，字散規條攏是，所以逐逝ê白攏 khiā 佇烏ê邊仔——
        `text_mask` kā規條當做墨。
        """
        rgb = np.full((20, 40, 3), 255, dtype=np.uint8)
        rgb[2::4] = 0                      # 烏字逐逝攏有
        edge, total = blank_runs.cut_evidence(rgb, self.SPEC)
        self.assertGreater(edge, 0)
        self.assertLess(edge / total, 0.3)

    def test_an_empty_strip_divides_by_nothing(self):
        self.assertEqual(blank_runs.cut_evidence(strip(), self.SPEC), (0, 0))


class TestEdgeMarks(unittest.TestCase):
    """墨ê**形**：字是規排幼痕，管仔佮裝飾毋是。

    干焦量墨ê量佮伊集中無，分袂出予切斷ê字佮光ê細物件。實測ê假
    ê內底上厲害彼个是菜園ê鍍鋅水管（002晚 cue 479，佔比 0.309），
    佮 006 彼段真ê（0.320）差不多仝款——**無一个門檻分會開**。

    形分會開：一逝字ê下半截是**濟條幼ê痕**（筆畫），水管是**少
    數條闊ê**，裝飾是**幾條爾爾**。實測：

        真ê   006 cue 170  16 痕  中位闊 4
              056晚 cue 312  26 痕  中位闊 4
              058晨 cue 77   29 痕  中位闊 5
        假ê   002晚 cue 479  14 痕  中位闊 **21**（水管）
              002午 cue 737   6 痕（布料掛飾）
              057午 cue 386   2 痕（過場動畫）

    Spec 講ê就是這件：「字形只剩下半截被截斷的證據」。
    """

    SPEC = cuelib.MaskSpec()

    def _strip_with_marks(self, count, width, rows=(0, 3)):
        """頂逝khǹg `count` 條闊 `width` ê痕，逐條下底攏有烏邊。"""
        rgb = np.full((20, 400, 3), 120, dtype=np.uint8)
        x = 5
        for _ in range(count):
            rgb[rows[0]:rows[1], x:x + width] = 255
            rgb[rows[1]:rows[1] + 4, x:x + width] = 0
            x += width + 4
        return rgb

    def test_a_row_of_strokes_counts_them(self):
        rgb = self._strip_with_marks(12, 4)
        self.assertGreaterEqual(blank_runs.edge_marks(rgb, self.SPEC)[0], 10)

    def test_it_reports_the_median_width(self):
        marks, width = blank_runs.edge_marks(self._strip_with_marks(12, 4),
                                             self.SPEC)
        self.assertEqual(marks, 12)
        self.assertEqual(width, 4)

    def test_one_long_bar_is_not_a_row_of_strokes(self):
        """水管：一條闊ê，痕數少、闊度大。"""
        marks, width = blank_runs.edge_marks(self._strip_with_marks(2, 60),
                                             self.SPEC)
        self.assertLess(marks, 10)
        self.assertGreater(width, 20)

    def test_a_couple_of_specks_are_not_a_row_of_strokes(self):
        marks, _ = blank_runs.edge_marks(self._strip_with_marks(2, 4),
                                         self.SPEC)
        self.assertLess(marks, 10)

    def test_an_empty_strip_has_no_marks(self):
        rgb = np.full((20, 400, 3), 120, dtype=np.uint8)
        self.assertEqual(blank_runs.edge_marks(rgb, self.SPEC), (0, 0))


class TestFlaggedRuns(unittest.TestCase):
    """證據講了算，長度干焦排順序。

    006 ê 12 條病灶愛掠著，仝彼集 13 條ê揭牌空鏡袂使誤報——若準用
    長度做唯一判準，兩爿拄好倒péng。
    """

    SPANS = [(10, 21), (100, 112)]        # 12 條有病、13 條無代誌
    EVIDENCE = {}
    for _cue in range(10, 22):
        EVIDENCE[_cue] = (400, 800, 20, 4)   # 墨khû佇頂逝、形是字
    for _cue in range(100, 113):
        EVIDENCE[_cue] = (0, 4000, 0, 0)     # 畫面爾爾，頂逝無墨

    def test_the_short_run_with_edge_ink_is_flagged(self):
        got = blank_runs.flagged_runs(self.SPANS, self.EVIDENCE, floor=100)
        self.assertEqual([(r["first"], r["last"]) for r in got], [(10, 21)])

    def test_the_longer_clean_run_is_not_flagged(self):
        got = blank_runs.flagged_runs(self.SPANS, self.EVIDENCE, floor=100)
        self.assertNotIn((100, 112), [(r["first"], r["last"]) for r in got])

    def test_a_flagged_run_carries_the_evidence_and_its_length(self):
        got = blank_runs.flagged_runs(self.SPANS, self.EVIDENCE, floor=100)
        self.assertEqual(got[0]["ink"], 400)
        self.assertEqual(got[0]["cues"], 12)

    def test_evidence_below_the_floor_is_not_flagged(self):
        got = blank_runs.flagged_runs(self.SPANS, self.EVIDENCE, floor=500)
        self.assertEqual(got, [])

    def test_the_strongest_evidence_comes_first_not_the_longest_run(self):
        spans = [(1, 2), (50, 80)]
        evidence = {1: (900, 1200, 20, 4), 2: (900, 1200, 20, 4)}
        for cue in range(50, 81):
            evidence[cue] = (200, 400, 18, 4)
        got = blank_runs.flagged_runs(spans, evidence, floor=100)
        self.assertEqual([r["first"] for r in got], [1, 50])

    def test_a_cue_with_no_strip_counts_as_no_evidence(self):
        """圖條無佇咧（work dir 清掉矣）袂使煏——算做無證據就好。"""
        got = blank_runs.flagged_runs([(5, 6)], {}, floor=100)
        self.assertEqual(got, [])

    def test_a_graphic_card_run_is_not_flagged_however_inky(self):
        """實測 006：圖卡ê頂逝墨比病灶較濟，比值分會開，絕對量分袂開。"""
        evidence = {}
        for cue in range(1, 7):
            evidence[cue] = (387, 23322, 30, 4)   # 006 cue 149 實測
        got = blank_runs.flagged_runs([(1, 6)], evidence, floor=100)
        self.assertEqual(got, [])

    def test_a_bright_thin_object_is_not_flagged(self):
        """002晚 cue 479 實測：菜園水管，佔比 0.309，形毋是字。"""
        evidence = {1: (389, 1259, 14, 21)}
        got = blank_runs.flagged_runs([(1, 1)], evidence, floor=60,
                                      share=0.11)
        self.assertEqual(got, [])

    def test_a_cut_off_line_of_type_is_flagged(self):
        """006 cue 170 實測：16 痕、中位闊 4——形著、量著、集中著。"""
        evidence = {1: (145, 453, 16, 4)}
        got = blank_runs.flagged_runs([(1, 1)], evidence, floor=60,
                                      share=0.11)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["marks"], 16)

    def test_a_speck_does_not_shadow_a_real_one_in_the_same_run(self):
        """一條雜訊ê比值會使足懸（1/2 ＝ 0.5），毋過墨無夠。

        揀「比值上懸」彼條來代表規段，就會予這種雜訊kā真病灶閬掉——
        雜訊過袂了絕對門檻，規段soah綴伊落勾。判準是「**有一條**
        兩爿門檻攏過」，毋是「上懸彼條過」。
        """
        evidence = {1: (1, 2, 1, 1), 2: (300, 1000, 20, 4)}
        got = blank_runs.flagged_runs([(1, 2)], evidence, floor=100,
                                      share=0.11)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["ink"], 300)

    def test_a_run_of_nothing_but_specks_is_not_flagged(self):
        evidence = {1: (1, 2, 1, 1), 2: (2, 3, 1, 1)}
        got = blank_runs.flagged_runs([(1, 2)], evidence, floor=100,
                                      share=0.11)
        self.assertEqual(got, [])

    def test_the_share_gate_can_be_set(self):
        evidence = {1: (300, 3044, 20, 4)}    # 006 cue 1246 實測，比值 0.099
        self.assertEqual(
            blank_runs.flagged_runs([(1, 1)], evidence, floor=100,
                                    share=0.20), [])
        self.assertEqual(
            len(blank_runs.flagged_runs([(1, 1)], evidence, floor=100,
                                        share=0.05)), 1)


class TestCueTimes(unittest.TestCase):
    """複查清單ê時間欄：分「節目尾ê卡片」佮「中段漏勾ê對白」就靠伊。

    Store ê時間軸是規批做煞才定版ê，所以**當teh校讀彼批**佇 store
    內底揣無——拄好就是欲看清單彼批。所以時間對 work dir 家己ê
    時間軸提。
    """

    def _work(self, cues):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        os.makedirs(os.path.join(tmp.name, paths.COARSE_STAGE))
        path = os.path.join(tmp.name, paths.COARSE_STAGE, "cues.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"cues": cues}, handle)
        return tmp.name

    def test_it_maps_each_cue_to_its_seconds(self):
        work = self._work([{"index": 1, "start": 0.5, "end": 2.0},
                           {"index": 2, "start": 2.0, "end": 3.5}])
        self.assertEqual(blank_runs.cue_times(work),
                         {1: (0.5, 2.0), 2: (2.0, 3.5)})

    def test_a_work_dir_with_no_timeline_is_empty_not_an_error(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.assertEqual(blank_runs.cue_times(tmp.name), {})


class TestNoStripsIsNotNoFindings(unittest.TestCase):
    """「無圖條通量」佮「無代誌」是兩句無仝ê話。

    Work dir 是會使清掉ê，清掉了後這支就無證據通講話。彼陣若報
    「清氣」，就是kā「毋知」講做「無代誌」。
    """

    def test_a_missing_work_dir_answers_none(self):
        with mock.patch.object(blank_runs, "work_of", lambda name: None):
            self.assertIsNone(blank_runs.review("20210106_006_午間_Cou_鄒"))

    def test_a_work_dir_with_no_flagged_runs_answers_an_empty_list(self):
        with mock.patch.object(blank_runs, "work_of", lambda name: "/tmp"), \
             mock.patch.object(blank_runs, "blanks", lambda name: {}), \
             mock.patch.object(blank_runs, "evidence_of", lambda w, r: {}):
            self.assertEqual(blank_runs.review("20210106_006_午間_Cou_鄒"),
                             [])


if __name__ == "__main__":
    unittest.main()
