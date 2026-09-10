"""逐條標記：交付 SRT → 逐條ê「這列的語言」。

材料**干焦**讀 3-srt/。這搭ê fixture 就是按呢做ê：干焝予伊 SRT
文字佮 smkul 彼逝，無予伊 cues、無予伊 vision——若程式偷讀彼兩个，
測試連跑都跑袂起來。

上大ê坑是行號：組裝會kā兩逝文字全款ê相黏 cue 併做一條（39 集有
4 集按呢，094 泰雅併掉 78 條）。行號愛對 SRT 提，莫家己算 cue。
"""
import textwrap
import unittest

from scripts.aiyalaeho.langcheck import mark


AMIS = {"kako", "maolah", "matini", "tangasa", "maafo", "patatiko",
        "kakialawan", "haw", "kita"}
BUNUN = {"halinga", "maitastutasa", "cina", "sain", "tupa", "masial",
         "mudanin", "sidi", "tastu"}
LEX = {"阿美": AMIS, "布農": BUNUN}


def srt(*blocks):
    return "\n\n".join(textwrap.dedent(b).strip() for b in blocks) + "\n"


ONE = srt("""
    1
    00:00:06,220 --> 00:00:09,560
    族語：
    華語：養蜂是另外一塊工作環境的
""", """
    2
    00:01:41,500 --> 00:01:45,020
    族語：Patatiko ho kita i kakialawan a 節目 haw
    華語：我們再回到節目
""", """
    3
    00:02:46,900 --> 00:02:50,100
    族語：母親的語言 母語
    華語：cina tu halinga
""", """
    4
    00:03:10,000 --> 00:03:14,000
    族語：Tangasa to matini maafo to
    華語：直到到今天
""", """
    5
    00:04:00,000 --> 00:04:04,000
    族語：sain hai maitastutasa cina tupa
    華語：這是其中一個的
""")


class TestEntries(unittest.TestCase):
    def test_the_number_comes_from_the_srt(self):
        got = mark.entries(ONE)
        self.assertEqual([e.number for e in got], [1, 2, 3, 4, 5])

    def test_numbers_are_not_recounted(self):
        # 併過ê集：SRT ê行號跳過去 4，程式愛照抄，莫家己對 1 排落去。
        merged = srt("""
            1
            00:00:01,000 --> 00:00:02,000
            族語：kako
            華語：我
        """, """
            9
            00:00:03,000 --> 00:00:04,000
            族語：matini
            華語：今天
        """)
        self.assertEqual([e.number for e in mark.entries(merged)], [1, 9])

    def test_the_start_time_is_copied_from_the_srt(self):
        # SRT ê時間有 0.5 秒留白，毋是真正ê切換點。抄過來就好，
        # 莫換算——換算是bug通覕ê所在。
        self.assertEqual(mark.entries(ONE)[1].start, "00:01:41,500")

    def test_the_end_time_is_copied_too(self):
        self.assertEqual(mark.entries(ONE)[1].end, "00:01:45,020")

    def test_both_times_survive_into_the_mark(self):
        got = mark.marks(ONE, "阿美", LEX, language_code="ami")[1]
        self.assertEqual((got.start, got.end),
                         ("00:01:41,500", "00:01:45,020"))

    def test_the_two_rows_come_apart(self):
        got = mark.entries(ONE)[3]
        self.assertEqual(got.formosan, "Tangasa to matini maafo to")
        self.assertEqual(got.han, "直到到今天")

    def test_a_blank_formosan_row_keeps_its_label(self):
        got = mark.entries(ONE)[0]
        self.assertEqual(got.formosan, "")
        self.assertEqual(got.han, "養蜂是另外一塊工作環境的")


class TestLabels(unittest.TestCase):
    def marks(self, text=ONE, tribe="阿美", code="ami"):
        return mark.marks(text, tribe, LEX, language_code=code)

    def test_a_blank_formosan_row_means_the_screen_was_chinese(self):
        # 畫面頂懸干焦一逝，彼逝是華語。
        self.assertEqual(self.marks()[0].label, "華語")

    def test_latin_plus_han_is_code_switching(self):
        # 標籤無帶族語別ê名——「卑南語夾華語」「泰雅語夾華語」按呢
        # 逐族一款，篩起來真麻煩。
        self.assertEqual(self.marks()[1].label, "族語夾雜華語")

    def test_swapped_rows_are_put_back_and_then_judged(self):
        # 114 布農 cue 714 彼款：族語列規列漢字、華語列是族語，兩
        # 逝激反去。掉轉來才判——判做「華語」是無對ê，彼條有族語。
        got = self.marks()[2]
        self.assertEqual(got.formosan, "cina tu halinga")
        self.assertEqual(got.han, "母親的語言 母語")
        self.assertEqual(got.label, mark.PURE)

    def test_plain_own_language_is_the_ordinary_case(self):
        self.assertEqual(self.marks()[3].label, mark.PURE)

    def test_another_tribes_language_is_unsure(self):
        got = self.marks()[4]
        self.assertEqual(got.label, "無法確定")
        self.assertEqual(got.suspect, "布農")
        self.assertGreater(got.rate, 0)


class TestThresholds(unittest.TestCase):
    """標「無法確定」ê兩个門檻。無門檻ê話 39 集標出 4242 條
    （15.1%），規份無路用；有門檻賰 748 條（2.7%）。"""

    def one(self, formosan, tribe="阿美"):
        text = srt("""
            1
            00:00:01,000 --> 00:00:02,000
            族語：%s
            華語：x
        """ % formosan)
        return mark.marks(text, tribe, LEX, language_code="ami")[0]

    def test_a_short_row_is_not_flagged(self):
        # 「sain hai」干焦兩个詞，命中率毋是 0% 就是 100%，是雜訊。
        self.assertEqual(self.one("sain hai").label, mark.PURE)

    def test_a_long_enough_row_of_another_language_is_flagged(self):
        got = self.one("sain hai maitastutasa cina tupa")
        self.assertEqual(got.label, "無法確定")
        self.assertEqual(got.suspect, "布農")

    def test_a_narrow_lead_is_not_flagged(self):
        # 賽德克 102 對太魯閣是 89% 對 82%，才差 7%——仝一个語言ê
        # 兩个方言本底就相像，毋是別族來賓。
        both = {"kako", "matini", "tangasa", "maafo", "sain"}
        lex = {"阿美": both - {"sain"}, "布農": both}
        text = srt("""
            1
            00:00:01,000 --> 00:00:02,000
            族語：kako matini tangasa maafo sain
            華語：x
        """)
        got = mark.marks(text, "阿美", lex, language_code="ami")[0]
        self.assertEqual(got.label, mark.PURE)

    def test_the_thresholds_are_named_not_buried(self):
        self.assertEqual(mark.MIN_WORDS, 5)
        self.assertEqual(mark.MIN_MARGIN, 0.40)


class TestFactsCarryNoGuess(unittest.TestCase):
    def test_the_certain_labels_leave_the_guess_columns_empty(self):
        for one in mark.marks(ONE, "阿美", LEX, language_code="ami"):
            if one.label != mark.UNSURE:
                self.assertEqual(one.suspect, "", one.label)
                self.assertEqual(one.rate, 0.0, one.label)


class TestVocabularyIsClosed(unittest.TestCase):
    def test_only_four_labels_exist(self):
        seen = set()
        for one in mark.marks(ONE, "阿美", LEX, language_code="ami"):
            seen.add(one.label)
        self.assertLessEqual(
            seen, {mark.PURE, mark.MIXED, mark.CHINESE, mark.UNSURE})

    def test_the_mixed_label_carries_no_tribe_name(self):
        for tribe in ("阿美", "卑南", "泰雅"):
            got = mark.marks(ONE, tribe, LEX, language_code="ami")
            for one in got:
                self.assertNotIn(tribe, one.label)


class TestEveryEntryIsClassified(unittest.TestCase):
    def test_the_count_matches_the_srt(self):
        # 逐集分布表ê五个欄相加愛等於字幕條數，所以逐條攏愛有標籤。
        got = mark.marks(ONE, "阿美", LEX, language_code="ami")
        self.assertEqual(len(got), 5)
        for one in got:
            self.assertTrue(one.label)


if __name__ == "__main__":
    unittest.main()
