"""tools/mtgold/sweep: the merge threshold scanned on 開會了's gold.

開會了 burns the Formosan line into the picture, so which subtitles a
recognised segment really covers can be read off the words. The scan
grades each candidate threshold against that. It is a reference beside
the news judging, not the decision: a talk show is cut differently.
"""
import unittest

from tools.mtgold import sweep


def seg(i, start, end, formosan):
    return {"index": i, "start": start, "end": end, "formosan": formosan,
            "han": ""}


def ent(j, start, end, formosan):
    return {"index": j, "true_start": start, "true_end": end,
            "formosan": formosan, "han": "字幕%d" % j, "cues": [j]}


ENTRIES = [ent(0, 0.0, 4.0, "ci sera kako mikeriday anini"),
           ent(1, 4.0, 8.0, "mihomong to angcoh a demak"),
           ent(2, 8.0, 12.0, "angcoh a niyaro i kalingko posko")]
# a 1.2 s pause keeps the two apart when chunking; the second subtitle
# (4–8 s) lies 2 s in the first segment (50%) and 0.8 s in the second (20%)
SEGMENTS = [seg(0, 0.0, 6.0, "ci sera kako mikeriday anini mihomong to"),
            seg(1, 7.2, 12.0, "angcoh a demak angcoh a niyaro i kalingko")]


class TestSweep(unittest.TestCase):
    def test_one_row_per_candidate(self):
        rows, missing = sweep.sweep([("開會了_068_Amis_阿美", SEGMENTS,
                                      ENTRIES)])
        self.assertEqual([r["門檻"] for r in rows],
                         ["不合併", "10%", "20%", "30%", "40%", "50%"])
        self.assertEqual(missing, [])

    def test_low_threshold_merges_the_straddled_pair(self):
        rows, _ = sweep.sweep([("開會了_068_Amis_阿美", SEGMENTS, ENTRIES)])
        by = {}
        for row in rows:
            by[row["門檻"]] = row
        self.assertEqual(by["不合併"]["組數"], 2)
        self.assertEqual(by["20%"]["組數"], 1)
        self.assertEqual(by["30%"]["組數"], 2)

    def test_episode_without_recognition_is_listed_not_fatal(self):
        # 107 拉阿魯哇: the server returned empty text twice
        rows, missing = sweep.sweep([
            ("開會了_068_Amis_阿美", SEGMENTS, ENTRIES),
            ("開會了_107_Hla'alua_拉阿魯哇", None, ENTRIES)])
        self.assertEqual(missing, ["開會了_107_Hla'alua_拉阿魯哇"])
        self.assertEqual(len(rows), 6)

    def test_news_like_chunks_fuse_short_segments(self):
        short = [seg(0, 0.0, 2.0, "a"), seg(1, 2.5, 4.0, "b"),
                 seg(2, 9.0, 10.0, "c")]
        chunks = sweep.merge_chunks(short)
        self.assertEqual([c["formosan"] for c in chunks], ["a b", "c"])


if __name__ == "__main__":
    unittest.main()
