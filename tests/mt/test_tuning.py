"""tuning: pick the merge threshold from Claude's grades on news samples.

A "location" is the boundary between two neighbouring recognised
segments that some subtitle straddles. How much of that subtitle falls
on the smaller side decides its bucket; moving the threshold across a
bucket changes exactly the locations in it, so each bucket is judged on
its own: the pair merged into one group versus split into two.
"""
import unittest

from scripts.errors import PipelineError
from scripts.mt import tuning


def seg(i, start, end, formosan="a b c d e f g h i j"):
    return {"index": i, "start": start, "end": end, "formosan": formosan,
            "han": "譯文%d" % i}


def ent(j, start, end):
    return {"index": j, "true_start": start, "true_end": end,
            "han": "字幕%d" % j, "formosan": "", "cues": [j]}


class TestLocations(unittest.TestCase):
    def test_bucket_is_the_smaller_side_share(self):
        segs = [seg(0, 0.0, 10.0), seg(1, 10.0, 20.0)]
        ents = [ent(0, 2.0, 6.0), ent(1, 8.8, 12.8), ent(2, 14.0, 18.0)]
        found = tuning.locations(segs, ents)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["boundary"], 0)
        # 1.2 s of 4 s on the smaller side: 30%, bucket 30–40
        self.assertEqual(found[0]["bucket"], 3)

    def test_largest_straddler_decides(self):
        segs = [seg(0, 0.0, 10.0), seg(1, 10.0, 20.0)]
        ents = [ent(0, 9.8, 13.8), ent(1, 8.0, 12.0)]   # 5% and 50%
        self.assertEqual(tuning.locations(segs, ents)[0]["bucket"], 4)

    def test_half_is_the_top_bucket_and_nothing_goes_above(self):
        self.assertEqual(tuning.bucket_of(0.5), 4)
        self.assertEqual(tuning.bucket_of(0.4999), 4)
        self.assertEqual(tuning.bucket_of(0.1), 1)
        self.assertEqual(tuning.bucket_of(0.0999), 0)

    def test_three_versions_isolate_the_pair(self):
        segs = [seg(0, 0.0, 10.0), seg(1, 10.0, 20.0)]
        ents = [ent(0, 2.0, 6.0), ent(1, 8.8, 12.8), ent(2, 14.0, 18.0)]
        loc = tuning.locations(segs, ents)[0]
        merged, part_a, part_b = tuning.versions(loc)
        self.assertEqual(merged, {"segs": [0, 1], "entries": [0, 1, 2]})
        # the straddler goes to the side it overlaps more
        self.assertEqual(part_a, {"segs": [0], "entries": [0]})
        self.assertEqual(part_b, {"segs": [1], "entries": [1, 2]})

    def test_boundary_whose_straddler_lives_elsewhere_is_no_location(self):
        # short VAD pieces: the subtitle touches three segments and most
        # of it lies in the third, so neither side of 0|1 owns a subtitle
        # and there is nothing to judge at that boundary (met on the first
        # real sampling run)
        segs = [seg(0, 0.0, 1.0), seg(1, 1.0, 2.0), seg(2, 2.0, 10.0)]
        ents = [ent(0, 0.5, 6.0)]
        found = tuning.locations(segs, ents)
        self.assertEqual([loc["boundary"] for loc in found], [1])

    def test_side_without_subtitles_has_no_group(self):
        segs = [seg(0, 0.0, 10.0), seg(1, 10.0, 20.0)]
        ents = [ent(0, 9.0, 13.0)]
        loc = tuning.locations(segs, ents)[0]
        _merged, part_a, _part_b = tuning.versions(loc)
        self.assertIsNone(part_a)


class TestSample(unittest.TestCase):
    def pool(self, counts):
        out = []
        for bucket, count in enumerate(counts):
            for k in range(count):
                out.append({"key": ("ep", bucket * 1000 + k),
                            "bucket": bucket})
        return out

    def test_same_seed_same_sample(self):
        pool = self.pool([300, 300, 300, 300, 300])
        first, _ = tuning.sample(pool, 97, seed=7)
        again, _ = tuning.sample(list(reversed(pool)), 97, seed=7)
        self.assertEqual([p["key"] for p in first],
                         [p["key"] for p in again])
        self.assertEqual(len(first), 5 * 97)

    def test_short_bucket_is_taken_whole_and_reported(self):
        chosen, short = tuning.sample(self.pool([300, 300, 300, 300, 40]),
                                      97, seed=7)
        self.assertEqual(len(chosen), 4 * 97 + 40)
        self.assertEqual(short, {4: 40})


class TestBatches(unittest.TestCase):
    def test_merged_and_split_never_share_a_batch(self):
        items = []
        for k in range(150):
            items.append({"id": 3 * k + 1, "kind": "G"})
            items.append({"id": 3 * k + 2, "kind": "A"})
            items.append({"id": 3 * k + 3, "kind": "B"})
        batches = tuning.batches(items, size=200, part=50)
        for batch in batches:
            kinds = set()
            for part in batch:
                for item in part:
                    kinds.add("G" if item["kind"] == "G" else "AB")
            self.assertEqual(len(kinds), 1)
        self.assertEqual(sum(len(p) for b in batches for p in b), 450)

    def test_a_batch_is_four_parts_of_fifty(self):
        items = [{"id": k, "kind": "G"} for k in range(200)]
        batches = tuning.batches(items, size=200, part=50)
        self.assertEqual([len(p) for p in batches[0]], [50, 50, 50, 50])

    def test_overlong_row_is_flagged(self):
        self.assertTrue(tuning.too_long("x" * 1801))
        self.assertFalse(tuning.too_long("x" * 1800))


class TestIngest(unittest.TestCase):
    def test_complete_reply_is_taken(self):
        got = tuning.ingest([1, 2, 3], "1\t高\t理由\n2\t中\t\n3\t低\t理由\n")
        self.assertEqual(got, {1: "高", 2: "中", 3: "低"})

    def test_one_line_short_refuses_the_whole_batch(self):
        with self.assertRaises(PipelineError) as caught:
            tuning.ingest([1, 2, 3], "1\t高\t理由\n2\t中\t理由\n")
        self.assertIn("3", str(caught.exception))

    def test_bad_label_refuses_the_whole_batch(self):
        with self.assertRaises(PipelineError):
            tuning.ingest([1, 2], "1\t高\n2\t普通\n")

    def test_duplicate_or_extra_id_refuses(self):
        with self.assertRaises(PipelineError):
            tuning.ingest([1, 2], "1\t高\n2\t中\n2\t低\n")
        with self.assertRaises(PipelineError):
            tuning.ingest([1, 2], "1\t高\n2\t中\n9\t低\n")


class TestCompare(unittest.TestCase):
    def test_usable_words_decide(self):
        # merged 40 words 高 = 40; split 20 高 + 20 低 = 20
        self.assertEqual(tuning.outcome(("高", 40), ("高", 20), ("低", 20)),
                         "合併較好")
        # merged 中 = 20; split both 高 = 40
        self.assertEqual(tuning.outcome(("中", 40), ("高", 20), ("高", 20)),
                         "拆開較好")
        self.assertEqual(tuning.outcome(("高", 40), ("高", 20), ("高", 20)),
                         "一樣")

    def test_missing_side_scores_nothing(self):
        self.assertEqual(tuning.outcome(("高", 40), None, ("高", 30)),
                         "合併較好")

    def test_wilson_interval(self):
        low, high = tuning.wilson(70, 100)
        self.assertAlmostEqual(low, 0.604, places=3)
        self.assertAlmostEqual(high, 0.781, places=3)

    def test_verdict_uses_the_interval_and_ignores_ties(self):
        self.assertEqual(tuning.verdict(70, 30), "合併較好")
        self.assertEqual(tuning.verdict(30, 70), "拆開較好")
        self.assertEqual(tuning.verdict(55, 45), "分不出")
        self.assertEqual(tuning.verdict(0, 0), "分不出")


class TestChoose(unittest.TestCase):
    def test_undecided_takes_the_lower_threshold(self):
        verdicts = {0: "拆開較好", 1: "分不出", 2: "合併較好", 3: "合併較好",
                    4: "合併較好"}
        self.assertEqual(tuning.choose(verdicts), 0.1)

    def test_a_split_bucket_pushes_the_threshold_up(self):
        verdicts = {0: "拆開較好", 1: "拆開較好", 2: "分不出", 3: "合併較好",
                    4: "合併較好"}
        self.assertEqual(tuning.choose(verdicts), 0.2)

    def test_split_even_at_the_top_means_no_merging(self):
        verdicts = {0: "分不出", 1: "分不出", 2: "分不出", 3: "分不出",
                    4: "拆開較好"}
        self.assertIsNone(tuning.choose(verdicts))

    def test_a_split_bucket_above_a_good_one_wins(self):
        # merging must be fine in every bucket from t upward
        verdicts = {0: "分不出", 1: "合併較好", 2: "拆開較好", 3: "合併較好",
                    4: "合併較好"}
        self.assertEqual(tuning.choose(verdicts), 0.3)


if __name__ == "__main__":
    unittest.main()
