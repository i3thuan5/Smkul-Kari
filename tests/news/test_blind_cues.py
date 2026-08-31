"""blind_cues：contact sheet 看袂著ê彼寡 cue，按怎揀出來。

圖條是 `cuelib.Cue.composite()` 產ê，有三个所在會kā字幕藏起來：

1. `MAX_SAMPLES = 24`，5 fps ⇒ 一个 cue 上濟看 4.8 秒，尾溜無看著
2. `len(samples) < 3` ⇒ 退轉去單幀，只反映 `sample_ts` 彼一目躡
3. `frames ≥ 3` ⇒ 逐像素中位數，cue 內底換過ê短句予伊洗掉

三項ê共同表現攏仝款：**`frames` 記ê是「有幾格予判定做猶是仝一句」，
乘以 0.2 秒就是實際看過ê時間；`end - start` 是這个 cue 宣稱ê時間窗。
兩者ê差，就是無人看過ê部分。**

實測（20210222_053_午間_Atayal_泰雅，改寫著ê四條）：

    cue  85  frames=8  看 1.6s  宣稱 3.50s  → 無看著 1.90s
    cue 201  frames=2  看 0.4s  宣稱 5.00s  → 無看著 4.60s
    cue 295  frames=2  看 0.4s  宣稱 3.30s  → 無看著 2.90s
    cue 573  frames=3  看 0.6s  宣稱 4.54s  → 無看著 3.94s

所以判準是**差額**，毋是 `frames` 家己嘛毋是時長家己——20210222_053
ê cue 861 `frames=17`（看起來袂少）嘛中鏢，17×0.2=3.4s 對 6.08s。
"""
import unittest

from scripts.news import blind_cues


def cue(index, start, end, frames):
    return {"index": index, "start": start, "end": end, "frames": frames}


class TestUnseen(unittest.TestCase):
    def test_it_is_the_gap_between_claimed_and_sampled(self):
        # 5.00 秒ê窗，才看 2 格＝0.4 秒
        self.assertAlmostEqual(
            blind_cues.unseen(cue(201, 100.0, 105.0, 2)), 4.6)

    def test_a_fully_sampled_cue_has_nothing_unseen(self):
        # 2 秒ê窗，10 格＝2.0 秒，拄好看透
        self.assertAlmostEqual(
            blind_cues.unseen(cue(1, 0.0, 2.0, 10)), 0.0)

    def test_the_sampling_cap_makes_long_cues_unseen(self):
        # MAX_SAMPLES=24 ⇒ 上濟 4.8 秒，30 秒ê cue 賰 25.2 秒無看著
        self.assertAlmostEqual(
            blind_cues.unseen(cue(693, 0.0, 30.0, 24)), 25.2)

    def test_more_frames_than_the_window_never_goes_negative(self):
        # 取樣率若無拄好 5 fps，算出來會超過窗；負ê無意義
        self.assertEqual(blind_cues.unseen(cue(1, 0.0, 1.0, 99)), 0.0)


class TestRisky(unittest.TestCase):
    """揀出愛轉去母帶查ê彼寡。"""

    CUES = [
        cue(1, 0.0, 2.0, 10),        # 看透，免查
        cue(2, 2.0, 7.0, 2),         # 無看著 4.6 秒
        cue(3, 7.0, 8.0, 5),         # 看透
        cue(4, 8.0, 14.0, 17),       # 無看著 2.6 秒（frames 袂少嘛中鏢）
        cue(5, 14.0, 14.9, 2),       # 無看著 0.5 秒，門檻以下
    ]

    def test_it_returns_the_ones_over_the_threshold(self):
        got = blind_cues.risky(self.CUES, floor=1.0)
        self.assertEqual([c["index"] for c in got], [2, 4])

    def test_the_worst_comes_first(self):
        got = blind_cues.risky(self.CUES, floor=1.0)
        self.assertEqual(got[0]["index"], 2)

    def test_a_lower_floor_catches_more(self):
        got = blind_cues.risky(self.CUES, floor=0.4)
        self.assertEqual([c["index"] for c in got], [2, 4, 5])

    def test_each_carries_how_much_was_unseen(self):
        got = blind_cues.risky(self.CUES, floor=1.0)
        self.assertAlmostEqual(got[0]["unseen"], 4.6)

    def test_nothing_risky_is_an_empty_list(self):
        got = blind_cues.risky([cue(1, 0.0, 2.0, 10)], floor=1.0)
        self.assertEqual(got, [])


class TestSummary(unittest.TestCase):
    def test_it_counts_and_totals(self):
        got = blind_cues.summary(TestRisky.CUES, floor=1.0)
        self.assertEqual(got["cues"], 5)
        self.assertEqual(got["risky"], 2)
        self.assertAlmostEqual(got["unseen"], 7.2)

    def test_the_share_is_a_percentage_of_all_cues(self):
        got = blind_cues.summary(TestRisky.CUES, floor=1.0)
        self.assertAlmostEqual(got["share"], 40.0)

    def test_an_empty_episode_does_not_divide_by_zero(self):
        got = blind_cues.summary([], floor=1.0)
        self.assertEqual(got["cues"], 0)
        self.assertEqual(got["share"], 0.0)


class TestBatchOf(unittest.TestCase):
    """愛講會出哪一个 cue 佇佗一个 b??.tsv，才有法度改。"""

    def test_the_first_batch_holds_cue_one(self):
        self.assertEqual(blind_cues.batch_of(1, size=96), "b01")

    def test_the_boundary_belongs_to_the_earlier_batch(self):
        self.assertEqual(blind_cues.batch_of(96, size=96), "b01")
        self.assertEqual(blind_cues.batch_of(97, size=96), "b02")

    def test_a_late_cue_lands_in_a_two_digit_batch(self):
        self.assertEqual(blind_cues.batch_of(1017, size=96), "b11")


if __name__ == "__main__":
    unittest.main()
