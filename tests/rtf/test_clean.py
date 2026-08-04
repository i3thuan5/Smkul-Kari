"""Cleaning decoded 文稿 text: markup, section marks, and language split."""
import unittest

from scripts.news import rtf


class TestIsCjkLine(unittest.TestCase):
    def test_chinese_line_is_kept(self):
        self.assertTrue(rtf.is_cjk_line("去年底桃園復興巴陵的一場大火"))

    def test_latin_line_is_dropped(self):
        # the indigenous-language rendering of the same story
        self.assertFalse(rtf.is_cjk_line("Ati han ako ko singsi"))

    def test_digits_only_line_is_dropped(self):
        self.assertFalse(rtf.is_cjk_line("110.02.01 1100"))

    def test_mostly_han_with_some_latin_is_kept(self):
        self.assertTrue(rtf.is_cjk_line("記者Yosifu在現場報導新聞"))


class TestClean(unittest.TestCase):
    def test_markup_blocks_never_reach_dialogue(self):
        text = "[[鏡面：標題卡]]\n主播開場的第一句話"
        self.assertEqual(rtf.clean(text), ["主播開場的第一句話"])

    def test_markup_spanning_lines_is_removed(self):
        text = "[[攝影\n剪接]]\n正文在這裡繼續說明"
        self.assertEqual(rtf.clean(text), ["正文在這裡繼續說明"])

    def test_section_marks_are_removed(self):
        text = "第一段的內容講述火災\n##\n第二段的內容講述復原"
        self.assertEqual(rtf.clean(text),
                         ["第一段的內容講述火災", "第二段的內容講述復原"])

    def test_latin_lines_are_filtered_out(self):
        text = "中文的這一行留下來\nnga'ay ho^ kamo\n下一行中文也留下"
        self.assertEqual(rtf.clean(text),
                         ["中文的這一行留下來", "下一行中文也留下"])

    def test_wrapping_parentheses_are_stripped(self):
        self.assertEqual(rtf.clean("（受訪者說明事件經過）"),
                         ["受訪者說明事件經過"])


if __name__ == "__main__":
    unittest.main()
