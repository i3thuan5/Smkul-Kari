"""交付報表：建議寫法的依據順序、判定轉成修改、三份 CSV。

建議寫法依據順序（使用者確認 2026-10-15）：該集語別權威（辭典語別相同
用辭典，不同用 E樂園 該語別）＞ 開會了全語料次數 ＞ 上字文稿次數。
判語言別差異的不給建議、標待討論。處理方式只有四個值。
"""
import collections
import os
import tempfile
import unittest

from scripts.aiyalaeho.cleaning import candidates
from scripts.aiyalaeho.cleaning import dialect
from scripts.aiyalaeho.cleaning import report
from scripts.aiyalaeho.cleaning import verdicts
from scripts.aiyalaeho.cleaning.source import Entry

E086 = "開會了_086_Pinuyumayan_卑南"
E087 = "開會了_087_Pinuyumayan_卑南"


def entries(*texts):
    out = []
    for number, text in enumerate(texts, start=1):
        out.append(Entry(number, "00:00:0%d,000" % number,
                         "00:00:0%d,500" % number, text, "華語%d" % number))
    return out


def built(dictionary=None, klokah=None, corpus=None, extra=()):
    evidence = candidates.Evidence(
        dictionary=dictionary or {"garem", "lrakan"},
        klokah=klokah or {"南王": {"garem"}, "西群": {"harem", "likavung"}},
        kaldi={"semekan"},
        corpus=corpus or {},
        transcripts=collections.Counter(),
        dict_variety="南王")
    episodes = [
        candidates.EpisodeText(E086, "卑南", ("南王",),
                               entries("garem semekan")),
        candidates.EpisodeText(E087, "卑南", ("西群", "知本"),
                               entries("zi harem i Likavungg",
                                       "Likavung harum", "kiramilla",
                                       *extra)),
    ]
    return candidates.build(episodes, evidence)


def verdict(kind, suggestion="", reason="理由"):
    return verdicts.TextVerdict(kind, suggestion, reason, "b01")


class TestSuggestion(unittest.TestCase):
    def test_the_episode_variety_wins_over_the_dictionary(self):
        # Claude 建議了辭典（南王）的 garem，但 087 是西群：西群 E樂園 的
        # harem 才是權威。
        b = built()
        typo = verdict("錯字", "garem")
        got, note = report.suggestion_for("harum", b, typo)
        self.assertEqual(got, "harem")
        self.assertIn("garem", note)

    def test_an_authorised_suggestion_is_kept(self):
        got, note = report.suggestion_for("likavungg", built(),
                                          verdict("錯字", "Likavung"))
        self.assertEqual(got, "Likavung")
        self.assertEqual(note, "")

    def test_corpus_count_breaks_a_tie(self):
        # Likavng 的兩個相近寫法 likavung、likavong 西群都收，Claude 建議的
        # Likavang 哪裡都沒有：取開會了全語料出現多的那個。
        b = built(klokah={"西群": {"likavung", "likavong"}},
                  corpus={"likavung": collections.Counter({"087": 10}),
                          "likavong": collections.Counter({"087": 1})},
                  extra=("Likavng likavong",))
        got, note = report.suggestion_for(
            "likavng", b, verdict("錯字", "Likavang"))
        self.assertEqual(got, "Likavung")
        self.assertIn("Likavang", note)


class TestFixes(unittest.TestCase):
    def setUp(self):
        self.b = built()
        self.texts = {}
        for episode_entries, name in ((entries("garem semekan"), E086),
                                      (entries("zi harem i Likavungg",
                                               "Likavung harum",
                                               "kiramilla"), E087)):
            for entry in episode_entries:
                self.texts[(name, entry.number)] = entry
        self.text = {"likavungg": verdict("錯字", "Likavung", "多一個 g"),
                     "harum": verdict("語言別差異"),
                     "kiramilla": verdict("不確定")}

    def test_only_typos_go_to_the_image_check(self):
        items = report.typo_items(self.b, self.text, self.texts,
                                  lambda name, number: ["/s.png"])
        words = []
        for item in items:
            words.append(item.word)
        self.assertEqual(words, ["Likavungg"])
        self.assertEqual(items[0].suggestion, "Likavung")

    def test_image_verdicts_decide_what_is_fixed(self):
        image = {(E087, 1, "Likavungg"): verdicts.ImageVerdict(
            "播出端錯字", "Likavungg", "畫面兩個 g", "b01")}
        fixes = report.typo_fixes(self.b, self.text, image, self.texts)
        self.assertEqual(len(fixes), 1)
        self.assertEqual(fixes[0].replacement, "Likavung")
        self.assertEqual(fixes[0].kind, "播出端錯字")
        self.assertIn("多一個 g", fixes[0].basis)
        self.assertIn("畫面兩個 g", fixes[0].basis)

    def test_ocr_misread_takes_what_the_screen_shows(self):
        image = {(E087, 1, "Likavungg"): verdicts.ImageVerdict(
            "OCR 讀錯", "Likavung", "畫面一個 g", "b01")}
        fixes = report.typo_fixes(self.b, self.text, image, self.texts)
        self.assertEqual(fixes[0].kind, "OCR 讀錯")
        self.assertEqual(fixes[0].replacement, "Likavung")

    def test_unreadable_is_not_fixed(self):
        image = {(E087, 1, "Likavungg"): verdicts.ImageVerdict(
            "看不出來", "", "模糊", "b01")}
        self.assertEqual(
            report.typo_fixes(self.b, self.text, image, self.texts), [])


class TestTables(unittest.TestCase):
    def setUp(self):
        self.b = built()
        self.texts = {}
        for name, texts in ((E086, ("garem semekan",)),
                            (E087, ("zi harem i Likavungg", "Likavung harum",
                                    "kiramilla"))):
            for entry in entries(*texts):
                self.texts[(name, entry.number)] = entry
        self.text = {"likavungg": verdict("錯字", "Likavung", "多一個 g"),
                     "harum": verdict("語言別差異", "", "西群寫法"),
                     "kiramilla": verdict("不確定")}
        self.changed = {(E087, 1, "likavungg")}

    def rows(self, which):
        if which == "dictionary":
            rows = report.dictionary_rows({"卑南": self.b}, self.text,
                                          self.changed, self.texts)
        else:
            rows = report.spelling_rows({"卑南": self.b}, self.text,
                                        self.changed)
        header = rows[0]
        out = []
        for row in rows[1:]:
            out.append(dict(zip(header, row)))
        return header, out

    def test_handling_is_one_of_four_values(self):
        for which in ("dictionary", "spelling"):
            _header, rows = self.rows(which)
            for row in rows:
                self.assertIn(row["處理方式"], report.HANDLING)

    def test_dictionary_table_header(self):
        header, _rows = self.rows("dictionary")
        self.assertEqual(header, ["族語別", "詞形", "辭典狀態",
                                  "最接近的辭典詞條", "E樂園見過的語別",
                                  "Kaldi詞表", "出現次數", "第一次出現",
                                  "族語列", "華語列", "處理方式", "依據"])

    def test_dialect_against_the_dictionary_is_for_discussion(self):
        _header, rows = self.rows("dictionary")
        found = {}
        for row in rows:
            found[row["詞形"]] = row
        self.assertNotIn("garem", found)
        self.assertEqual(found["harem"]["辭典狀態"], "近似")
        self.assertEqual(found["harem"]["最接近的辭典詞條"], "garem")
        self.assertEqual(found["harem"]["處理方式"], "待討論")
        self.assertEqual(found["Likavungg"]["處理方式"], "已修改")
        self.assertEqual(found["semekan"]["處理方式"], "不改")
        self.assertEqual(found["kiramilla"]["處理方式"], "待討論")
        self.assertEqual(found["Likavungg"]["第一次出現"], E087 + "#1")

    def test_spelling_table_groups_a_typo_with_its_target(self):
        header, rows = self.rows("spelling")
        self.assertEqual(header, ["族語別", "組別", "寫法", "各集次數", "辭典",
                                  "E樂園見過的語別", "文字分類", "建議寫法",
                                  "處理方式", "依據"])
        group = {}
        for row in rows:
            if row["寫法"] in ("Likavung", "Likavungg"):
                group[row["寫法"]] = row
        self.assertEqual(group["Likavung"]["組別"],
                         group["Likavungg"]["組別"])
        self.assertEqual(group["Likavungg"]["處理方式"], "已修改")
        self.assertEqual(group["Likavung"]["處理方式"], "建議統一")
        self.assertEqual(group["Likavung"]["建議寫法"], "Likavung")

    def test_a_dialect_judgement_gets_no_suggestion(self):
        _header, rows = self.rows("spelling")
        for row in rows:
            if row["文字分類"] == "語言別差異":
                self.assertEqual(row["建議寫法"], "")
                self.assertEqual(row["處理方式"], "待討論")


class TestOverrides(unittest.TestCase):
    """人工改判：使用者裁定某些錯字列待討論、不改（2026-10-15）。

    082 的 odal 整集一致不寫撇號，可能是南勢寫法；087 的 zalaw 整集
    一致用 z，可能是西群寫法；087#286「tatena 'mu」改成 tatena' 會多一個
    撇號。Claude 判錯字、看圖也確認畫面就是這樣，但不能就改。
    """

    def setUp(self):
        self.b = built()
        self.texts = {}
        for name, texts in ((E086, ("garem semekan",)),
                            (E087, ("zi harem i Likavungg", "Likavung harum",
                                    "kiramilla"))):
            for entry in entries(*texts):
                self.texts[(name, entry.number)] = entry
        self.text = {"likavungg": verdict("錯字", "Likavung", "多一個 g"),
                     "harum": verdict("語言別差異"),
                     "kiramilla": verdict("不確定")}
        self.image = {(E087, 1, "Likavungg"): verdicts.ImageVerdict(
            "播出端錯字", "Likavungg", "畫面兩個 g", "b01")}
        self.overrides = {"likavungg": "可能是語言別寫法"}

    def test_an_overridden_typo_is_not_fixed(self):
        self.assertEqual(report.typo_fixes(self.b, self.text, self.image,
                                           self.texts, self.overrides), [])

    def test_both_tables_say_for_discussion_and_why(self):
        by_language = {"卑南": self.overrides}
        rows = report.dictionary_rows({"卑南": self.b}, self.text, set(),
                                      self.texts, by_language)
        found = {}
        for row in rows[1:]:
            if row[1] == "Likavungg":
                found = dict(zip(rows[0], row))
        self.assertEqual(found["處理方式"], "待討論")
        self.assertIn("人工改判：可能是語言別寫法", found["依據"])
        rows = report.spelling_rows({"卑南": self.b}, self.text, set(),
                                    by_language)
        for row in rows[1:]:
            got = dict(zip(rows[0], row))
            if got["寫法"] == "Likavungg":
                self.assertEqual(got["文字分類"], "錯字")
                self.assertEqual(got["處理方式"], "待討論")
                self.assertIn("人工改判", got["依據"])

    def test_the_override_file(self):
        folder = tempfile.mkdtemp(prefix="override-")
        path = os.path.join(folder, "人工改判.csv")
        report.write(path, [["族語別", "詞形", "理由"],
                            ["阿美", "odal", "可能是南勢寫法"],
                            ["卑南", "Tamalakaw", "可能是西群寫法"]])
        got = verdicts.load_overrides(path)
        self.assertEqual(got, {"阿美": {"odal": "可能是南勢寫法"},
                               "卑南": {"tamalakaw": "可能是西群寫法"}})
        self.assertEqual(verdicts.load_overrides(
            os.path.join(folder, "沒有這個檔.csv")), {})


class TestDialectTable(unittest.TestCase):
    def test_middle_confidence_falls_back_to_the_language_code(self):
        result = dialect.Result("中", "西群", "pyu",
                                {"南王": 0.34, "知本": 0.53, "西群": 0.55,
                                 "建和": 0.43}, {"西群": 8, "知本": 2},
                                ("西群", "知本"))
        rows = report.dialect_rows([(E087, "卑南", "", result)])
        row = dict(zip(rows[0], rows[1]))
        self.assertEqual(rows[0], ["成果檔名", "族語別(中)", "smkul標記語別",
                                   "推測語別", "語言別代號", "把握",
                                   "各語別覆蓋率", "分段第一名", "依據"])
        self.assertEqual(row["推測語別"], "西群")
        self.assertEqual(row["語言別代號"], "pyu")
        self.assertEqual(row["各語別覆蓋率"],
                         "西群 55%;知本 53%;建和 43%;南王 34%")
        self.assertEqual(row["分段第一名"], "西群 8/10 段;知本 2/10 段")
        self.assertIn("2 點", row["依據"])


class TestFiles(unittest.TestCase):
    def test_utf8_no_bom_lf_and_repeatable(self):
        folder = tempfile.mkdtemp(prefix="report-")
        path = os.path.join(folder, "t.csv")
        report.write(path, [["欄"], ["值, 有逗號"]])
        with open(path, "rb") as handle:
            first = handle.read()
        self.assertFalse(first.startswith(b"\xef\xbb\xbf"))
        self.assertNotIn(b"\r\n", first)
        report.write(path, [["欄"], ["值, 有逗號"]])
        with open(path, "rb") as handle:
            self.assertEqual(handle.read(), first)


if __name__ == "__main__":
    unittest.main()
