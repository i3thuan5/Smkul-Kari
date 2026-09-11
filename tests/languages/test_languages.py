"""族語別佮語言別ê代號對照表：查代號、倒轉查名、查無ê時指名。

規範ê正本是 `kithann/規範/族語及語言別名稱 - 族語名稱.csv` 佮同目錄ê
`- 語言別名稱.csv`，兩份攏是 gitignore ê——換一台機器就無去，所以
程式內底愛有一份綴 repo 走ê對照表（CLAUDE.md 明文）。這馬兩个語料
攏愛用伊：《開會了》對檔名剖語言別，族語新聞嘛愛填 `語言別代號`。
"""
import unittest

from scripts import languages
from scripts.errors import PipelineError


# 族語新聞 983 逝內底出現ê 16 種族語別。每一種攏愛查有代號，無就
# 有一整族ê集數填無 `語言別代號`——彼欄 CLAUDE.md 講袂使留空。
NEWS_LANGUAGES = [
    "卑南", "卡那卡那富", "噶瑪蘭", "太魯閣", "布農", "拉阿魯哇",
    "排灣", "撒奇萊雅", "泰雅", "賽夏", "賽德克", "邵", "鄒",
    "阿美", "雅美", "魯凱",
]


class TestEveryNewsLanguageHasACode(unittest.TestCase):
    def test_all_sixteen_resolve(self):
        for name in NEWS_LANGUAGES:
            self.assertTrue(languages.code_for(name, ""), name)

    def test_each_one_has_an_english_spelling_too(self):
        # `族語別(英)` 佮 `族語別(中)` 愛一對一：兩爿攏是共同欄位，
        # 六張表 join ê時對袂起來就穿幫。
        seen = {}
        for name in NEWS_LANGUAGES:
            english = languages.english_for(name)
            self.assertTrue(english, name)
            self.assertNotIn(english, seen, "%s 佮 %s 仝一个英文拼法"
                             % (name, seen.get(english)))
            seen[english] = name


class TestTrukuIsNotSeediq(unittest.TestCase):
    """太魯閣佮賽德克 ISO 歸做仝一个 `trv`，毋過是無仝ê語言。

    短期照 RFC 5646 ê私有標籤分開。兩爿真正濫過：檔名寫「德路固」ê
    彼集（`102-賽德克語-德路固`）是**賽德克**底下ê變體 `trv-x-trk`，
    佮「太魯閣語」`trv-x-truku` 無仝。濫做伙ê話，交付表彼欄會講伊是
    另外一種語言。
    """

    def test_truku_keeps_its_private_tag(self):
        self.assertEqual(languages.code_for("太魯閣", ""), "trv-x-truku")

    def test_it_is_not_flattened_to_the_shared_iso_code(self):
        self.assertNotEqual(languages.code_for("太魯閣", ""), "trv")

    def test_seediq_itself_is_the_bare_code(self):
        self.assertEqual(languages.code_for("賽德克", ""), "trv")

    def test_teruku_variety_belongs_to_seediq(self):
        self.assertEqual(languages.code_for("賽德克", "德路固"), "trv-x-trk")

    def test_the_two_do_not_collide(self):
        self.assertNotEqual(languages.code_for("賽德克", "德路固"),
                            languages.code_for("太魯閣", ""))


class TestFallingBackToTheLanguageCode(unittest.TestCase):
    """查有語言別就用語言別代號，查無就退族語別代號——袂使留空。

    族語新聞 983 逝內底干焦 1 逝ê影片檔名帶變體線索
    （`魯凱語-霧台20210101S1100.mp4`），賰ê 968 逝查無。所以
    「`語言別` 空」是常態，「代號空」才是錯。
    """

    def test_no_variety_gives_the_language_code(self):
        self.assertEqual(languages.code_for("阿美", ""), "ami")

    def test_a_variety_the_standard_lists_gives_its_own_tag(self):
        self.assertEqual(languages.code_for("阿美", "秀姑巒"), "ami-x-skl")

    def test_a_variety_the_standard_does_not_list_falls_back(self):
        # `083-魯凱語-非霧台` 就是按呢：字樣留佇 `語言別` 欄，代號退
        # 族語級。家己掰一个標籤ê話，交付表彼格對別人是無意義ê。
        self.assertEqual(languages.code_for("魯凱", "非霧台"), "dru")

    def test_taiwanese_character_variants_normalise(self):
        # 規範寫「霧臺」，檔名寫「霧台」——查表進前愛正規化。
        self.assertEqual(languages.code_for("魯凱", "霧台"),
                         languages.code_for("魯凱", "霧臺"))


class TestUnknownNamesAreNamedNotGuessed(unittest.TestCase):
    def test_an_unknown_language_is_refused(self):
        with self.assertRaises(PipelineError) as caught:
            languages.code_for("霍格華茲", "")
        self.assertIn("霍格華茲", str(caught.exception))

    def test_the_message_lists_what_it_does_know(self):
        with self.assertRaises(PipelineError) as caught:
            languages.code_for("霍格華茲", "")
        self.assertIn("阿美", str(caught.exception))

    def test_an_unknown_english_spelling_is_refused(self):
        with self.assertRaises(PipelineError):
            languages.english_for("霍格華茲")


class TestReverseLookup(unittest.TestCase):
    """對代號倒轉查族語別佮語言別。

    `1-句對.csv` 彼 41 逝干焦有 `語言別代號`，`族語別(英)`、
    `族語別(中)`、`語言別` 三欄愛對伊推。
    """

    def test_a_variety_tag_resolves_to_language_and_variety(self):
        self.assertEqual(languages.language_of("ami-x-frng"), "阿美")
        self.assertEqual(languages.variety_of("ami-x-frng"), "馬蘭")
        self.assertEqual(languages.english_for(
            languages.language_of("ami-x-frng")), "Amis")

    def test_a_bare_language_code_has_no_variety(self):
        self.assertEqual(languages.language_of("bnn"), "布農")
        self.assertEqual(languages.variety_of("bnn"), "")

    def test_truku_resolves_back_to_truku_not_seediq(self):
        self.assertEqual(languages.language_of("trv-x-truku"), "太魯閣")
        self.assertEqual(languages.language_of("trv"), "賽德克")

    def test_a_code_outside_the_table_is_named(self):
        with self.assertRaises(PipelineError) as caught:
            languages.language_of("xx-x-nope")
        self.assertIn("xx-x-nope", str(caught.exception))

    def test_und_is_a_real_answer_not_an_error(self):
        # `und` 是 ISO 639-2／639-3 家己對「未確定語言」ê答案。116 集
        # （無語言卡、無字幕）就是按呢登記ê。
        self.assertEqual(languages.language_of("und"), languages.UNKNOWN)


class TestVarietyOwner(unittest.TestCase):
    """變體字樣家己就講會出伊是佗一族ê。

    `98-東魯凱-無字幕.mp4` 是kā變體寫佇族語別彼位，所以愛倒轉揣。
    """

    def test_a_variety_names_its_language(self):
        self.assertEqual(languages.variety_owner("東魯凱"), "魯凱")

    def test_something_that_is_not_a_variety_owns_nothing(self):
        self.assertIsNone(languages.variety_owner("阿美"))


if __name__ == "__main__":
    unittest.main()
