"""詞庫比對佮方言別正音轉換。

兩件會出代誌ê：

  轉換用取代      南勢阿美 u→o／b→f／v→f 若是**取代**原樣，辭典
                  收ê彼个方言別（秀姑巒）家己會變較䆀。愛是加法：
                  原樣抑是轉換後，任一个中就算中。
  轉換濫使套      套去逐个阿美集ê話，秀姑巒ê命中率去予灌水，看
                  袂出方言別ê差別。愛照語言代號查。
"""
import unittest

from scripts.aiyalaeho.langcheck import vocab


AMIS = {"kako", "maolah", "matini", "tangasa", "faloco'", "nga'ay",
        "sowal", "mafana'"}
BUNUN = {"halinga", "maitastutasa", "cina", "sain", "tupa", "masial"}


class TestScoring(unittest.TestCase):
    def test_a_row_scores_against_each_lexicon(self):
        got = vocab.scores(["kako", "maolah"],
                           {"阿美": AMIS, "布農": BUNUN})
        self.assertEqual(got["阿美"], 1.0)
        self.assertEqual(got["布農"], 0.0)

    def test_an_empty_row_scores_nothing(self):
        self.assertEqual(vocab.scores([], {"阿美": AMIS}), {"阿美": 0.0})


class TestRankingIsThePlainRate(unittest.TestCase):
    """排名就是詞庫命中率，無做規模校正。

    捌試過 lift（命中率 ÷ 該族詞庫佔全部ê比例），量了較䆀——
    整集判定 34/39，無校正是 37/39。太魯閣詞庫上大，除落去
    坐落尾，123 彼集 696 條去予標 685 條。
    """

    def test_the_top_rate_wins(self):
        row = ["kako", "maolah", "matini", "hulakay"]
        big = set(row)
        for number in range(7 * len(AMIS)):
            big.add("filler%03d" % number)
        tribe, rate = vocab.best(row, {"阿美": AMIS, "太魯閣": big})
        self.assertEqual(tribe, "太魯閣")
        self.assertEqual(rate, 1.0)

    def test_a_tie_is_broken_by_name_so_output_is_stable(self):
        # CSV 愛逐 byte 重建會著，所以平分ê時愛逐擺揀仝一个。
        same = {"kako", "matini"}
        first = vocab.best(["kako"], {"阿美": same, "布農": same})
        second = vocab.best(["kako"], {"阿美": same, "布農": same})
        self.assertEqual(first, second)

    def test_a_tribe_with_one_episode_is_scored_like_any_other(self):
        # 詞庫來自辭典，毋是語料，所以「這族干焦一集」無影響。
        tribe, _rate = vocab.best(["halinga", "cina"],
                                  {"阿美": AMIS, "布農": BUNUN})
        self.assertEqual(tribe, "布農")


class TestVarietyFolding(unittest.TestCase):
    """南勢阿美：u→o、b→f、v→f，然後才對秀姑巒辭典。"""

    def test_nanshi_amis_hits_after_folding(self):
        # 「maulah」是南勢寫法，辭典收ê是「maolah」。
        plain = vocab.scores(["maulah"], {"阿美": AMIS})
        folded = vocab.scores(["maulah"], {"阿美": AMIS},
                              language_code="ami-x-iams")
        self.assertEqual(plain["阿美"], 0.0)
        self.assertEqual(folded["阿美"], 1.0)

    def test_folding_is_additive_not_a_replacement(self):
        # 取代ê話這條會敗：「kako」轉換了變「kaka」，辭典無收。
        got = vocab.scores(["kako"], {"阿美": AMIS},
                           language_code="ami-x-iams")
        self.assertEqual(got["阿美"], 1.0)

    def test_other_amis_codes_are_not_folded(self):
        # 秀姑巒（ami-x-skl）佮無標ê（ami）攏莫套，若無命中率去予灌水。
        for code in ("ami-x-skl", "ami", None):
            got = vocab.scores(["maulah"], {"阿美": AMIS},
                               language_code=code)
            self.assertEqual(got["阿美"], 0.0, code)

    def test_the_fold_table_only_carries_what_was_measured(self):
        # 干焦南勢阿美量過。別族ê對應規則莫先臆。
        self.assertEqual(set(vocab.FOLDS), {"ami-x-iams"})


class TestFoldingDoesNotTouchText(unittest.TestCase):
    def test_folding_a_word_leaves_the_original_alone(self):
        row = ["maulah"]
        vocab.scores(row, {"阿美": AMIS}, language_code="ami-x-iams")
        self.assertEqual(row, ["maulah"])


class TestVerdict(unittest.TestCase):
    def test_the_top_tribe_and_its_rate_come_back(self):
        tribe, rate = vocab.best(["kako", "maolah"],
                                 {"阿美": AMIS, "布農": BUNUN})
        self.assertEqual(tribe, "阿美")
        self.assertEqual(rate, 1.0)

    def test_nothing_matches_anywhere(self):
        tribe, rate = vocab.best(["zzz", "qqq"],
                                 {"阿美": AMIS, "布農": BUNUN})
        self.assertIsNone(tribe)
        self.assertEqual(rate, 0.0)


if __name__ == "__main__":
    unittest.main()
