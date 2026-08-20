"""detect: the comparison unit is one Chinese sentence of the subtitle.

Each entry carries `sent_end` -- would its line end in a full stop or a
comma, judged from the subtitle's own semantics. A block is the run of
entries up to the next full stop and never crosses one: VSO/SVO word
order may scramble inside a sentence, never beyond it.
"""
import unittest

from scripts.asrmt.align import detect
from tests.asrmt import fixtures


def grid(flags):
    entries = fixtures.entries_grid(len(flags))
    for row, flag in zip(entries, flags):
        row["sent_end"] = flag
    return entries


class TestSentenceBlocks(unittest.TestCase):
    def test_runs_end_at_the_full_stop(self):
        # 逗、逗、句。｜句。 -> blocks of 3 and 1
        blocks = detect.build_blocks([], grid([False, False, True, True]))
        self.assertEqual(len(blocks), 2)
        self.assertEqual(blocks[0]["entries"], [0, 1, 2])
        self.assertEqual(blocks[1]["entries"], [3])

    def test_a_block_never_crosses_a_full_stop(self):
        # continuous speech over all four entries must not merge two
        # sentences: the unit is semantic, not acoustic
        entries = grid([True, False, True, True])
        sents = [(0.0, 8.0, "主播一路講不停")]
        blocks = detect.build_blocks(sents, entries)
        self.assertEqual(blocks[0]["entries"], [0])
        self.assertEqual(blocks[1]["entries"], [1, 2])
        self.assertEqual(blocks[2]["entries"], [3])

    def test_an_unlabelled_entry_stands_alone(self):
        entries = fixtures.entries_grid(2)
        blocks = detect.build_blocks([], entries)
        self.assertEqual(len(blocks), 2)

    def test_a_trailing_run_without_a_stop_still_closes(self):
        blocks = detect.build_blocks([], grid([True, False, False]))
        self.assertEqual(blocks[-1]["entries"], [1, 2])

    def test_speech_sentences_ride_along_by_overlap(self):
        entries = grid([False, True])
        sents = [(0.5, 3.5, "壓住整句的語音"), (30.0, 32.0, "遠處")]
        blocks = detect.build_blocks(sents, entries)
        self.assertEqual(blocks[0]["sents"], [0])


class TestMergeGroups(unittest.TestCase):
    """使用者裁定：交錯的句子用「合併」處理，不移時間——DP 跨塊配對
    與 offset 的位移窗落到鄰塊，都是把相鄰語意句聯併的證據。"""

    def _doc(self, entries, classes, deltas=None, matched=None):
        blocks = detect.build_blocks([], entries)
        block_of = {}
        for pos, block in enumerate(blocks):
            for j in block["entries"]:
                block_of[entries[j]["index"]] = pos
        records = []
        for row in entries:
            index = row["index"]
            records.append({
                "index": index, "block": block_of[index],
                "class": classes.get(index, "ok"),
                "best_delta": (deltas or {}).get(index, 0.0),
            })
        return {"entries": records, "matched_entries": matched or []}

    def test_no_evidence_keeps_blocks_as_groups(self):
        entries = grid([True, True])
        doc = self._doc(entries, {1: "ok", 2: "ok"})
        groups = detect.merge_groups(doc, entries)
        self.assertNotEqual(groups[1], groups[2])

    def test_dp_pairing_across_blocks_unions_them(self):
        # 語音側條1 對到字幕側條1+2（跨兩塊）→ 兩句聯併
        entries = grid([True, True])
        doc = self._doc(entries, {1: "mismatch", 2: "mismatch"},
                        matched=[{"a": (0, 1), "b": (0, 2),
                                  "score": 0.3}])
        groups = detect.merge_groups(doc, entries)
        self.assertEqual(groups[1], groups[2])

    def test_weak_dp_pairing_is_ignored(self):
        entries = grid([True, True])
        doc = self._doc(entries, {1: "mismatch", 2: "mismatch"},
                        matched=[{"a": (0, 1), "b": (0, 2),
                                  "score": 0.05}])
        groups = detect.merge_groups(doc, entries)
        self.assertNotEqual(groups[1], groups[2])

    def test_offset_shifted_window_unions_with_its_neighbour(self):
        # 條2 的最佳 δ=-2.0：位移窗落回條1 的塊 → 兩句聯併
        entries = grid([True, True])
        doc = self._doc(entries, {1: "ok", 2: "offset"},
                        deltas={2: -2.0})
        groups = detect.merge_groups(doc, entries)
        self.assertEqual(groups[1], groups[2])

    def test_a_span_cap_stops_runaway_chains(self):
        # 證據鏈把四句連環時，超過時距上限的聯併被擋下
        entries = grid([True] * 4)   # 每條 2s，四塊
        doc = self._doc(entries, {1: "mismatch", 2: "mismatch",
                                  3: "mismatch", 4: "mismatch"},
                        matched=[{"a": (0, 1), "b": (0, 2), "score": .5},
                                 {"a": (1, 2), "b": (1, 3), "score": .4},
                                 {"a": (2, 3), "b": (2, 4), "score": .3}])
        groups = detect.merge_groups(doc, entries, max_span=5.0)
        spans = {}
        for row in entries:
            g = groups[row["index"]]
            spans.setdefault(g, [row["true_start"], row["true_end"]])
            spans[g][0] = min(spans[g][0], row["true_start"])
            spans[g][1] = max(spans[g][1], row["true_end"])
        for lo, hi in spans.values():
            self.assertLessEqual(hi - lo, 5.0)

    def test_groups_close_over_the_consecutive_range(self):
        # 塊0 與塊2 被證據連起來時，夾在中間的塊1 一併納入
        entries = grid([True, True, True])
        doc = self._doc(entries, {1: "mismatch", 3: "mismatch"},
                        matched=[{"a": (0, 1), "b": (0, 3),
                                  "score": 0.4}])
        groups = detect.merge_groups(doc, entries)
        self.assertEqual(groups[1], groups[2])
        self.assertEqual(groups[2], groups[3])


class TestWindowedAnchors(unittest.TestCase):
    def test_far_away_word_is_not_a_hit(self):
        numerals = {"3": ["tolo"]}
        words = [fixtures.word("tolo", 381.0, 381.5)]
        hits = detect.match_anchors([3], words, numerals,
                                    lo=16.0, hi=46.0)
        self.assertEqual(hits, [])

    def test_nearby_word_is_a_hit(self):
        numerals = {"3": ["tolo"]}
        words = [fixtures.word("tolo", 30.0, 30.5)]
        hits = detect.match_anchors([3], words, numerals,
                                    lo=16.0, hi=46.0)
        self.assertEqual(len(hits), 1)

    def test_provided_number_words_override_the_regex(self):
        # CKIP 斷詞後「新聞一開始」不含獨立數詞 → 呼叫端給空清單
        entries = fixtures.entries_grid(1, subtitle_of=lambda i:
                                        "新聞一開始")
        for row in entries:
            row["word_i"] = []
            row["formosan"] = ""
            row["zh"] = {"ailabs": "", "claude": ""}
            row["formosan_from_zh"] = {"ailabs": "", "claude": ""}
        doc = detect.diagnose("試", entries, [], [],
                              numerals={"1": ["cecay"]},
                              numbers_by_entry={1: []})
        self.assertEqual(doc["anchors"], [])


if __name__ == "__main__":
    unittest.main()
