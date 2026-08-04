"""make_srt: the slate guard, source priority, and rebuild's missing-input
failure (the srt-data-store spec's "缺件時明確失敗" scenario)."""
import os
import tempfile
import unittest
from unittest import mock

from scripts.news import make_srt
from scripts.news import paths
from scripts.news import rebuild


def record(index, start, end, ocr="", aligned=""):
    return {"index": index, "start": start, "end": end,
            "ocr": ocr, "aligned": aligned, "source": "",
            "coverage": 0.0, "compactness": 0.0}


class TestDropLeader(unittest.TestCase):
    def test_cue_opening_on_frame_zero_is_blanked(self):
        # broadcast masters open on bars and a slate whose white text sits in
        # the subtitle band; a cue starting at 0.0 cannot be dialogue
        records = [record(1, 0.0, 14.0, ocr="x2同。"),
                   record(2, 15.0, 18.0, ocr="真正的第一句")]
        got = make_srt.drop_leader(records)
        self.assertEqual(got[0]["ocr"], "")
        self.assertEqual(got[1]["ocr"], "真正的第一句")

    def test_nothing_after_half_a_second_is_touched(self):
        records = [record(1, 5.8, 8.0, ocr="最早的真實字幕")]
        got = make_srt.drop_leader(records)
        self.assertEqual(got[0]["ocr"], "最早的真實字幕")


class TestSourcePriority(unittest.TestCase):
    RECORDS = [record(1, 0.0, 1.0, ocr="辨識的字", aligned="文稿的字"),
               record(2, 1.0, 2.0, ocr="只有辨識"),
               record(3, 2.0, 3.0)]

    def test_best_prefers_aligned_and_falls_back_to_ocr(self):
        got = make_srt.entries_from(self.RECORDS, "best")
        self.assertEqual(got, [(0.0, 1.0, "文稿的字"),
                               (1.0, 2.0, "只有辨識")])

    def test_rtf_only_never_ships_recogniser_text(self):
        got = make_srt.entries_from(self.RECORDS, "rtf")
        self.assertEqual(got, [(0.0, 1.0, "文稿的字")])


class TestRebuildMissingInputs(unittest.TestCase):
    """Missing pieces are named and fail the run -- no partial delivery."""

    ENTRY = {"srt_name": "20210201_032_午間_Atayal_泰雅", "truncated": ""}

    def test_missing_cues_json_is_named(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty = os.path.join(tmp, "empty")
            os.makedirs(empty)
            with mock.patch.object(paths, "KARI_CUES", empty), \
                    mock.patch.object(paths, "KARI_VISION", empty), \
                    mock.patch.object(paths, "KARI_VISION_RTF", empty), \
                    mock.patch.object(paths, "SRT_DIR", empty):
                problems = rebuild.check_inputs([dict(self.ENTRY)])
        text = "\n".join(problems)
        self.assertIn("cues/20210201_032_午間_Atayal_泰雅.json", text)
        self.assertIn("no vision TSVs", text)

    def test_truncated_episodes_need_no_inputs(self):
        entry = {"srt_name": "whatever", "truncated": "上傳不完整"}
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(paths, "KARI_CUES", tmp), \
                    mock.patch.object(paths, "KARI_VISION", tmp), \
                    mock.patch.object(paths, "KARI_VISION_RTF", tmp), \
                    mock.patch.object(paths, "SRT_DIR", tmp):
                problems = rebuild.check_inputs([entry])
        self.assertEqual(problems, [])


if __name__ == "__main__":
    unittest.main()
