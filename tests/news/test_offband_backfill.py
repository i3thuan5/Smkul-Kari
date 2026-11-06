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


class TestSheetMask(unittest.TestCase):
    """組合圖裁切用ê遮罩愛是重切彼个 preset ê，毋通是預設白字判準。

    2024-06-03 155 晚間部落達人段用 titv-news-flower 重切：組合圖照
    「白字墨水」所在ê欄裁圖條，prepare 交 `mask: {}`，裁切用預設遮罩，
    彩色花字算做背景，434「一定非常愛這個人」、621「肉質也美味」規句
    予人裁掉、542「就像挑老公一樣 挑好的」干焦賰「就像挑老公」
    （2026-10-16 讀者逐條對原生圖條才發現）。
    """

    def test_flower_preset_mask_keeps_outline_saturation(self):
        mask = offband_backfill.sheet_mask("titv-news-flower")
        self.assertEqual(mask.get("outline_saturation"), 90)

    def test_offband_preset_mask_is_its_own(self):
        mask = offband_backfill.sheet_mask("titv-news-offband")
        self.assertIsNone(mask.get("outline_saturation"))
        self.assertTrue(mask.get("outline"))


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


class TestPlanKind(unittest.TestCase):
    """補切ê段落類型記佇 plan，apply 照 plan 標區域。

    2024 試做五集（032 晚、034 晨、196 晨、028 午、210 晨）ê島語時間、
    部落信箱從來無補切，work dir 已經清掉，干焦會當用這支直接改
    Kari-SRT；原本 KIND 寫死「帶外專題」，補落去會變做帶外專題，段落表
    佮時間軸 areas 攏標毋著。
    """

    def test_a_plan_from_before_kinds_existed_is_still_offband(self):
        self.assertEqual(offband_backfill.plan_kind({"lo": 1, "hi": 2}),
                         "帶外專題")

    def test_an_island_plan_lands_as_island(self):
        self.assertEqual(offband_backfill.plan_kind({"kind": "島語時間"}),
                         "島語時間")

    def test_a_kind_outside_the_segment_types_is_refused(self):
        with self.assertRaises(PipelineError):
            offband_backfill.plan_kind({"kind": "島語"})


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

    def test_an_earlier_stretch_wins_when_the_store_has_no_table(self):
        # 2021 那幾集原本沒有段落表；060 晚間分三段補切，第二段起要接在
        # 前一段的表上，不然前一段的「帶外專題」會被洗掉
        self.write(self.out + "/0-segments.csv", "帶外專題")
        self.assertEqual(self.start()[0]["類型"], "帶外專題")

    def test_the_stretch_table_is_used_when_it_matches_the_store(self):
        # 前一段 apply 過，兩份內容一樣；用補切目錄那份才留得住「依據」
        self.write(self.store + "/2024-12/%s.csv" % self.NAME, "攝影棚")
        self.write(self.out + "/0-segments.csv", "攝影棚")
        notes = []
        rows = offband_backfill.starting_table(
            self.NAME, self.out, store=self.store, notes=notes)
        self.assertEqual(rows[0]["依據"], "Claude Vision 確認")
        self.assertEqual(notes, [])

    def test_a_stale_stretch_table_loses_to_the_store_and_says_so(self):
        # 060 午：補切目錄留著舊的表，Kari-SRT 那份之後訂正過，
        # 2474.5–2579 的三列被合成一列攝影棚蓋回去，而且沒有任何警告
        self.write(self.store + "/2024-12/%s.csv" % self.NAME, "攝影棚")
        self.write(self.out + "/0-segments.csv", "帶外專題")
        notes = []
        rows = offband_backfill.starting_table(
            self.NAME, self.out, store=self.store, notes=notes)
        self.assertEqual(rows[0]["類型"], "攝影棚")
        self.assertEqual(len(notes), 1)
        self.assertIn("Kari-SRT", notes[0])

    def test_a_store_table_without_basis_still_passes_the_check(self):
        # Kari-SRT 的段落表不存「依據」欄（write_store 拿掉）。2026-10-20
        # 補切 2023-02 058 晚、059 午時，從 store 讀進來的列依據全是空字串，
        # apply 時 segments.check 擋下「第 2 逝：依據 ''」，段落表沒有入庫。
        path = self.store + "/2024-12/%s.csv" % self.NAME
        os.makedirs(os.path.dirname(path), exist_ok=True)
        segments.write_store(path, [
            {"起秒": "0", "迄秒": "100", "類型": "攝影棚", "單元語別": "阿美",
             "字幕上緣y": "840", "字幕下緣y": "930", "依據": "自動",
             segments.INTERVIEWEE: "無", segments.SPEECH: "無"}])
        rows = self.start()
        self.assertTrue(rows[0]["依據"])
        self.assertEqual(segments.check(rows, self.NAME, 100.0), [])

    def test_no_table_anywhere_means_classify_afresh(self):
        self.assertIsNone(self.start())

    def unapplied_plan(self, start_table=None):
        """上一次 prepare 寫的 plan，時間軸還是它那時候那份（沒有 apply）。"""
        import json
        timeline = self.root + "/cues.json"
        with open(timeline, "w", encoding="utf-8") as handle:
            handle.write('{"cues": []}')
        plan = {"store_sha": offband_backfill._sha(timeline)}
        if start_table is not None:
            plan["start_table"] = start_table
        os.makedirs(self.out, exist_ok=True)
        with open(self.out + "/plan.json", "w", encoding="utf-8") as handle:
            json.dump(plan, handle, ensure_ascii=False, indent=2,
                      sort_keys=True)
        return timeline

    def test_redoing_an_unapplied_prepare_starts_from_its_start(self):
        # 187 晚：同一集換一個 lo 重新 prepare，第一次蓋上去的列殘留在表裡
        before = [{"起秒": "0", "迄秒": "100", "類型": "攝影棚",
                   "單元語別": "阿美", "字幕上緣y": "840", "字幕下緣y": "930",
                   "依據": "人工", segments.INTERVIEWEE: "",
                   segments.SPEECH: ""}]
        timeline = self.unapplied_plan(before)
        self.write(self.out + "/0-segments.csv", "帶外專題")
        rows = offband_backfill.starting_table(
            self.NAME, self.out, store=self.store, timeline=timeline)
        self.assertEqual(rows[0]["類型"], "攝影棚")

    def test_redoing_an_unapplied_prepare_that_classified_afresh(self):
        # 上一次是重算的（沒有表可接），plan 記 start_table: null；重做時也
        # 要重算，不可以接上一次蓋過的補切目錄那份
        timeline = self.unapplied_plan(start_table=None)
        with open(self.out + "/plan.json", encoding="utf-8") as handle:
            text = handle.read()
        with open(self.out + "/plan.json", "w", encoding="utf-8") as handle:
            handle.write(text.replace("{", '{"start_table": null,', 1))
        self.write(self.out + "/0-segments.csv", "帶外專題")
        self.assertIsNone(offband_backfill.starting_table(
            self.NAME, self.out, store=self.store, timeline=timeline))

    def test_an_unapplied_plan_from_before_start_tables_uses_the_store(self):
        # 128 晚卑南：補切目錄留著一份沒 apply 的 plan（舊格式），那份表
        # 有它蓋上去的帶外專題列；Kari-SRT 的表才是它開始時的樣子
        timeline = self.unapplied_plan()
        self.write(self.store + "/2024-12/%s.csv" % self.NAME, "攝影棚")
        self.write(self.out + "/0-segments.csv", "帶外專題")
        notes = []
        rows = offband_backfill.starting_table(
            self.NAME, self.out, store=self.store, timeline=timeline,
            notes=notes)
        self.assertEqual(rows[0]["類型"], "攝影棚")
        self.assertEqual(notes, [])            # 照 Kari-SRT 的，沒有要警告的

    def test_an_unapplied_plan_from_before_start_tables_warns(self):
        timeline = self.unapplied_plan()
        self.write(self.out + "/0-segments.csv", "帶外專題")
        notes = []
        rows = offband_backfill.starting_table(
            self.NAME, self.out, store=self.store, timeline=timeline,
            notes=notes)
        self.assertEqual(rows[0]["類型"], "帶外專題")
        self.assertEqual(len(notes), 1)


class TestStretchEdges(unittest.TestCase):
    """187 晚：prepare 精修出來的末條 cue 迄點 1572.204 超過 hi 1572.121，
    壓到範圍外的下一條；apply 也沒擋重疊，事後用 place_cue bounds 手動修。"""

    def test_new_cues_are_clipped_to_the_stretch(self):
        new = [cue(1, 1499.9, 1503.0, "帶外專題"),
               cue(2, 1570.0, 1572.204, "帶外專題")]
        got = offband_backfill.clip(new, 1500.0, 1572.121)
        self.assertEqual((got[0]["start"], got[0]["end"]), (1500.0, 1503.0))
        self.assertEqual((got[1]["start"], got[1]["end"]),
                         (1570.0, 1572.121))
        self.assertEqual(new[1]["end"], 1572.204)       # 傳進來的不動

    def test_a_cue_left_with_nothing_inside_is_dropped(self):
        new = [cue(1, 1572.121, 1572.3, "帶外專題"),
               cue(2, 1560.0, 1561.0, "帶外專題")]
        got = offband_backfill.clip(new, 1500.0, 1572.121)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["start"], 1560.0)

    def test_a_new_cue_running_into_a_kept_one_is_reported(self):
        old = [cue(1, 1560.0, 1572.5), cue(2, 1572.5, 1575.0)]
        new = [cue(1, 1571.0, 1573.0, "帶外專題")]
        spliced = offband_backfill.splice(old, 1550.0, 1572.121, new)
        fresh = offband_backfill.fresh_numbers(spliced, old)
        found = offband_backfill.fresh_overlaps(spliced, fresh)
        self.assertEqual(len(found), 1)
        self.assertIn("1573.000", found[0])

    def test_old_overlaps_outside_the_stretch_do_not_block(self):
        # 全庫既有的重疊（323 午 1198／1199、361 晚 1014／1015）不在補切範圍，
        # 不能因為它們擋住補切
        old = [cue(1, 10.0, 13.0), cue(2, 12.0, 14.0), cue(3, 30.0, 40.0)]
        new = [cue(1, 31.0, 33.0, "帶外專題"), cue(2, 34.0, 36.0, "帶外專題")]
        spliced = offband_backfill.splice(old, 30.0, 40.0, new)
        fresh = offband_backfill.fresh_numbers(spliced, old)
        self.assertEqual(offband_backfill.fresh_overlaps(spliced, fresh), [])


if __name__ == "__main__":
    unittest.main()


ROW_FIELDS = ("起秒", "迄秒", "類型", "單元語別", "字幕上緣y", "字幕下緣y")


def row(start, end, kind, language="布農", top="722", bottom="848",
        who="無", speech="無", basis="人工"):
    return {"起秒": start, "迄秒": end, "類型": kind, "單元語別": language,
            "字幕上緣y": top, "字幕下緣y": bottom, "依據": basis,
            segments.INTERVIEWEE: who, segments.SPEECH: speech}


class TestSameTable(unittest.TestCase):
    """兩份段落表是不是同一份，比的是值不是字串。

    舊做法拿 `store_text` 比原始字串：補切目錄寫 100.500、Kari-SRT 寫
    100.5，數字寫法不同就當成兩份表，印假警告，還改用 Kari-SRT 那份，
    「依據」欄於是全部變成「人工」。
    """

    def test_number_spelling_does_not_make_two_tables(self):
        mine = [row("0", "100.500", "攝影棚", basis="Claude Vision 確認")]
        theirs = [row("0", "100.5", "攝影棚", basis="")]
        self.assertTrue(offband_backfill.same_table(mine, theirs))

    def test_a_different_value_is_a_different_table(self):
        self.assertFalse(offband_backfill.same_table(
            [row("0", "100", "攝影棚")], [row("0", "100", "外景新聞")]))
        self.assertFalse(offband_backfill.same_table(
            [row("0", "100", "攝影棚")], [row("0", "100.001", "攝影棚")]))
        self.assertFalse(offband_backfill.same_table(
            [row("0", "100", "攝影棚")],
            [row("0", "50", "攝影棚"), row("50", "100", "攝影棚")]))

    def test_the_stretch_table_keeps_its_basis_over_spelling(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        name = "20241209_344_晚間_Amis_阿美"
        stored = os.path.join(tmp.name, "store", "2024-12", name + ".csv")
        os.makedirs(os.path.dirname(stored))
        segments.write_store(stored, [row("0", "100.5", "攝影棚")])
        out = os.path.join(tmp.name, "out")
        os.makedirs(out)
        segments.write(os.path.join(out, "0-segments.csv"),
                       [row("0", "100.500", "攝影棚",
                            basis="Claude Vision 確認")])
        notes = []
        rows = offband_backfill.starting_table(
            name, out, store=os.path.join(tmp.name, "store"), notes=notes)
        self.assertEqual(notes, [])
        self.assertEqual(rows[0]["依據"], "Claude Vision 確認")


class TestOverrideKeepsConfirmedFields(unittest.TestCase):
    """299 晚 1216–2567 帶外專題在 Kari-SRT 已經確認成「鄒 890–970、受訪者
    無、無」，prepare 卻照第一列的語別和重切的區域寫成「布農 690–1040」、
    受訪者空白；apply 下去就把確認過的值蓋掉（303 晚、304 午、352 晚、
    057 晚同樣，6 份沒 apply 的 plan 裡 5 份是這種）。"""

    def test_an_existing_row_of_the_same_kind_keeps_its_values(self):
        rows = [row("0", "1216", "攝影棚"),
                row("1216", "2567", "帶外專題", "鄒", "890", "970"),
                row("2567", "2600", "其他")]
        got = offband_backfill.override(rows, 1216, 2567, "帶外專題",
                                        band=(690, 1040))
        middle = got[1]
        self.assertEqual(
            (middle["類型"], middle["單元語別"], middle["字幕上緣y"],
             middle["字幕下緣y"], middle[segments.INTERVIEWEE],
             middle[segments.SPEECH]),
            ("帶外專題", "鄒", "890", "970", "無", "無"))

    def test_a_row_of_another_kind_does_not_lend_its_values(self):
        rows = [row("0", "100", "攝影棚"),
                row("100", "300", "外景新聞", "卑南", who="pyu",
                    speech="族語或華語")]
        got = offband_backfill.override(rows, 150, 250, "帶外專題",
                                        band=(910, 1032))
        self.assertEqual((got[2]["字幕上緣y"], got[2][segments.INTERVIEWEE]),
                         ("910", ""))


class TestRedoAfterTheStoreChanged(unittest.TestCase):
    """新格式 plan 還沒 apply、重新 prepare：舊做法直接用 plan 記的開始表，
    不看 Kari-SRT 現在的表。plan 記的是攝影棚、之後 Kari-SRT 訂正成外景
    新聞，重做拿到的還是攝影棚，也沒有任何警告。"""

    NAME = "20241209_344_晚間_Amis_阿美"

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = tmp.name
        self.out = os.path.join(self.root, "out")
        self.store = os.path.join(self.root, "store")
        os.makedirs(self.out)
        self.timeline = os.path.join(self.root, "cues.json")
        with open(self.timeline, "w", encoding="utf-8") as handle:
            handle.write('{"cues": []}')

    def plan(self, start_table):
        import json
        plan = {"store_sha": offband_backfill._sha(self.timeline),
                "start_table": start_table, "lo": 10, "hi": 20}
        with open(os.path.join(self.out, "plan.json"), "w",
                  encoding="utf-8") as handle:
            json.dump(plan, handle, ensure_ascii=False, indent=2,
                      sort_keys=True)

    def store_table(self, kind):
        path = os.path.join(self.store, "2024-12", self.NAME + ".csv")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        segments.write_store(path, [row("0", "100", kind)])

    def start(self, notes):
        return offband_backfill.starting_table(
            self.NAME, self.out, store=self.store, timeline=self.timeline,
            notes=notes)

    def test_a_store_corrected_since_the_plan_wins_and_says_so(self):
        self.plan([row("0", "100", "攝影棚")])
        self.store_table("外景新聞")
        notes = []
        self.assertEqual(self.start(notes)[0]["類型"], "外景新聞")
        self.assertEqual(len(notes), 1)
        self.assertIn("Kari-SRT", notes[0])

    def test_a_plan_that_classified_afresh_yields_to_a_store_table(self):
        self.plan(None)
        self.store_table("外景新聞")
        notes = []
        self.assertEqual(self.start(notes)[0]["類型"], "外景新聞")
        self.assertEqual(len(notes), 1)

    def test_an_unchanged_store_keeps_the_plans_basis(self):
        self.plan([row("0", "100", "攝影棚", basis="Claude Vision 確認")])
        self.store_table("攝影棚")
        notes = []
        self.assertEqual(self.start(notes)[0]["依據"], "Claude Vision 確認")
        self.assertEqual(notes, [])


class TestWiring(unittest.TestCase):
    """prepare、apply 真的有接上裁切、重疊檢查、段落表比對。

    審查時把 prepare 的 clip、check_overlaps，apply 的 check_overlaps，
    plan 的 start_table 全部拿掉，純函式的測試照樣全過；6 份還沒 apply 的
    plan（128 晚、299 晚、303 晚、304 午、352 晚、057 晚）補切目錄的表全
    跟 Kari-SRT 不同，apply 只要讀者 TSV、不要影片，隨時可能有人跑，跑下去
    128 晚 2421–2649 兩列外景新聞會被蓋回帶外專題、沒有警告。這組用合成
    的 Kari-SRT 跑整條 prepare／apply（重切、精修、組合圖換成假的）。
    """

    NAME = "20231026_299_晚間_Bunun_布農"
    LO, HI = 100.0, 140.0

    def setUp(self):
        import json
        from unittest import mock
        self.json = json
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = tmp.name
        self.root = root
        for attr, sub in (("KARI_CUES", "cues"), ("KARI_VISION", "vision"),
                          ("SRT_DIR", "srt"), ("SEGMENTS_STORE", "segs"),
                          ("NEWS_OUT", "out")):
            patch = mock.patch.object(offband_backfill.paths, attr,
                                      os.path.join(root, sub))
            patch.start()
            self.addCleanup(patch.stop)
        paths = offband_backfill.paths
        self.timeline = paths.stage_path(paths.KARI_CUES, self.NAME, ".json")
        self.table = paths.stage_path(paths.SEGMENTS_STORE, self.NAME, ".csv")
        self.vision = paths.stage_path(paths.KARI_VISION, self.NAME)
        self.srt = paths.stage_path(paths.SRT_DIR, self.NAME, ".srt")
        for path in (self.timeline, self.table, self.srt):
            os.makedirs(os.path.dirname(path), exist_ok=True)
        os.makedirs(self.vision)
        # 舊時間軸：1 0–20、2 20–60、3 100–120（範圍內，要被換掉）、
        # 4 141–160、5 160–200
        self.old = [cue(1, 0.0, 20.0), cue(2, 20.0, 60.0),
                    cue(3, 100.0, 120.0), cue(4, 141.0, 160.0),
                    cue(5, 160.0, 200.0)]
        self.write_json(self.timeline, {"cues": self.old,
                                        "duration": 200.0})
        segments.write_store(self.table, [
            row("0", "100", "攝影棚"), row("100", "140", "外景新聞"),
            row("140", "200", "攝影棚")])
        with open(os.path.join(self.vision, "b01.tsv"), "w",
                  encoding="utf-8") as handle:
            handle.write("1\than\t甲\n2\than\t乙\n3\than\t\n"
                         "4\than\t丁\n5\than\t戊\n")
        self.refined = []
        self.recut_presets = []
        self.manifests = []
        patches = [
            mock.patch.object(offband_backfill, "_entry",
                              lambda name: {"srt_name": name,
                                            "族語別(中)": "布農"}),
            mock.patch("scripts.news.segment_recut._recut", self.fake_recut),
            mock.patch("scripts.news.segment_recut._refine", self.fake_refine),
            mock.patch("scripts.ocr.sheets.build_sheets", self.fake_sheets),
            mock.patch("scripts.news.pairs_run.in_scope", lambda name: False),
            mock.patch("scripts.news.rebuild.rebuild_one", self.fake_rebuild),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def write_json(self, path, doc):
        with open(path, "w", encoding="utf-8") as handle:
            self.json.dump(doc, handle, ensure_ascii=False, indent=2,
                           sort_keys=True)

    def fake_recut(self, video, lo, span, out, preset, **kwargs):
        # 沒有量字幕列時不可以傳 presets：照舊用 presets.json
        self.recut_presets.append(kwargs.get("presets"))
        return "coarse"

    def fake_refine(self, video, coarse, preset, **kwargs):
        region = [0, 930, 1920, 110]
        if kwargs.get("presets"):
            # 真的精修把粗切時用的 region 原樣帶出來
            with open(kwargs["presets"], encoding="utf-8") as handle:
                region = self.json.load(handle)[preset]["region"]
        path = os.path.join(self.root, "refined.json")
        self.write_json(path, {"refined": True, "lines": [],
                               "region": region, "cues": self.refined})
        return path

    def fake_sheets(self, out, manifest):
        self.manifests.append(manifest)
        return 1

    def fake_rebuild(self, entry, tmp):
        with open(os.path.join(tmp, "srt", entry["srt_name"] + ".srt"),
                  "w", encoding="utf-8") as handle:
            handle.write("1\n")

    def snapshot(self):
        out = {}
        for path in (self.timeline, self.table, self.srt,
                     os.path.join(self.vision, "b01.tsv")):
            if os.path.exists(path):
                with open(path, encoding="utf-8") as handle:
                    out[path] = handle.read()
        out["tsv"] = sorted(os.listdir(self.vision))
        return out

    def plan_path(self):
        return os.path.join(offband_backfill.out_dir(self.NAME), "plan.json")

    def reader(self, plan):
        path = os.path.join(self.root, "reader.tsv")
        with open(path, "w", encoding="utf-8") as handle:
            for number in plan["fresh"]:
                handle.write("%d\than\t新%d\n" % (number, number))
        return path

    def test_prepare_clips_the_last_cue_to_the_stretch(self):
        # 187 晚：精修把末條迄點推到 1572.204，超過迄秒
        self.refined = [cue(1, 102.0, 110.0), cue(2, 120.0, 140.3)]
        plan = offband_backfill.prepare(self.NAME, self.LO, self.HI, "v")
        last = plan["spliced"][plan["fresh"][-1] - 1]
        self.assertEqual(last["end"], self.HI)

    def test_prepare_refuses_a_new_cue_over_a_kept_one(self):
        # 範圍外的 cue 4 從 141 起，新 cue 若在範圍內卻壓到它要擋；用一條
        # 跨過 lo 的舊 cue 做：舊 cue 2 改成 20–101
        self.old[1] = cue(2, 20.0, 101.0)
        self.write_json(self.timeline, {"cues": self.old,
                                        "duration": 200.0})
        self.refined = [cue(1, 100.0, 110.0)]
        with self.assertRaises(PipelineError):
            offband_backfill.prepare(self.NAME, self.LO, self.HI, "v")
        self.assertFalse(os.path.exists(self.plan_path()))

    def test_prepare_records_the_start_table_and_the_store_table_sha(self):
        self.refined = [cue(1, 102.0, 110.0)]
        plan = offband_backfill.prepare(self.NAME, self.LO, self.HI, "v")
        self.assertEqual(len(plan["start_table"]), 3)
        self.assertEqual(plan["store_segments_sha"],
                         offband_backfill._sha(self.table))

    def test_apply_refuses_overlaps_before_writing_anything(self):
        self.refined = [cue(1, 102.0, 110.0)]
        plan = offband_backfill.prepare(self.NAME, self.LO, self.HI, "v")
        fresh = plan["fresh"][0]
        plan["spliced"][fresh - 1]["end"] = 142.0       # 壓到 cue 4（141 起）
        self.write_json(self.plan_path(), plan)
        before = self.snapshot()
        with self.assertRaises(PipelineError):
            offband_backfill.apply(self.NAME, self.reader(plan))
        self.assertEqual(self.snapshot(), before)

    def test_apply_refuses_a_store_table_changed_since_prepare(self):
        self.refined = [cue(1, 102.0, 110.0)]
        plan = offband_backfill.prepare(self.NAME, self.LO, self.HI, "v")
        segments.write_store(self.table, [
            row("0", "100", "攝影棚"), row("100", "140", "外景新聞"),
            row("140", "200", "外景新聞")])       # prepare 之後有人訂正
        before = self.snapshot()
        with self.assertRaises(PipelineError) as caught:
            offband_backfill.apply(self.NAME, self.reader(plan))
        self.assertIn("段落表", str(caught.exception))
        self.assertEqual(self.snapshot(), before)

    def old_format_plan(self):
        """128 晚那種：plan 沒記 Kari-SRT 段落表的 sha，補切目錄的表跟
        Kari-SRT 現在的不一樣（Kari-SRT 之後把那段訂正成外景新聞）。"""
        self.refined = [cue(1, 102.0, 110.0)]
        plan = offband_backfill.prepare(self.NAME, self.LO, self.HI, "v")
        del plan["store_segments_sha"]
        del plan["start_table"]
        self.write_json(self.plan_path(), plan)
        return plan

    def test_apply_refuses_an_old_plan_whose_table_differs(self):
        plan = self.old_format_plan()
        before = self.snapshot()
        with self.assertRaises(PipelineError) as caught:
            offband_backfill.apply(self.NAME, self.reader(plan))
        self.assertIn("--keep-store-table", str(caught.exception))
        self.assertEqual(self.snapshot(), before)

    def test_keep_store_table_applies_and_leaves_the_table(self):
        plan = self.old_format_plan()
        with open(self.table, encoding="utf-8") as handle:
            table = handle.read()
        offband_backfill.apply(self.NAME, self.reader(plan),
                               keep_store_table=True)
        with open(self.table, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), table)
        with open(self.timeline, encoding="utf-8") as handle:
            book = self.json.load(handle)
        self.assertEqual(len(book["cues"]), len(plan["spliced"]))

    def test_a_fresh_plan_applies_and_installs_its_table(self):
        self.refined = [cue(1, 102.0, 110.0)]
        plan = offband_backfill.prepare(self.NAME, self.LO, self.HI, "v")
        offband_backfill.apply(self.NAME, self.reader(plan))
        kinds = []
        for one in segments.read(self.table):
            kinds.append(one["類型"])
        self.assertEqual(kinds, ["攝影棚", "帶外專題", "攝影棚"])

    def test_a_gap_in_tsv_numbers_does_not_overwrite_the_last_tsv(self):
        # 034 晨（2026-11-04）：2-vision 有 b01、b02、b04、b05（b03 早就併掉），
        # 新 TSV 照「份數 + 1」取名成 b05.tsv，把原本 523 列的 b05 整份蓋掉
        os.rename(os.path.join(self.vision, "b01.tsv"),
                  os.path.join(self.vision, "b03.tsv"))
        with open(os.path.join(self.vision, "b01.tsv"), "w",
                  encoding="utf-8") as handle:
            handle.write("")
        self.refined = [cue(1, 102.0, 110.0)]
        plan = offband_backfill.prepare(self.NAME, self.LO, self.HI, "v")
        offband_backfill.apply(self.NAME, self.reader(plan))
        self.assertEqual(sorted(os.listdir(self.vision)),
                         ["b01.tsv", "b03.tsv", "b04.tsv"])
        with open(os.path.join(self.vision, "b03.tsv"),
                  encoding="utf-8") as handle:
            self.assertIn("\t甲\n", handle.read())


class TestProbeSunkenRows(TestWiring):
    """`prepare --probe`：2021 文化小辭典已讀字的集，重切前先量字幕列。

    文化小辭典子母畫面的字幕高低逐集不同（2021-11 量到 770–838 到
    815–870；2021-01～02 量到 779–829 到 829–879），照 preset 固定的比對列
    810–880 切，20211124 晚一條 cue 長 31.2 秒、兩句整句不見。`segment_recut`
    有量列那一步，但它拒絕已讀字的集；`offband_backfill` 只吃 preset。
    繼承 `TestWiring` 的合成 Kari-SRT，連帶確認加了 probe 之後原本那組照過。
    """

    PRESET = "titv-news-dict-2021"

    def frames(self, top, bottom, count=9, seed=1):
        import numpy as np
        rng = np.random.default_rng(seed)
        out = []
        for index in range(count):
            frame = rng.integers(0, 150, size=(160, 300, 3), dtype=np.uint8)
            spot = rng.integers(0, 130)
            frame[spot:spot + 25, :] = 235
            left = 20 + 7 * index
            frame[top:bottom, left:left + 200:3] = 250
            out.append(frame)
        return out

    def noise(self, video, lo, hi):
        import numpy as np
        rng = np.random.default_rng(3)
        out = []
        for _index in range(9):
            out.append(rng.integers(0, 150, size=(160, 300, 3),
                                    dtype=np.uint8))
        return out

    def test_the_cut_follows_the_measured_rows(self):
        from scripts.news import segment_recut
        self.refined = [cue(1, 102.0, 110.0)]
        plan = offband_backfill.prepare(
            self.NAME, self.LO, self.HI, "v", preset=self.PRESET,
            kind="文化小辭典", probe=lambda video, lo, hi: self.frames(75, 130))
        fitted = self.recut_presets[0]
        self.assertTrue(fitted)
        with open(fitted, encoding="utf-8") as handle:
            layout = self.json.load(handle)[self.PRESET]
        region = layout["region"]
        rows = layout["mask"]["compare_rows"]
        top = segment_recut.PROBE_TOP + 75
        bottom = segment_recut.PROBE_TOP + 130
        self.assertLessEqual(abs(region[1] - (top - 10)), 3)
        self.assertLessEqual(abs(region[1] + region[3] - (bottom + 10)), 3)
        self.assertLessEqual(abs(region[1] + rows[0] - top), 3)
        self.assertLessEqual(abs(region[1] + rows[1] - bottom), 3)
        # 補切目錄裡，不是 Kari-SRT 或 repo
        self.assertTrue(fitted.startswith(
            offband_backfill.out_dir(self.NAME)))
        self.assertEqual(plan["region"], region)
        # 組合圖照同一份遮罩裁圖條
        self.assertEqual(self.manifests[0]["mask"]["compare_rows"], rows)

    def test_without_probe_nothing_changes(self):
        # 帶外專題、島語時間、花字那幾類照舊：不傳 presets、plan 沒有新欄
        self.refined = [cue(1, 102.0, 110.0)]
        plan = offband_backfill.prepare(self.NAME, self.LO, self.HI, "v")
        self.assertEqual(self.recut_presets, [None])
        self.assertEqual(sorted(plan), sorted([
            "srt_name", "lo", "hi", "store_sha", "spliced", "fresh",
            "old_total", "region", "preset", "kind", "start_table",
            "store_segments_sha"]))
        self.assertEqual(self.manifests[0]["mask"],
                         offband_backfill.sheet_mask(offband_backfill.PRESET))

    def test_rows_that_cannot_be_measured_fall_back_with_a_warning(self):
        import contextlib
        import io
        self.refined = [cue(1, 102.0, 110.0)]
        said = io.StringIO()
        with contextlib.redirect_stdout(said):
            plan = offband_backfill.prepare(
                self.NAME, self.LO, self.HI, "v", preset=self.PRESET,
                kind="文化小辭典", probe=self.noise)
        self.assertEqual(self.recut_presets, [None])
        self.assertIn("量不到", said.getvalue())
        self.assertEqual(plan["preset"], self.PRESET)

    def test_probe_with_a_preset_that_does_not_sink_is_refused(self):
        with self.assertRaises(PipelineError):
            offband_backfill.prepare(
                self.NAME, self.LO, self.HI, "v",
                preset="titv-news-offband", kind="帶外專題",
                probe=lambda video, lo, hi: self.frames(75, 130))
        self.assertEqual(self.recut_presets, [])
        self.assertFalse(os.path.exists(self.plan_path()))

    def test_the_command_line_flag_reaches_prepare(self):
        from unittest import mock
        seen = {}

        def fake(name, lo, hi, video, preset, kind, probe=None):
            seen["probe"] = probe
        with mock.patch.object(offband_backfill, "prepare", fake):
            offband_backfill.main(["prepare", self.NAME, "100", "140", "v",
                                   "--preset", self.PRESET, "--kind",
                                   "文化小辭典", "--probe"])
        from scripts.news import segment_recut
        self.assertIs(seen["probe"], segment_recut._probe)
