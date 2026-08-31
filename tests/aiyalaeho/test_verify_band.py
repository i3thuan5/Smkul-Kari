"""verify_band: is this episode's two-row band where the preset says?

Every case below is one of the fifteen episodes actually measured, played
back as numbers so the rules can be exercised without a video. The
measurements are in the module docstring; what matters here is that each
rule has a real file behind it, including the two that first got the
verdict wrong.
"""
import unittest

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


def verdict(score, runs, contrast=FLAT):
    return verify_band.verdict(score, runs, SLOTS, REGION, contrast)


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
        # 083 干焦一逝華語；164 佇取樣彼段干焦量著頂彼逝。
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


if __name__ == "__main__":
    unittest.main()
