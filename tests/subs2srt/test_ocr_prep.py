"""Recogniser output clean-up rules."""
import unittest

from scripts.subs2srt import cli as subs2srt


class TestCleanText(unittest.TestCase):
    def test_chinese_spaces_are_dropped(self):
        line = {"lang": "chi_tra"}
        self.assertEqual(subs2srt.clean_text("我 就 請", line), "我就請")

    def test_latin_spaces_are_collapsed_not_dropped(self):
        line = {"lang": "eng"}
        self.assertEqual(subs2srt.clean_text("Ati  han   ako", line),
                         "Ati han ako")


if __name__ == "__main__":
    unittest.main()
