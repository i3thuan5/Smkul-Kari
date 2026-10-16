"""b、c 項候選：每個族語詞形一列，證據並排，初篩決定哪些送 Claude。

量到的坑（2026-10-15）：

  語言別正音      vocab.fold 會把 082 的 kaku 折成 kako，語言別差異就從表上
                消失——候選比對不可套
  用錯語別      087 的 harem 南王辭典沒有（只收 garem），西群 E樂園 有；
                拿辭典判就變錯字
  差一個字母    kamo／kamok、mita／mita'、qani／kani 都是不同的詞，
                不能自動判錯字
  Kaldi 詞表    只證明「這族有人這樣寫」，不給建議寫法
  漢字          族語列夾漢字約 430 條（李芳媚老師），不進候選
  節目名        'a'iyalaeho: 跨族語都有錯拼（'a'iylaeho:、'a'alaeho:……）
"""
import collections
import unittest

from scripts.aiyalaeho.cleaning import candidates
from scripts.aiyalaeho.cleaning.source import Entry
from scripts.lexicon import script


def entry(number, formosan, han=""):
    return Entry(number, "00:00:01,000", "00:00:02,000", formosan, han)


def episode(name, considered, *texts):
    entries = []
    for number, text in enumerate(texts, start=1):
        entries.append(entry(number, text))
    return candidates.EpisodeText(name, "卑南", tuple(considered), entries)


def evidence(**kwargs):
    base = {
        "dictionary": {"garem", "kemazu", "kanta", "kamo", "kamok"},
        "klokah": {"南王": {"garem", "kamo", "kamok"},
                   "西群": {"harem", "likavung", "kamo"},
                   "知本": {"harem", "likavung"}},
        "kaldi": {"semekan"},
        "corpus": {},
        "transcripts": collections.Counter({"likavung": 3}),
        "dict_variety": "南王",
    }
    base.update(kwargs)
    return candidates.Evidence(**base)


E086 = "開會了_086_Pinuyumayan_卑南"
E087 = "開會了_087_Pinuyumayan_卑南"


class TestTokens(unittest.TestCase):
    def test_same_ruler_as_script_words_but_case_kept(self):
        text = "ay harem i Likavungg nanta 李芳媚 李老師 1000 ㄅㄆ 'a'iyalaeho:"
        got = candidates.tokens(text)
        lowered = []
        for token in got:
            lowered.append(token.lower())
        self.assertEqual(lowered, script.words(text))
        self.assertIn("Likavungg", got)

    def test_han_bopomofo_and_digits_never_become_words(self):
        for token in candidates.tokens("李芳媚老師 ㄅㄆㄇㄈ 1000 kanta"):
            self.assertEqual(token, "kanta")


class TestProgrammeName(unittest.TestCase):
    def test_misspellings_across_languages_are_found(self):
        for wrong in ("'a'iylaeho:", "'a'alaeho:", "'a'iyalaheo:",
                      "'a'iylahaeho:", "'a'iyalaho:", "a'iyalaeho:",
                      "'A'iyalaeho"):
            self.assertEqual(candidates.programme_variants(
                "Po:long %s a kamok" % wrong), [wrong], wrong)

    def test_the_right_spelling_and_other_words_are_not(self):
        self.assertEqual(candidates.programme_variants(
            "'a'iyalaeho: kayzaeh kapayaka:i'"), [])

    def test_a_derived_form_is_not_a_misspelling(self):
        # 全語料掃過：'a'iyalaeho:an、'a'iyalaeho:tan 是加了詞綴的衍生詞，
        # 冒號後面還接字母——不是節目名打錯。
        self.assertEqual(candidates.programme_variants(
            "'a'iyalaeho:an 'a'iyalaeho:tan"), [])


class TestScreening(unittest.TestCase):
    def build(self, episodes, **kwargs):
        return candidates.build(episodes, evidence(**kwargs))

    def test_the_episode_variety_decides_not_the_dictionary(self):
        # 087 判中（西群、知本）：harem 西群 E樂園 有，就不是錯字候選。
        got = self.build([episode(E087, ("西群", "知本"), "zi harem mu")])
        self.assertEqual(got.words["harem"].screen, candidates.SEEN_HERE)

    def test_dictionary_counts_only_for_its_own_variety(self):
        # 086 南王：辭典（南王）收 garem → 該集語別見過；
        # 087 西群：garem 只有南王有 → 其他語別見過，不是「見過」。
        got = self.build([episode(E086, ("南王",), "garem"),
                          episode(E087, ("西群", "知本"), "garem")])
        self.assertEqual(got.words["garem"].screen, candidates.SEEN_ELSEWHERE)
        got = self.build([episode(E086, ("南王",), "garem")])
        self.assertEqual(got.words["garem"].screen, candidates.SEEN_HERE)

    def test_kaldi_only_is_marked_but_not_sent(self):
        got = self.build([episode(E086, ("南王",), "semekan")])
        self.assertEqual(got.words["semekan"].screen, candidates.KALDI_ONLY)
        self.assertNotIn("semekan", got.to_send())

    def test_unknown_words_are_sent(self):
        got = self.build([episode(E087, ("西群", "知本"),
                                  "kazu i Likavungg nanta")])
        self.assertEqual(got.words["likavungg"].screen, candidates.SEND)
        self.assertIn("likavungg", got.to_send())
        self.assertEqual(got.words["likavungg"].display, "Likavungg")

    def test_han_in_the_formosan_row_is_not_a_candidate(self):
        got = self.build([episode(E087, ("西群",),
                                  "i Likavung nanta 李芳媚 李老師")])
        for key in got.words:
            self.assertTrue(key.isascii(), key)

    def test_case_and_apostrophe_variants_are_one_word(self):
        got = self.build([episode(E087, ("西群",), "Likavung likavung"),
                          episode(E086, ("南王",), "menaʼu mena'u")])
        self.assertEqual(sum(got.words["likavung"].episodes.values()), 2)
        self.assertEqual(sum(got.words["mena'u"].episodes.values()), 2)

    def test_programme_name_is_not_a_spelling_candidate(self):
        got = self.build([episode(E087, ("西群",), "'a'iylaeho: kanta")])
        self.assertNotIn("'a'iylaeho:", got.words)


class TestNeighbours(unittest.TestCase):
    def build(self, episodes, **kwargs):
        return candidates.build(episodes, evidence(**kwargs))

    def test_no_dialect_folding(self):
        # 082 的 kaku 和其他集的 kako 要是兩個詞形。
        ev = evidence(klokah={"南勢": {"kaku"}, "秀姑巒": {"kako"}},
                      dictionary={"kako"}, dict_variety="秀姑巒")
        got = candidates.build(
            [candidates.EpisodeText("開會了_068_Amis_阿美", "阿美",
                                    ("秀姑巒",), [entry(1, "kako")]),
             candidates.EpisodeText("開會了_082_Amis_阿美", "阿美",
                                    ("南勢", "秀姑巒"), [entry(1, "kaku")])],
            ev)
        self.assertIn("kaku", got.words)
        self.assertIn("kako", got.words)
        self.assertIn("kako", got.words["kaku"].neighbours)

    def test_attested_in_disjoint_varieties_is_dialect(self):
        ev = evidence(klokah={"南勢": {"kaku"}, "秀姑巒": {"kako"}},
                      dictionary={"kako"}, dict_variety="秀姑巒")
        got = candidates.build(
            [candidates.EpisodeText("開會了_068_Amis_阿美", "阿美",
                                    ("秀姑巒",), [entry(1, "kako")]),
             candidates.EpisodeText("開會了_082_Amis_阿美", "阿美",
                                    ("南勢", "秀姑巒"), [entry(1, "kaku")])],
            ev)
        group = got.words["kaku"].group
        self.assertTrue(group)
        self.assertEqual(got.words["kako"].group, group)
        self.assertEqual(got.group_kind[group], candidates.DIALECT)

    def test_attested_in_a_shared_variety_is_different_words(self):
        # kamo、kamok 南王都收：是兩個詞，不進拼寫不一致表、不送判。
        got = self.build([episode(E086, ("南王",), "kamo kamok")])
        self.assertEqual(got.words["kamo"].group, "")
        self.assertNotIn("kamok", got.to_send())

    def test_a_one_letter_neighbour_is_not_by_itself_a_typo(self):
        got = self.build([episode(E087, ("西群",), "Likavung Likavungg")])
        self.assertEqual(got.words["likavung"].screen, candidates.SEEN_HERE)
        self.assertEqual(got.words["likavungg"].screen, candidates.SEND)
        self.assertEqual(got.words["likavungg"].neighbours, ["likavung"])

    def test_words_sent_for_judging_do_not_chain_groups_together(self):
        # 卑南真資料：送判的詞經「差一個字母」一路連下去，串成 68 個詞
        # 的一組，拼寫不一致表沒人讀得懂。送判詞的分組等判完、照「錯字
        # → 建議寫法」再分；候選這一層只把語言別差異對連成組。
        got = self.build([episode(E087, ("西群",),
                                  "harem harum hirum hiram")])
        for key in ("harum", "hirum", "hiram"):
            self.assertEqual(got.words[key].screen, candidates.SEND)
            self.assertEqual(got.words[key].group, "")

    def test_nearest_dictionary_entry(self):
        got = self.build([episode(E087, ("西群",), "harem")])
        self.assertEqual(got.words["harem"].nearest, ["garem"])


class TestRows(unittest.TestCase):
    def test_evidence_columns(self):
        corpus = {"likavung": collections.Counter({"087": 10, "106": 1}),
                  "likavungg": collections.Counter({"087": 2})}
        got = candidates.build(
            [episode(E087, ("西群", "知本"), "Likavungg", "Likavungg",
                     "Likavung")],
            evidence(corpus=corpus))
        rows = got.rows()
        self.assertEqual(rows[0], candidates.HEADER)
        found = None
        for row in rows[1:]:
            if row[0] == "Likavungg":
                found = dict(zip(candidates.HEADER, row))
        self.assertEqual(found["出現集數"], "087")
        self.assertEqual(found["各集次數"], "087:2")
        self.assertEqual(found["辭典"], "無")
        self.assertEqual(found["E樂園見過的語別"], "")
        self.assertEqual(found["Kaldi詞表"], "無")
        self.assertEqual(found["開會了全語料次數"], "2")
        self.assertEqual(found["上字文稿次數"], "0")
        self.assertEqual(found["相近寫法"], "Likavung（087:10;106:1）")
        self.assertEqual(found["初篩"], candidates.SEND)

    def test_rows_are_sorted_and_repeatable(self):
        eps = [episode(E087, ("西群",), "zi harem Likavungg kanta")]
        self.assertEqual(candidates.build(eps, evidence()).rows(),
                         candidates.build(eps, evidence()).rows())


if __name__ == "__main__":
    unittest.main()
