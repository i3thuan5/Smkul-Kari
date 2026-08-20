"""dpalign: the banded monotone DP with merge steps.

Pins the speech-subtitle-alignment spec's 配對恢復 requirement: crossed
sentences recovered by a 2-2 merge, splits by 1-2/2-1, unmatched units
skipped at a penalty, nothing matched outside the time band, anchors as
a soft bonus -- and the output monotone by construction.
"""
import unittest

from scripts.asrmt.align import dpalign


def unit(start, end, text):
    return (start, end, text)


def table_sim(table):
    def sim(a_text, b_text):
        return table.get((a_text, b_text), 0.0)
    return sim


class TestDiagonal(unittest.TestCase):
    def test_equal_sequences_match_one_to_one_in_order(self):
        a = [unit(0, 2, "A1"), unit(2, 4, "A2"), unit(4, 6, "A3")]
        b = [unit(0, 2, "B1"), unit(2, 4, "B2"), unit(4, 6, "B3")]
        sim = table_sim({("A1", "B1"): 1.0, ("A2", "B2"): 1.0,
                         ("A3", "B3"): 1.0})
        got = dpalign.align(a, b, sim)
        pairs = []
        for m in got:
            pairs.append((m["a"], m["b"]))
        self.assertEqual(pairs,
                         [((0, 1), (0, 1)), ((1, 2), (1, 2)),
                          ((2, 3), (2, 3))])

    def test_output_is_monotone(self):
        a = [unit(0, 2, "A1"), unit(2, 4, "A2"), unit(4, 6, "A3")]
        b = [unit(0, 2, "B1"), unit(2, 4, "B2"), unit(4, 6, "B3")]
        sim = table_sim({("A1", "B1"): 0.9, ("A2", "B2"): 0.4,
                         ("A3", "B3"): 0.9, ("A2", "B3"): 0.5})
        got = dpalign.align(a, b, sim)
        last_a = -1
        last_b = -1
        for m in got:
            self.assertGreaterEqual(m["a"][0], last_a)
            self.assertGreaterEqual(m["b"][0], last_b)
            last_a = m["a"][1] - 1
            last_b = m["b"][1] - 1


class TestMerges(unittest.TestCase):
    def test_crossed_pair_is_recovered_by_a_two_two_merge(self):
        # VSO vs SVO: the high sims sit on the anti-diagonal, which no
        # monotone 1-1 path can take -- the 2-2 merge collects them.
        a = [unit(0, 2, "我牧會"), unit(2, 4, "這個教會")]
        b = [unit(0, 2, "我在教會"), unit(2, 4, "牧會")]
        sim = table_sim({
            ("我牧會", "我在教會"): 0.15, ("我牧會", "牧會"): 0.9,
            ("這個教會", "我在教會"): 0.7, ("這個教會", "牧會"): 0.0,
            ("我牧會 這個教會", "我在教會 牧會"): 0.9,
        })
        got = dpalign.align(a, b, sim)
        self.assertEqual(len(got), 1)
        self.assertEqual((got[0]["a"], got[0]["b"]), ((0, 2), (0, 2)))

    def test_one_speech_sentence_split_over_two_entries(self):
        a = [unit(0, 4, "整句話")]
        b = [unit(0, 2, "前半"), unit(2, 4, "後半")]
        sim = table_sim({("整句話", "前半"): 0.3, ("整句話", "後半"): 0.3,
                         ("整句話", "前半 後半"): 0.9})
        got = dpalign.align(a, b, sim)
        self.assertEqual(len(got), 1)
        self.assertEqual((got[0]["a"], got[0]["b"]), ((0, 1), (0, 2)))


class TestBandAndSkips(unittest.TestCase):
    def test_nothing_matches_outside_the_time_band(self):
        a = [unit(0, 2, "同文")]
        b = [unit(60, 62, "同文對")]
        sim = table_sim({("同文", "同文對"): 1.0})
        got = dpalign.align(a, b, sim, band_seconds=10.0)
        self.assertEqual(got, [])

    def test_an_extra_entry_is_skipped_not_forced(self):
        a = [unit(0, 2, "A1"), unit(4, 6, "A2")]
        b = [unit(0, 2, "B1"), unit(2, 4, "加譯"), unit(4, 6, "B2")]
        sim = table_sim({("A1", "B1"): 0.9, ("A2", "B2"): 0.9})
        got = dpalign.align(a, b, sim)
        pairs = []
        for m in got:
            pairs.append((m["a"], m["b"]))
        self.assertEqual(pairs, [((0, 1), (0, 1)), ((1, 2), (2, 3))])


class TestBonus(unittest.TestCase):
    def test_anchor_bonus_steers_an_otherwise_even_choice(self):
        a = [unit(0, 2, "甲")]
        b = [unit(0, 2, "乙一"), unit(2, 4, "乙二")]
        sim = table_sim({("甲", "乙一"): 0.5, ("甲", "乙二"): 0.5})

        def bonus(a_range, b_range):
            if b_range == (1, 2):
                return 0.2
            return 0.0

        got = dpalign.align(a, b, sim, bonus=bonus)
        matched_b = []
        for m in got:
            matched_b.append(m["b"])
        self.assertIn((1, 2), matched_b)


if __name__ == "__main__":
    unittest.main()
