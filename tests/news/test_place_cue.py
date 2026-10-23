"""place_cue：照量好ê秒數插一條 cue，抑是調一條 cue ê起迄。

2026-10-21 20211203_337_晚間 1178–1180 秒「山」「海」兩條單字字幕：空拍
浪花逐格墨量 314–504，比單一字（約 150）較大，切段器切袂開，重切嘛仝款；
「山」規條無 cue，「海」ê cue 416 起點晚 0.58 秒、尾仔閣佮 417 相連。
split_cue 干焦會剖一條有ê cue，所以愛另外一支：量好ê秒數直接插入、調界。
"""
import unittest

from scripts.errors import PipelineError
from scripts.news import place_cue


def cue(index, start, end):
    return {"index": index, "start": start, "end": end, "frames": 3,
            "ink": 900, "sample_ts": start,
            "images": {"han": "2-strips/%05d_han.png" % index}}


def run():
    # 1:0–1  2:1–2  （空檔 2–4）  3:4–5  4:5–6
    return [cue(1, 0.0, 1.0), cue(2, 1.0, 2.0), cue(3, 4.0, 5.0),
            cue(4, 5.0, 6.0)]


class TestInsert(unittest.TestCase):
    def test_lands_in_the_gap_and_takes_the_next_number(self):
        got, index = place_cue.insert(run(), 2.5, 3.5)
        self.assertEqual(index, 3)
        self.assertEqual((got[2]["start"], got[2]["end"]), (2.5, 3.5))

    def test_later_cues_are_renumbered_but_keep_their_strip(self):
        # strip 檔名毋綴新編號走（split_cue 仝款ê理由）
        got, _ = place_cue.insert(run(), 2.5, 3.5)
        self.assertEqual([c["index"] for c in got], [1, 2, 3, 4, 5])
        self.assertEqual(got[3]["images"]["han"], "2-strips/00003_han.png")
        self.assertEqual((got[3]["start"], got[3]["end"]), (4.0, 5.0))

    def test_new_cue_has_no_strip_and_samples_inside_itself(self):
        got, _ = place_cue.insert(run(), 2.5, 3.5)
        self.assertEqual(got[2]["images"], {})
        self.assertTrue(2.5 <= got[2]["sample_ts"] <= 3.5)
        self.assertTrue(got[2]["placed"])

    def test_a_gap_exactly_filled_is_allowed(self):
        got, index = place_cue.insert(run(), 2.0, 4.0)
        self.assertEqual(index, 3)

    def test_overlapping_an_existing_cue_is_an_error(self):
        # 量著ê秒數若硩著別條，先用 bounds 縮彼條，毋通默默疊做伙
        with self.assertRaises(PipelineError):
            place_cue.insert(run(), 1.5, 3.0)
        with self.assertRaises(PipelineError):
            place_cue.insert(run(), 3.0, 4.5)

    def test_before_the_first_cue_takes_number_one(self):
        cues = run()
        cues[0]["start"] = 0.5
        got, index = place_cue.insert(cues, 0.0, 0.5)
        self.assertEqual(index, 1)
        self.assertEqual(got[1]["index"], 2)

    def test_empty_or_reversed_span_is_an_error(self):
        with self.assertRaises(PipelineError):
            place_cue.insert(run(), 3.0, 3.0)
        with self.assertRaises(PipelineError):
            place_cue.insert(run(), 3.5, 2.5)


class TestBounds(unittest.TestCase):
    def test_moves_the_times_and_nothing_else(self):
        got = place_cue.set_bounds(run(), 3, 3.0, 5.0)
        self.assertEqual((got[2]["start"], got[2]["end"]), (3.0, 5.0))
        self.assertEqual(len(got), 4)
        self.assertEqual(got[2]["images"]["han"], "2-strips/00003_han.png")

    def test_sample_ts_follows_into_the_new_span(self):
        got = place_cue.set_bounds(run(), 3, 4.5, 5.0)
        self.assertTrue(4.5 <= got[2]["sample_ts"] <= 5.0)

    def test_running_into_a_neighbour_is_an_error(self):
        # 337 晚 416 延到 1179.80 會硩著 417（1179.745 起）：兩條愛先後調
        with self.assertRaises(PipelineError):
            place_cue.set_bounds(run(), 3, 1.5, 5.0)
        with self.assertRaises(PipelineError):
            place_cue.set_bounds(run(), 3, 4.0, 5.5)

    def test_unknown_cue_is_an_error(self):
        with self.assertRaises(PipelineError):
            place_cue.set_bounds(run(), 9, 4.0, 5.0)


class TestRemap(unittest.TestCase):
    def test_rows_shift_and_the_new_row_is_added(self):
        rows = [(1, "a"), (2, "b"), (3, "c"), (4, "d")]
        got = place_cue.remap_rows(rows, 3, "新")
        self.assertEqual(got, [(1, "a"), (2, "b"), (3, "新"), (4, "c"),
                               (5, "d")])

    def test_rows_of_another_file_only_shift(self):
        got = place_cue.shift_rows([(2, "b"), (3, "c")], 3)
        self.assertEqual(got, [(2, "b"), (4, "c")])

    def test_sheets_shift_and_new_cue_joins_the_previous_ones_sheet(self):
        sheets = {"s1.png": [1, 2], "s2.png": [3, 4]}
        got = place_cue.remap_sheets(sheets, 3)
        self.assertEqual(got, {"s1.png": [1, 2, 3], "s2.png": [4, 5]})

    def test_sheets_new_first_cue_joins_the_first_sheet(self):
        sheets = {"s1.png": [1, 2], "s2.png": [3, 4]}
        got = place_cue.remap_sheets(sheets, 1)
        self.assertEqual(got, {"s1.png": [1, 2, 3], "s2.png": [4, 5]})


if __name__ == "__main__":
    unittest.main()
