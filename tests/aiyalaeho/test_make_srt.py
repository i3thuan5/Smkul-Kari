"""make_srt: two labelled rows per entry, on the shared assembly chain.

The delivered format is the one the speech side already uses -- 族語：／
華語： -- so a reader never has to work out which row is which language,
and an empty row is visibly empty rather than missing.
"""
import json
import os
import shutil
import tempfile
import unittest

from scripts import datadirs
from scripts.aiyalaeho import make_srt


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="aiya-srt-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.work = os.path.join(self.tmp, "work")
        os.makedirs(self.work)
        self.out = os.path.join(self.tmp, "out.srt")

    def build(self, cues, texts, duration=None):
        manifest = {
            "lines": [{"name": "formosan", "y": 12, "h": 60},
                      {"name": "han", "y": 72, "h": 64}],
            "cues": cues,
        }
        if duration is not None:
            manifest["duration"] = duration
        os.makedirs(os.path.join(self.work, "1-cues"), exist_ok=True)
        with open(datadirs.coarse_cues(self.work), "w",
                  encoding="utf-8") as handle:
            json.dump(manifest, handle, ensure_ascii=False)
        with open(os.path.join(self.work, "transcripts.json"), "w",
                  encoding="utf-8") as handle:
            json.dump(texts, handle, ensure_ascii=False)
        return make_srt.run(self.work, self.out)

    def body(self):
        with open(self.out, encoding="utf-8") as handle:
            return handle.read()

    def blocks(self):
        out = []
        for chunk in self.body().strip().split("\n\n"):
            if chunk.strip():
                out.append(chunk.split("\n"))
        return out


def cue(index, start, end):
    return {"index": index, "start": start, "end": end}


class TestTwoLabelledRows(unittest.TestCase):
    def test_the_labels_are_the_speech_side_ones(self):
        self.assertEqual(make_srt.LABELS,
                         (("formosan", "族語："), ("han", "華語：")))


class TestEntries(Fixture):
    def test_an_entry_carries_both_rows(self):
        self.build([cue(1, 10.0, 14.0)],
                   {"1": {"formosan": "Nga'ay ho^", "han": "大家好"}})
        self.assertEqual(self.blocks()[0][2:],
                         ["族語：Nga'ay ho^", "華語：大家好"])

    def test_an_empty_formosan_row_keeps_its_label(self):
        # 讀ê人愛分會出「這逝無字幕」佮「漏去一逝」。
        self.build([cue(1, 10.0, 14.0)],
                   {"1": {"formosan": "", "han": "這也就是今天的原因"}})
        self.assertEqual(self.blocks()[0][2:],
                         ["族語：", "華語：這也就是今天的原因"])

    def test_an_empty_han_row_keeps_its_label(self):
        self.build([cue(1, 10.0, 14.0)],
                   {"1": {"formosan": "hosana", "han": ""}})
        self.assertEqual(self.blocks()[0][2:], ["族語：hosana", "華語："])

    def test_a_cue_with_neither_row_is_left_out(self):
        self.build([cue(1, 10.0, 14.0), cue(2, 20.0, 24.0)],
                   {"1": {"formosan": "", "han": ""},
                    "2": {"formosan": "x", "han": "y"}})
        self.assertEqual(len(self.blocks()), 1)

    def test_a_cue_nobody_read_is_left_out(self):
        self.build([cue(1, 10.0, 14.0)], {})
        self.assertEqual(self.body(), "")

    def test_an_episode_with_no_cues_delivers_an_empty_srt(self):
        # 無字幕ê集數（88／90／98）：0 條 cue，0 行 SRT，照常交付。
        qc = self.build([], {})
        self.assertEqual(self.body(), "")
        self.assertEqual(qc["cues"], 0)
        self.assertEqual(qc["srt_lines"], 0)


class TestMerging(Fixture):
    def test_the_same_two_rows_next_to_each_other_merge(self):
        self.build([cue(1, 10.0, 12.0), cue(2, 12.0, 14.0)],
                   {"1": {"formosan": "a", "han": "甲"},
                    "2": {"formosan": "a", "han": "甲"}})
        self.assertEqual(len(self.blocks()), 1)

    def test_one_row_differing_keeps_them_apart(self):
        # 合併愛比兩逝合起來ê字串，毋是干焦比一逝。
        self.build([cue(1, 10.0, 12.0), cue(2, 12.0, 14.0)],
                   {"1": {"formosan": "a", "han": "甲"},
                    "2": {"formosan": "a", "han": "乙"}})
        self.assertEqual(len(self.blocks()), 2)


class TestPadding(Fixture):
    def test_a_lone_entry_gets_half_a_second_each_side(self):
        self.build([cue(1, 10.0, 14.0)], {"1": {"formosan": "a",
                                                "han": "甲"}},
                   duration=100.0)
        self.assertEqual(self.blocks()[0][1],
                         "00:00:09,500 --> 00:00:14,500")

    def test_entries_too_close_meet_at_the_midpoint(self):
        # 1.0–2.0 佮 2.2–3.2：中點 2.1 拄好相接，袂重疊。
        self.build([cue(1, 1.0, 2.0), cue(2, 2.2, 3.2)],
                   {"1": {"formosan": "a", "han": "甲"},
                    "2": {"formosan": "b", "han": "乙"}}, duration=100.0)
        got = self.blocks()
        self.assertEqual(got[0][1], "00:00:00,500 --> 00:00:02,100")
        self.assertEqual(got[1][1], "00:00:02,100 --> 00:00:03,700")

    def test_the_first_entry_never_starts_before_zero(self):
        self.build([cue(1, 0.2, 2.0)], {"1": {"formosan": "a", "han": "甲"}},
                   duration=100.0)
        self.assertTrue(self.blocks()[0][1].startswith("00:00:00,000"))

    def test_the_last_entry_never_runs_past_the_video(self):
        self.build([cue(1, 90.0, 99.8)], {"1": {"formosan": "a",
                                                "han": "甲"}},
                   duration=100.0)
        self.assertTrue(self.blocks()[0][1].endswith("00:01:40,000"))

    def test_padding_never_reaches_the_timeline_on_disk(self):
        # cues.json 永遠存真實切換點；留白干焦佇 SRT 輸出。
        self.build([cue(1, 10.0, 14.0)], {"1": {"formosan": "a",
                                                "han": "甲"}},
                   duration=100.0)
        with open(datadirs.cues_to_read(self.work),
                  encoding="utf-8") as handle:
            manifest = json.load(handle)
        self.assertEqual(manifest["cues"][0]["start"], 10.0)
        self.assertEqual(manifest["cues"][0]["end"], 14.0)


class TestQc(Fixture):
    def test_the_counts_describe_the_episode(self):
        qc = self.build([cue(1, 10.0, 14.0), cue(2, 20.0, 24.0),
                         cue(3, 30.0, 34.0)],
                        {"1": {"formosan": "a", "han": "甲"},
                         "2": {"formosan": "", "han": "乙"},
                         "3": {"formosan": "", "han": ""}})
        self.assertEqual(qc["cues"], 3)
        self.assertEqual(qc["cues_with_text"], 2)
        self.assertEqual(qc["formosan_rows"], 1)
        self.assertEqual(qc["han_rows"], 2)
        self.assertEqual(qc["srt_lines"], 2)


if __name__ == "__main__":
    unittest.main()
