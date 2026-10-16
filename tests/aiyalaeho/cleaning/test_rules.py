"""a 項規則清洗：撇號、多餘空白、重複標點。

量到的資料性質（10 集，2026-10-15）：

  冒號         詞的一部分：'a'iyalaeho:（賽夏語節目名）、賽夏 kapayaka:i'、
               泰雅辭典 abaw:——不是標點
  ’ 夾空白     全語料 10 行，都是「’ 後接 1～4 個空白」（087 mena’   u）；
               併不併要看圖，規則不能自己併
  雙撇 "       真的符號（085 "awsa'、092 'a"iy），不是重複標點
  雙空白       族語列約 60 條（082 22、087 20）；華語列 22 條（086 12）是
               畫面斷句，縮成一個、不刪
  刪節號       081 Padaka...........、......；Sipulun... 的 3 點是正常的
  空列         082 族語列空 171 條，清洗後仍要是空的
"""
import unittest

from scripts.aiyalaeho.cleaning import rules


def kinds(steps):
    out = []
    for step in steps:
        out.append(step.kind)
    return out


class TestColon(unittest.TestCase):
    def test_colon_is_part_of_the_word(self):
        text = "'a'iyalaeho: kapayaka:i' abaw:"
        cleaned, steps = rules.clean(text)
        self.assertEqual(cleaned, text)
        self.assertEqual(steps, [])


class TestApostrophe(unittest.TestCase):
    def test_curly_and_modifier_become_straight(self):
        cleaned, steps = rules.clean("ngaʼay ho ma’ulid")
        self.assertEqual(cleaned, "nga'ay ho ma'ulid")
        self.assertEqual(kinds(steps), ["撇號"])

    def test_gap_after_curly_is_collapsed_but_not_joined(self):
        cleaned, steps = rules.clean(
            "zi harem mu kemani ku mena’   u kana")
        self.assertEqual(cleaned, "zi harem mu kemani ku mena' u kana")
        self.assertEqual(kinds(steps), ["撇號", "多餘空白"])

    def test_gaps_are_reported_for_a_look(self):
        gaps = rules.apostrophe_gaps(
            "magal qu ’  san nha mqbaq mosa blaq balay")
        self.assertEqual(gaps, [rules.Gap("’  san", "' san", "'san")])
        gaps = rules.apostrophe_gaps("zi izumu ma’   ulidta intana")
        self.assertEqual(gaps, [rules.Gap("ma’   ulidta", "ma' ulidta",
                                          "ma'ulidta")])

    def test_no_gap_no_report(self):
        self.assertEqual(rules.apostrophe_gaps("nga'ay ho ma’ulid"), [])

    def test_double_quote_is_a_real_mark(self):
        text = "\"awsa' 'a\"iy"
        cleaned, steps = rules.clean(text)
        self.assertEqual(cleaned, text)
        self.assertEqual(steps, [])


class TestSpaces(unittest.TestCase):
    def test_runs_of_spaces_become_one(self):
        cleaned, steps = rules.clean("kemazu i kanta i  Likavungg")
        self.assertEqual(cleaned, "kemazu i kanta i Likavungg")
        self.assertEqual(kinds(steps), ["多餘空白"])

    def test_chinese_phrase_break_is_kept_as_one_space(self):
        cleaned, _steps = rules.clean("稍待一會兒  我們即將共同來探討")
        self.assertEqual(cleaned, "稍待一會兒 我們即將共同來探討")

    def test_empty_row_stays_empty(self):
        self.assertEqual(rules.clean(""), ("", []))


class TestPunctuation(unittest.TestCase):
    def test_four_or_more_dots_become_three(self):
        self.assertEqual(rules.clean("Padaka...........")[0], "Padaka...")
        self.assertEqual(rules.clean("......")[0], "...")
        cleaned, steps = rules.clean("Puq puq dau ca kitatasal ......")
        self.assertEqual(cleaned, "Puq puq dau ca kitatasal ...")
        self.assertEqual(kinds(steps), ["重複標點"])

    def test_three_dots_are_a_normal_ellipsis(self):
        self.assertEqual(rules.clean("Sipulun..."), ("Sipulun...", []))
        self.assertEqual(rules.clean("Hankok...Taywan")[0],
                         "Hankok...Taywan")

    def test_repeated_exclamation_and_question_marks(self):
        self.assertEqual(rules.clean("試試看!!")[0], "試試看!")
        self.assertEqual(rules.clean("真的嗎？？")[0], "真的嗎？")

    def test_steps_chain_from_before_to_after(self):
        # 對照表一處一列：每一步的「修改前」接上一步的「修改後」。
        text = "ma’   u  ......"
        cleaned, steps = rules.clean(text)
        self.assertEqual(steps[0].before, text)
        for index in range(1, len(steps)):
            self.assertEqual(steps[index].before, steps[index - 1].after)
        self.assertEqual(steps[-1].after, cleaned)


if __name__ == "__main__":
    unittest.main()
