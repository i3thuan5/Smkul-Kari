"""hallucination: text-only flags for sapolita segments.

Measured on 144,806 news segments: 9.7% carry one 3-gram that makes up
30%+ of the segment (「ʼa ʼa ʼa …」 over the closing music), 38 MT rows
are 「一、二、三、…」 number runs, and the Amis benchmark episode has a
mid-programme segment in a Tsou-looking orthography (ʉ everywhere)."""
import unittest

from scripts.mt import hallucination


class TestRepeat(unittest.TestCase):
    def test_closing_music_loop_is_flagged(self):
        words = ("ʼa " * 20).split()
        self.assertGreaterEqual(hallucination.repeat_ratio(words), 0.9)

    def test_normal_sentence_is_low(self):
        words = "o tanosok a lalan no salikaka no kiwit a niyaroʼ".split()
        self.assertLess(hallucination.repeat_ratio(words), 0.3)

    def test_too_short_to_judge_is_zero(self):
        self.assertEqual(hallucination.repeat_ratio(["a", "b"]), 0.0)


class TestNumberRun(unittest.TestCase):
    def test_number_run_flagged(self):
        self.assertTrue(hallucination.number_run(
            "一、二、三、三、四、三、六、六、七、七、九"))

    def test_real_number_sentence_not_flagged(self):
        self.assertFalse(hallucination.number_run("有二十年之多的農作物"))


class TestLexicon(unittest.TestCase):
    def test_rate_is_share_of_words_in_lexicon(self):
        lexicon = {"salikaka", "niyaro'", "kako"}
        words = ["salikaka", "kako", "xxxx", "yyyy"]
        self.assertAlmostEqual(hallucination.lexicon_rate(words, lexicon),
                               0.5)

    def test_apostrophe_shape_does_not_matter(self):
        lexicon = {"niyaro'"}
        self.assertAlmostEqual(hallucination.lexicon_rate(["niyaroʼ"],
                                                          lexicon), 1.0)

    def test_no_words_is_zero(self):
        self.assertEqual(hallucination.lexicon_rate([], {"a"}), 0.0)


class TestLanguageCheck(unittest.TestCase):
    """A 邵語 episode carried an interviewee speaking 泰雅; a 賽德克
    episode carried an Amis music teacher (judged 高 by Claude, both).
    The pair is a fine translation in the wrong language for the
    per-language corpus -- only the dictionaries can tell."""

    LEXICONS = {"邵": {"ita", "thau", "wazaqan", "kilhpiz", "minrusa"},
                "泰雅": {"tayal", "qani", "kawas", "miru", "nqrqes"}}

    def test_other_tribe_wins_by_a_margin(self):
        words = ["miru", "zega", "nqrqes", "tayal", "qani", "kawas"]
        got = hallucination.language_check(words, self.LEXICONS, "邵")
        self.assertEqual(got["best_tribe"], "泰雅")
        self.assertTrue(got["foreign"])

    def test_own_tribe_is_not_foreign(self):
        words = ["ita", "thau", "wazaqan", "kilhpiz", "xxx"]
        got = hallucination.language_check(words, self.LEXICONS, "邵")
        self.assertEqual(got["best_tribe"], "邵")
        self.assertFalse(got["foreign"])

    def test_too_short_never_foreign(self):
        got = hallucination.language_check(["tayal", "qani"],
                                           self.LEXICONS, "邵")
        self.assertFalse(got["foreign"])

    def test_small_margin_is_not_foreign(self):
        # 3/6 own vs 4/6 other: 17 points apart, under the 40 floor
        words = ["ita", "thau", "wazaqan", "tayal", "qani", "kawas"]
        lexicons = {"邵": {"ita", "thau", "wazaqan"},
                    "泰雅": {"tayal", "qani", "kawas", "ita"}}
        got = hallucination.language_check(words, lexicons, "邵")
        self.assertFalse(got["foreign"])


class TestFlags(unittest.TestCase):
    def test_flags_bundle(self):
        seg = {"formosan": "ʼa ʼa ʼa ʼa ʼa ʼa ʼa ʼa", "han": "一、二、三、四、五、六"}
        flags = hallucination.flags(seg)
        self.assertTrue(flags["repeat"])
        self.assertTrue(flags["number_run"])
        self.assertTrue(flags["suspicious"])

    def test_clean_segment_not_suspicious(self):
        seg = {"formosan": "o tanosok a lalan no salikaka no kiwit",
               "han": "這是一條漫長的歧路"}
        self.assertFalse(hallucination.flags(seg)["suspicious"])


if __name__ == "__main__":
    unittest.main()
