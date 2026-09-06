"""逐集一份詞表，予彼一集所有ê批次共用。

本底逐个 agent 攏佇家己彼 50 條內底對頭推導錨點。量著ê代價有兩項：
**慢**（逐條 12 秒內底有一部份是咧重推），佮**無一致**（噶瑪蘭彼集
三个 agent 各自推出 `qaqanan`＝食物，泰雅彼集無仝批對仝一个詞ê認定
無仝）。

改做判定進前先掃規集：族語逝內底ê詞，若佇幾若條無相干ê列攏對著仝
一个華語主題，就是這集ê錨點。掃出來ê表逐批共用——省八擺重推，而且
規集ê標準仝一支尺。

門檻是**三擺**：兩擺可能是搪著，三擺才算話。這佮 prompt 內底講ê仝款。
"""
import unittest

from scripts.asrmt import glossary


def rows(pairs):
    out = []
    for i, (formosan, subtitle) in enumerate(pairs):
        out.append({"index": i + 1, "formosan": formosan,
                    "subtitle": subtitle})
    return out


class TestCandidates(unittest.TestCase):
    def test_a_word_that_recurs_with_the_same_topic_is_an_anchor(self):
        data = rows([("mi foksi ko tamdaw", "拳擊隊今天成立"),
                     ("o foksi a mikilim", "拳擊教練表示"),
                     ("foksi haw kako", "他從小就練拳擊"),
                     ("caay ko nga'ay", "天氣不佳")])
        found = glossary.anchors(data)
        self.assertIn("foksi", found)

    def test_twice_is_not_enough(self):
        """兩擺會使是搪著——族語詞蓋短，湊巧同齊出現真正常。"""
        data = rows([("mi foksi ko tamdaw", "拳擊隊今天成立"),
                     ("o foksi a mikilim", "拳擊教練表示"),
                     ("caay ko nga'ay", "天氣不佳")])
        self.assertNotIn("foksi", glossary.anchors(data))

    def test_a_word_with_no_shared_topic_is_not_an_anchor(self):
        """逐擺對著無仝主題ê詞，是虛詞抑是烏白湠ê，毋是錨點。"""
        data = rows([("o mita a tamdaw", "拳擊隊今天成立"),
                     ("o mita haw", "天氣不佳"),
                     ("o mita ko", "部落舉辦豐年祭")])
        self.assertNotIn("mita", glossary.anchors(data))

    def test_it_says_which_chinese_the_word_goes_with(self):
        data = rows([("mi foksi ko tamdaw", "拳擊隊今天成立"),
                     ("o foksi a mikilim", "拳擊教練表示"),
                     ("foksi haw kako", "他從小就練拳擊")])
        self.assertEqual(glossary.anchors(data)["foksi"], "拳擊")

    def test_very_short_words_are_skipped(self):
        """一兩个字母ê攏是虛詞，湊出來ê「主題」無意義。"""
        data = rows([("a o ko tamdaw", "拳擊隊今天成立"),
                     ("a o ko mikilim", "拳擊教練表示"),
                     ("a o ko kako", "他從小就練拳擊")])
        for word in glossary.anchors(data):
            self.assertGreater(len(word), 2, word)


class TestRendering(unittest.TestCase):
    def test_it_writes_one_line_per_anchor(self):
        data = rows([("mi foksi ko tamdaw", "拳擊隊今天成立"),
                     ("o foksi a mikilim", "拳擊教練表示"),
                     ("foksi haw kako", "他從小就練拳擊")])
        text = glossary.render(glossary.anchors(data))
        self.assertIn("foksi", text)
        self.assertIn("拳擊", text)
        self.assertEqual(len(text.strip().splitlines()), 1)

    def test_an_empty_glossary_says_so_rather_than_being_blank(self):
        """空白ê檔案予人掠做「猶未做」；講明「揣無」才免人閣去揣。"""
        text = glossary.render({})
        self.assertTrue(text.strip())


if __name__ == "__main__":
    unittest.main()
