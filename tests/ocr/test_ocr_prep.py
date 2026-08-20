"""Recogniser output clean-up rules."""
import unittest

from scripts.ocr import ocr


class TestCleanText(unittest.TestCase):
    def test_chinese_spaces_are_dropped(self):
        line = {"lang": "chi_tra"}
        self.assertEqual(ocr.clean_text("我 就 請", line), "我就請")

    def test_latin_spaces_are_collapsed_not_dropped(self):
        line = {"lang": "eng"}
        self.assertEqual(ocr.clean_text("Ati  han   ako", line),
                         "Ati han ako")


if __name__ == "__main__":
    unittest.main()
