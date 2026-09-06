"""機器譯文ê字形愛佮這个語料仝一款。

翻譯服務ê輸出大部份是正體，毋過內底摻著日文字形佮簡體。量規份快取
（35 萬个漢字）佮畫面字幕（44 萬个）比：

    字對        譯文        畫面字幕（對照）
    裡／裏      2491／221   1197／2
    說／説      2264／4     1710／0
    讚／讃        56／8       13／0
    沒／没      1205／5     1098／0
    樣／样      1628／1     1391／0

電視台家己印ê字幕差不多百分之百一致，服務ê輸出無。`説`、`讃` 是日文
字形，`没`、`样` 是簡體，這四款毋是臺灣用字；`裏` 是正體舊體，合法，
毋過這个語料一直用 `裡`。

**正規化做佇 render，毋是做佇快取。** 快取ê意義是「服務講啥」ê忠實
紀錄，改伊就毋是紀錄矣。交付檔是人欲讀ê，愛照語料ê字形。按呢逐
byte 重建嘛照常成立——正規化是 render ê一部份。
"""
import unittest

from scripts.asrmt import orthography


class TestNormalise(unittest.TestCase):
    def test_japanese_variants_become_taiwanese(self):
        self.assertEqual(orthography.normalise("他説了"), "他說了")
        self.assertEqual(orthography.normalise("讃美"), "讚美")

    def test_simplified_becomes_traditional(self):
        self.assertEqual(orthography.normalise("没有"), "沒有")
        self.assertEqual(orthography.normalise("這样"), "這樣")

    def test_the_old_variant_follows_the_corpus(self):
        """`裏` 是正體，毋是簡體——這條是統一，毋是改毋著。"""
        self.assertEqual(orthography.normalise("在家裏"), "在家裡")

    def test_text_with_nothing_to_fix_is_returned_unchanged(self):
        for text in ("沒有這樣說", "族語新聞", "", "50萬元"):
            self.assertEqual(orthography.normalise(text), text)

    def test_it_does_not_touch_letters_or_digits(self):
        self.assertEqual(orthography.normalise("mikeriday 50"),
                         "mikeriday 50")

    def test_every_mapping_goes_one_way_only(self):
        """對照表袂使有環——`a→b` 佮 `b→a` 做伙會來回無煞。"""
        for wrong, right in orthography.FIXES.items():
            self.assertNotIn(right, orthography.FIXES)
            self.assertNotEqual(wrong, right)

    def test_the_table_says_why_each_one_is_there(self):
        self.assertEqual(sorted(orthography.FIXES),
                         sorted(["没", "样", "説", "讃", "裏"]))


if __name__ == "__main__":
    unittest.main()
