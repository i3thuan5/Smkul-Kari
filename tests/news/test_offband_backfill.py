"""offband_backfill：已經讀完字ê集數，補切一段帶外字幕。

2021 年 7–8 月十幾集ê專題，對白印佇 y≈940–1035，字幕帶切出來ê cue 是照
帶內ê名牌、衣服切ê，讀者照規矩留空。欲補愛重切彼段——**讀字了後**
重切，後壁逐條攏重新編號，store 內底ê TSV 攏愛綴咧徙。號碼徙毋著，
文字就落佇別條字幕，無一个所在會報錯（逝數對、欄數對）。

這組測試顧ê是純算術：舊編號 → 新編號、TSV 改寫、段落表覆寫。
"""
import os
import tempfile
import unittest

from scripts.errors import PipelineError
from scripts.news import offband_backfill
from scripts.news import segments


def cue(index, start, end, area=None):
    item = {"index": index, "start": start, "end": end}
    if area:
        item["area"] = area
    return item


def band(count, step=20.0):
    out = []
    for index in range(count):
        out.append(cue(index + 1, index * step + 1, index * step + 15))
    return out


class TestRenumbering(unittest.TestCase):

    def setUp(self):
        self.old = band(10)                           # 1,21,…,181
        self.new = [cue(1, 50, 58, "帶外專題"), cue(2, 60, 70, "帶外專題"),
                    cue(3, 72, 79, "帶外專題")]
        self.spliced = offband_backfill.splice(self.old, 40, 100, self.new)

    def test_cues_outside_keep_their_text_under_a_new_number(self):
        moves = offband_backfill.moves(self.old, self.spliced)
        # 舊 1、2 無振動；舊 3–5（41、61、81）hőng換掉；舊 6 起徙號
        self.assertEqual(moves[1], 1)
        self.assertEqual(moves[2], 2)
        self.assertNotIn(3, moves)
        self.assertNotIn(5, moves)
        self.assertEqual(moves[6], 6)
        self.assertEqual(moves[10], 10)

    def test_the_new_cues_are_the_ones_carrying_the_area(self):
        fresh = offband_backfill.fresh_numbers(self.spliced)
        self.assertEqual(fresh, [3, 4, 5])

    def test_a_cue_that_moved_in_time_is_not_matched(self):
        # 時間無仝就毋是仝一條——照號碼對會kā文字囥去別條。
        spliced = []
        for item in self.spliced:
            spliced.append(dict(item))
        spliced[0]["start"] += 0.2
        moves = offband_backfill.moves(self.old, spliced)
        self.assertNotIn(1, moves)


class TestTsvRewrite(unittest.TestCase):

    def test_rows_are_renumbered_and_the_replaced_ones_dropped(self):
        rows = [(1, "甲"), (3, ""), (4, ""), (6, "丙"), (10, "丁")]
        moves = {1: 1, 2: 2, 6: 7, 10: 11}
        got = offband_backfill.rewrite(rows, moves, 10)
        self.assertEqual(got, [(1, "甲"), (7, "丙"), (11, "丁")])

    def test_text_is_passed_through_byte_for_byte(self):
        rows = [(2, " 前後空白 \t內底tab")]
        got = offband_backfill.rewrite(rows, {2: 5}, 10)
        self.assertEqual(got, [(5, " 前後空白 \t內底tab")])

    def test_a_row_for_a_cue_that_never_existed_stops_everything(self):
        with self.assertRaises(PipelineError):
            offband_backfill.rewrite([(99, "x")], {1: 1}, 10)


class TestReaderRows(unittest.TestCase):
    """讀者寫ê TSV 干焦會使有新 cue ê號碼，閣愛逐條攏有。"""

    def test_every_fresh_cue_needs_a_row(self):
        with self.assertRaises(PipelineError) as caught:
            offband_backfill.check_reader([(3, "a"), (4, "b")], [3, 4, 5])
        self.assertIn("5", str(caught.exception))

    def test_a_row_outside_the_stretch_is_refused(self):
        with self.assertRaises(PipelineError):
            offband_backfill.check_reader([(2, "a"), (3, "b")], [3])

    def test_a_complete_read_passes(self):
        offband_backfill.check_reader([(3, "a"), (4, ""), (5, "c")],
                                      [3, 4, 5])


class TestSegmentsOverride(unittest.TestCase):
    """段落表：像素規則判ê表，帶外專題彼段人工蓋過去。"""

    def rows(self):
        return [
            {"起秒": "0", "迄秒": "100", "類型": "攝影棚", "單元語別": "雅美",
             "字幕上緣y": "722", "字幕下緣y": "844", "依據": "自動"},
            {"起秒": "100", "迄秒": "300", "類型": "外景新聞",
             "單元語別": "雅美", "字幕上緣y": "722", "字幕下緣y": "844",
             "依據": "自動"},
            {"起秒": "300", "迄秒": "600.000", "類型": "主播外景",
             "單元語別": "雅美", "字幕上緣y": "722", "字幕下緣y": "844",
             "依據": segments.PENDING}]

    def test_the_stretch_becomes_one_manual_row(self):
        got = offband_backfill.override(self.rows(), 150, 420, "帶外專題")
        kinds = []
        for row in got:
            kinds.append((row["起秒"], row["迄秒"], row["類型"], row["依據"]))
        self.assertEqual(kinds, [
            ("0", "100", "攝影棚", "自動"),
            ("100", "150", "外景新聞", "自動"),
            ("150", "420", "帶外專題", "人工"),
            ("420", "600.000", "主播外景", segments.PENDING)])
        middle = got[2]
        self.assertEqual((middle["字幕上緣y"], middle["字幕下緣y"]),
                         ("930", "1040"))
        again = offband_backfill.override(got, 450, 500, "帶外專題",
                                          band=(868, 990))
        self.assertEqual((again[4]["起秒"], again[4]["字幕上緣y"],
                          again[4]["字幕下緣y"]), ("450", "868", "990"))
        self.assertEqual(again[2]["類型"], "帶外專題")   # 頭一擺ê猶在
        self.assertEqual(segments.check(got, "x", 600.0),
                         ["x 第 5 逝：依據 '待確認' 毋是 "
                          + "、".join(segments.BASES)])


class TestStartingTable(unittest.TestCase):
    """補切進前ê段落表對佗來。

    `20241209_344_晚間_Amis_阿美` 段落表已經讀者確認入庫矣，補切煞用
    2021 ê畫面判準重算一份，讀者確認過ê逝予一堆「他族插播／待確認」
    蓋掉。2021 彼幾集本底無段落表，所以無出代誌。
    """

    NAME = "20241209_344_晚間_Amis_阿美"

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = tmp.name
        self.out = self.root + "/out"
        self.store = self.root + "/store"

    def write(self, path, kind):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        segments.write(path, [
            {"起秒": "0", "迄秒": "100", "類型": kind, "單元語別": "阿美",
             "字幕上緣y": "840", "字幕下緣y": "930",
             "依據": "Claude Vision 確認"}])

    def start(self):
        return offband_backfill.starting_table(self.NAME, self.out,
                                               store=self.store)

    def test_a_confirmed_table_in_the_store_is_the_start(self):
        self.write(self.store + "/2024-12/%s.csv" % self.NAME, "攝影棚")
        self.assertEqual(self.start()[0]["類型"], "攝影棚")

    def test_an_earlier_stretch_of_the_same_episode_wins(self):
        self.write(self.store + "/2024-12/%s.csv" % self.NAME, "攝影棚")
        self.write(self.out + "/0-segments.csv", "帶外專題")
        self.assertEqual(self.start()[0]["類型"], "帶外專題")

    def test_no_table_anywhere_means_classify_afresh(self):
        self.assertIsNone(self.start())


if __name__ == "__main__":
    unittest.main()
