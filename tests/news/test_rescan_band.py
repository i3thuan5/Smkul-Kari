"""rescan_band：kā一段用毋著帶切ê cue 換掉，其他ê重新編號。

這是規條管線內底上危險ê操作——**規集ê cue 號碼會振動**，而且
`b*.tsv`、`transcripts.json`、`sheets.json`、`strips/` 五項攏是用
號碼做鍵ê。有一項無綴著，文字就會落佇毋著ê時間頂懸，**無一个
所在會報錯**：逝數對、欄數對、`ingest` ê覆蓋率嘛是 100%。

所以純算術彼部份（切、接、重編號）家己一支函式，用合成資料
逐條驗過。
"""
import unittest

from scripts.errors import PipelineError
from scripts.news import rescan_band


def cue(index, start, end, text="x"):
    return {"index": index, "start": start, "end": end,
            "images": {"han": "strips/%05d_han.png" % index}}


def run(count, start=0.0, step=1.0):
    out = []
    for i in range(count):
        out.append(cue(i + 1, start + i * step, start + (i + 1) * step))
    return out


class TestSplice(unittest.TestCase):
    """舊ê [lo, hi] 提掉，新ê囥入去，規排重編 1..N。"""

    def test_replacing_one_with_one_keeps_the_count(self):
        got = rescan_band.splice(run(5), 3, 3, [cue(1, 2.0, 3.0)])
        self.assertEqual(len(got), 5)
        self.assertEqual([c["index"] for c in got], [1, 2, 3, 4, 5])

    def test_replacing_one_with_three_grows_the_list(self):
        new = [cue(1, 2.0, 2.3), cue(2, 2.3, 2.6), cue(3, 2.6, 3.0)]
        got = rescan_band.splice(run(5), 3, 3, new)
        self.assertEqual(len(got), 7)
        self.assertEqual([c["index"] for c in got], [1, 2, 3, 4, 5, 6, 7])

    def test_replacing_three_with_one_shrinks_it(self):
        got = rescan_band.splice(run(5), 2, 4, [cue(1, 1.0, 4.0)])
        self.assertEqual([c["index"] for c in got], [1, 2, 3])

    def test_the_kept_cues_keep_their_times(self):
        got = rescan_band.splice(run(5), 3, 3, [cue(1, 2.0, 3.0)])
        self.assertEqual(got[0]["start"], 0.0)
        self.assertEqual(got[-1]["end"], 5.0)

    def test_the_new_cues_keep_their_times(self):
        new = [cue(1, 2.0, 2.4), cue(2, 2.4, 3.0)]
        got = rescan_band.splice(run(5), 3, 3, new)
        self.assertEqual((got[2]["start"], got[2]["end"]), (2.0, 2.4))
        self.assertEqual((got[3]["start"], got[3]["end"]), (2.4, 3.0))

    def test_replacing_the_whole_episode_is_allowed(self):
        got = rescan_band.splice(run(3), 1, 3, [cue(1, 0.0, 3.0)])
        self.assertEqual([c["index"] for c in got], [1])

    def test_a_range_outside_the_list_is_an_error(self):
        with self.assertRaises(PipelineError):
            rescan_band.splice(run(5), 4, 9, [cue(1, 0.0, 1.0)])

    def test_hi_before_lo_is_an_error(self):
        with self.assertRaises(PipelineError):
            rescan_band.splice(run(5), 4, 2, [cue(1, 0.0, 1.0)])

    def test_an_empty_replacement_is_an_error(self):
        """規段提掉、無囥物件入去，是講「遮無字幕」——彼愛家己講，
        袂使當做重切ê結果恬恬做出來。"""
        with self.assertRaises(PipelineError):
            rescan_band.splice(run(5), 2, 3, [])

    def test_times_stay_in_order_across_the_seam(self):
        new = [cue(1, 2.0, 2.5)]
        got = rescan_band.splice(run(5), 3, 3, new)
        for before, after in zip(got, got[1:]):
            self.assertLessEqual(before["end"], after["start"])


class TestImagesAreNotRewrittenByIndex(unittest.TestCase):
    """`splice` 袂使照 index 重寫 `images`。

    舊版 `main()` 有一逝 `cue["images"] = {"han": "strips/%05d_han.png"
    % cue["index"]}`，是**無條件**照序號重寫規份。Strip 換做時間號名
    了後，彼逝會kā `images` 寫做序號形——磁碟頂懸是時間名，就指去
    無彼張圖。別个 session 掠著ê。
    """

    def test_kept_cues_keep_their_own_images(self):
        cues = run(5)
        got = rescan_band.splice(cues, 3, 3, [cue(1, 2.0, 3.0)])
        self.assertEqual(got[0]["images"]["han"], "strips/00001_han.png")
        self.assertEqual(got[4]["images"]["han"], "strips/00005_han.png")

    def test_renumbering_does_not_touch_images(self):
        """後壁ê cue 退號ê時，伊ê圖猶原是原本彼張。"""
        cues = run(5)
        new = [cue(1, 2.0, 2.4), cue(2, 2.4, 3.0)]
        got = rescan_band.splice(cues, 3, 3, new)
        self.assertEqual(got[5]["index"], 6)
        self.assertEqual(got[5]["images"]["han"], "strips/00005_han.png")


class TestMapping(unittest.TestCase):
    """舊號碼對新號碼；[lo, hi] 內底ê無對應（伊hőng換掉矣）。"""

    def test_cues_before_the_range_do_not_move(self):
        got = rescan_band.mapping(5, 3, 3, 1)
        self.assertEqual(got[1], 1)
        self.assertEqual(got[2], 2)

    def test_cues_in_the_range_have_no_mapping(self):
        got = rescan_band.mapping(5, 2, 4, 1)
        for old in (2, 3, 4):
            self.assertNotIn(old, got)

    def test_cues_after_shift_by_the_difference(self):
        # 3 條換做 1 條 → 後壁ê退 2
        got = rescan_band.mapping(5, 2, 4, 1)
        self.assertEqual(got[5], 3)

    def test_growing_pushes_later_cues_up(self):
        # 1 條換做 3 條 → 後壁ê進 2
        got = rescan_band.mapping(5, 3, 3, 3)
        self.assertEqual(got[4], 6)
        self.assertEqual(got[5], 7)

    def test_no_two_old_cues_land_on_the_same_new_one(self):
        got = rescan_band.mapping(20, 5, 9, 7)
        self.assertEqual(len(set(got.values())), len(got))

    def test_the_mapping_never_reorders(self):
        got = rescan_band.mapping(20, 5, 9, 7)
        olds = sorted(got)
        news = [got[o] for o in olds]
        self.assertEqual(news, sorted(news))


class TestRemapTsvRows(unittest.TestCase):
    """TSV ê逝愛照 mapping 徙；hőng換掉彼段ê逝愛提掉。"""

    ROWS = [(1, "一"), (2, "二"), (3, "三"), (4, "四"), (5, "五")]

    def test_rows_before_the_range_are_untouched(self):
        got = rescan_band.remap_rows(self.ROWS,
                                     rescan_band.mapping(5, 3, 3, 1))
        self.assertIn((1, "一"), got)
        self.assertIn((2, "二"), got)

    def test_rows_in_the_replaced_range_are_dropped(self):
        got = rescan_band.remap_rows(self.ROWS,
                                     rescan_band.mapping(5, 3, 3, 1))
        self.assertNotIn("三", [text for _, text in got])

    def test_rows_after_the_range_are_renumbered(self):
        got = dict(rescan_band.remap_rows(self.ROWS,
                                          rescan_band.mapping(5, 3, 3, 3)))
        self.assertEqual(got[6], "四")
        self.assertEqual(got[7], "五")

    def test_the_result_is_in_cue_order(self):
        got = rescan_band.remap_rows(list(reversed(self.ROWS)),
                                     rescan_band.mapping(5, 3, 3, 3))
        self.assertEqual([n for n, _ in got], sorted(n for n, _ in got))

    def test_text_is_never_altered(self):
        rows = [(1, "有\ttab ê字"), (5, "  頭尾空白  ")]
        got = dict(rescan_band.remap_rows(rows,
                                          rescan_band.mapping(5, 3, 3, 1)))
        self.assertEqual(got[1], "有\ttab ê字")
        self.assertEqual(got[5], "  頭尾空白  ")


class TestRebuildSheets(unittest.TestCase):
    """重做組合圖了後愛寫一份空ê transcripts.json。

    2022-12 353 晚間：讀字讀煞、猶未組裝就發現帶外專題愛重切，work dir
    內底猶無 `5-transcripts/`。重切、接 cue、TSV 重編號、組合圖攏做好矣，
    上尾寫 transcripts.json 煞因為目錄無佇咧 FileNotFoundError 倒去
    （2026-10-16）。重切是無 dry-run 以外ê退路ê操作，倒佇上尾一步上歹收。
    """

    def test_writes_transcripts_when_the_folder_is_missing(self):
        import json
        import os
        import tempfile
        from unittest import mock
        from scripts import datadirs
        with tempfile.TemporaryDirectory() as work:
            target = datadirs.transcripts_file(work)
            self.assertFalse(os.path.isdir(os.path.dirname(target)))
            with mock.patch.object(rescan_band.sheets, "build_sheets",
                                   return_value=3), \
                    mock.patch.object(rescan_band.gap_sheets,
                                      "news_sheet_layout",
                                      return_value=(None, None, None)):
                made = rescan_band.rebuild_sheets(work, {"cues": []})
            self.assertEqual(made, 3)
            with open(target, encoding="utf-8") as handle:
                self.assertEqual(json.load(handle), {})


class TestMainPersistsStripRefs(unittest.TestCase):
    """重切出來ê cue 愛指向 `han` 圖條，而且愛寫入磁碟頂ê時間軸。

    2022-12 353 晚間重切 373 條：`move_strips` 有 kā 新圖條抄做
    `t…_han.png`、mā kā cue 改做 `{"han": …}`，毋過時間軸是佇
    `move_strips` 進前就寫落去矣，磁碟頂ê 373 條猶是 recut 原本ê
    `{"line0": …}`。組合圖干焦認 `han`，規段 373 條攏予跳過，
    30 張組合圖內底無半條重切ê cue，嘛無報錯（2026-10-16）。
    """

    def test_recut_cues_point_at_han_strips_on_disk(self):
        import json
        import os
        import tempfile
        from unittest import mock
        from scripts import datadirs
        from scripts.ocr import stripname
        stem = "2022_353_2022-12-19_晚間_Amis_阿美"
        with tempfile.TemporaryDirectory() as root:
            work = os.path.join(root, stem + ".work")
            timeline = datadirs.refined_cues(work)
            os.makedirs(os.path.dirname(timeline))
            os.makedirs(datadirs.strips_dir(work))
            old = []
            for i in range(5):
                start = 10.0 * i
                old.append({"index": i + 1, "start": start,
                            "end": start + 5,
                            "images": {"han": datadirs.strip_ref(
                                stripname.of(start, "han"))}})
            with open(timeline, "w", encoding="utf-8") as handle:
                json.dump({"cues": old}, handle)
            video = os.path.join(root, "v.mkv")
            open(video, "w").close()
            vision = os.path.join(root, "vision")

            def fake_recut(video, start, duration, out, region=None,
                           venv=None):
                os.makedirs(datadirs.strips_dir(out), exist_ok=True)
                new = []
                for n, t in enumerate((11.0, 13.0, 16.0)):
                    name = "%05d_line0.png" % (n + 1)
                    open(os.path.join(datadirs.strips_dir(out), name),
                         "w").close()
                    new.append({"index": n + 1, "start": t, "end": t + 2,
                                "images": {"line0": datadirs.strip_ref(
                                    name)}})
                return new

            with mock.patch.object(rescan_band.paths, "work_dir",
                                   return_value=work), \
                    mock.patch.object(rescan_band, "recut", fake_recut), \
                    mock.patch.object(
                        rescan_band, "_srt_name",
                        return_value="20221219_353_晚間_Amis_阿美"), \
                    mock.patch.object(rescan_band.paths, "KARI_VISION",
                                      vision), \
                    mock.patch.object(rescan_band, "rebuild_sheets"), \
                    mock.patch.object(rescan_band.lowpri, "be_nice"):
                rescan_band.main([stem, "2", "3", "--video", video])
            with open(timeline, encoding="utf-8") as handle:
                cues = json.load(handle)["cues"]
            self.assertEqual(len(cues), 6)
            for cue in cues[1:4]:
                self.assertEqual(list(cue["images"]), ["han"])
                self.assertTrue(os.path.exists(
                    os.path.join(work, cue["images"]["han"])))


if __name__ == "__main__":
    unittest.main()
