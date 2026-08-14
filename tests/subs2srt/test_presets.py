"""Preset loading after parameterisation: the engine owns no preset file."""
import json
import os
import tempfile
import unittest

from scripts.news import paths
from scripts.subs2srt import detect


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
