"""detect: the attribution matrix and the diagnostic record.

Every entry gets one of five classes, each decision traceable to the
scores that made it (歸因可追溯), the thresholds ride along marked
uncalibrated until the human pass, and running detection changes nothing
it read (偵測是唯讀的 -- enforced structurally: diagnose() only returns
a document).
"""
import unittest

from scripts.asrmt.align import detect
from tests.asrmt import fixtures


def diag(word_i=(0,), conf=0.95, block_score=0.8, entry_score=0.8,
         recovered=0.0, agreement=0.9):
    scores = {"ailabs": block_score, "claude": max(0.0, block_score - 0.1)}
    entry_scores = {"ailabs": entry_score,
                    "claude": max(0.0, entry_score - 0.1)}
    return {
        "word_i": list(word_i), "avg_conf": conf,
        "block_score": scores, "entry_score": entry_scores,
        "engine_agreement": agreement, "recovered": recovered,
    }


class TestMatrix(unittest.TestCase):
    def _cls(self, row):
        return detect.classify(row, detect.DEFAULT_THRESHOLDS)

    def test_no_words_is_no_speech(self):
        self.assertEqual(self._cls(diag(word_i=())), "no-speech")

    def test_good_content_is_ok(self):
        self.assertEqual(self._cls(diag(block_score=0.7)), "ok")

    def test_block_score_rescues_a_low_entry_score(self):
        # 語序倒置：條目級低分、塊級高分 -> 不誤報
        row = diag(block_score=0.8, entry_score=0.05)
        self.assertEqual(self._cls(row), "ok")

    def test_one_engine_matching_is_enough(self):
        row = diag(block_score=0.05)
        row["block_score"] = {"ailabs": 0.05, "claude": 0.6}
        self.assertEqual(self._cls(row), "ok")

    def test_low_score_low_conf_is_asr_doubt(self):
        row = diag(block_score=0.1, entry_score=0.1, conf=0.4)
        self.assertEqual(self._cls(row), "asr-doubt")

    def test_low_score_recovered_by_shift_is_offset(self):
        row = diag(block_score=0.1, entry_score=0.1, recovered=0.7)
        self.assertEqual(self._cls(row), "offset")

    def test_otherwise_mismatch(self):
        row = diag(block_score=0.1, entry_score=0.1)
        self.assertEqual(self._cls(row), "mismatch")


class TestDiagnose(unittest.TestCase):
    def _run(self):
        entries = fixtures.entries_grid(2, subtitle_of=lambda i:
                                        ["今天主持", "介紹部落"][i])
        for row in entries:
            row["word_i"] = []
            row["formosan"] = ""
            row["zh"] = {"ailabs": "", "claude": ""}
            row["formosan_from_zh"] = {"ailabs": "", "claude": ""}
        entries[0]["word_i"] = [0, 1]
        entries[0]["formosan"] = "mikeriday anini"
        entries[0]["zh"] = {"ailabs": "今天主持", "claude": "今天由我主持"}
        words = fixtures.words_evenly("mikeriday anini", 0.2, 1.8)
        sents = [(0.2, 1.8, "mikeriday anini")]
        return detect.diagnose("試集", entries, words, sents)

    def test_document_carries_uncalibrated_thresholds(self):
        doc = self._run()
        self.assertFalse(doc["calibrated"])
        self.assertEqual(doc["thresholds"], detect.DEFAULT_THRESHOLDS)

    def test_every_entry_has_a_traceable_record(self):
        doc = self._run()
        self.assertEqual(len(doc["entries"]), 2)
        first = doc["entries"][0]
        self.assertIn("class", first)
        self.assertIn("block_score", first)
        self.assertIn("avg_conf", first)
        self.assertEqual(doc["entries"][1]["class"], "no-speech")

    def test_summary_names_every_class_count(self):
        doc = self._run()
        text = detect.summary_md(doc)
        self.assertIn("no-speech", text)
        self.assertIn("尚未校準", text)

    def test_summary_carries_the_block_view_when_entries_given(self):
        entries = fixtures.entries_grid(2, subtitle_of=lambda i:
                                        ["前半", "後半"][i])
        entries[0]["sent_end"] = False
        entries[1]["sent_end"] = True
        for row in entries:
            row["word_i"] = [0]
            row["formosan"] = "kako"
            row["zh"] = {"ailabs": "", "claude": ""}
            row["formosan_from_zh"] = {"ailabs": "", "claude": ""}
        words = [fixtures.word("kako", 0.2, 0.6)]
        doc = detect.diagnose("試集", entries, words, [])
        text = detect.summary_md(doc, entries)
        self.assertIn("┌", text)          # 新句開始
        self.assertIn("│", text)          # 同句延續
        self.assertIn("前半，", text)      # 逗號＝句未完
        self.assertIn("後半。", text)      # 句號＝句尾
        self.assertIn("[", text)          # 歸類註記


class TestMatchedEntries(unittest.TestCase):
    def test_low_scoring_entries_get_a_recovered_pairing(self):
        # crossed pair: per-entry scores low, merged high -> the DP binds
        # entries 1 and 2 into one matched group
        entries = fixtures.entries_grid(2)
        entries[0]["subtitle"] = "我在教會"
        entries[1]["subtitle"] = "牧會"
        entries[0]["zh"] = {"ailabs": "我牧會", "claude": ""}
        entries[1]["zh"] = {"ailabs": "這個教會", "claude": ""}
        matches = detect.recover_pairs(entries)
        self.assertTrue(matches)
        self.assertEqual(matches[0]["b"], (0, 2))


if __name__ == "__main__":
    unittest.main()
