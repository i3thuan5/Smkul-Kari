"""族別 → 翻譯服務ê語言碼，一張靜態表。

本底這是**逐集偵測**ê：ka̋ 五个阿美碼逐个翻 50 逝，看佗一个分數較懸。
試點量出來五个平手（平均分 0.063 上下），所以偵測是白了 250 擺請求，
換來一个佮擲筊仝款ê答案。這馬直接查表。

表內底ê碼是對服務ê下拉選單抄落來ê（2026-09-05 抄，41 个碼、16 族），
毋是家己編ê——編毋著服務袂共你講，伊會用一个無仝ê方言翻予你。

上要緊ê坑：**賽德克ê碼是 `trv_` 起頭ê**（trv_Delu／trv_Duda／
trv_Tegu），佮太魯閣（trv_Truk）仝前綴。本底用「前綴猜族別」ê寫法
會kā賽德克送去太魯閣彼个選單——彼个選單內底無彼三个碼。所以族別愛
對表提，袂使對碼ê前綴臆。
"""
import json
import os
import unittest

from scripts.asrmt import dialects
from scripts.errors import PipelineError

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
INVENTORY = os.path.join(ROOT, "Kari-SRT", "news", "inventory.json")


class TestTheTableCoversTheCorpus(unittest.TestCase):
    def test_every_ethnicity_in_the_inventory_has_a_code(self):
        if not os.path.exists(INVENTORY):
            self.skipTest("Kari-SRT 無掛起來")
        with open(INVENTORY, encoding="utf-8") as handle:
            rows = json.load(handle)
        missing = set()
        for row in rows:
            name = row.get("族語別(英)")
            if name and name not in dialects.CHOSEN:
                missing.add(name)
        self.assertEqual(missing, set())

    def test_all_sixteen_ethnicities_are_there(self):
        self.assertEqual(len(dialects.CHOSEN), 16)


class TestLookup(unittest.TestCase):
    def test_a_known_ethnicity_gives_its_code(self):
        self.assertEqual(dialects.lang_of("Rukai"), "dru_Dawu")

    def test_amis_keeps_the_code_the_pilot_cached_under(self):
        """試點規集ê譯文（706 逝）就是囥佇 ami_Xiug 這个鍵下跤。換
        別个碼，彼寡攏變做無命中，愛閣問服務一擺。而且五个碼品質
        平手，無理由換。"""
        self.assertEqual(dialects.lang_of("Amis"), "ami_Xiug")

    def test_an_unknown_ethnicity_fails_loud_and_names_it(self):
        with self.assertRaises(PipelineError) as caught:
            dialects.lang_of("Klingon")
        self.assertIn("Klingon", str(caught.exception))

    def test_every_chosen_code_is_one_the_service_offers(self):
        for _english, code in sorted(dialects.CHOSEN.items()):
            self.assertIn(code, dialects.SERVICE_LANGS, code)


class TestTheSeediqTrap(unittest.TestCase):
    def test_seediq_codes_start_with_the_truku_prefix(self):
        self.assertTrue(dialects.lang_of("Seediq").startswith("trv_"))

    def test_but_the_ethnicity_is_still_seediq(self):
        """前綴臆會共伊送去太魯閣彼个選單，彼內底干焦 trv_Truk。"""
        self.assertEqual(dialects.ethnicity_of(dialects.lang_of("Seediq")),
                         "賽德克")
        self.assertEqual(dialects.ethnicity_of("trv_Truk"), "太魯閣")

    def test_an_unknown_code_fails_loud(self):
        with self.assertRaises(PipelineError) as caught:
            dialects.ethnicity_of("zzz_Nope")
        self.assertIn("zzz_Nope", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
