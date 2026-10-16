"""語言別推測：對 E樂園 各語別詞表算覆蓋率，並分段看第一名穩不穩。

門檻是拿這 10 集量出來的（2026-10-15）：

  085 賽考利克 87%，次高 49%       領先 38 點、各段一致 → 高
  086 南王 76%，其他 23～27%       領先 49 點、15/15 段 → 高
  084 海岸 80%，秀姑巒 77%         只領先 3 點、10/10 段 → 中
  087 西群 55%，知本 53%           只領先 2 點、8/10 段  → 中
  082 各語別 53～59%               分段第一名在南勢與秀姑巒／馬蘭交錯
                                   （6/10 段）→ 混合，不是南勢
  068 已標秀姑巒，只比海岸高 3 點  照標記，不重推
"""
import unittest

from scripts.aiyalaeho.cleaning import dialect

# 三個假語別，各自認得的詞不重疊；「zzz」三個都認得。
VOCABS = {
    "南勢": {"aaa", "zzz"},
    "秀姑巒": {"bbb", "zzz"},
    "海岸": {"ccc", "zzz"},
}


def lines(*parts):
    """("aaa", 30) 這種 (詞, 列數) 串起來，一列一詞。"""
    out = []
    for word, count in parts:
        for _ in range(count):
            out.append(word)
    return out


def infer(text_lines, labelled=""):
    return dialect.infer(text_lines, VOCABS, "阿美", labelled=labelled,
                         window=10, min_words=5)


class TestVerdicts(unittest.TestCase):
    def test_clear_lead_and_steady_windows_is_high(self):
        result = infer(lines(("aaa", 90), ("bbb", 10)))
        self.assertEqual(result.verdict, "高")
        self.assertEqual(result.variety, "南勢")
        self.assertEqual(result.code, "ami-x-iams")
        self.assertEqual(result.considered, ("南勢",))

    def test_a_small_lead_is_never_high(self):
        # 每一段都是南勢第一，但全集只贏 5 點：084、087 的樣子。
        window = ["aaa bbb"] * 9 + ["aaa aaa bbb"]
        result = infer(window * 10)
        self.assertEqual(result.verdict, "中")
        self.assertEqual(result.variety, "南勢")
        self.assertEqual(result.code, "ami")
        self.assertEqual(set(result.considered), {"南勢", "秀姑巒"})

    def test_alternating_windows_is_mixed(self):
        # 082：分段第一名交錯，全集最高的那個也只佔六段。
        text = (lines(("aaa", 10)) + lines(("bbb", 10))) * 3 \
            + lines(("aaa", 10)) * 3 + lines(("ccc", 10))
        result = infer(text)
        self.assertEqual(result.verdict, "混合")
        self.assertEqual(result.code, "ami")
        self.assertEqual(set(result.considered), {"南勢", "秀姑巒", "海岸"})

    def test_a_labelled_episode_keeps_its_label(self):
        result = infer(lines(("aaa", 52), ("bbb", 48)), labelled="秀姑巒")
        self.assertEqual(result.verdict, "已標記")
        self.assertEqual(result.variety, "秀姑巒")
        self.assertEqual(result.code, "ami-x-skl")
        self.assertEqual(result.considered, ("秀姑巒",))

    def test_a_language_with_one_variety_is_not_inferred(self):
        result = dialect.infer(["kayzaeh"], {"": {"kayzaeh"}}, "賽夏")
        self.assertEqual(result.verdict, "單一語別")
        self.assertEqual(result.code, "xsy")
        self.assertEqual(result.considered, ("",))

    def test_thin_windows_do_not_vote(self):
        # 詞次不夠的段不算：最後一段只有 2 列，不能讓它投成「混合」。
        text = lines(("aaa", 90)) + lines(("ccc", 2))
        result = infer(text)
        self.assertEqual(result.windows, {"南勢": 9})

    def test_rates_are_reported_per_variety(self):
        result = infer(lines(("aaa", 50), ("zzz", 50)))
        self.assertAlmostEqual(result.rates["南勢"], 1.0)
        self.assertAlmostEqual(result.rates["秀姑巒"], 0.5)


if __name__ == "__main__":
    unittest.main()
