"""normalise(): what counts as matchable evidence."""
import unittest

from scripts.news import align


class TestNormalise(unittest.TestCase):
    def test_punctuation_is_dropped(self):
        # the subtitler re-punctuates freely and tesseract invents marks
        self.assertEqual(align.normalise("大火，燒了！「三天」"),
                         "大火燒了三天")

    def test_latin_and_digits_survive(self):
        self.assertEqual(align.normalise("4000多種plants"), "4000多種plants")

    def test_whitespace_is_dropped(self):
        self.assertEqual(align.normalise("我 就 請"), "我就請")

    def test_empty_input(self):
        self.assertEqual(align.normalise(""), "")


if __name__ == "__main__":
    unittest.main()
