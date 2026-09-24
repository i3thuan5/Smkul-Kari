"""vision_tools.prompt: 一批ê範圍佮 TSV 名，愛佮 `ingest` 講ê仝款。

提示是產ê毋是手寫ê，所以「範圍算毋著」無人會發現——TSV 寫出來
逝數對、欄數對，干焦內容囥毋著位。遮ê測試是彼枝把關。
"""
import csv
import json
import os
import re
import tempfile
import unittest
from unittest import mock

from scripts import catalogue_checks as checks
from scripts.errors import PipelineError
from scripts.news import paths
from scripts.news.vision_tools import prompt
from tests.ocr.test_sheetsize import png_bytes


def blank_reload():
    """Re-import `prompt` so its module-level SCRATCH is recomputed."""
    import importlib
    return importlib.reload(prompt)


def sheets_of(count, per=4):
    """`sheets.json` ê形：sheet_001.png → [1,2,3,4]、sheet_002.png → [5..8]。"""
    out = {}
    for i in range(count):
        cues = []
        for k in range(per):
            cues.append(i * per + k + 1)
        out["sheet_%03d.png" % (i + 1)] = cues
    return out


def write_book(work, book, sizes=None):
    """sheets.json 佮逐張 PNG（切批愛讀檔頭算重量）。"""
    index = paths.sheets_index(work)
    os.makedirs(os.path.dirname(index), exist_ok=True)
    with open(index, "w", encoding="utf-8") as handle:
        json.dump(book, handle)
    for name in book:
        width, height = (sizes or {}).get(name, (1000, 800))
        with open(os.path.join(os.path.dirname(index), name), "wb") as fh:
            fh.write(png_bytes(width, height))


def names_of(batches):
    out = []
    for batch in batches:
        out.append(list(batch))
    return out


class VisionPromptCase(unittest.TestCase):
    """逐个 case 家己一个 work dir，內底囥合成ê sheets.json 佮圖。

    一張 1000×800 ê圖是 36×29 ＝ 1,044 个視覺 token，4 條 cue 加
    68，重量 1,112；一批扣掉起手 69,184 賰 50,816，裝會落 45 張。
    """

    NAME = "20210224_055_午間_Cou_鄒"
    SLUG = "2021_055_2021-02-24_午間_Cou_鄒"
    REMOTE = ("/docker/ilrdf-corpus/族語新聞/110.1-110.10/2月/"
              "21NL003_55午間族語新聞.mp4")

    def setUp(self):
        # 來源路徑本底愛讀節目目錄；測試離線，換做固定值
        patcher = mock.patch.object(prompt, "remote_of",
                                    return_value=self.REMOTE)
        patcher.start()
        self.addCleanup(patcher.stop)
        # 編號看 Kari-SRT 既有ê TSV：測試莫去讀著真ê彼集
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.vision = tmp.name
        patcher = mock.patch.object(prompt.paths, "KARI_VISION", tmp.name)
        patcher.start()
        self.addCleanup(patcher.stop)

    def work(self, count, per=4, verified=None, sizes=None):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        write_book(tmp.name, sheets_of(count, per), sizes)
        if verified is not None:
            path = paths.verified_file(tmp.name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(verified, handle)
        return tmp.name

    def brief_in(self, work, which, **kw):
        with mock.patch.object(prompt, "episode", return_value=self.NAME), \
                mock.patch.object(prompt, "workdir", return_value=work):
            return prompt.brief(self.SLUG, which, **kw)

    def brief(self, count, which, per=4, **kw):
        return self.brief_in(self.work(count, per), which, **kw)

    def existing_tsv(self, name, cues):
        folder = paths.stage_path(self.vision, self.NAME)
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, name), "w", encoding="utf-8") as fh:
            for cue in cues:
                fh.write("%d\than\t字\n" % cue)


class TestBatchContents(VisionPromptCase):
    """判準逐張列出這批愛讀ê圖——分出來ê批佇檔名頂懸無連紲。"""

    def test_every_sheet_of_the_batch_is_named(self):
        work = self.work(100)
        batch = prompt.batches_of(work)[0]
        text = self.brief_in(work, 1)
        for name in batch:
            self.assertIn("`%s`" % name, text)

    def test_no_first_to_last_range_is_given(self):
        # 照「第一張–最後一張」讀，會讀著別批ê圖
        text = self.brief(100, 1)
        self.assertNotIn("`–`", text)
        self.assertIsNone(re.search(r"`sheet_\d+\.png`–`sheet_", text))

    def test_sheets_of_other_batches_are_not_named(self):
        work = self.work(100)
        plan = prompt.batches_of(work)
        text = self.brief_in(work, 2)
        for name in plan[0]:
            self.assertNotIn("`%s`" % name, text)

    def test_line_count_is_the_batchs_cues(self):
        work = self.work(100)
        count = len(prompt.batches_of(work)[0]) * 4
        self.assertIn("%d 逝" % count, self.brief_in(work, 1))

    def test_batch_past_the_end_is_an_error(self):
        with self.assertRaises(PipelineError):
            self.brief(100, 9)

    def test_verified_sheets_are_not_handed_out_again(self):
        # 讀到一半：頭 50 張已經收入去，賰ê才愛讀
        verified = {}
        for cue in range(1, 201):
            verified[str(cue)] = {"han": True}
        work = self.work(100, verified=verified)
        planned = []
        for batch in prompt.batches_of(work):
            planned += batch
        wanted = []
        for n in range(51, 101):
            wanted.append("sheet_%03d.png" % n)
        self.assertEqual(sorted(planned), wanted)


class TestPlan(unittest.TestCase):
    """最長作業優先分配：批數照總重量，各批差不多重，批內小到大。"""

    CAP = prompt.CEILING - prompt.BASE

    def weights(self, values):
        out = []
        for n, value in enumerate(values):
            out.append(("s%03d.png" % n, value))
        return out

    def loads(self, batches, table):
        out = []
        for batch in batches:
            total = 0
            for name in batch:
                total += table[name]
            out.append(total)
        return out

    def test_every_sheet_exactly_once_and_no_empty_batch(self):
        values = []
        for n in range(80):
            values.append(3000 + (n * 37) % 900)
        items = self.weights(values)
        got = prompt.plan(items)
        flat = []
        for batch in got:
            self.assertTrue(batch)
            flat += batch
        self.assertEqual(sorted(flat), sorted(dict(items)))

    def test_batch_count_comes_from_the_total_weight(self):
        # 照張數切：大圖多ê集每批超過上限、小圖多ê集濟開批
        items = self.weights([2000] * 60)          # 120,000
        self.assertEqual(len(prompt.plan(items)),
                         -(-120000 // self.CAP))
        items = self.weights([8000] * 20)          # 160,000
        self.assertEqual(len(prompt.plan(items)),
                         -(-160000 // self.CAP))

    def test_batches_weigh_about_the_same(self):
        # 照檔名切ê時各批差 1.23–1.44 倍
        values = []
        for n in range(90):
            values.append(800 + (n * n * 7919) % 4000)
        items = self.weights(values)
        got = prompt.plan(items)
        loads = self.loads(got, dict(items))
        self.assertGreater(len(got), 1)
        self.assertLessEqual(max(loads) / min(loads), 1.1)

    def test_small_sheets_are_read_first(self):
        # 先入 context ê圖，後壁逐則回覆攏愛閣算一擺：大到小貴約 10%
        items = self.weights([5000, 900, 3000, 1200, 4000, 700])
        table = dict(items)
        for batch in prompt.plan(items):
            got = []
            for name in batch:
                got.append(table[name])
            self.assertEqual(got, sorted(got))

    def test_the_same_input_always_gives_the_same_batches(self):
        # 重量相仝ê兩張順序無固定，兩支程式就對袂著
        items = self.weights([1000] * 70)
        once = prompt.plan(items)
        again = prompt.plan(list(reversed(items)))
        self.assertEqual(once, again)
        for batch in once:
            self.assertEqual(batch, sorted(batch))

    def test_clustered_big_sheets_get_an_extra_batch(self):
        # 分完猶有一批超過上限，就加開一批重分
        items = self.weights([30000, 30000, 30000, 100, 100])
        got = prompt.plan(items)
        table = dict(items)
        for load in self.loads(got, table):
            self.assertLessEqual(load, self.CAP)
        self.assertEqual(len(got), 3)

    def test_a_sheet_bigger_than_a_batch_still_goes_out_alone(self):
        items = self.weights([self.CAP + 5000, 100])
        got = prompt.plan(items)
        self.assertEqual(len(got), 2)
        self.assertIn(["s000.png"], got)

    def test_nothing_to_read_is_no_batch(self):
        self.assertEqual(prompt.plan([]), [])

    def test_fewer_sheets_than_batches_makes_no_empty_batch(self):
        items = self.weights([self.CAP * 3])
        self.assertEqual(prompt.plan(items), [["s000.png"]])

    def test_the_estimate_adds_the_fixed_part_once(self):
        self.assertEqual(prompt.estimate([1000, 2000]),
                         prompt.BASE + 3000)


class TestWeights(VisionPromptCase):

    def test_weight_is_visual_tokens_plus_rows(self):
        # 1000×800 → 36×29 ＝ 1,044；4 條 cue × 17 ＝ 68
        work = self.work(1)
        self.assertEqual(prompt.sheet_weights(work, ["sheet_001.png"]),
                         [("sheet_001.png", 1044 + 68)])

    def test_a_wider_sheet_weighs_more(self):
        work = self.work(2, sizes={"sheet_002.png": (1988, 1400)})
        got = dict(prompt.sheet_weights(work, ["sheet_001.png",
                                               "sheet_002.png"]))
        self.assertGreater(got["sheet_002.png"], got["sheet_001.png"])


class TestScratch(VisionPromptCase):
    """Scratchpad 是逐支 agent 公家ê，checkpoint ê路徑愛家己一份。"""

    def test_scratch_path_names_the_episode_and_the_batch(self):
        text = self.brief(100, 2)
        self.assertIn(self.NAME + "-b02", text)

    def test_two_batches_of_one_episode_do_not_share_it(self):
        one = self.brief(100, 1)
        two = self.brief(100, 2)
        self.assertNotIn(self.NAME + "-b01", two)
        self.assertNotIn(self.NAME + "-b02", one)

    def test_empty_env_var_falls_back_to_the_default(self):
        """空字串是「設了無值」，`os.environ.get` 掠做設矣，
        `os.path.join("", x)` 就吐一个相對路徑出來。"""
        with mock.patch.dict(os.environ, {"CLAUDE_SCRATCH": ""}):
            got = blank_reload().SCRATCH
        self.assertTrue(got.startswith("/"), got)

    def test_placeholder_is_filled_in(self):
        self.assertNotIn("{scratch}", self.brief(100, 1))

    def test_no_placeholder_is_left_behind(self):
        """`brief.md` 內底逐个 `{…}` 攏愛hőng換掉，一个都莫賰。

        賰落來ê `{sheets}` 這款物件袂報錯，是**直接印佇讀者面頭前**
        ê一句死字。逐擺佇 brief.md 加新ê鍵，`_brief` ê `fill` 若無
        綴leh加就是按呢。所以莫干焦顧一个鍵，規包掠。
        """
        text = self.brief(100, 1)
        left = re.findall(r"\{[a-z_]+\}", text)
        self.assertEqual(left, [], "brief.md 有無換ê鍵：%s" % left)


class TestSheetNames(VisionPromptCase):
    """圖條檔名是 `t00015200.png` 這款，無底線通好剖。

    本底 `_brief` 用 `names[0].split("_")[1]` 提編號，去hőng e81f1f1
    改過ê打包規則咬著：新ê名是「圖條闊度」做ê `t00015200.png`，剖
    出來只有一逝，`[1]` 就 IndexError——2026-09-12 beh派 2021-01
    ê讀者ê時規支倒去。提示內底講ê愛是**檔名家己**，毋是編號。
    """

    def work_named(self, names, per=4):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        book = {}
        for i, name in enumerate(names):
            cues = []
            for k in range(per):
                cues.append(i * per + k + 1)
            book[name] = cues
        write_book(tmp.name, book)
        return tmp.name

    def brief_named(self, names, which, **kw):
        work = self.work_named(names)
        with mock.patch.object(prompt, "episode", return_value=self.NAME), \
                mock.patch.object(prompt, "workdir", return_value=work):
            return prompt.brief("2021_055_2021-02-24_午間_Cou_鄒", which, **kw)

    NAMES = ["t00015200.png", "t00022200.png", "t00023600.png"]

    def test_a_name_without_an_underscore_does_not_crash(self):
        text = self.brief_named(self.NAMES, 1)
        self.assertIn("t00015200.png", text)

    def test_every_sheet_is_named_in_full(self):
        text = self.brief_named(self.NAMES, 1)
        for name in self.NAMES:
            self.assertIn("`%s`" % name, text)

    def test_the_timeline_named_is_the_one_that_exists(self):
        """時間軸ê路徑愛指著實在有ê彼份，毋是 `<work>/cues.json`。

        時間軸分做 `1-cues/`（粗切）佮 `3-refined/`（精修）了後，
        平ê `<work>/cues.json` 就無矣。提示猶原按呢寫，讀者beh抽
        原生格核對ê時開無彼份檔——**恬恬失敗**：伊會當家己臆一
        个時間，抑是規氣放棄核對。
        """
        work = self.work_named(self.NAMES)
        os.makedirs(os.path.join(work, "1-cues"))
        with open(os.path.join(work, "1-cues", "cues.json"), "w",
                  encoding="utf-8") as handle:
            json.dump({"cues": []}, handle)
        with mock.patch.object(prompt, "episode", return_value=self.NAME), \
                mock.patch.object(prompt, "workdir", return_value=work):
            text = prompt.brief(self.SLUG, 1)
        self.assertIn("1-cues/cues.json", text)
        self.assertNotIn("%s/cues.json" % work, text)

    def test_a_refined_timeline_wins_over_the_coarse_one(self):
        work = self.work_named(self.NAMES)
        for stage in ("1-cues", "3-refined"):
            os.makedirs(os.path.join(work, stage))
            with open(os.path.join(work, stage, "cues.json"), "w",
                      encoding="utf-8") as handle:
                json.dump({"cues": []}, handle)
        with mock.patch.object(prompt, "episode", return_value=self.NAME), \
                mock.patch.object(prompt, "workdir", return_value=work):
            text = prompt.brief(self.SLUG, 1)
        self.assertIn("3-refined/cues.json", text)

    def test_no_placeholder_is_left_behind_either(self):
        text = self.brief_named(self.NAMES, 1)
        left = re.findall(r"\{[a-z_]+\}", text)
        self.assertEqual(left, [], "brief.md 有無換ê鍵：%s" % left)


class TestTsvName(VisionPromptCase):
    def test_default_name_follows_the_batch_number(self):
        text = self.brief(100, 3)
        self.assertIn("b03.tsv", text)

    def test_numbering_continues_after_what_is_already_in(self):
        # 讀到一半閣派，兩爿攏對 b01 起算，會kā已經收入去ê b01 蓋掉
        verified = {}
        for cue in range(1, 201):
            verified[str(cue)] = {"han": True}
        self.existing_tsv("b01.tsv", range(1, 101))
        self.existing_tsv("b02.tsv", range(101, 201))
        work = self.work(100, verified=verified)
        text = self.brief_in(work, 1)
        self.assertIn("b03.tsv", text)
        self.assertNotIn("b01.tsv", text)

    def test_a_tsv_still_being_written_does_not_shift_the_numbers(self):
        # 讀者寫到一半、猶未 ingest ê檔，就是這批本身，莫算做「已經收」
        self.existing_tsv("b01.tsv", range(1, 30))
        text = self.brief(100, 2)
        self.assertIn("b02.tsv", text)

    def test_override_is_used_instead(self):
        text = self.brief(100, 1, tsv="b07.tsv")
        self.assertIn("b07.tsv", text)
        self.assertNotIn("b01.tsv", text)

    def test_override_does_not_swallow_the_episode_name(self):
        """本底這个參數號做 `name`，去hőng `name = episode(slug)` 蓋去，
        TSV 就變做集數名。"""
        text = self.brief(100, 1, tsv="b07.tsv")
        self.assertIn(self.NAME, text)
        self.assertIn(os.path.join(self.NAME, "b07.tsv"), text)


class TestCueRange(VisionPromptCase):
    """重切了後，欲讀ê毋是「第幾批」，是「cue 幾號到幾號」。"""

    def brief_for(self, count, lo, hi, per=4, **kw):
        work = self.work(count, per)
        with mock.patch.object(prompt, "episode", return_value=self.NAME), \
                mock.patch.object(prompt, "workdir", return_value=work):
            return prompt.brief_range(
                "2021_055_2021-02-24_午間_Cou_鄒", lo, hi, **kw)

    def test_only_the_sheets_holding_those_cues(self):
        # 逐張 4 條：cue 9–16 是 sheet_003、sheet_004
        text = self.brief_for(20, 9, 16)
        self.assertIn("`sheet_003.png`", text)
        self.assertIn("`sheet_004.png`", text)
        self.assertNotIn("`sheet_002.png`", text)
        self.assertNotIn("`sheet_005.png`", text)

    def test_a_partial_sheet_is_still_included(self):
        """Cue 10 佇 sheet_003 中央——彼張愛入來，讀者才看會著。"""
        text = self.brief_for(20, 10, 15)
        self.assertIn("`sheet_003.png`", text)
        self.assertIn("`sheet_004.png`", text)
        self.assertNotIn("`sheet_002.png`", text)
        self.assertNotIn("`sheet_005.png`", text)

    def test_the_cue_range_reported_is_the_one_asked_for(self):
        """圖條罩 9..16，毋過欲讀ê是 10..15——講ê愛是後者。

        講「9..16」ê話，讀者會kā別段已經讀過ê cue 閣寫一擺，
        `ingest` 就會擋規集。"""
        text = self.brief_for(20, 10, 15)
        self.assertIn("cue 10..15", text)
        self.assertNotIn("cue 9..16", text)
        self.assertIn("6 逝", text)

    def test_a_range_with_no_sheet_is_an_error(self):
        with self.assertRaises(PipelineError):
            self.brief_for(20, 900, 999)

    def test_the_tsv_name_is_the_callers(self):
        text = self.brief_for(20, 9, 16, tsv="b05.tsv")
        self.assertIn("b05.tsv", text)

    def test_the_asked_range_is_named_when_the_sheets_hold_more(self):
        """邊ê圖條頂懸有別段ê cue，彼幾條已經讀過矣。

        058晚 b05 就是按呢：圖條罩著 292..444，毋過 444 早就佇
        `b02.tsv` 內底。讀者若照圖條寫，`ingest` 會報「cue 444
        佇兩个檔攏有」，規批擋落來。伊家己掠著才無出代誌——
        彼是運氣，毋是把關。
        """
        text = self.brief_for(20, 10, 15)
        self.assertIn("**干焦寫 cue 10..15**", text)
        self.assertIn("6 逝", text)

    def test_nothing_extra_is_said_when_the_range_fits_the_sheets(self):
        text = self.brief_for(20, 9, 16)
        self.assertNotIn("干焦寫 cue", text)


class TestPerSheet(VisionPromptCase):
    """「逐張幾條」愛用算ê，莫寫死。

    重切了後ê圖條逐張 3 條（059晚 b09 就是），提示soah寫「逐張 4 條」，
    讀者若照按呢算逝數就會算毋著。伊是去看 `sheets.json` 才無出代誌。
    """

    def test_three_per_sheet_is_said_as_three(self):
        text = self.brief(24, 1, per=3)
        self.assertIn("逐張 3 條", text)
        self.assertNotIn("逐張 4 條", text)

    def test_four_per_sheet_is_still_four(self):
        text = self.brief(24, 1, per=4)
        self.assertIn("逐張 4 條", text)

    def test_a_ragged_last_sheet_is_said_as_at_most(self):
        """尾張較少ê時，講「上濟幾條」較誠實。"""
        work = self.work(3, 4)
        import json
        with open(paths.sheets_index(work), encoding="utf-8") as fh:
            data = json.load(fh)
        data["sheet_003.png"] = [9, 10]
        with open(paths.sheets_index(work), "w",
                  encoding="utf-8") as fh:
            json.dump(data, fh)
        with mock.patch.object(prompt, "episode", return_value=self.NAME), \
                mock.patch.object(prompt, "workdir", return_value=work):
            text = prompt.brief(self.SLUG, 1)
        self.assertIn("上濟 4 條", text)


class TestEpisodeLookup(unittest.TestCase):
    """`episode()` 對節目目錄（`smkul.csv`）讀，毋是對 `inventory.json`。

    `inventory.json` 佇 b787084 提掉矣（逐一欄對節目目錄推導會出來），
    `batches.py` 綴leh改用 `episodes.load()`，這爿無改著——2026-09-12
    beh派 2021-01 ê讀者ê時，`prompt.py` 當場 FileNotFoundError，規个
    視覺辨識派袂出去。這組測試是彼枝把關：只要閣有人去讀彼份無存在
    ê檔，遮就紅。
    """

    ROW = {"成果檔名": "20210210_041_午間_Cou_鄒",
           "節目名稱": "午間族語新聞", "年度": "2021", "集數": "41",
           "播出日期": "2021-02-10", "族語別(英)": "Cou",
           "族語別(中)": "鄒", "語言別": "", "語言別代號": "tsu",
           "原始影片檔案位置":
               "ilrdf-corpus/族語新聞/21NL003_41午間族語新聞.mp4",
           "備註": ""}
    SLUG = "2021_041_2021-02-10_午間_Cou_鄒"

    def _table(self, rows):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = os.path.join(tmp.name, "smkul.csv")
        head = list(checks.head(checks.NEWS_KEYS)) + [
            "原始影片檔案位置", "備註"]
        with open(path, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=head)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
        return path

    def test_name_comes_from_the_catalogue(self):
        path = self._table([self.ROW])
        with mock.patch.object(prompt.paths, "TRACKER_STORE", path):
            got = prompt.episode(self.SLUG)
        self.assertEqual(got, self.ROW["成果檔名"])

    def test_no_inventory_json_is_read(self):
        """目錄下底無 `inventory.json` 嘛愛做會出來。

        本底 `episode()` 開 `<KARI>/news/inventory.json`，檔無矣就
        FileNotFoundError——彼毋是「揣無這集」，是規支工具倒去。
        """
        path = self._table([self.ROW])
        with mock.patch.object(prompt.paths, "TRACKER_STORE", path), \
                mock.patch.object(prompt.paths, "KARI",
                                  os.path.dirname(path)):
            got = prompt.episode(self.SLUG)
        self.assertEqual(got, self.ROW["成果檔名"])

    def test_slug_not_in_inventory_is_an_error(self):
        path = self._table([self.ROW])
        with mock.patch.object(prompt.paths, "TRACKER_STORE", path):
            with self.assertRaises(PipelineError):
                prompt.episode("揣無這集")


class TestOpeningBrief(unittest.TestCase):
    """片頭辨識ê讀者說明：讀語別牌佮主播，寫 `opening.ingest` 食ê TSV。"""

    def setUp(self):
        self.text = prompt.opening_brief(
            [("/w/opening_001.png", ["20241201_336_晨間_Thau_邵",
                                     "20241201_336_午間_Kanakanavu_卡那卡那富"])],
            "/scratch/opening.tsv")

    def test_every_sheet_and_episode_is_named(self):
        self.assertIn("/w/opening_001.png", self.text)
        self.assertIn("20241201_336_晨間_Thau_邵", self.text)
        self.assertIn("/scratch/opening.tsv", self.text)

    def test_the_badge_is_written_as_the_chinese_name(self):
        # 目錄比ê是 `族語別(中)`；寫 Thau 抑是「邵語」就對袂著。
        self.assertIn("中文族名", self.text)
        self.assertIn("判不準", self.text)

    def test_the_columns_are_the_ones_ingest_reads(self):
        self.assertIn("成果檔名<TAB>秒數<TAB>語別牌<TAB>主播", self.text)

    def test_no_placeholder_is_left(self):
        self.assertIsNone(re.search(r"\{[a-z_]+\}", self.text))


class TestSegmentsBrief(unittest.TestCase):
    """段落確認ê讀者說明：判不準ê段逐段看截圖，回類型佮單元語別。"""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.work = os.path.join(tmp.name, "x.work")
        from scripts.news import segments
        rows = [
            {"起秒": "0", "迄秒": "200", "類型": "外景新聞",
             "單元語別": "拉阿魯哇", "字幕上緣y": "722", "字幕下緣y": "848",
             "依據": "自動"},
            {"起秒": "200", "迄秒": "450", "類型": "島語時間",
             "單元語別": "拉阿魯哇", "字幕上緣y": "940",
             "字幕下緣y": "1060", "依據": segments.PENDING},
            {"起秒": "450", "迄秒": "600.000", "類型": "外景新聞",
             "單元語別": "拉阿魯哇", "字幕上緣y": "722", "字幕下緣y": "848",
             "依據": "自動"}]
        os.makedirs(self.work)
        segments.write(paths.segments_file(self.work), rows)
        self.text = prompt.segments_brief(self.work, "/scratch/seg.tsv")

    def test_only_the_pending_segment_is_asked(self):
        self.assertIn("200", self.text)
        self.assertIn("島語時間", self.text)
        self.assertNotIn("\t0\t", self.text)

    def test_the_frames_to_look_at_are_named(self):
        self.assertIn("00201.png", self.text)
        self.assertIn("00325.png", self.text)

    def test_island_time_asks_which_language_it_teaches(self):
        # 7/14 拉阿魯哇那集ê島語時間教泰雅語，看右上角標誌。
        self.assertIn("島語時間／○○族語", self.text)

    def test_the_answer_columns_are_the_ones_apply_reads(self):
        self.assertIn("起秒<TAB>類型<TAB>單元語別", self.text)
        from scripts.news import segments
        for kind in segments.TYPES:
            self.assertIn(kind, self.text)

    def test_the_red_bar_language_is_not_a_segment_language(self):
        self.assertIn("紅條", self.text)

    def test_no_placeholder_is_left(self):
        self.assertIsNone(re.search(r"\{[a-z_]+\}", self.text))


class TestMainBriefKnowsOffBandCues(unittest.TestCase):
    """讀字ê讀者說明愛講：帶 `area` ê cue 是帶外字幕；紅條族語毋收。"""

    def test_the_brief_says_so(self):
        with open(prompt.BRIEF, encoding="utf-8") as handle:
            text = handle.read()
        self.assertIn("帶外", text)
        self.assertIn("島語時間", text)
        self.assertIn("紅條", text)


if __name__ == "__main__":
    unittest.main()


class TestCeiling(unittest.TestCase):
    """每批上限 120,000，是量出來ê，毋是揀ê。

    2026-09-11，18 輪實讀、3,367 條 cue（usage 照回覆ê `message.id`
    歸併）：尖峰累積 context ≈ 69,184 ＋ 視覺 token ＋ 逐逝數 × 17，
    對平行讀ê六輪誤差 −2.1%～+32.7%。快取失效ê線佇 175k–184k
    （≤175k 失效 0 擺；184k 彼輪失效 3 擺、重寫 166,380 token）。
    上限訂 120,000，估算最壞 +32.7% 嘛才 ~160k，離彼條線猶有空。

    換模型、換 harness、抑是組合圖ê打包規則改，攏愛重量。
    """

    CLIFF = 175000
    WORST = 1.327

    def test_the_measured_constants(self):
        self.assertEqual(prompt.CEILING, 120000)
        self.assertEqual(prompt.BASE, 69184)
        self.assertEqual(prompt.PER_ROW, 17)

    def test_the_worst_underestimate_stays_under_the_cache_cliff(self):
        self.assertLess(prompt.CEILING * self.WORST, self.CLIFF)

    def test_the_old_knobs_are_gone(self):
        # 一批幾張、尾批地板：佮累積 context 無關，莫閣予人調
        self.assertFalse(hasattr(prompt, "SIZE"))
        self.assertFalse(hasattr(prompt, "MIN_TAIL"))


class TestNativeFrameSource(VisionPromptCase):
    """讀者抽原生格ê影片：有封存 mkv 用 mkv，無就愛講按怎抓 mp4。

    mp4 來源ê集數無封存 mkv。1 月 81 批ê讀者攏去 `kithann/out/mkv/`
    揣，揣無就退轉去看 strips，無一个抽會著原生格——025午 規段字幕
    落佇帶跤、歌詞頂逝予帶裁去，攏需要原生格才讀會完整。使用者裁定
    2026-09-15：沒有 mkv 就看 mp4。
    """

    def test_without_an_archive_the_reader_is_told_how_to_fetch_the_mp4(self):
        with mock.patch.object(prompt, "MKV_DIR", "/nonexistent-mkv"):
            text = self.brief(40, 1)
        self.assertIn("sftp.sh get", text)
        self.assertIn(self.REMOTE, text)
        # 暫存也照月份分層
        self.assertIn(os.path.join(prompt.READ_STAGE, "2021-02",
                                   "21NL003_55午間族語新聞.mp4"), text)

    def test_the_fetch_command_uses_the_server_path_as_is(self):
        # remote_of 已經是伺服器絕對路徑；閣加 /docker/ilrdf-corpus 就
        # 變做 /docker/ilrdf-corpus/docker/…，/home/mkv-raw 嘛仝款揣無
        with mock.patch.object(prompt, "MKV_DIR", "/nonexistent-mkv"):
            text = self.brief(40, 1)
        self.assertIn('sftp.sh get "%s"' % self.REMOTE, text)

    def test_the_brief_names_the_stage_folders(self):
        # 讀者照工作說明去找圖：寫 `sheets/`、`strips/` 就找不到
        text = self.brief(40, 1)
        self.assertIn("/4-sheets/", text)
        self.assertIn("4-sheets/sheets.json", text)
        self.assertIn("/2-strips/", text)
        self.assertNotIn("/sheets/`", text)
        self.assertNotIn("/strips/`", text)

    def test_the_work_dir_is_the_month_layered_one(self):
        slug = "2021_055_2021-02-24_午間_Cou_鄒"
        self.assertEqual(prompt.workdir(slug),
                         os.path.join("kithann", "out", "news", "1-ocr",
                                      "2021-02", slug + ".work"))

    def test_with_an_archive_the_mkv_is_used_and_nothing_is_fetched(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        os.makedirs(os.path.join(tmp.name, "2021-02"))
        mkv = os.path.join(tmp.name, "2021-02", self.NAME + ".mkv")
        open(mkv, "wb").close()
        with mock.patch.object(prompt, "MKV_DIR", tmp.name):
            text = self.brief(40, 1)
        self.assertIn(mkv, text)
        self.assertNotIn("sftp.sh get", text)
