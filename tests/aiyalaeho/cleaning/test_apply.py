"""清洗版 SRT 與修改前後對照表。

清洗版直接改交付 SRT 的文字行，不重組：重組時文字變得一樣的相鄰兩條
會被 merge_repeats 併掉，編號一位移，對照表就對不上交付版。

d 項：語言別差異、不同詞、斷詞不同、不確定、看不出來的一律不改，只列表。
"""
import unittest

from scripts.aiyalaeho.cleaning import apply
from scripts.errors import PipelineError
from tests.aiyalaeho.cleaning import fixtures

NAME = "開會了_087_Pinuyumayan_卑南"


def srt_text():
    store = fixtures.Store()
    store.episode(NAME, [
        (10.0, 12.0, "ay harem i  Likavungg nanta", "介紹利嘉部落"),
        (13.0, 15.0, "Kako kakoay kako", "我"),
        (16.0, 18.0, "", "稍待一會兒  我們"),
        (19.0, 21.0, "zi mena’   u kana", "放眼看"),
        (22.0, 24.0, "Po:long 'a'iylaeho: a kamok", "收看'a'iyalaho:"),
        (25.0, 27.0, "Puq puq ......", "試試看!!"),
    ])
    return store.srt_text(NAME)


def run(fixes=(), merges=()):
    return apply.clean_episode(srt_text(), NAME, list(fixes), list(merges))


class TestLayoutUnchanged(unittest.TestCase):
    def test_only_text_after_the_labels_differs(self):
        before = srt_text()
        after, _changes = run(
            fixes=[apply.Fix(NAME, 1, "likavungg", "Likavung", "播出端錯字",
                             "看圖確認")],
            merges=[apply.Merge(NAME, 4, "mena' u", "mena'u", "同一詞")])
        old_lines = before.split("\n")
        new_lines = after.split("\n")
        self.assertEqual(len(old_lines), len(new_lines))
        for old, new in zip(old_lines, new_lines):
            if old.startswith(("族語：", "華語：")):
                self.assertEqual(old[:3], new[:3])
            else:
                self.assertEqual(old, new)

    def test_empty_row_keeps_its_label(self):
        after, _changes = run()
        self.assertIn("\n族語：\n華語：稍待一會兒 我們\n", after)


class TestWhatIsApplied(unittest.TestCase):
    def test_rules_programme_merge_and_fix(self):
        after, _changes = run(
            fixes=[apply.Fix(NAME, 1, "likavungg", "Likavung", "播出端錯字",
                             "看圖確認")],
            merges=[apply.Merge(NAME, 4, "mena' u", "mena'u", "同一詞")])
        self.assertIn("族語：ay harem i Likavung nanta\n", after)
        self.assertIn("族語：zi mena'u kana\n", after)
        self.assertIn("族語：Po:long 'a'iyalaeho: a kamok\n", after)
        self.assertIn("華語：收看'a'iyalaeho:\n", after)
        self.assertIn("族語：Puq puq ...\n", after)
        self.assertIn("華語：試試看!\n", after)

    def test_without_a_decision_nothing_beyond_rules_changes(self):
        # 語言別差異、不確定、看不出來：沒有 Fix／Merge，就不動那個詞。
        after, _changes = run()
        self.assertIn("Likavungg", after)
        self.assertIn("族語：zi mena' u kana\n", after)

    def test_whole_word_only_and_capital_kept(self):
        after, _changes = run(fixes=[
            apply.Fix(NAME, 2, "kako", "kaku", "播出端錯字", "測試")])
        self.assertIn("族語：Kaku kakoay kaku\n", after)

    def test_a_fix_pointing_at_the_wrong_entry_stops(self):
        # 出現位置對錯一條，改的就是別條字幕——寧可中止。
        with self.assertRaises(PipelineError) as caught:
            run(fixes=[apply.Fix(NAME, 5, "kako", "kaku", "播出端錯字",
                                 "測試")])
        self.assertIn("第 5 條", str(caught.exception))


class TestChanges(unittest.TestCase):
    def test_one_row_per_change_chained(self):
        _after, changes = run(fixes=[
            apply.Fix(NAME, 1, "likavungg", "Likavung", "播出端錯字",
                      "看圖確認")])
        first = []
        for change in changes:
            if change.number == 1:
                first.append(change)
        kinds = []
        for change in first:
            kinds.append(change.kind)
        self.assertEqual(kinds, ["多餘空白", "播出端錯字"])
        self.assertEqual(first[0].before, "ay harem i  Likavungg nanta")
        self.assertEqual(first[0].after, first[1].before)
        self.assertEqual(first[1].after, "ay harem i Likavung nanta")
        self.assertEqual(first[0].row, "族語")
        self.assertEqual(first[0].start, "00:00:09,500")

    def test_rows_for_the_table(self):
        _after, changes = run()
        rows = apply.change_rows(changes)
        self.assertEqual(rows[0], apply.CHANGE_HEADER)
        self.assertEqual(rows[0], ["成果檔名", "字幕編號", "開始時間",
                                   "結束時間", "列", "修改前", "修改後", "類別",
                                   "依據"])
        kinds = set()
        for row in rows[1:]:
            kinds.add(row[7])
        self.assertEqual(kinds, {"多餘空白", "節目名", "重複標點", "撇號"})


if __name__ == "__main__":
    unittest.main()
