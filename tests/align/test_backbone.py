"""3-gram voting and the monotonic backbone over candidate offsets."""
import unittest

from scripts.news import align


def reference_index(reference):
    index = {}
    for i in range(len(reference) - align.GRAM + 1):
        index.setdefault(reference[i:i + align.GRAM], []).append(i)
    return index


class TestCandidates(unittest.TestCase):
    REF = "春天的花開在山坡上面夏天的雨落在稻田中間秋天的風吹過部落廣場"

    def test_votes_concentrate_on_the_true_offset(self):
        index = reference_index(self.REF)
        got = align.candidates("夏天的雨落在稻田中間", index)
        self.assertTrue(got)
        offset, votes = got[0]
        self.assertEqual(offset, self.REF.index("夏"))

    def test_half_wrong_reading_still_finds_its_offset(self):
        index = reference_index(self.REF)
        # tesseract-grade noise: half the characters wrong
        got = align.candidates("夏天的雨茶在稻田申間", index)
        self.assertTrue(got)
        self.assertEqual(got[0][0], self.REF.index("夏"))

    def test_too_short_for_a_gram_yields_nothing(self):
        index = reference_index(self.REF)
        self.assertEqual(align.candidates("夏", index), [])


class TestBackbone(unittest.TestCase):
    def test_offsets_are_monotonic(self):
        # cue 1 has a decoy candidate far ahead with more votes than its
        # true offset; taking the decoy would cut cue 2 out of the chain,
        # so the neighbours outvote it and the sequence stays increasing
        per_cue = [
            [(10, 5)],
            [(200, 7), (30, 4)],
            [(50, 5)],
        ]
        chosen = align.backbone(per_cue)
        self.assertEqual(chosen[0][0], 10)
        self.assertEqual(chosen[1][0], 30)
        self.assertEqual(chosen[2][0], 50)

    def test_repeated_phrase_lands_between_its_neighbours(self):
        ref = ("開場白說明今天的主題內容" "耆老表示這件事情很重要"
               "中段介紹部落的歷史脈絡" "耆老表示這件事情很重要"
               "結尾感謝大家收看節目再見")
        texts = ["中段介紹部落的歷史脈絡", "耆老表示這件事情很重要",
                 "結尾感謝大家收看節目再見"]
        placed = align.align(texts, ref)
        self.assertIsNotNone(placed[1])
        # the second occurrence, after the cue before it -- not the first
        self.assertGreater(placed[1]["lo"], placed[0]["hi"] - 1)
        self.assertLess(placed[1]["hi"], placed[2]["lo"] + 1)

    def test_empty_candidates_yield_empty_backbone(self):
        self.assertEqual(align.backbone([[], []]), {})


if __name__ == "__main__":
    unittest.main()
