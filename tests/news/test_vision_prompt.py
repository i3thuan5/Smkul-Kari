"""vision_tools.prompt: 一批ê範圍佮 TSV 名，愛佮 `ingest` 講ê仝款。

提示是產ê毋是手寫ê，所以「範圍算毋著」無人會發現——TSV 寫出來
逝數對、欄數對，干焦內容囥毋著位。遮ê測試是彼枝把關。
"""
import json
import os
import tempfile
import unittest
from unittest import mock

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
        """232 張是 72×3＋16；16 張ê尾批傷細，倂入前一批變 88 張。"""
        text = self.brief(232, 3, size=72)
        self.assertIn("`sheet_145.png`–`sheet_232.png`", text)
        self.assertIn("cue 577..928", text)
        self.assertIn("352 逝", text)

    def test_batch_past_the_end_is_an_error(self):
        with self.assertRaises(PipelineError):
            self.brief(232, 4, size=72)

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
        self.assertEqual(prompt.plan(294, 72), [(0, 72), (72, 144),
                                                (144, 216), (216, 294)])

    def test_tail_long_enough_stays_on_its_own(self):
        self.assertEqual(prompt.plan(120, 72), [(0, 72), (72, 120)])

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
    def test_slug_not_in_inventory_is_an_error(self):
        inv = {"episodes": [{"slug": "別集", "srt_name": "別名"}]}
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        os.makedirs(os.path.join(tmp.name, "news"))
        with open(os.path.join(tmp.name, "news", "inventory.json"), "w",
                  encoding="utf-8") as handle:
            json.dump(inv, handle)
        with mock.patch.object(prompt.paths, "KARI", tmp.name):
            with self.assertRaises(PipelineError):
                prompt.episode("揣無這集")


if __name__ == "__main__":
    unittest.main()
