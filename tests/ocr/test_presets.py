"""Preset loading after parameterisation: the engine owns no preset file."""
import json
import os
import tempfile
import unittest

from scripts.news import paths
from scripts.ocr import band as detect
from scripts.ocr import cuelib


class TestLoadPresets(unittest.TestCase):
    def test_no_path_means_no_presets(self):
        self.assertEqual(detect.load_presets(None), {})
        self.assertEqual(detect.load_presets(""), {})

    def test_missing_file_means_no_presets(self):
        self.assertEqual(detect.load_presets("/no/such/presets.json"), {})

    def test_engine_package_ships_no_preset_file(self):
        engine_dir = os.path.dirname(detect.__file__)
        self.assertFalse(os.path.exists(os.path.join(engine_dir,
                                                     "presets.json")))


class TestMatchPreset(unittest.TestCase):
    def _presets_file(self, presets):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = os.path.join(tmp.name, "presets.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(presets, handle)
        return path

    def test_substring_match_against_file_name(self):
        path = self._presets_file({"news": {"match": "NL00",
                                            "region": [0, 722, 1920, 122]}})
        key, preset = detect.match_preset("/x/20NL003_32午間.mxf", path)
        self.assertEqual(key, "news")

    def test_no_needle_no_match(self):
        path = self._presets_file({"news": {"region": [0, 0, 1, 1]}})
        key, preset = detect.match_preset("/x/whatever.mp4", path)
        self.assertIsNone(key)
        self.assertIsNone(preset)

    def test_without_a_presets_path_nothing_matches(self):
        key, preset = detect.match_preset("/x/20NL003.mxf", None)
        self.assertIsNone(key)


class TestNewsPresets(unittest.TestCase):
    """The corpus preset file the news pipeline actually ships."""

    def setUp(self):
        self.presets = detect.load_presets(paths.ENGINE_PRESETS)

    def test_titv_news_is_present_and_shaped_right(self):
        self.assertIn("titv-news", self.presets)
        preset = self.presets["titv-news"]
        self.assertEqual(len(preset["region"]), 4)
        # the region must stop above the red lower-third at y=846/848
        self.assertLessEqual(preset["region"][1] + preset["region"][3], 845)

    def test_mxf_batch_still_matches_by_file_name(self):
        key, _ = detect.match_preset("20NL003_32午間族語新聞.mxf",
                                     paths.ENGINE_PRESETS)
        self.assertEqual(key, "titv-news")


class TestLowerEdgeFollowsTheRedBar(unittest.TestCase):
    """字幕帶下緣照紅色標題條ê位置定，毋是逐年共用一个。

    2023 年起紅條上緣佇 y 851／852，偏下字幕ê羅馬字下伸筆畫（g j p q y）
    佮括號到 845–850，844 會切掉 1–5 px；放到 850 就碰著紅條頂懸ê過渡
    列。2021 年紅條上緣佇 846／848，下緣 848 會kā紅條切入字幕帶。
    """

    def setUp(self):
        with open(paths.ENGINE_PRESETS, encoding="utf-8") as handle:
            self.presets = json.load(handle)

    def test_the_2021_layout_stays_at_844(self):
        region = self.presets["titv-news"]["region"]
        self.assertEqual(region[1] + region[3], 844)

    def test_the_848_layout_is_the_same_but_four_rows_lower(self):
        base = self.presets["titv-news"]
        deep = self.presets["titv-news-848"]
        self.assertEqual(deep["region"], [0, 722, 1920, 126])
        for key in ("mask", "lines", "sheet"):
            want = json.loads(json.dumps(base[key]))
            got = json.loads(json.dumps(deep[key]))
            if key == "lines":
                want[0]["h"] = 126
            self.assertEqual(got, want, key)

    def test_the_848_layout_is_never_picked_by_file_name(self):
        # 檔名 match 仝款 `NL00` ê話，兩个 preset 搶仝一支檔。
        self.assertNotIn("match", self.presets["titv-news-848"])

    def test_both_declare_straddle_and_the_red_exclusion(self):
        for name in ("titv-news", "titv-news-848"):
            slots = self.presets[name]["sheet"]["row_slots"]
            self.assertGreater(slots["straddle"], 0, name)
            self.assertEqual(slots["exclude"],
                             {"r_min": 20, "gb_max": 25, "r_minus_g": 15},
                             name)

    def test_the_amis_mxf_preset_is_left_alone(self):
        slots = self.presets["amis-titv-news"]["sheet"]["row_slots"]
        self.assertNotIn("straddle", slots)
        self.assertNotIn("exclude", slots)

    def test_the_2024_08_layout_is_centred_above_the_red_bar(self):
        # 2024-08 起：字幕置中、墨水平台 y 860–925；y 932 一條白細邊，
        # 938 起紅條（紅條內ê族語標題 950–1005）。
        preset = self.presets["titv-news-2024-08"]
        top, height = preset["region"][1], preset["region"][3]
        self.assertLessEqual(top, 850)
        self.assertGreaterEqual(top + height, 926)
        self.assertLessEqual(top + height, 931)
        self.assertEqual(preset["lines"][0]["h"], height)
        cols = preset["mask"]["compare_cols"]
        self.assertLessEqual(cols[0], 780)
        self.assertGreaterEqual(cols[1], 1320)
        self.assertNotIn("right_anchor", preset["mask"])
        self.assertNotIn("match", preset)

    def test_the_centred_layout_ignores_the_badge_columns_on_the_sheets(self):
        # 「族語」語別牌 x 210–310 佇字幕帶內，墨較濟ê時會搶走欄裁切。
        cols = self.presets["titv-news-2024-08"]["sheet"]["ignore_cols"]
        self.assertLessEqual(cols[0], 200)
        self.assertGreaterEqual(cols[1], 320)
        self.assertLessEqual(cols[1], 560)       # 對白置中，毋通食著
        # 置中字幕對稱裁（白底頂懸ê頭一字遮罩掠無，cue 450「三叉坑」）。
        # 中線毋是畫面ê 960：字幕置中佇語別牌正爿彼塊，三集量著墨ê
        # 中點中位數 1069–1074。用 960 ê話逐條攏向倒爿加裁 ~220 px，
        # 組合圖闊五成；揀較細ê 1064，中線估偏嘛是加裁，毋是切字。
        centre = self.presets["titv-news-2024-08"]["sheet"]["centre"]
        self.assertGreaterEqual(centre, 1055)
        self.assertLessEqual(centre, 1069)

    def test_the_centred_layout_says_where_its_box_and_badge_are(self):
        layout = self.presets["titv-news-2024-08"]["shots"]
        self.assertEqual(layout["red_rule"], {"r_minus_g": 40,
                                              "r_minus_b": 40})
        self.assertEqual(layout["name_rule"],
                         {"r_min": 20, "gb_max": 25, "r_minus_g": 15})
        # 半透明、會換內容，分袂出在毋在：關掉（test_shot_features）
        self.assertIs(layout["box"], False)
        self.assertIs(layout["badge"], False)

    def test_each_band_preset_says_where_its_red_bar_is(self):
        # 紅條位置綴版型：舊版型 y 852–912，2024-08 起 938–1010。shots
        # 若用舊ê，新版型量著ê是字幕，主播段一段都揣袂著。
        want = {"titv-news-848": [852, 912], "titv-news": [852, 912],
                "titv-news-2024-08": [938, 1010]}
        for name, rows in want.items():
            self.assertEqual(self.presets[name]["shots"]["red_rows"], rows,
                             name)

    def test_every_month_has_exactly_one_band_preset(self):
        for year in range(2021, 2025):
            for month in range(1, 13):
                key = "%d-%02d" % (year, month)
                owners = []
                for name, preset in self.presets.items():
                    span = preset.get("months")
                    if span and span[0] <= key <= span[1]:
                        owners.append(name)
                self.assertEqual(len(owners), 1, (key, owners))


class TestOffBandAreas(unittest.TestCase):
    """帶外段落（段落表標ê）重切用ê區域。

    實測：島語時間對白置中 y≈960–1050、x≈620–1300；部落信箱旁白
    y 913–967、詩句 y 608–703、三行版第三行 y 712–752；開場蒙太奇斜體
    y≈705–838，左右無一定；2021 帶外專題 y≈950–1002（`rescan_band` 用
    y 910 起 122 列重切過六集）。
    """

    def setUp(self):
        with open(paths.ENGINE_PRESETS, encoding="utf-8") as handle:
            self.presets = json.load(handle)

    def rows(self, name):
        region = self.presets[name]["region"]
        return region[1], region[1] + region[3]

    def cols(self, name):
        preset = self.presets[name]
        region = preset["region"]
        cols = preset["mask"].get("compare_cols") or (0, region[2])
        return region[0] + cols[0], region[0] + cols[1]

    def test_island_time_is_matched_in_the_middle(self):
        # 置右比對遮罩（1250–1790）看袂著置中ê對白。
        lo, hi = self.cols("titv-news-island")
        self.assertLessEqual(lo, 620)
        self.assertGreaterEqual(hi, 1300)
        top, bottom = self.rows("titv-news-island")
        self.assertLessEqual(top, 950)
        self.assertGreaterEqual(bottom, 1055)

    def test_the_2021_feature_packages_are_matched_in_the_middle(self):
        lo, hi = self.cols("titv-news-offband")
        self.assertLessEqual(lo, 620)
        self.assertGreaterEqual(hi, 1300)
        top, bottom = self.rows("titv-news-offband")
        self.assertLessEqual(top, 940)
        self.assertGreaterEqual(bottom, 1010)

    def test_the_feature_region_starts_right_after_the_weather_box(self):
        # 2021 左下角ê天氣框（晚間）佮「午間新聞」框，右緣攏佇 x 391
        # （18 集判斷格 144 格量著 143 格 391）；框內溫度白字會輪播，
        # 框入去就切出假 cue。本底從 420 起，20210719_200 午間 cue 340
        # 「他是來新竹…」ê頭一字黑邊佇 x 414，予人切一屑仔（使用者
        # 2026-09-24 看圖講「線還是有切到」）。
        for name in ("titv-news-offband", "titv-news-offband-high"):
            left, _top, width, _h = self.presets[name]["region"]
            self.assertGreaterEqual(left, 392, name)
            self.assertLessEqual(left, 412, name)
            self.assertEqual(left + width, 1920, name)

    def test_the_two_line_drama_fits_the_high_variant(self):
        # 20210301_060 晚間ê族語戲劇：族語一逝 y 878–935、華語一逝
        # 939–989，置中。`titv-news-offband`（910 起）會切掉族語彼逝。
        top, bottom = self.rows("titv-news-offband-high")
        self.assertLessEqual(top, 870)
        self.assertGreaterEqual(bottom, 990)
        lo, hi = self.cols("titv-news-offband-high")
        self.assertLessEqual(lo, 620)
        self.assertGreaterEqual(hi, 1300)

    def test_the_mailbox_takes_the_third_line_across_the_band_top(self):
        top, bottom = self.rows("titv-news-mailbox")
        self.assertLessEqual(top, 600)
        self.assertGreaterEqual(bottom, 980)

    def test_the_montage_is_wide(self):
        top, bottom = self.rows("titv-news-montage")
        self.assertLessEqual(top, 690)
        self.assertGreaterEqual(bottom, 880)
        self.assertEqual(self.cols("titv-news-montage"), (0, 1920))

    def test_off_band_areas_do_not_anchor_right(self):
        # 置中抑是左右無一定：right_anchor 會kā右爿ê雜訊加入圖條。
        for name in ("titv-news-island", "titv-news-offband",
                     "titv-news-offband-high",
                     "titv-news-mailbox", "titv-news-montage"):
            self.assertNotIn("right_anchor", self.presets[name]["mask"], name)
            self.assertNotIn("match", self.presets[name], name)
            self.assertNotIn("months", self.presets[name], name)

    def test_the_line_height_is_the_region_height(self):
        for name in ("titv-news-island", "titv-news-offband",
                     "titv-news-mailbox", "titv-news-montage"):
            preset = self.presets[name]
            self.assertEqual(preset["lines"][0]["h"], preset["region"][3],
                             name)

    def test_segment_recut_names_only_presets_that_exist(self):
        from scripts.news import segment_recut
        for name in segment_recut.AREA_PRESETS.values():
            self.assertIn(name, self.presets)


if __name__ == "__main__":
    unittest.main()


class TestSegmentOptionsComeFromThePreset(unittest.TestCase):
    """Sampling and the compare window are declared, not stored.

    Ruled 2026-09-09: the timeline gains no new keys. `MaskSpec.from_dict`
    therefore ignores these three, and the caller has to lift them off the
    preset itself. If that lifting is ever dropped, cutting silently falls
    back to full-resolution, whole-band comparison -- the timeline still
    looks fine, it just costs 16x more and splits one sentence into several
    cues again.
    """

    def test_from_dict_does_not_carry_them(self):
        spec = cuelib.MaskSpec.from_dict(
            {"outline": False, "scale": 2, "compare_cols": [1250, 1790]})
        self.assertFalse(spec.outline)
        self.assertEqual(spec.scale, 1)
        self.assertIsNone(spec.compare_cols)

    def test_cli_lifts_them_off_the_preset(self):
        preset = {"region": [0, 722, 1920, 122],
                  "mask": {"outline": True, "scale": 2,
                           "compare_cols": [1250, 1790],
                           "compare_rows": [4, 114]}}
        spec = cuelib.segment_spec(preset)
        self.assertEqual(spec.scale, 2)
        self.assertEqual(tuple(spec.compare_cols), (1250, 1790))
        self.assertEqual(tuple(spec.compare_rows), (4, 114))

    def test_a_preset_without_them_keeps_todays_behaviour(self):
        spec = cuelib.segment_spec(
            {"region": [0, 876, 1920, 138], "mask": {"outline": False}})
        self.assertEqual(spec.scale, 1)
        self.assertIsNone(spec.compare_cols)
        self.assertIsNone(spec.compare_rows)


class TestMinInkIsDeclaredWholeBandFullResolution(unittest.TestCase):
    """`--min-ink` keeps meaning "pixels over the whole band, unsampled".

    The number appears in the README, the skill and half a dozen notes as
    120. Rather than change what it means, the code converts it to whatever
    the segmenter is actually looking at. The manifest keeps the declared
    120, so `refine_cues` must apply the very same conversion -- if only one
    of the two does, every frame reads as blank on one side and nothing at
    all comes out.

    The value is not delicate: measured across 12 to 120 the cut was
    effectively unchanged. What matters is that both sides agree.
    """

    def test_unscaled_unwindowed_is_unchanged(self):
        got = cuelib.effective_min_ink(
            120, cuelib.MaskSpec(), [0, 722, 1920, 122])
        self.assertEqual(got, 120)

    def test_half_scale_takes_a_quarter(self):
        got = cuelib.effective_min_ink(
            120, cuelib.MaskSpec(scale=2), [0, 722, 1920, 122])
        self.assertEqual(got, 30)

    def test_window_takes_its_share_of_the_area(self):
        spec = cuelib.MaskSpec(scale=2, compare_cols=(1250, 1790),
                               compare_rows=(4, 114))
        got = cuelib.effective_min_ink(120, spec, [0, 722, 1920, 122])
        # (540*110)/(1920*122)/4 of 120
        self.assertEqual(got, 7)

    def test_never_drops_below_one(self):
        spec = cuelib.MaskSpec(scale=4, compare_cols=(0, 20))
        self.assertGreaterEqual(
            cuelib.effective_min_ink(1, spec, [0, 722, 1920, 122]), 1)


class TestManifestKeysDoNotGrow(unittest.TestCase):
    """Cutting a cue writes the same keys it always did.

    Ruled 2026-09-09. The check is here rather than left to review because
    the failure is invisible: an extra key breaks nothing today, it just
    quietly makes the store carry engine tuning that no reader of the store
    ever uses, and once it is in a thousand files it is not coming out.
    """

    MASK_KEYS = {"white_min", "max_spread", "dark_max", "outline",
                 "outline_size", "thin", "thin_size", "band_probe",
                 "band_rows"}

    def test_mask_block_of_a_windowed_spec_has_only_the_old_keys(self):
        preset = {"region": [0, 722, 1920, 122],
                  "mask": {"outline": True, "scale": 2,
                           "compare_cols": [1250, 1790],
                           "compare_rows": [4, 114]}}
        spec = cuelib.segment_spec(preset)
        self.assertEqual(spec.scale, 2)          # it is in use ...
        self.assertEqual(set(spec.to_dict().keys()),
                         self.MASK_KEYS)         # ... and not in the file


class TestShippedPresetsDeclareTheirLayout(unittest.TestCase):
    """What each corpus actually declares, and what it deliberately does not.

    The 開會了 half is the one worth guarding. Its subtitles sit on an opaque
    gradient bar, so no picture reaches the mask at all and there is nothing
    for a compare window to clean up: measured repeats were 0, 0 and 78
    across three episodes against 268, 70 and 370 for news. Adding one there
    bought nothing on two episodes and cost two swallowed sentences on the
    third, and cropping its strips shaved the apostrophes off the Formosan
    row -- 98.6% down to 76.8%. So the absence is a decision, not an
    oversight, and it is asserted here.
    """

    def _news(self):
        with open(paths.ENGINE_PRESETS, encoding="utf-8") as handle:
            return json.load(handle)

    def _aiyalaeho(self):
        here = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))))
        with open(os.path.join(here, "scripts", "aiyalaeho", "presets.json"),
                  encoding="utf-8") as handle:
            return json.load(handle)

    def _band(self):
        """字幕帶 y 722 起ê彼幾个；帶外區域（島語時間…）另外有規矩。"""
        out = {}
        for key, preset in self._news().items():
            if preset["region"][1] == 722:
                out[key] = preset
        return out

    def test_news_declares_sampling_window_and_slots(self):
        for key, preset in self._band().items():
            spec = cuelib.segment_spec(preset)
            self.assertEqual(spec.scale, 2, key)
            self.assertEqual(tuple(spec.compare_cols), (1250, 1790), key)
            self.assertEqual(tuple(spec.compare_rows), (4, 114), key)
            slots = preset["sheet"]["row_slots"]
            self.assertEqual(slots["split"], 65, key)
            self.assertEqual(slots["min_ratio"], 2.0, key)

    def test_aiyalaeho_samples_but_declares_no_window_and_no_slots(self):
        for key, preset in self._aiyalaeho().items():
            spec = cuelib.segment_spec(preset)
            self.assertEqual(spec.scale, 2, key)
            self.assertIsNone(spec.compare_cols, key)
            self.assertIsNone(spec.compare_rows, key)
            self.assertNotIn("sheet", preset, key)

    def test_the_news_window_sits_inside_the_news_region(self):
        for key, preset in self._band().items():
            region = preset["region"]
            cols = preset["mask"]["compare_cols"]
            rows = preset["mask"]["compare_rows"]
            self.assertLessEqual(cols[1], region[2], key)
            self.assertLessEqual(rows[1], region[3], key)
            self.assertLess(preset["sheet"]["row_slots"]["split"],
                            region[3], key)
