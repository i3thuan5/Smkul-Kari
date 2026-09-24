"""tier: 高信心／中信心／不採用, and the one reason a group is dropped.

Every case here is a group the explore phase actually met."""
import unittest

from scripts.mt import tier


def classify(**kw):
    values = {"hallucinated": False, "other_language": False,
              "rate": 0.6, "chrf": 0.05, "words": 30, "baseline": 0.5}
    values.update(kw)
    return tier.classify(**values)


class TestLevels(unittest.TestCase):
    def test_clean_group_is_high(self):
        self.assertEqual(classify(), ("高信心", ""))

    def test_rate_just_at_the_high_line_counts(self):
        # 0.8 × 0.5 = 0.4 exactly; ≥, and not lost to float rounding
        self.assertEqual(classify(rate=0.4)[0], "高信心")

    def test_mt_unlike_the_subtitle_caps_at_mid(self):
        self.assertEqual(classify(chrf=0.01), ("中信心", ""))

    def test_chrf_exactly_at_the_line_counts(self):
        self.assertEqual(classify(chrf=0.02)[0], "高信心")

    def test_nine_words_caps_at_mid(self):
        self.assertEqual(classify(words=9), ("中信心", ""))

    def test_mid_band(self):
        # between 0.6 × 0.5 and 0.8 × 0.5
        self.assertEqual(classify(rate=0.35), ("中信心", ""))

    def test_baseline_is_per_tribe(self):
        # 卑南 reads its dictionary at 0.17 even in the anchor's opening;
        # 0.12 is 70% of that -- a fair 中, not a drop
        self.assertEqual(classify(rate=0.12, baseline=0.17)[0], "中信心")


class TestReasons(unittest.TestCase):
    def test_fragment_scoring_one_is_still_dropped(self):
        # 「harung uri」: both words in the dictionary, nothing to learn
        self.assertEqual(classify(words=2, rate=1.0), ("不採用", "詞數不足"))

    def test_other_language_even_when_own_rate_passes(self):
        self.assertEqual(classify(other_language=True, rate=0.6),
                         ("不採用", "別族語言"))

    def test_loop_or_number_run_is_hallucination(self):
        self.assertEqual(classify(hallucinated=True), ("不採用", "幻覺"))

    def test_low_rate(self):
        self.assertEqual(classify(rate=0.2), ("不採用", "命中率不足"))

    def test_reason_order_is_fixed(self):
        self.assertEqual(classify(hallucinated=True, other_language=True,
                                  words=2, rate=0.0), ("不採用", "幻覺"))
        self.assertEqual(classify(other_language=True, words=2, rate=0.0),
                         ("不採用", "別族語言"))
        self.assertEqual(classify(words=2, rate=0.0), ("不採用", "詞數不足"))

    def test_merge_threshold_lives_here(self):
        # 調參結果（2026-09-24）：五格都是合併較好，取最低候選值
        self.assertAlmostEqual(tier.MERGE_FRACTION, 0.10)


if __name__ == "__main__":
    unittest.main()
