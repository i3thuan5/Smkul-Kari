"""load: the two sides of an episode, read the way the alignment needs
them -- sapolita segments with their VAD boundaries, store cues with
their true windows (not the padded SRT ones)."""
import json
import os
import shutil
import tempfile
import unittest

from scripts.mt import load

SAPOLITA = """1
00:00:15,623 --> 00:00:33,781
族語：polong a salikaka ngaʼay ho
華語：大家好

2
00:00:33,781 --> 00:00:53,609
族語：o sapilacal nangra tayni
華語：

3
00:01:00,000 --> 00:01:05,000
族語：tada ko
"""


class TestWhisperSegments(unittest.TestCase):
    def test_reads_both_labelled_rows(self):
        segs = load.whisper_segments(SAPOLITA)
        self.assertEqual(len(segs), 3)
        self.assertEqual(segs[0]["formosan"], "polong a salikaka ngaʼay ho")
        self.assertEqual(segs[0]["han"], "大家好")
        self.assertAlmostEqual(segs[0]["start"], 15.623)
        self.assertAlmostEqual(segs[0]["end"], 33.781)

    def test_empty_or_missing_han_row_is_empty_string(self):
        segs = load.whisper_segments(SAPOLITA)
        self.assertEqual(segs[1]["han"], "")
        self.assertEqual(segs[2]["han"], "")
        self.assertEqual(segs[2]["formosan"], "tada ko")

    def test_index_is_position_not_srt_number(self):
        segs = load.whisper_segments(SAPOLITA)
        self.assertEqual([s["index"] for s in segs], [0, 1, 2])


class TestStoreEntries(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mt-load-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.cues = os.path.join(self.tmp, "ep.json")
        self.vision = os.path.join(self.tmp, "ep")
        os.makedirs(self.vision)

    def _write(self, cues, rows):
        with open(self.cues, "w", encoding="utf-8") as handle:
            json.dump({"cues": cues, "duration": 100.0}, handle)
        with open(os.path.join(self.vision, "b01.tsv"), "w",
                  encoding="utf-8") as handle:
            for row in rows:
                handle.write("\t".join(row) + "\n")

    def test_true_window_kept_beside_padded_one(self):
        self._write(
            [{"index": 1, "start": 10.0, "end": 13.0},
             {"index": 2, "start": 20.0, "end": 23.0}],
            [("1", "han", "大家好"), ("2", "han", "新聞一開始")])
        entries = load.store_entries(self.cues, self.vision)
        self.assertEqual(len(entries), 2)
        self.assertAlmostEqual(entries[0]["true_start"], 10.0)
        self.assertAlmostEqual(entries[0]["true_end"], 13.0)
        # SRT padding is 0.5 s each side; the alignment must not see it
        self.assertAlmostEqual(entries[0]["srt_start"], 9.5)
        self.assertEqual(entries[0]["han"], "大家好")
        self.assertEqual(entries[0]["cues"], [1])

    def test_same_text_consecutive_cues_fuse_and_keep_both_ids(self):
        # a moving background splits one subtitle into two cues
        self._write(
            [{"index": 1, "start": 10.0, "end": 12.0},
             {"index": 2, "start": 12.0, "end": 14.0}],
            [("1", "han", "同一句"), ("2", "han", "同一句")])
        entries = load.store_entries(self.cues, self.vision)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["cues"], [1, 2])
        self.assertAlmostEqual(entries[0]["true_end"], 14.0)

    def test_blank_cues_are_not_entries(self):
        self._write(
            [{"index": 1, "start": 10.0, "end": 12.0},
             {"index": 2, "start": 12.0, "end": 14.0}],
            [("1", "han", ""), ("2", "han", "有字")])
        entries = load.store_entries(self.cues, self.vision)
        self.assertEqual([e["han"] for e in entries], ["有字"])

    def test_two_row_programme_keeps_both_rows(self):
        self._write(
            [{"index": 1, "start": 10.0, "end": 12.0}],
            [("1", "formosan", "Nga'ay ho^"), ("1", "han", "大家好")])
        entries = load.store_entries(self.cues, self.vision)
        self.assertEqual(entries[0]["formosan"], "Nga'ay ho^")
        self.assertEqual(entries[0]["han"], "大家好")

    def test_leader_slate_cue_at_zero_is_dropped_for_news(self):
        self._write(
            [{"index": 1, "start": 0.0, "end": 14.0},
             {"index": 2, "start": 14.0, "end": 17.0}],
            [("1", "han", "x2同。"), ("2", "han", "大家好")])
        entries = load.store_entries(self.cues, self.vision,
                                     drop_leader=True)
        self.assertEqual([e["han"] for e in entries], ["大家好"])


if __name__ == "__main__":
    unittest.main()
