"""build_inventory: filename parsing, the 1100 date-prefix trap, srt_name."""
import os
import tempfile
import unittest
from unittest import mock

from scripts.news import build_inventory


class TestSlotParsing(unittest.TestCase):
    def test_episode_and_slot_come_from_the_chinese_word(self):
        match = build_inventory.SLOT_RE.search("20NL003_32午間族語新聞.mxf")
        self.assertEqual(match.group(1), "32")
        self.assertEqual(match.group(2), "午間")

    def test_nl_code_is_not_what_decides_the_slot(self):
        # 21NL004_37午間: the NL004 code is the 晚間 code, but the file is
        # 午間 -- the regex reads the Chinese word, not the code
        match = build_inventory.SLOT_RE.search("21NL004_37午間族語新聞.mxf")
        self.assertEqual(match.group(2), "午間")

    def test_unparseable_name_yields_no_match(self):
        self.assertIsNone(build_inventory.SLOT_RE.search("readme.mxf"))


class TestNames(unittest.TestCase):
    ROW = {
        "年度": "2021",
        "播出日期": "2021-02-01",
        "播出時段": "午間",
        "族語別(英)": "Atayal",
        "族語別(中)": "泰雅",
    }

    def test_srt_name_format(self):
        self.assertEqual(build_inventory.srt_name(self.ROW, "32"),
                         "20210201_032_午間_Atayal_泰雅")

    def test_episode_is_zero_padded_to_sort_in_broadcast_order(self):
        self.assertIn("_005_", build_inventory.srt_name(dict(self.ROW), "5"))

    def test_slug_keeps_the_dashed_date(self):
        self.assertEqual(build_inventory.slugify(self.ROW, "32"),
                         "2021_032_2021-02-01_午間_Atayal_泰雅")


class TestFindTranscript(unittest.TestCase):
    """Folder names start with a ROC date that itself begins with `1100`,
    which is also the 午間 broadcast-time stamp. The time must be looked
    for after the date, or every folder matches every 午間 episode."""

    def _corpus(self, folders):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = os.path.join(tmp.name, "110年2月_族語新聞文稿")
        os.makedirs(root)
        for name in folders:
            os.makedirs(os.path.join(root, name))
        return tmp.name

    FOLDERS = ["1100201 1100原視新聞泰雅", "1100202 1100原視新聞賽夏"]

    def test_date_prefix_1100_does_not_read_as_broadcast_time(self):
        corpus = self._corpus(self.FOLDERS)
        with mock.patch.object(build_inventory, "CORPUS", corpus):
            path, warning = build_inventory.find_transcript(
                "1100201", "午間", "泰雅")
        # exactly one hit: had `1100` matched inside the date, both folders
        # would hit and this would come back as a 多個文稿符合 warning
        self.assertEqual(path, os.path.join("110年2月_族語新聞文稿",
                                            self.FOLDERS[0]))
        self.assertEqual(warning, "")

    def test_wrong_slot_finds_nothing(self):
        corpus = self._corpus(self.FOLDERS)
        with mock.patch.object(build_inventory, "CORPUS", corpus):
            path, warning = build_inventory.find_transcript(
                "1100201", "晚間", "泰雅")
        self.assertEqual(path, "")

    def test_language_mismatch_is_warned_not_dropped(self):
        corpus = self._corpus(self.FOLDERS)
        with mock.patch.object(build_inventory, "CORPUS", corpus):
            path, warning = build_inventory.find_transcript(
                "1100201", "午間", "賽夏")
        self.assertTrue(path)
        self.assertIn("語言", warning)


if __name__ == "__main__":
    unittest.main()
