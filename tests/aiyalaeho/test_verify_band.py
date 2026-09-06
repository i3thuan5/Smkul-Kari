"""verify_band: is this episode's two-row band where the preset says?

Every case below is one of the fifteen episodes actually measured, played
back as numbers so the rules can be exercised without a video. The
measurements are in the module docstring; what matters here is that each
rule has a real file behind it, including the two that first got the
verdict wrong.
"""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from scripts.aiyalaeho import verify_band
from scripts.errors import PipelineError


# The preset: region y=876..1014, Formosan row 888..948, Chinese 948..1012.
REGION = (0, 876, 1920, 138)
SLOTS = [(888, 948), (948, 1012)]

# 量著ê帶比（16 集）：有帶 2.0–22，無帶 0.8–1.0。
WITH_BAND = 15.0
BAND_LOW = 2.0      # 081：帶頂懸ê攝影棚溫色，分母大起來
NO_BAND = 1.0       # 新聞版型量著 1.0、88 量著 0.8


FLAT = 1.2          # 88／90 量著 1.12 佮 1.35
STRUCTURED = 4.0    # 新聞版型量著 4.04


# 帶崁著佗幾列。規个 region ＝ 37 集彼款；924..1014 是 083——帶頂沿
# 佇 region 第 48 列，族語槽（888..948）ê下跤根本無帶。
WHOLE_BAND = (876, 1014)
LOW_BAND = (924, 1014)


def verdict(score, runs, contrast=FLAT, band=None):
    return verify_band.verdict(score, runs, SLOTS, REGION, contrast, band)


class TestBandPresent(unittest.TestCase):
    def test_the_standard_two_rows_pass(self):
        # 068：906..930 佮 955..979。
        self.assertEqual(verdict(WITH_BAND, [(906, 930), (955, 979)]),
                         ("ok", []))

    def test_a_band_that_has_drifted_down_passes(self):
        # 117：規條帶低十外 px，兩逝猶原佇家己ê槽內。
        self.assertEqual(verdict(WITH_BAND, [(919, 947), (968, 1004)]),
                         ("ok", []))

    def test_the_chinese_row_may_reach_the_foot_of_the_region(self):
        # 094 字腳到 1011——華語槽開闊到 1012 就是為著這款。
        self.assertEqual(verdict(WITH_BAND, [(970, 1011)]), ("ok", []))

    def test_one_row_only_passes(self):
        # 164 佇取樣彼段干焦量著頂彼逝。（083 嘛是一逝，毋過伊ê帶
        # 崁袂著族語槽，予下跤 TestSlotsOnBand 彼條擋落來矣。）
        self.assertEqual(verdict(WITH_BAND, [(953, 977)]), ("ok", []))
        self.assertEqual(verdict(WITH_BAND, [(905, 928)]), ("ok", []))

    def test_a_warm_studio_above_the_band_still_passes(self):
        # 081：兩逝各佇家己ê槽內（904..929、953..990），帶ê比才 2.0
        # ——門檻园 2.5 ê時誤擋著這集。
        self.assertEqual(verdict(BAND_LOW, [(904, 929), (953, 990)]),
                         ("ok", []))

    # 有字幕逝ê形狀ê時，剖面本底就有對比（一逝字就是一个峰），所以
    # 下底這幾條攏傳 STRUCTURED——傳平坦值是合成出來ê、真實袂發生ê組合。
    def test_a_row_outside_every_slot_is_a_mismatch(self):
        state, problems = verdict(WITH_BAND, [(860, 884)], STRUCTURED)
        self.assertEqual(state, "mismatch")
        self.assertIn("860", problems[0])

    def test_two_rows_in_one_slot_is_a_mismatch(self):
        state, problems = verdict(WITH_BAND, [(950, 970), (990, 1010)],
                                  STRUCTURED)
        self.assertEqual(state, "mismatch")
        self.assertIn("仝一个槽", problems[0])

    def test_the_band_colour_does_not_gate_the_verdict(self):
        # 081：帶ê色才 2.0（比無帶ê 1.0 無懸偌濟），毋過兩逝各佇槽內。
        # 色ê數字袂當推翻位置這个主證據。
        self.assertEqual(verdict(NO_BAND, [(904, 929), (953, 990)]),
                         ("ok", []))


class TestNoBand(unittest.TestCase):
    def test_an_episode_with_no_subtitles_is_not_a_failure(self):
        # 88：亮攝影棚，規區平坦——一塊罩牢規區ê ink，無帶。90、98 是
        # 連 ink 都無。照做落去，切出 0 條 cue 就是著ê結果。
        self.assertEqual(verdict(NO_BAND, [(876, 1014)]), ("no-band", []))
        self.assertEqual(verdict(NO_BAND, []), ("no-band", []))

    def test_no_band_but_structured_ink_is_a_mismatch(self):
        # 新聞版型：無這條帶，煞有一塊有對比ê墨水（紅帶佮名牌）。
        state, problems = verdict(NO_BAND, [(876, 1014)], STRUCTURED)
        self.assertEqual(state, "mismatch")
        self.assertTrue(any("對比" in line for line in problems), problems)


class TestContrast(unittest.TestCase):
    def _ink(self, rows):
        return rows

    def test_a_flat_profile_has_no_contrast(self):
        flat = []
        for _row in range(138):
            flat.append(140.0)
        got = verify_band.contrast_of(flat, 876, REGION)
        self.assertLess(got, verify_band.CONTRAST)

    def test_a_block_of_ink_shows_up_as_contrast(self):
        rows = []
        for row in range(138):
            rows.append(407.0 if 80 <= row <= 120 else 70.0)
        got = verify_band.contrast_of(rows, 876, REGION)
        self.assertGreater(got, verify_band.CONTRAST)


class TestRuns(unittest.TestCase):
    def _ink(self, level, *runs):
        ink = []
        for row in range(876, 1014):
            value = 0.0
            for lo, hi in runs:
                if lo <= row < hi:
                    value = level
            ink.append(value)
        return ink

    def test_ink_above_the_floor_is_a_row(self):
        got = verify_band.runs_of(self._ink(300.0, (906, 930)), 876,
                                  876, 1014)
        self.assertEqual(got, [(906, 930)])

    def test_a_quiet_chinese_row_still_counts(self):
        # 華語逝ê ink（83–143）比族語逝（219–453）細真濟。用相對門檻
        # ê時，164 彼逝就恬恬無去矣——所以門檻是絕對ê。
        got = verify_band.runs_of(self._ink(83.0, (953, 977)), 876,
                                  876, 1014)
        self.assertEqual(got, [(953, 977)])

    def test_noise_is_not_a_row(self):
        # 98：peak 37，規集攏是雜訊。
        got = verify_band.runs_of(self._ink(37.0, (949, 968)), 876,
                                  876, 1014)
        self.assertEqual(got, [])

    def test_only_the_rows_the_band_covers_are_looked_at(self):
        # 083：帶對 y≈940 才起，頂懸彼塊 876..924 是亮畫面，毋是字幕。
        ink = self._ink(450.0, (876, 924))
        for row in range(953, 977):
            ink[row - 876] = 143.0
        self.assertEqual(verify_band.runs_of(ink, 876, 940, 1014),
                         [(953, 977)])

    def test_a_gap_of_a_few_rows_inside_one_row_of_text(self):
        got = verify_band.runs_of(self._ink(300.0, (906, 918), (921, 930)),
                                  876, 876, 1014)
        self.assertEqual(got, [(906, 930)])


class TestBandMeasurement(unittest.TestCase):
    def _band(self, inside, outside):
        rows = []
        for row in range(876 - 62, 1014):
            rows.append(inside if row >= 876 else outside)
        return rows

    def test_the_score_is_inside_over_outside(self):
        score = verify_band.band_score(self._band(0.45, 0.03), 814, REGION)
        self.assertGreater(score, verify_band.BAND_SCORE)

    def test_a_featureless_region_scores_about_one(self):
        score = verify_band.band_score(self._band(0.22, 0.25), 814, REGION)
        self.assertLess(score, verify_band.BAND_SCORE)

    def test_the_band_extent_is_where_the_band_is(self):
        rows = []
        for row in range(876 - 62, 1014):
            rows.append(0.9 if row >= 940 else 0.05)
        self.assertEqual(verify_band.band_extent(rows, 814, REGION),
                         (940, 1014))


class TestSlots(unittest.TestCase):
    def test_slots_come_from_the_preset(self):
        preset = {
            "region": list(REGION),
            "lines": [{"name": "formosan", "y": 12, "h": 60},
                      {"name": "han", "y": 72, "h": 64}],
        }
        self.assertEqual(verify_band.slots_of(preset), SLOTS)

    def test_a_single_row_preset_is_not_this_check(self):
        preset = {"region": [0, 722, 1920, 122],
                  "lines": [{"name": "han", "y": 0, "h": 122}]}
        self.assertRaises(PipelineError, verify_band.slots_of, preset)


class TestSlotsOnBand(unittest.TestCase):
    """宣告ê槽下跤愛有帶——083 就是對這个空縫溜過去ê。

    `rows_fit` 干焦問「揣著ê逐逝有囥佇某一个槽內無」。083 彼逝華語
    確實囥佇華語槽內，所以判 ok，紲落去切 cue——毋過族語槽彼 36 列
    根本毋是帶，是畫面。遮罩 88.3% 是白襯衫，換句ê時陣距離才 0.21–0.27，
    一條 cue 就走過四句。

    量著ê兩爿：083 族語槽佮帶重疊 24/60 ＝ 0.40；其餘 37 集帶崁規个
    region，逐个槽攏是 1.00。門檻 0.9 是留予「帶頂沿量差幾列」ê餘裕。
    """

    def test_the_threshold(self):
        self.assertEqual(verify_band.SLOT_ON_BAND, 0.9)

    def test_083_is_refused_even_though_its_row_sits_in_a_slot(self):
        state, problems = verdict(WITH_BAND, [(953, 977)], STRUCTURED,
                                  LOW_BAND)
        self.assertEqual(state, "mismatch")
        self.assertTrue(problems)

    def test_it_names_the_slot_and_the_band(self):
        _state, problems = verdict(WITH_BAND, [(953, 977)], STRUCTURED,
                                   LOW_BAND)
        joined = "\n".join(problems)
        self.assertIn("888", joined)     # 崁袂著ê彼个槽
        self.assertIn("924", joined)     # 帶對佗位起

    def test_a_band_over_the_whole_region_passes(self):
        self.assertEqual(verdict(WITH_BAND, [(905, 928), (953, 990)],
                                 FLAT, WHOLE_BAND),
                         ("ok", []))

    def test_the_low_preset_case_still_passes(self):
        # 087／094：規條帶低 14 px，毋過帶猶原崁規个 region，
        # 用低版 preset ê槽去量，覆蓋率是 1.00。
        self.assertEqual(verdict(WITH_BAND, [(918, 943), (966, 1003)],
                                 FLAT, WHOLE_BAND),
                         ("ok", []))

    def test_omitting_the_band_keeps_every_old_verdict(self):
        # 無傳帶範圍ê時，行為佮進前一模一樣——既有彼十二條靠這點。
        self.assertEqual(verdict(WITH_BAND, [(905, 928), (953, 990)]),
                         ("ok", []))
        self.assertEqual(verdict(NO_BAND, []), ("no-band", []))

    def test_no_band_does_not_run_this_check(self):
        # 無帶ê時 `check` kā範圍囥做規个 region，這條就免問。
        self.assertEqual(verdict(NO_BAND, [], FLAT, WHOLE_BAND),
                         ("no-band", []))


class TestExitCodes(unittest.TestCase):
    """三款判定三个離開碼——批次迴圈干焦看會著這个。

    進前 no-band 佮 ok 攏回 0，迴圈就照切落去：088 ê亮攝影棚予
    `band_probe` 一直觸發，切出 311 條布料紋理ê cue。
    """

    def _run(self, state, problems=()):
        report = {"score": 15.0, "band": (876, 1014), "runs": [],
                  "slots": SLOTS, "frames": 240, "contrast": 1.2}
        with mock.patch.object(verify_band, "check",
                               return_value=(state, list(problems), report)):
            return verify_band.main(["v.mp4", "--quiet"])

    def test_ok_is_zero(self):
        self.assertEqual(self._run("ok"), 0)

    def test_mismatch_is_one(self):
        self.assertEqual(self._run("mismatch", ["槽下跤無帶"]), 1)

    def test_no_band_is_two(self):
        self.assertEqual(self._run("no-band"), 2)

    def test_the_three_are_distinguishable(self):
        got = [self._run("ok"), self._run("mismatch"), self._run("no-band")]
        self.assertEqual(len(set(got)), 3)


class TestBandJsonOutput(unittest.TestCase):
    """量著ê物件寫落工作目錄，予 `cues --band-rows` 讀。"""

    def _write(self, state="ok", problems=()):
        tmp = tempfile.mkdtemp(prefix="aiya-bandjson-")
        self.addCleanup(shutil.rmtree, tmp, True)
        path = os.path.join(tmp, "band.json")
        report = {"score": 15.0, "band": (924, 1014), "runs": [(953, 977)],
                  "slots": SLOTS, "frames": 240, "contrast": 1.2}
        with mock.patch.object(verify_band, "check",
                               return_value=(state, list(problems), report)):
            verify_band.main(["v.mp4", "--quiet", "--band-json", path])
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)

    def test_it_records_the_measured_rows(self):
        self.assertEqual(self._write()["band"], [924, 1014])

    def test_it_records_the_verdict(self):
        self.assertEqual(self._write()["state"], "ok")

    def test_it_records_the_problems_for_a_mismatch(self):
        got = self._write("mismatch", ["槽 888..948 下跤無帶"])
        self.assertEqual(got["state"], "mismatch")
        self.assertEqual(got["problems"], ["槽 888..948 下跤無帶"])

    def test_it_is_written_even_when_the_verdict_is_bad(self):
        # 判毋著ê時陣嘛愛留紀錄：批次就是欲提彼逝問題去寫理由欄。
        self.assertIn("band", self._write("no-band"))

    def test_it_is_readable(self):
        # `Kari-SRT/` 以外ê嘛照規矩：人拍開愛看有。
        tmp = tempfile.mkdtemp(prefix="aiya-bandjson-")
        self.addCleanup(shutil.rmtree, tmp, True)
        path = os.path.join(tmp, "band.json")
        report = {"score": 15.0, "band": (924, 1014), "runs": [],
                  "slots": SLOTS, "frames": 240, "contrast": 1.2}
        with mock.patch.object(verify_band, "check",
                               return_value=("ok", [], report)):
            verify_band.main(["v.mp4", "--quiet", "--band-json", path])
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        self.assertIn("\n", text)


if __name__ == "__main__":
    unittest.main()
