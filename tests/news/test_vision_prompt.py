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
from scripts.news.vision_tools import prompt


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


class VisionPromptCase(unittest.TestCase):
    """逐个 case 家己一个 work dir，內底囥合成ê sheets.json。"""

    NAME = "20210224_055_午間_Cou_鄒"

    def work(self, count, per=4):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        with open(os.path.join(tmp.name, "sheets.json"), "w",
                  encoding="utf-8") as handle:
            json.dump(sheets_of(count, per), handle)
        return tmp.name

    def brief(self, count, which, per=4, **kw):
        work = self.work(count, per)
        with mock.patch.object(prompt, "episode", return_value=self.NAME), \
                mock.patch.object(prompt, "workdir", return_value=work):
            return prompt.brief("2021_055_2021-02-24_午間_Cou_鄒", which, **kw)


class TestRange(VisionPromptCase):
    def test_first_batch_takes_the_first_size_sheets(self):
        text = self.brief(232, 1, size=72)
        self.assertIn("`sheet_001.png`–`sheet_072.png`", text)
        self.assertIn("cue 1..288", text)

    def test_second_batch_starts_where_the_first_stopped(self):
        text = self.brief(232, 2, size=72)
        self.assertIn("`sheet_073.png`–`sheet_144.png`", text)
        self.assertIn("cue 289..576", text)

    def test_last_batch_stops_at_the_last_sheet(self):
        """232 張是 72×3＋16。

        `MIN_TAIL` 對 24 降做 8 了後（2026-09-09，批次大小改 24 順紲改ê），
        16 張ê尾批**無夠細**，家己徛做一批矣。`MIN_TAIL` 是模組常數毋是
        參數，所以連 `size=72` 這款寫死ê案例嘛綴leh變——本底掠做「傳
        size=72 ê測試袂振動」，是掠毋著。
        """
        text = self.brief(232, 3, size=72)
        self.assertIn("`sheet_145.png`–`sheet_216.png`", text)
        self.assertIn("cue 577..864", text)

    def test_a_tail_shorter_than_the_floor_is_still_folded(self):
        """尾批若真正細（`MIN_TAIL` 以下）猶原倂入前一批。

        每一个讀者攏有固定開銷（~19k token），閣派一个讀者去讀彼幾
        張並無較俗。地板對 8 落到 2（2026-09-09，批次改 4 張順紲改ê）
        了後，這條ê尾巴愛跟leh縮：本底 220 張（尾 4 張）已經**倂
        袂著**矣，愛用 217 張（尾 1 張）才閣試著這條路。`MIN_TAIL`
        是模組常數毋是參數，所以連 `size=72` 這款寫死ê案例嘛綴leh變。
        """
        text = self.brief(217, 3, size=72)
        self.assertIn("`sheet_145.png`–`sheet_217.png`", text)

    def test_batch_past_the_end_is_an_error(self):
        with self.assertRaises(PipelineError):
            self.brief(232, 5, size=72)

    def test_line_count_is_cues_not_sheets(self):
        """逐張 4 條ê時 72 張是 288 逝——講「72 逝」讀者就寫了了無夠。"""
        text = self.brief(232, 1, size=72)
        self.assertIn("288 逝", text)
        self.assertNotIn("72 逝", text)


class TestPlan(unittest.TestCase):
    """尾批莫留細个：固定成本佮批ê大細無關，6 張ê尾批逐張開 4.2 倍。"""

    def test_exact_multiple_is_left_alone(self):
        self.assertEqual(prompt.plan(216, 72), [(0, 72), (72, 144),
                                                (144, 216)])

    def test_short_tail_is_folded_into_the_batch_before_it(self):
        """289 = 72×4＋1，尾 1 張佇地板（2）以下，倂入去。

        本底遮寫 294（尾 6 張），彼是地板猶原是 8 ê時ê數字；地板落
        到 2 了後 6 張家己徛做一批矣。
        """
        self.assertEqual(prompt.plan(289, 72), [(0, 72), (72, 144),
                                                (144, 216), (216, 289)])

    def test_a_tail_at_the_floor_stands_on_its_own(self):
        """拄仔好 `MIN_TAIL` 張ê尾**無**倂——地板是「以下」才倂。

        地板對 2 起做 8 了後（2026-09-11），這條ê數字愛綴leh換：
        296 ＝ 72×4＋8，尾拄仔好 8 張。
        """
        self.assertEqual(prompt.plan(296, 72), [(0, 72), (72, 144),
                                                (144, 216), (216, 288),
                                                (288, 296)])

    def test_a_tail_between_the_old_floor_and_the_new_one_is_folded(self):
        """地板對 2 起做 8：尾 4 張本底家己徛，這馬愛倂入去。

        `MIN_TAIL` 是模組常數，這條就是咧釘伊實際ê值——若有人kā地板
        改轉去 2，這條會紅。一个讀者ê固定開銷實測是 $1.43（依 18 輪
        transcript 精算），派一个讀者去讀 4 張（開會了約 56 條）ê時，
        彼 $1.43 攤落去就是每 cue $0.026，比倂入前一批貴四倍。
        """
        self.assertEqual(prompt.plan(292, 72), [(0, 72), (72, 144),
                                                (144, 216), (216, 292)])

    def test_tail_long_enough_stays_on_its_own(self):
        self.assertEqual(prompt.plan(120, 72), [(0, 72), (72, 120)])

    def test_a_size_below_one_is_an_error_not_a_hang(self):
        """`lo += size` 若無行進前，彼个迴圈永遠袂煞。

        `batches --size -1` 行會到遮：argparse 收負數收甲真歡喜，
        `size or SIZE` 看 -1 是真ê就放伊過。**症頭是規支恬恬卡牢**，
        無輸出、無錯誤，看起來親像咧做工。
        """
        for bad in (0, -1):
            with self.assertRaises(PipelineError):
                prompt.plan(10, bad)

    def test_shorter_than_one_batch_is_one_batch(self):
        self.assertEqual(prompt.plan(20, 72), [(0, 20)])

    def test_fold_never_leaves_a_gap_or_an_overlap(self):
        for total in range(1, 400):
            spans = prompt.plan(total, 72)
            self.assertEqual(spans[0][0], 0)
            self.assertEqual(spans[-1][1], total)
            for before, after in zip(spans, spans[1:]):
                self.assertEqual(before[1], after[0])


class TestScratch(VisionPromptCase):
    """Scratchpad 是逐支 agent 公家ê，checkpoint ê路徑愛家己一份。"""

    def test_scratch_path_names_the_episode_and_the_batch(self):
        text = self.brief(232, 2, size=72)
        self.assertIn(self.NAME + "-b02", text)

    def test_two_batches_of_one_episode_do_not_share_it(self):
        one = self.brief(232, 1, size=72)
        two = self.brief(232, 2, size=72)
        self.assertNotIn(self.NAME + "-b01", two)
        self.assertNotIn(self.NAME + "-b02", one)

    def test_empty_env_var_falls_back_to_the_default(self):
        """空字串是「設了無值」，`os.environ.get` 掠做設矣，
        `os.path.join("", x)` 就吐一个相對路徑出來。"""
        with mock.patch.dict(os.environ, {"CLAUDE_SCRATCH": ""}):
            got = blank_reload().SCRATCH
        self.assertTrue(got.startswith("/"), got)

    def test_placeholder_is_filled_in(self):
        self.assertNotIn("{scratch}", self.brief(232, 1, size=72))

    def test_no_placeholder_is_left_behind(self):
        """`brief.md` 內底逐个 `{…}` 攏愛hőng換掉，一个都莫賰。

        賰落來ê `{sheets}` 這款物件袂報錯，是**直接印佇讀者面頭前**
        ê一句死字。逐擺佇 brief.md 加新ê鍵，`_brief` ê `fill` 若無
        綴leh加就是按呢。所以莫干焦顧一个鍵，規包掠。
        """
        text = self.brief(232, 1, size=72)
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
        with open(os.path.join(tmp.name, "sheets.json"), "w",
                  encoding="utf-8") as handle:
            json.dump(book, handle)
        return tmp.name

    def brief_named(self, names, which, **kw):
        work = self.work_named(names)
        with mock.patch.object(prompt, "episode", return_value=self.NAME), \
                mock.patch.object(prompt, "workdir", return_value=work):
            return prompt.brief("2021_055_2021-02-24_午間_Cou_鄒", which, **kw)

    NAMES = ["t00015200.png", "t00022200.png", "t00023600.png"]

    def test_a_name_without_an_underscore_does_not_crash(self):
        text = self.brief_named(self.NAMES, 1, size=8)
        self.assertIn("t00015200.png", text)

    def test_the_first_and_last_sheet_are_named_in_full(self):
        text = self.brief_named(self.NAMES, 1, size=8)
        self.assertIn("`t00015200.png`–`t00023600.png`", text)

    def test_the_timeline_named_is_the_one_that_exists(self):
        """時間軸ê路徑愛指著實在有ê彼份，毋是 `<work>/cues.json`。

        時間軸分做 `1-cues/`（粗切）佮 `2-refined/`（精修）了後，
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
            text = prompt.brief("2021_055_2021-02-24_午間_Cou_鄒", 1, size=8)
        self.assertIn("1-cues/cues.json", text)
        self.assertNotIn("%s/cues.json" % work, text)

    def test_a_refined_timeline_wins_over_the_coarse_one(self):
        work = self.work_named(self.NAMES)
        for stage in ("1-cues", "2-refined"):
            os.makedirs(os.path.join(work, stage))
            with open(os.path.join(work, stage, "cues.json"), "w",
                      encoding="utf-8") as handle:
                json.dump({"cues": []}, handle)
        with mock.patch.object(prompt, "episode", return_value=self.NAME), \
                mock.patch.object(prompt, "workdir", return_value=work):
            text = prompt.brief("2021_055_2021-02-24_午間_Cou_鄒", 1, size=8)
        self.assertIn("2-refined/cues.json", text)

    def test_no_placeholder_is_left_behind_either(self):
        text = self.brief_named(self.NAMES, 1, size=8)
        left = re.findall(r"\{[a-z_]+\}", text)
        self.assertEqual(left, [], "brief.md 有無換ê鍵：%s" % left)


class TestTsvName(VisionPromptCase):
    def test_default_name_follows_the_batch_number(self):
        text = self.brief(232, 3, size=72)
        self.assertIn("b03.tsv", text)

    def test_override_is_used_instead(self):
        """一集若換過批次大小，照 `which` 算ê名會佮已經寫好ê撞號。"""
        text = self.brief(232, 1, size=72, tsv="b07.tsv")
        self.assertIn("b07.tsv", text)
        self.assertNotIn("b01.tsv", text)

    def test_override_does_not_swallow_the_episode_name(self):
        """本底這个參數號做 `name`，去hőng `name = episode(slug)` 蓋去，
        TSV 就變做集數名。"""
        text = self.brief(232, 1, size=72, tsv="b07.tsv")
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
        self.assertIn("`sheet_003.png`–`sheet_004.png`", text)

    def test_a_partial_sheet_is_still_included(self):
        """Cue 10 佇 sheet_003 中央——彼張愛入來，讀者才看會著。"""
        text = self.brief_for(20, 10, 15)
        self.assertIn("`sheet_003.png`–`sheet_004.png`", text)

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
        text = self.brief(24, 1, per=3, size=8)
        self.assertIn("逐張 3 條", text)
        self.assertNotIn("逐張 4 條", text)

    def test_four_per_sheet_is_still_four(self):
        text = self.brief(24, 1, per=4, size=8)
        self.assertIn("逐張 4 條", text)

    def test_a_ragged_last_sheet_is_said_as_at_most(self):
        """尾張較少ê時，講「上濟幾條」較誠實。"""
        work = self.work(3, 4)
        import json
        with open(os.path.join(work, "sheets.json"), encoding="utf-8") as fh:
            data = json.load(fh)
        data["sheet_003.png"] = [9, 10]
        with open(os.path.join(work, "sheets.json"), "w",
                  encoding="utf-8") as fh:
            json.dump(data, fh)
        with mock.patch.object(prompt, "episode", return_value=self.NAME), \
                mock.patch.object(prompt, "workdir", return_value=work):
            text = prompt.brief("2021_055_2021-02-24_午間_Cou_鄒", 1, size=8)
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


if __name__ == "__main__":
    unittest.main()


class TestBatchSizeDefaults(unittest.TestCase):
    """一批 24 張，尾批地板 8。

    **這組數字翻過兩擺，兩擺攏是量出來ê，紲落來寫ê是兩擺ê理路。**

    **頭一擺（2026-09-10，24 → 4）**：組合圖ê打包改了後（`LONG_EDGE`
    壓 2000、逐張各自算闊），新聞一張對 4 條 cue 變做 ~25 條。`SIZE`
    若無綴leh改，24 張 × 25 條 ＝ 600 條／批，是本底 96 條ê六倍。彼
    時量ê三个點（逐點攏是 Opus、真正讀、費用照 `message.id` 歸併）：

        cue 數   張數   回覆數   尖峰 context   每 cue
           56     4      28       66,121      $0.0236
           98     7      34       86,042      $0.0196
          196    14     102      145,474      $0.0327

    56–98 平、196 翹起來，所以搝轉去 4 張（~100 條）。**彼時是著ê。**

    **第二擺（2026-09-11，4 → 24）**：`brief.md` 加一條「開圖愛佇仝
    一則訊息內底同時發 3–4 个 Read」了後，頭前彼條曲線就無效矣——
    彼時貴ê是**回覆數**，一則讀一張ê時回覆數綴張數超線性大；平行讀
    了後回覆數變做差不多是定數（14 張 12 則、28 張 18 則），成本
    變做近倍線性。仝一批圖、仝一份判準，干焦改讀法：

        14 張／196 條：一則一張 102 則回覆 $6.40；平行讀 12 則 $1.87

    平行讀了後重量ê三个點：

        cue 數   張數   回覆數   尖峰 context   每 cue
          196    14      12      115,106      $0.0095
          392    28      18      157,721      $0.0059   ← 上俗
          560    40      26      183,672      $0.0067

    **底部對 98 條徙到 392 條。** 而且 560 彼點翹起來ê原因掠著矣：
    transcript ê `diagnostics.cache_miss_reason` 講是 `messages_changed`
    ——**快取hőng作廢、規段 context 用 $6.25/M 重寫**，彼輪重寫
    166,380 token（＝$1.04，佔彼批 $3.75 ê四分之一）。175k 彼幾輪
    失效 0 擺，184k 彼輪失效 3 擺。**所以上限是「快取懸崖」，毋是
    視窗**：18 輪 transcript 內底壓縮 0 擺、圖hőng提掉 0 擺。

    24 張ê尖峰實測（照檔名順序切）是 121k／130k／143k，離懸崖猶有
    三十外 k。整集：開會了 111（977 條）18 批 $27.93 → 3 批 $6.48。

    `MIN_TAIL` 愛綴 `SIZE` 走：8 張（新聞約 200 條）徛會住，4 張
    （~100 條）攤彼份 $1.43 ê起手費就貴四倍，倂入去較俗。

    **《開會了》莫用這个數字。** 彼爿一張 ~14 條，24 張ê尖峰實測是
    175k，拄仔好貼佇懸崖頂懸；而且彼爿ê族語列有撇號ê字形問題
    （`'` hőng寫做 `"`，三个讀者內底一个會犯）。彼爿走ê是別一份 brief。
    """

    NEWS_PER_SHEET = 25       # 新聞一張約幾條 cue（壓 2000 了後）
    NEWS_SHEET_TOKENS = 1900  # 新聞一張約幾个視覺 token（實測中位 1,890）
    BASE = 69184              # 固定底（提示、工具、累積ê推理文字）
    PER_ROW = 17              # 逐逝 TSV 佇 context 內底ê重量
    CLIFF = 175000            # 快取開始失效彼條線

    def test_the_default_batch_is_twenty_four_sheets(self):
        self.assertEqual(prompt.SIZE, 24)

    def test_the_tail_floor_scales_with_it(self):
        self.assertEqual(prompt.MIN_TAIL, 8)
        self.assertLess(prompt.MIN_TAIL, prompt.SIZE)

    def test_a_news_batch_stays_under_the_cache_cliff(self):
        """真正ê上限是快取失效，毋是 cue 數。

        懸過彼條線ê症頭是**恬恬加錢**：無錯誤、無警告，干焦 cache
        寫入翻倍。184k 彼輪重寫 166,380 token。
        """
        rows = prompt.SIZE * self.NEWS_PER_SHEET
        peak = (self.BASE + prompt.SIZE * self.NEWS_SHEET_TOKENS
                + rows * self.PER_ROW)
        self.assertLess(peak, self.CLIFF)

    def test_an_eight_sheet_tail_stands_on_its_own(self):
        """8 張（新聞約 200 條）徛會住，莫倂入去。"""
        self.assertEqual(prompt.plan(32), [(0, 24), (24, 32)])

    def test_a_four_sheet_tail_is_folded(self):
        """4 張（~100 條）攤彼份 $1.43 起手費貴四倍，倂入去較俗。"""
        self.assertEqual(prompt.plan(28), [(0, 28)])

    def test_fifty_one_sheets_is_three_batches(self):
        """058晨 壓 2000 了後ê實際張數：51 張，24＋24＋3，尾 3 張倂入。"""
        self.assertEqual(prompt.plan(51), [(0, 24), (24, 51)])
