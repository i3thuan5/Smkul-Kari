"""讀交付 SRT 的兩列，並從字幕編號找回 cue 與原生圖條。

看圖要送原生圖條（1920×60），組合圖的解析度分不出撇號與字距。
兩個量到的坑：

  圖條路徑      1-cues 清單寫 `strips/t…_formosan.png`（舊名），實際
                目錄是 `2-strips/`；照清單拼路徑會找不到
  一條多個 cue  相鄰同文字的 cue 被 merge_repeats 併成一條字幕；看圖
                只送第一個 cue，另一張圖上的字就沒人看
"""
import os
import unittest

from scripts.aiyalaeho.cleaning import source
from scripts.errors import PipelineError
from tests.aiyalaeho.cleaning import fixtures

NAME = "開會了_087_Pinuyumayan_卑南"


class SourceCase(unittest.TestCase):
    def setUp(self):
        self.store = fixtures.Store()
        self.store.episode(NAME, [
            (10.0, 12.0, "ay harem i  Likavungg", "介紹利嘉部落"),
            (12.0, 14.0, "kemazu i kanta", "我們也是一樣"),
            (14.0, 16.0, "kemazu i kanta", "我們也是一樣"),
            (16.0, 18.0, "", "稍待一會兒  我們"),
            (18.0, 20.0, "zi mena’   u", "放眼看"),
        ])

    def cue_map(self):
        return source.cue_map(NAME, self.store.cues_dir,
                              self.store.vision_dir)


class TestReadSrt(SourceCase):
    def test_entries_keep_number_time_and_both_rows(self):
        entries = source.read_srt(self.store.srt_path(NAME))
        self.assertEqual(len(entries), 4)
        first = entries[0]
        self.assertEqual(first.number, 1)
        self.assertEqual(first.start, "00:00:09,500")
        self.assertEqual(first.formosan, "ay harem i  Likavungg")
        self.assertEqual(first.han, "介紹利嘉部落")

    def test_an_empty_row_is_an_empty_string(self):
        entries = source.read_srt(self.store.srt_path(NAME))
        self.assertEqual(entries[2].formosan, "")
        self.assertEqual(entries[2].han, "稍待一會兒  我們")


class TestCueMap(SourceCase):
    def test_a_merged_entry_maps_to_every_cue_it_came_from(self):
        mapping = self.cue_map()
        self.assertEqual(sorted(mapping), [1, 2, 3, 4])
        indices = []
        for cue in mapping[2]:
            indices.append(cue["index"])
        self.assertEqual(indices, [2, 3])

    def test_strips_resolve_to_the_numbered_stage_folder(self):
        mapping = self.cue_map()
        got = source.strips(NAME, mapping[2], self.store.work_root)
        self.assertEqual(len(got), 2)
        for path in got:
            self.assertIn(os.sep + "2-strips" + os.sep, path)
            self.assertTrue(path.endswith("_formosan.png"))
            self.assertTrue(os.path.exists(path))

    def test_a_missing_strip_names_episode_and_entry(self):
        mapping = self.cue_map()
        os.remove(source.strips(NAME, mapping[4], self.store.work_root)[0])
        with self.assertRaises(PipelineError) as caught:
            source.strips(NAME, mapping[4], self.store.work_root)
        self.assertIn(NAME, str(caught.exception))
        self.assertIn("cue 5", str(caught.exception))

    def test_mapping_disagreeing_with_the_srt_stops(self):
        # 2-vision 被改過、3-srt 沒重組：對應會錯位，要當場擋。
        path = os.path.join(self.store.vision_dir, NAME, "b01.tsv")
        with open(path, encoding="utf-8") as handle:
            body = handle.read()
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(body.replace("kemazu i kanta", "kemazu", 1))
        with self.assertRaises(PipelineError):
            source.checked_cue_map(NAME, self.store.srt_path(NAME),
                                   self.store.cues_dir,
                                   self.store.vision_dir)


OTHER = "開會了_119_Bunun_布農"


class TestLanguageMarks(SourceCase):
    """逐條語言標記：b、c 與語言別推測只看本族語的列。

    布農 111／119／122 是多族來賓的集，各約 225 條被標「無法確定」（119
    疑似賽夏 88、排灣 60、雅美 45、噶瑪蘭 30）；照舊整集拿去比布農辭典，
    布農會冒出 3,944 個查無詞形，119 的郡群覆蓋率掉到 24%。
    """

    def marks_path(self, rows):
        path = os.path.join(self.store.root, "逐條語言標記.csv")
        return fixtures.write_marks(path, rows)

    def entries(self):
        return source.read_srt(self.store.srt_path(NAME))

    def full_rows(self, labels):
        rows = [(OTHER, 1, "純族語")]
        for number, label in enumerate(labels, start=1):
            rows.append((NAME, number, label))
        return rows

    def test_marks_keyed_by_entry_number(self):
        path = self.marks_path(self.full_rows(
            ["純族語", "族語夾雜華語", "華語", "無法確定"]))
        marks = source.language_marks(NAME, self.entries(), path)
        self.assertEqual(marks, {1: "純族語", 2: "族語夾雜華語", 3: "華語",
                                 4: "無法確定"})

    def test_own_language_keeps_pure_and_mixed_only(self):
        # 「華語」是族語列空白；「無法確定」是別族來賓。兩種都不進
        # b、c，但 a 項照做（那是呼叫端的事，這裡只篩）。
        path = self.marks_path(self.full_rows(
            ["純族語", "族語夾雜華語", "華語", "無法確定"]))
        entries = self.entries()
        kept = source.own_language(
            entries, source.language_marks(NAME, entries, path))
        numbers = []
        for entry in kept:
            numbers.append(entry.number)
        self.assertEqual(numbers, [1, 2])

    def test_labels_come_from_langcheck_constants(self):
        # 標籤用字面值比對的話，langcheck 改措辭後全部列被篩掉、候選
        # 變空也不會報錯。
        from scripts.aiyalaeho.langcheck import mark
        self.assertEqual(source.OWN_LANGUAGE, (mark.PURE, mark.MIXED))

    def test_missing_entry_names_episode_and_number(self):
        # 交付 SRT 重組過、多了一條，逐條語言標記沒跟著重建。
        rows = self.full_rows(["純族語", "純族語", "純族語"])
        with self.assertRaises(PipelineError) as caught:
            source.language_marks(NAME, self.entries(), self.marks_path(rows))
        self.assertIn(NAME, str(caught.exception))
        self.assertIn("4", str(caught.exception))

    def test_extra_number_names_episode_and_number(self):
        rows = self.full_rows(["純族語"] * 4) + [(NAME, 9, "純族語")]
        with self.assertRaises(PipelineError) as caught:
            source.language_marks(NAME, self.entries(), self.marks_path(rows))
        self.assertIn(NAME, str(caught.exception))
        self.assertIn("9", str(caught.exception))

    def test_duplicate_number_stops(self):
        rows = self.full_rows(["純族語"] * 4) + [(NAME, 2, "華語")]
        with self.assertRaises(PipelineError) as caught:
            source.language_marks(NAME, self.entries(), self.marks_path(rows))
        self.assertIn("2", str(caught.exception))

    def test_multi_guest_episode_is_one_in_ten_unsure(self):
        # 布農 111／119／122 的「無法確定」佔 23.5%／22.0%／27.1%；其他
        # 集最高是阿美 082 的 6.0%。門檻一成，切在兩群中間。
        self.assertTrue(source.multi_guest({1: "純族語", 2: "無法確定",
                                            3: "純族語", 4: "華語"}))
        marks = {}
        for number in range(1, 18):
            marks[number] = "純族語"
        marks[18] = "無法確定"
        self.assertFalse(source.multi_guest(marks))
        marks[19] = "無法確定"
        self.assertTrue(source.multi_guest(marks))

    def test_episode_absent_from_marks_stops(self):
        with self.assertRaises(PipelineError) as caught:
            source.language_marks(NAME, self.entries(),
                                  self.marks_path([(OTHER, 1, "純族語")]))
        self.assertIn(NAME, str(caught.exception))


if __name__ == "__main__":
    unittest.main()
