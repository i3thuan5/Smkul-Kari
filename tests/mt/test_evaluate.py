"""evaluate: a method's groups against the text-based truth.

A group is (segments, entries). Its truth is the union of the entries
the segments' words came from, weighted by how many gold words each
entry carries -- a straddling one-word cue must not count as much as a
ten-word one."""
import unittest

from scripts.mt import evaluate


# truth per segment: {entry: (matched_words, total_words)}
TRUTH = {
    0: {"entries": {0: (5, 5), 1: (3, 6)}, "match_rate": 0.9},
    1: {"entries": {1: (3, 6), 2: (4, 4)}, "match_rate": 0.9},
    2: {"entries": {}, "match_rate": 0.0},
}
WORDS = {0: 5, 1: 6, 2: 4, 3: 7}


class TestGroupScore(unittest.TestCase):
    def test_perfect_group(self):
        score = evaluate.group_score({"segs": [0], "entries": [0, 1]},
                                     TRUTH, WORDS)
        self.assertAlmostEqual(score["precision"], 1.0)
        self.assertAlmostEqual(score["recall"], 1.0)

    def test_extra_entry_lowers_precision(self):
        score = evaluate.group_score({"segs": [0], "entries": [0, 1, 3]},
                                     TRUTH, WORDS)
        # 11 gold-backed words out of 18 entry words
        self.assertAlmostEqual(score["precision"], 11.0 / 18.0)
        self.assertAlmostEqual(score["recall"], 1.0)

    def test_missing_entry_lowers_recall(self):
        score = evaluate.group_score({"segs": [0], "entries": [0]},
                                     TRUTH, WORDS)
        self.assertAlmostEqual(score["precision"], 1.0)
        # entry 1 contributed 3 matched words of the 8 the segment covers
        self.assertAlmostEqual(score["recall"], 5.0 / 8.0)

    def test_merged_segments_pool_their_truth(self):
        score = evaluate.group_score({"segs": [0, 1], "entries": [0, 1, 2]},
                                     TRUTH, WORDS)
        self.assertAlmostEqual(score["precision"], 1.0)
        self.assertAlmostEqual(score["recall"], 1.0)

    def test_segment_with_no_truth_is_flagged(self):
        score = evaluate.group_score({"segs": [2], "entries": [3]},
                                     TRUTH, WORDS)
        self.assertEqual(score["precision"], 0.0)
        self.assertTrue(score["no_truth"])

    def test_strict_needs_the_exact_truth_set_lax_any_overlap(self):
        # truth of seg 0 is entries {0, 1}; entry 1 only half matched
        exact = evaluate.group_score({"segs": [0], "entries": [0, 1]},
                                     TRUTH, WORDS)
        self.assertTrue(exact["strict"])
        self.assertTrue(exact["lax"])
        extra = evaluate.group_score({"segs": [0], "entries": [0, 1, 3]},
                                     TRUTH, WORDS)
        self.assertFalse(extra["strict"])
        self.assertTrue(extra["lax"])
        wrong = evaluate.group_score({"segs": [0], "entries": [3]},
                                     TRUTH, WORDS)
        self.assertFalse(wrong["lax"])


class TestSummary(unittest.TestCase):
    def test_correct_is_both_above_threshold(self):
        groups = [{"segs": [0], "entries": [0, 1]},
                  {"segs": [1], "entries": [2]},
                  {"segs": [2], "entries": [3]}]
        summary = evaluate.summarize(groups, TRUTH, WORDS, threshold=0.8)
        self.assertEqual(summary["groups"], 3)
        self.assertEqual(summary["correct"], 1)
        # gold words: seg0 8 + seg1 7 = 15; group 0 recovers 8 of them
        self.assertAlmostEqual(summary["gold_word_recall"], 8.0 / 15.0)


class TestAuc(unittest.TestCase):
    def test_separable_is_one_and_reversed_is_zero(self):
        self.assertAlmostEqual(evaluate.auc([0.9, 0.8], [0.1, 0.2]), 1.0)
        self.assertAlmostEqual(evaluate.auc([0.1, 0.2], [0.9, 0.8]), 0.0)

    def test_ties_count_half(self):
        self.assertAlmostEqual(evaluate.auc([0.5], [0.5]), 0.5)

    def test_empty_side_is_nan(self):
        self.assertTrue(evaluate.auc([], [0.5]) != evaluate.auc([], [0.5]))


class TestRetention(unittest.TestCase):
    def test_threshold_sweep_reports_kept_good_and_bad(self):
        good = [0.9, 0.7, 0.4]
        bad = [0.6, 0.2]
        table = evaluate.retention(good, bad, thresholds=[0.5, 0.65])
        self.assertEqual(table[0]["threshold"], 0.5)
        self.assertAlmostEqual(table[0]["good_kept"], 2 / 3)
        self.assertAlmostEqual(table[0]["bad_kept"], 1 / 2)
        self.assertAlmostEqual(table[0]["precision"], 2 / 3)
        self.assertAlmostEqual(table[1]["good_kept"], 2 / 3)
        self.assertAlmostEqual(table[1]["bad_kept"], 0.0)


if __name__ == "__main__":
    unittest.main()
