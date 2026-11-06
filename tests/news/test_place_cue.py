"""place_cue：照量好ê秒數插一條 cue，抑是調一條 cue ê起迄。

2026-10-21 20211203_337_晚間 1178–1180 秒「山」「海」兩條單字字幕：空拍
浪花逐格墨量 314–504，比單一字（約 150）較大，切段器切袂開，重切嘛仝款；
「山」規條無 cue，「海」ê cue 416 起點晚 0.58 秒、尾仔閣佮 417 相連。
split_cue 干焦會剖一條有ê cue，所以愛另外一支：量好ê秒數直接插入、調界。
"""
import json
import os
import tempfile
import unittest
from unittest import mock

from scripts.errors import PipelineError
from scripts.news import paths
from scripts.news import place_cue
from scripts.news import split_cue


def cue(index, start, end, area=None, placed=False):
    item = {"index": index, "start": start, "end": end, "frames": 3,
            "ink": 900, "sample_ts": start,
            "images": {"han": "2-strips/%05d_han.png" % index}}
    if area:
        item["area"] = area
    if placed:
        item["placed"] = True
        item["images"] = {}
    return item


def island():
    # 286 晚島語時間：845 2045.027–2046.227、（空檔）、847 起 2047.812
    return [cue(1, 2040.0, 2045.027),
            cue(2, 2045.027, 2046.227, "島語時間"),
            cue(3, 2047.812, 2048.130, "島語時間"),
            cue(4, 2050.0, 2052.0)]


def run():
    # 1:0–1  2:1–2  （空檔 2–4）  3:4–5  4:5–6
    return [cue(1, 0.0, 1.0), cue(2, 1.0, 2.0), cue(3, 4.0, 5.0),
            cue(4, 5.0, 6.0)]


class TestInsert(unittest.TestCase):
    def test_lands_in_the_gap_and_takes_the_next_number(self):
        got, index = place_cue.insert(run(), 2.5, 3.5)
        self.assertEqual(index, 3)
        self.assertEqual((got[2]["start"], got[2]["end"]), (2.5, 3.5))

    def test_later_cues_are_renumbered_but_keep_their_strip(self):
        # strip 檔名毋綴新編號走（split_cue 仝款ê理由）
        got, _ = place_cue.insert(run(), 2.5, 3.5)
        self.assertEqual([c["index"] for c in got], [1, 2, 3, 4, 5])
        self.assertEqual(got[3]["images"]["han"], "2-strips/00003_han.png")
        self.assertEqual((got[3]["start"], got[3]["end"]), (4.0, 5.0))

    def test_new_cue_has_no_strip_and_samples_inside_itself(self):
        got, _ = place_cue.insert(run(), 2.5, 3.5)
        self.assertEqual(got[2]["images"], {})
        self.assertTrue(2.5 <= got[2]["sample_ts"] <= 3.5)
        self.assertTrue(got[2]["placed"])

    def test_a_gap_exactly_filled_is_allowed(self):
        got, index = place_cue.insert(run(), 2.0, 4.0)
        self.assertEqual(index, 3)

    def test_overlapping_an_existing_cue_is_an_error(self):
        # 量著ê秒數若硩著別條，先用 bounds 縮彼條，毋通默默疊做伙
        with self.assertRaises(PipelineError):
            place_cue.insert(run(), 1.5, 3.0)
        with self.assertRaises(PipelineError):
            place_cue.insert(run(), 3.0, 4.5)

    def test_before_the_first_cue_takes_number_one(self):
        cues = run()
        cues[0]["start"] = 0.5
        got, index = place_cue.insert(cues, 0.0, 0.5)
        self.assertEqual(index, 1)
        self.assertEqual(got[1]["index"], 2)

    def test_empty_or_reversed_span_is_an_error(self):
        with self.assertRaises(PipelineError):
            place_cue.insert(run(), 3.0, 3.0)
        with self.assertRaises(PipelineError):
            place_cue.insert(run(), 3.5, 2.5)


class TestInsertArea(unittest.TestCase):
    """插入的 cue 要跟著前後 cue 的 area。

    286 晚 cue 846（2046.227–2047.812 金句卡）是 place_cue insert 插的，
    前後都是「島語時間」，只有它沒有 area；移植工具照正本搬到 291 晚
    1036、301 晚 1399。全庫前後同一個 area、自己卻沒有的 placed cue 有
    1168 條（93 集）。靠 area 挑切法設定的程式（重播移植、驗收抽格）會把它當成頂層
    字幕帶。
    """

    def test_takes_the_area_both_neighbours_share(self):
        got, index = place_cue.insert(island(), 2046.227, 2047.812)
        self.assertEqual(index, 3)
        self.assertEqual(got[2]["area"], "島語時間")

    def test_no_area_where_the_neighbours_disagree(self):
        # 區域邊界：前一條是島語時間、後一條是頂層，判斷不出來就不寫
        got, index = place_cue.insert(island(), 2048.5, 2049.0)
        self.assertEqual(index, 4)
        self.assertNotIn("area", got[3])

    def test_no_area_at_the_ends_of_the_timeline(self):
        cues = island()
        cues[0]["area"] = "島語時間"
        got, _ = place_cue.insert(cues, 2030.0, 2031.0)
        self.assertNotIn("area", got[0])

    def test_an_earlier_placed_cue_without_area_is_looked_past(self):
        # 210 晨部落信箱 860、867、877 是先前插的空白 cue，都沒有 area；
        # 在它旁邊再插一條，要越過它看到前面那條「部落信箱」
        cues = [cue(1, 10.0, 12.0, "部落信箱"),
                cue(2, 12.0, 12.2, placed=True),
                cue(3, 13.0, 14.0, "部落信箱")]
        got, index = place_cue.insert(cues, 12.2, 12.9)
        self.assertEqual(index, 3)
        self.assertEqual(got[2]["area"], "部落信箱")

    def test_an_explicit_area_wins_and_empty_means_none(self):
        got, _ = place_cue.insert(island(), 2048.5, 2049.0, area="島語時間")
        self.assertEqual(got[3]["area"], "島語時間")
        got, _ = place_cue.insert(island(), 2046.227, 2047.812, area="")
        self.assertNotIn("area", got[2])


class TestDelete(unittest.TestCase):
    """刪一條 cue：259 晚排灣 903 只有 0.017 秒（2234.866–2234.883）、
    248 午噶瑪蘭 685／687／712 改成空白卻沒刪，都是殘留的空白 cue。"""

    def test_later_cues_move_up_and_keep_their_strip(self):
        got = place_cue.delete(run(), 2)
        numbers = []
        for one in got:
            numbers.append(one["index"])
        self.assertEqual(numbers, [1, 2, 3])
        self.assertEqual(got[1]["images"]["han"], "2-strips/00003_han.png")
        self.assertEqual((got[1]["start"], got[1]["end"]), (4.0, 5.0))

    def test_unknown_cue_is_an_error(self):
        with self.assertRaises(PipelineError):
            place_cue.delete(run(), 5)
        with self.assertRaises(PipelineError):
            place_cue.delete(run(), 0)

    def test_rows_drop_and_later_ones_shift_down(self):
        rows = [(1, "a"), (2, ""), (3, "c"), (4, "d")]
        self.assertEqual(place_cue.drop_rows(rows, 2),
                         [(1, "a"), (2, "c"), (3, "d")])

    def test_sheets_lose_the_cue_and_later_ones_shift_down(self):
        sheets = {"s1.png": [1, 2], "s2.png": [3, 4]}
        self.assertEqual(place_cue.drop_from_sheets(sheets, 2),
                         {"s1.png": [1], "s2.png": [2, 3]})

    def test_a_cue_with_text_needs_saying_so(self):
        # 有字的 cue 刪掉，那句就從 SRT 消失，不可以悄悄做
        with self.assertRaises(PipelineError):
            place_cue.check_droppable(["好像不太夠"], keep_text=False)
        place_cue.check_droppable([""], keep_text=False)
        place_cue.check_droppable([], keep_text=False)
        place_cue.check_droppable(["好像不太夠"], keep_text=True)


class TestMerge(unittest.TestCase):
    """併兩條相連的 cue：353 午噶瑪蘭 528（1298.997–1299.448）、529
    （1299.448–1300.483）都是「好像不太夠」，一句被切成兩條；361 晚
    1014／1015 重疊約 2 秒。"""

    def same_text(self):
        return [cue(1, 1297.146, 1298.997, "島語時間"),
                cue(2, 1298.997, 1299.448, "島語時間"),
                cue(3, 1299.448, 1300.483, "島語時間"),
                cue(4, 1300.483, 1302.401, "島語時間")]

    def test_one_cue_spans_both_and_keeps_the_first_strip(self):
        got = place_cue.merge(self.same_text(), 2)
        self.assertEqual(len(got), 3)
        self.assertEqual((got[1]["start"], got[1]["end"]),
                         (1298.997, 1300.483))
        self.assertEqual(got[1]["images"]["han"], "2-strips/00002_han.png")
        self.assertEqual(got[1]["area"], "島語時間")
        self.assertEqual(got[2]["index"], 3)
        self.assertEqual(got[2]["images"]["han"], "2-strips/00004_han.png")

    def test_overlapping_pair_ends_at_the_later_end(self):
        cues = [cue(1, 10.0, 14.0), cue(2, 12.0, 13.0), cue(3, 15.0, 16.0)]
        got = place_cue.merge(cues, 1)
        self.assertEqual((got[0]["start"], got[0]["end"]), (10.0, 14.0))

    def test_the_last_cue_has_nothing_to_merge_with(self):
        with self.assertRaises(PipelineError):
            place_cue.merge(run(), 4)

    def test_different_areas_are_not_merged(self):
        cues = [cue(1, 0.0, 1.0, "島語時間"), cue(2, 1.0, 2.0, "部落信箱")]
        with self.assertRaises(PipelineError):
            place_cue.merge(cues, 1)

    def test_an_area_only_one_side_has_is_kept(self):
        cues = [cue(1, 0.0, 1.0, placed=True), cue(2, 1.0, 2.0, "島語時間")]
        self.assertEqual(place_cue.merge(cues, 1)[0]["area"], "島語時間")

    def test_an_area_cue_and_a_top_band_cue_are_not_merged(self):
        # 沒有 placed、沒有 area 的是頂層字幕帶切的；跟島語時間那條併起來會
        # 整條標成島語時間，等於改了它的切法（fill_placed_area 不跟鄰居改
        # 頂層 cue 也是這個理由）
        cues = [cue(1, 0.0, 1.0, "島語時間"), cue(2, 1.0, 2.0),
                cue(3, 2.0, 3.0)]
        with self.assertRaises(PipelineError):
            place_cue.merge(cues, 1)
        two = place_cue.merge(cues, 2)            # 兩條都是頂層的照併
        self.assertNotIn("area", two[1])

    def test_text_same_or_one_blank_is_taken_otherwise_say_it(self):
        self.assertEqual(place_cue.merged_text("好像不太夠", "好像不太夠"),
                         "好像不太夠")
        self.assertEqual(place_cue.merged_text("", "沒有"), "沒有")
        self.assertEqual(place_cue.merged_text("哈哈", ""), "哈哈")
        with self.assertRaises(PipelineError):
            place_cue.merged_text("哈哈", "沒有")
        self.assertEqual(place_cue.merged_text("哈哈", "沒有", "哈哈 沒有"),
                         "哈哈 沒有")

    def test_rows_lose_the_second_and_carry_the_text_on_the_first(self):
        rows = [(1, "a"), (2, "好像不太夠"), (3, "好像不太夠"), (4, "d")]
        got = place_cue.merge_rows(rows, 2, "好像不太夠", here=True)
        self.assertEqual(got, [(1, "a"), (2, "好像不太夠"), (3, "d")])

    def test_rows_in_another_file_only_shift(self):
        # 第二條在別的 TSV：那一列要拿掉，不可以留下來變成第二個 528
        got = place_cue.merge_rows([(3, "好像不太夠"), (4, "d")], 2,
                                   "好像不太夠", here=False)
        self.assertEqual(got, [(3, "d")])


class TestApplyAcrossFiles(unittest.TestCase):
    """刪、併要同時改時間軸、sheets.json、各個 TSV。讀者分批是交錯的，
    相鄰兩條常常在不同的 TSV；只改其中一個檔，號碼就錯開一號，字落到
    別條字幕上，而且不會有地方報錯。"""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.work = os.path.join(tmp.name, "work")
        self.folder = os.path.join(tmp.name, "vision")
        os.makedirs(self.folder)
        os.makedirs(os.path.dirname(paths.sheets_index(self.work)))
        self.timeline = os.path.join(tmp.name, "cues.json")
        cues = [cue(1, 1297.146, 1298.997, "島語時間"),
                cue(2, 1298.997, 1299.448, "島語時間"),
                cue(3, 1299.448, 1300.483, "島語時間"),
                cue(4, 1300.483, 1302.401, "島語時間"),
                cue(5, 1302.401, 1303.0, "島語時間")]
        self.dump(self.timeline, {"cues": cues})
        self.dump(paths.sheets_index(self.work),
                  {"s1.png": [1, 2, 3], "s2.png": [4, 5]})
        split_cue.write_tsv(self.tsv("b01"), [(1, "沒想到他還回我說"),
                                              (2, "好像不太夠"), (5, "e")])
        split_cue.write_tsv(self.tsv("b02"), [(3, "好像不太夠"), (4, "")])
        for patch in (
                mock.patch.object(place_cue, "_name_of", lambda stem: "x"),
                mock.patch.object(place_cue.paths, "work_dir",
                                  lambda stem: self.work),
                mock.patch.object(place_cue.paths, "cues_to_read",
                                  lambda work: self.timeline),
                mock.patch.object(split_cue, "vision_folders",
                                  lambda name: [self.folder])):
            patch.start()
            self.addCleanup(patch.stop)

    def tsv(self, name):
        return os.path.join(self.folder, name + ".tsv")

    def dump(self, path, doc):
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(doc, handle, ensure_ascii=False, indent=2,
                      sort_keys=True)

    def load(self, path):
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)

    def test_merge_across_two_tsv_files(self):
        total, text = place_cue.apply_merge("stem", 2)
        self.assertEqual((total, text), (4, "好像不太夠"))
        self.assertEqual(split_cue.read_tsv(self.tsv("b01")),
                         [(1, "沒想到他還回我說"), (2, "好像不太夠"), (4, "e")])
        self.assertEqual(split_cue.read_tsv(self.tsv("b02")), [(3, "")])
        book = self.load(self.timeline)
        self.assertEqual((book["cues"][1]["start"], book["cues"][1]["end"]),
                         (1298.997, 1300.483))
        self.assertEqual(book["placed"][-1]["op"], "merge")
        self.assertEqual(self.load(paths.sheets_index(self.work)),
                         {"s1.png": [1, 2], "s2.png": [3, 4]})

    def test_delete_a_blank_cue_and_refuse_one_with_text(self):
        with self.assertRaises(PipelineError):
            place_cue.apply_delete("stem", 3)
        self.assertEqual(len(self.load(self.timeline)["cues"]), 5)
        self.assertEqual(place_cue.apply_delete("stem", 4), 4)
        self.assertEqual(split_cue.read_tsv(self.tsv("b01")),
                         [(1, "沒想到他還回我說"), (2, "好像不太夠"), (4, "e")])
        self.assertEqual(split_cue.read_tsv(self.tsv("b02")),
                         [(3, "好像不太夠")])
        self.assertEqual(self.load(paths.sheets_index(self.work)),
                         {"s1.png": [1, 2, 3], "s2.png": [4]})

    def test_insert_writes_the_area_into_the_timeline(self):
        # 只測 insert() 的話，apply_insert 沒把 area 傳下去、沒寫進 placed
        # 紀錄也照樣全過
        index, total, area = place_cue.apply_insert("stem", 1303.0, 1303.5,
                                                    "")
        self.assertEqual((index, total, area), (6, 6, None))
        place_cue.apply_bounds("stem", 6, 1303.0, 1303.4)
        index, total, area = place_cue.apply_insert(
            "stem", 1303.4, 1303.5, "x", area="島語時間")
        book = self.load(self.timeline)
        self.assertEqual(book["cues"][6]["area"], "島語時間")
        self.assertEqual(book["placed"][-1]["area"], "島語時間")

    def test_insert_between_one_area_follows_it_on_disk(self):
        place_cue.apply_bounds("stem", 3, 1299.448, 1300.0)
        index, _total, area = place_cue.apply_insert("stem", 1300.0, 1300.4,
                                                     "")
        self.assertEqual((index, area), (4, "島語時間"))
        self.assertEqual(self.load(self.timeline)["cues"][3]["area"],
                         "島語時間")

    def test_insert_refuses_an_area_the_episode_never_used(self):
        # 「島語」打成少一個字，寫進去之後誰都對不到 areas 的設定
        with self.assertRaises(PipelineError):
            place_cue.apply_insert("stem", 1303.0, 1304.0, "", area="島語")

    def test_area_changes_only_the_timeline_and_logs_it(self):
        before_tsv = split_cue.read_tsv(self.tsv("b01"))
        before_sheets = self.load(paths.sheets_index(self.work))
        self.assertTrue(place_cue.apply_area("stem", 3, ""))
        book = self.load(self.timeline)
        self.assertNotIn("area", book["cues"][2])
        self.assertEqual(book["placed"][-1],
                         {"op": "area", "cue": 3, "area": "",
                          "was": "島語時間"})
        self.assertEqual(split_cue.read_tsv(self.tsv("b01")), before_tsv)
        self.assertEqual(self.load(paths.sheets_index(self.work)),
                         before_sheets)

    def test_area_already_right_writes_nothing(self):
        # 重驗時已經是對的就不要再動：不寫檔、不多一筆紀錄
        self.assertFalse(place_cue.apply_area("stem", 2, "島語時間"))
        self.assertNotIn("placed", self.load(self.timeline))

    def test_area_refuses_a_name_the_episode_never_used(self):
        with self.assertRaises(PipelineError):
            place_cue.apply_area("stem", 2, "部落")


class TestRenumberHint(unittest.TestCase):
    """改完號碼要改訂正紀錄（renumber_fixes）。`--shift K 差` 是「≥K 的號碼
    加差」：刪 cue K 若照「--shift K -1」做，cue K 本身也被減 1，K 的訂正
    落到前一條上，不會報錯。刪 K 要 --shift K+1 -1、K 那一號的訂正人工看；
    併 K 要 --shift K+2 -1、K+1 那一號的訂正人工看。"""

    def test_delete_shifts_from_the_next_cue(self):
        hint = place_cue.renumber_hint("delete", 903)
        self.assertIn("--shift 904 -1", hint)
        self.assertNotIn("--shift 903 ", hint)
        self.assertIn("903", hint)

    def test_merge_shifts_from_two_after(self):
        hint = place_cue.renumber_hint("merge", 528)
        self.assertIn("--shift 530 -1", hint)
        self.assertIn("529", hint)

    def test_insert_shifts_from_the_new_cue(self):
        self.assertIn("--shift 846 1", place_cue.renumber_hint("insert", 846))


class TestStoreMode(unittest.TestCase):
    """work dir 已經清掉或改名 .stale-* 的集（259 晚排灣、248 午噶瑪蘭、
    353 午噶瑪蘭，2026-11-03 都只剩 .work.stale-*），舊做法擋在「無時間軸」，
    刪 cue、併 cue 根本用不了。`--store` 直接改 Kari-SRT 的時間軸、TSV，
    重做交付 SRT；還有 work dir 的不准用（之後 publish 會蓋回去）。"""

    NAME = "20230916_259_晚間_Paiwan_排灣"

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = tmp.name
        self.work = os.path.join(root, "x.work")
        os.makedirs(self.work + ".stale-1022")
        self.folder = os.path.join(root, "vision")
        os.makedirs(self.folder)
        for attr, sub in (("KARI_CUES", "cues"), ("SRT_DIR", "srt")):
            patch = mock.patch.object(place_cue.paths, attr,
                                      os.path.join(root, sub))
            patch.start()
            self.addCleanup(patch.stop)
        self.timeline = paths.stage_path(paths.KARI_CUES, self.NAME, ".json")
        self.srt = paths.stage_path(paths.SRT_DIR, self.NAME, ".srt")
        os.makedirs(os.path.dirname(self.timeline))
        os.makedirs(os.path.dirname(self.srt))
        cues = [cue(1, 2230.0, 2234.866), cue(2, 2234.866, 2234.883),
                cue(3, 2234.883, 2236.0)]
        with open(self.timeline, "w", encoding="utf-8") as handle:
            handle.write(json.dumps({"cues": cues}, ensure_ascii=False,
                                    indent=2, sort_keys=True) + "\n")
        split_cue.write_tsv(os.path.join(self.folder, "b01.tsv"),
                            [(1, "a"), (2, ""), (3, "c")])
        self.rebuilt = []
        entry = {"slug": "x", "srt_name": self.NAME}
        for patch in (
                mock.patch.object(place_cue, "_entry_of",
                                  lambda stem: entry),
                mock.patch.object(place_cue.paths, "work_dir",
                                  lambda stem: self.work),
                mock.patch.object(split_cue, "vision_folders",
                                  lambda name: [self.folder]),
                mock.patch("scripts.news.rebuild.rebuild_one",
                           self.fake_rebuild),
                mock.patch("scripts.news.pairs_run.in_scope",
                           lambda name: False)):
            patch.start()
            self.addCleanup(patch.stop)

    def fake_rebuild(self, entry, tmp):
        self.rebuilt.append(entry["srt_name"])
        with open(os.path.join(tmp, "srt", entry["srt_name"] + ".srt"), "w",
                  encoding="utf-8") as handle:
            handle.write("rebuilt\n")

    def test_without_store_the_error_names_the_stale_dir(self):
        with self.assertRaises(PipelineError) as caught:
            place_cue.apply_delete("stem", 2)
        self.assertIn("--store", str(caught.exception))
        self.assertIn("stale-1022", str(caught.exception))

    def test_store_mode_edits_kari_srt_and_rebuilds_the_srt(self):
        self.assertEqual(place_cue.apply_delete("stem", 2, store=True), 2)
        with open(self.timeline, encoding="utf-8") as handle:
            text = handle.read()
        self.assertTrue(text.endswith("}\n"))         # Kari-SRT 的排版
        self.assertEqual(len(json.loads(text)["cues"]), 2)
        self.assertEqual(split_cue.read_tsv(os.path.join(self.folder,
                                                         "b01.tsv")),
                         [(1, "a"), (2, "c")])
        self.assertEqual(self.rebuilt, [self.NAME])
        with open(self.srt, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "rebuilt\n")

    def test_store_mode_is_refused_while_a_work_dir_lives(self):
        timeline = paths.refined_cues(self.work)
        os.makedirs(os.path.dirname(timeline))
        with open(timeline, "w", encoding="utf-8") as handle:
            handle.write('{"cues": []}')
        with self.assertRaises(PipelineError):
            place_cue.apply_delete("stem", 2, store=True)
        self.assertEqual(self.rebuilt, [])

    def test_store_mode_area_keeps_layout_and_leaves_the_srt(self):
        # rebuild 不讀 area，交付 SRT 不會變，不用重做（也不重做平行語料）
        with open(self.timeline, encoding="utf-8") as handle:
            book = json.load(handle)
        book["areas"] = {"島語時間": {"preset": "titv-news-island"}}
        with open(self.timeline, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(book, ensure_ascii=False, indent=2,
                                    sort_keys=True) + "\n")
        self.assertTrue(place_cue.apply_area("stem", 3, "島語時間",
                                             store=True))
        with open(self.timeline, encoding="utf-8") as handle:
            text = handle.read()
        self.assertTrue(text.endswith("}\n"))
        self.assertEqual(json.loads(text)["cues"][2]["area"], "島語時間")
        self.assertEqual(self.rebuilt, [])

    def test_cli_area_with_store_and_lock(self):
        with open(self.timeline, encoding="utf-8") as handle:
            book = json.load(handle)
        book["areas"] = {"部落信箱": {"preset": "titv-news-mailbox"}}
        with open(self.timeline, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(book, ensure_ascii=False, indent=2,
                                    sort_keys=True) + "\n")
        lock = os.path.join(os.path.dirname(self.folder), "store.lock")
        with mock.patch("sys.stdout"):
            self.assertEqual(place_cue.main(
                ["--store", "--lock", lock, "stem", "area", "1",
                 "部落信箱"]), 0)
        with open(self.timeline, encoding="utf-8") as handle:
            self.assertEqual(json.load(handle)["cues"][0]["area"], "部落信箱")


class TestSetArea(unittest.TestCase):
    """只改一條 cue 的 area。060 午 cue 429「我們下次見」（1156.639–1159.274）
    跟首播 093 晚 511–512 起迄一樣、在部落信箱裡，area 卻寫島語時間（搬移時
    426–428 換掉了、429 沒換到）；fill_placed_area 判斷不出來的 4 條（358 晨
    1291、1292，160 午 839，161 午 736）也要人看畫面補。place_cue 原本只有
    insert、bounds、delete、merge，沒有只改 area 的，只能手改 JSON。"""

    def test_sets_the_area_and_nothing_else(self):
        cues = island()
        got = place_cue.set_area(cues, 3, "部落信箱")
        self.assertEqual(got[2]["area"], "部落信箱")
        before = dict(cues[2])
        after = dict(got[2])
        del before["area"]
        del after["area"]
        self.assertEqual(before, after)
        self.assertEqual(cues[2]["area"], "島語時間")     # 原本那份不動

    def test_empty_string_takes_the_area_off(self):
        # 頂層字幕帶切的 cue 就是沒有 area，不是有一個叫「頂層」的 area
        got = place_cue.set_area(island(), 2, "")
        self.assertNotIn("area", got[1])

    def test_unknown_cue_is_an_error(self):
        with self.assertRaises(PipelineError):
            place_cue.set_area(island(), 5, "島語時間")


class TestBounds(unittest.TestCase):
    def test_moves_the_times_and_nothing_else(self):
        got = place_cue.set_bounds(run(), 3, 3.0, 5.0)
        self.assertEqual((got[2]["start"], got[2]["end"]), (3.0, 5.0))
        self.assertEqual(len(got), 4)
        self.assertEqual(got[2]["images"]["han"], "2-strips/00003_han.png")

    def test_sample_ts_follows_into_the_new_span(self):
        got = place_cue.set_bounds(run(), 3, 4.5, 5.0)
        self.assertTrue(4.5 <= got[2]["sample_ts"] <= 5.0)

    def test_running_into_a_neighbour_is_an_error(self):
        # 337 晚 416 延到 1179.80 會硩著 417（1179.745 起）：兩條愛先後調
        with self.assertRaises(PipelineError):
            place_cue.set_bounds(run(), 3, 1.5, 5.0)
        with self.assertRaises(PipelineError):
            place_cue.set_bounds(run(), 3, 4.0, 5.5)

    def test_unknown_cue_is_an_error(self):
        with self.assertRaises(PipelineError):
            place_cue.set_bounds(run(), 9, 4.0, 5.0)


class TestRemap(unittest.TestCase):
    def test_rows_shift_and_the_new_row_is_added(self):
        rows = [(1, "a"), (2, "b"), (3, "c"), (4, "d")]
        got = place_cue.remap_rows(rows, 3, "新")
        self.assertEqual(got, [(1, "a"), (2, "b"), (3, "新"), (4, "c"),
                               (5, "d")])

    def test_rows_of_another_file_only_shift(self):
        got = place_cue.shift_rows([(2, "b"), (3, "c")], 3)
        self.assertEqual(got, [(2, "b"), (4, "c")])

    def test_sheets_shift_and_new_cue_joins_the_previous_ones_sheet(self):
        sheets = {"s1.png": [1, 2], "s2.png": [3, 4]}
        got = place_cue.remap_sheets(sheets, 3)
        self.assertEqual(got, {"s1.png": [1, 2, 3], "s2.png": [4, 5]})

    def test_sheets_new_first_cue_joins_the_first_sheet(self):
        sheets = {"s1.png": [1, 2], "s2.png": [3, 4]}
        got = place_cue.remap_sheets(sheets, 1)
        self.assertEqual(got, {"s1.png": [1, 2, 3], "s2.png": [4, 5]})


if __name__ == "__main__":
    unittest.main()
