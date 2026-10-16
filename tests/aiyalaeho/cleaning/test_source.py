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


if __name__ == "__main__":
    unittest.main()
