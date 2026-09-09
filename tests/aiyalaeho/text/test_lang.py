"""集的來源目錄名稱 → 語言別代號。

重用 `scripts.aiyalaeho.catalogue` 既有的 `LANGUAGES`（族語別）與
`VARIETIES`（族語別下的語言別），不另造一份對照表——那份規範表的正本
在 `kithann/規範/族語及語言別名稱 - *名稱.csv`，catalogue.py 已經把它
抄成 Python 字典，這裡直接借用。

判法：目錄名稱裡找得到某個語言別的慣用字（如「澤敖利」「霧台」）就用
那個代號；找不到但找得到族語別（如「賽夏」「布農」）就退到族語別代號；
兩者都找不到就中止——不留空、不編一個規範表裡沒有的代號。
"""
import unittest
import unittest.mock

from scripts.aiyalaeho.text import lang
from scripts.errors import PipelineError

# 全部 41 個真實目錄名稱，逐一核對代號——不是抽樣，是這個語料的全部。
_REAL_FOLDERS_AND_CODES = {
    "開會001_賽夏族": "xsy",
    "開會002_布農族": "bnn",
    "開會003_排灣族": "pwn",
    "開會004_泰雅族": "tay",
    "開會005_阿美族": "ami",
    "開會006_魯凱族": "dru",
    "開會007_布農族": "bnn",
    "開會008_魯凱族": "dru",
    "開會009_賽德克族": "trv",
    "開會010_阿美族母系社會": "ami",
    "開會011_排灣族": "pwn",
    "開會012_賽夏族": "xsy",
    "開會013_拉阿魯哇族": "sxr",
    "開會014_萬山正名": "dru-x-opnh",
    "開會015_太魯閣族": "trv-x-truku",
    "開會016_撒奇萊雅族": "szy",
    "開會017_噶瑪蘭族": "ckv",
    "開會018_泰雅汶水語": "tay-x-mtuw",
    "開會019_鄒族鞣皮": "tsu",
    "開會020_泰雅萬大語": "tay-x-plngw",
    "開會021_卑南族歌謠": "pyu",
    "開會022_泰雅口簧琴": "tay",
    "開會023_阿美族返服": "ami",
    "開會024_賽夏族河邊會議Ⅰ": "xsy",
    "開會025_賽夏族河邊會議Ⅱ": "xsy",
    "開會026_阿美族國民年金": "ami",
    "開會027_卡那卡那富族": "xnb",
    "開會028_布農族祭司": "bnn",
    "開會029_四季泰雅族": "tay-x-cql",
    "開會030_馬蘭阿美族": "ami-x-frng",
    "開會031_土坂排灣族": "pwn",
    "開會032_澤敖利泰雅": "tay-x-sul",
    "開會033_尖石泰雅族": "tay",
    "開會034_東魯凱族": "dru-x-trmk",
    "開會035-賽夏族祈天祭": "xsy",
    "開會036-東布青": "bnn",
    "開會037-大武魯凱": "dru-x-lbw",
    "開會038-恆春阿美": "ami-x-pld",
    "開會041-旅北阿美": "ami",
    "開會044-噶瑪蘭族": "ckv",
    "開會045-布農族挖礦": "bnn",
}


class TestReusesExistingTables(unittest.TestCase):
    """重用 catalogue.py 的表，不另造一份——這是 design.md 定案的做法。"""

    def test_resolves_all_41_real_folders(self):
        for folder, expected in _REAL_FOLDERS_AND_CODES.items():
            with self.subTest(folder=folder):
                self.assertEqual(lang.resolve(folder), expected)


class TestVarietyBeforeLanguage(unittest.TestCase):
    def test_variety_wins_when_named_in_the_folder(self):
        self.assertEqual(lang.resolve("開會032_澤敖利泰雅"), "tay-x-sul")

    def test_falls_back_to_the_parent_language_when_no_variety_named(self):
        self.assertEqual(lang.resolve("開會002_布農族"), "bnn")


class TestUndetermined(unittest.TestCase):
    """連族語別都查不出來、或一份資料混了大量不同的族語選不出代表，
    代號落到 ISO 639-2／639-3 的 `und`——跟 `catalogue.py` 116 集
    （無語言卡、無字幕）同一個先例，不是自己發明的代碼。`und` 是調查
    過後的結論，走的是跟 `開會036-東布青` 一樣的 `OVERRIDES` 機制，
    不是「查不到就自動退」的預設值——查不到預設仍然是中止（見
    `TestUnresolvableAborts`）。
    """

    def test_und_is_reachable_through_the_same_override_mechanism(self):
        overrides = dict(lang.OVERRIDES)
        overrides["開會999_混雜多語無法判定"] = "und"
        with unittest.mock.patch.object(lang, "OVERRIDES", overrides):
            self.assertEqual(lang.resolve("開會999_混雜多語無法判定"),
                             "und")


class TestUnresolvableAborts(unittest.TestCase):
    def test_a_folder_naming_nothing_recognizable_aborts(self):
        with self.assertRaises(PipelineError) as ctx:
            lang.resolve("開會999_完全查無的名字")
        self.assertIn("開會999_完全查無的名字", str(ctx.exception))

    def test_it_does_not_return_an_empty_string_or_an_invented_code(self):
        with self.assertRaises(PipelineError):
            lang.resolve("")


class TestOneExplicitOverride(unittest.TestCase):
    """開會036-東布青 的目錄名稱查不到任何族語別或語言別用字；轉出來的
    文字裡有「itu Bunun tuza tu maza madadaingaz…」，逐字唸出
    「Bunun」，所以覆寫成布農語——不是規則自動解出來的。
    """

    def test_the_override_resolves_to_bunun(self):
        self.assertEqual(lang.resolve("開會036-東布青"), "bnn")

    def test_the_override_is_recorded_with_its_evidence(self):
        # 覆寫依據要留在程式裡看得到，不是憑空覆寫。
        self.assertIn("開會036-東布青", lang.OVERRIDES)
        self.assertIn("Bunun", lang.OVERRIDE_EVIDENCE["開會036-東布青"])


if __name__ == "__main__":
    unittest.main()
