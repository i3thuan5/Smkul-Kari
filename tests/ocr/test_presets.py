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

    def test_news_declares_sampling_window_and_slots(self):
        for key, preset in self._news().items():
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
        for key, preset in self._news().items():
            region = preset["region"]
            cols = preset["mask"]["compare_cols"]
            rows = preset["mask"]["compare_rows"]
            self.assertLessEqual(cols[1], region[2], key)
            self.assertLessEqual(rows[1], region[3], key)
            self.assertLess(preset["sheet"]["row_slots"]["split"],
                            region[3], key)
