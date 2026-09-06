"""`MaskSpec.band_rows`：切 cue 的時陣干焦比帶內彼幾列。

為啥愛有這條：《開會了》083 ê帶干焦崁著 region ê下半（帶頂沿佇第 48 列，
族語槽煞對第 12 列起算），中央 36 列全是畫面。一格遮罩 88.3% 是白襯衫、
11.7% 才是字，換句ê時陣遮罩距離干焦 0.21–0.27，永遠碰袂著 0.35 ê門檻，
一條 cue 就按呢走過四句。

`band_rows` 是**切 cue ê遮罩**ê範圍，毋是圖條ê範圍——圖條照 preset ê
`lines` 切，讀者看著ê物件一个畫素都無振動。

上要緊ê是 `None` 彼條：news 彼爿無傳這个參數，遮罩愛佮進前逐畫素相仝，
按呢 news ê `rebuild --verify` 才會使做「引擎行為無變」ê證明。
"""
import unittest

import numpy as np

from scripts.ocr import cuelib


class Fixture(unittest.TestCase):
    """一塊烏底ê布，頂懸兩逝白筆劃——一逝佇帶內、一逝佇帶外。"""

    # 帶佇第 30 列起算，親像 083 彼款下半才有帶。
    BAND = (30, 60)

    def frame(self):
        canvas = np.full((60, 80, 3), 30, dtype=np.uint8)
        canvas[10:16, 10:70] = 255      # 帶外：畫面（白襯衫彼款）
        canvas[40:46, 10:70] = 255      # 帶內：真正ê字
        return canvas


class TestDefaultIsUnchanged(Fixture):
    """無傳 band_rows ê時，逐畫素愛佮進前一模一樣。"""

    def test_none_keeps_every_pixel(self):
        frame = self.frame()
        plain = cuelib.text_mask(frame, cuelib.MaskSpec())
        explicit = cuelib.text_mask(frame, cuelib.MaskSpec(band_rows=None))
        self.assertTrue((plain == explicit).all())

    def test_none_still_sees_ink_above_the_band(self):
        # 這條是頂懸彼條ê正例：無裁ê時陣，帶外彼逝白確實有入遮罩。
        # 若無這條，「裁了無仝」證明袂出來是裁ê功勞。
        mask = cuelib.text_mask(self.frame(), cuelib.MaskSpec())
        self.assertGreater(int(mask[10:16, :].sum()), 0)

    def test_a_spec_without_the_key_defaults_to_none(self):
        # 舊ê cues.json 內底無這隻鍵——讀入來愛是 None，行為無變。
        spec = cuelib.MaskSpec.from_dict({"white_min": 180})
        self.assertIsNone(spec.band_rows)


class TestCropping(Fixture):
    def test_rows_outside_the_band_are_dropped(self):
        spec = cuelib.MaskSpec(band_rows=self.BAND)
        mask = cuelib.text_mask(self.frame(), spec)
        self.assertEqual(int(mask[:30, :].sum()), 0)

    def test_rows_inside_the_band_are_untouched(self):
        frame = self.frame()
        plain = cuelib.text_mask(frame, cuelib.MaskSpec())
        cropped = cuelib.text_mask(frame, cuelib.MaskSpec(band_rows=self.BAND))
        lo, hi = self.BAND
        self.assertTrue((plain[lo:hi, :] == cropped[lo:hi, :]).all())
        self.assertGreater(int(cropped[lo:hi, :].sum()), 0)

    def test_the_whole_region_crops_nothing(self):
        # 帶崁規个 region ê彼 37 集：傳規範圍入去，佮無傳仝款。
        frame = self.frame()
        plain = cuelib.text_mask(frame, cuelib.MaskSpec())
        whole = cuelib.text_mask(frame, cuelib.MaskSpec(band_rows=(0, 60)))
        self.assertTrue((plain == whole).all())

    def test_the_change_between_two_frames_ignores_moving_picture(self):
        """083 彼个坑：帶外ê畫面咧振動，帶內ê字無變——距離愛是 0。"""
        first = self.frame()
        second = self.frame()
        second[10:16, 10:70] = 30       # 帶外彼塊白徙走（畫面換去）
        second[12:18, 20:60] = 255      # 徙去別位
        spec = cuelib.MaskSpec(band_rows=self.BAND)
        cropped = cuelib.mask_distance(cuelib.text_mask(first, spec),
                                       cuelib.text_mask(second, spec))
        self.assertEqual(cropped, 0.0)
        plain = cuelib.MaskSpec()
        uncropped = cuelib.mask_distance(cuelib.text_mask(first, plain),
                                         cuelib.text_mask(second, plain))
        self.assertGreater(uncropped, 0.3)


class TestRoundTrip(Fixture):
    def test_band_rows_survives_to_dict_and_back(self):
        spec = cuelib.MaskSpec(band_rows=(12, 72))
        again = cuelib.MaskSpec.from_dict(spec.to_dict())
        self.assertEqual(tuple(again.band_rows), (12, 72))

    def test_to_dict_names_the_key(self):
        # manifest ê `mask` 內底愛看會著，`refine_cues` 才有法度沿用。
        self.assertIn("band_rows", cuelib.MaskSpec().to_dict())

    def test_a_list_from_json_works_the_same_as_a_tuple(self):
        # JSON 讀轉來是 list，毋是 tuple。
        frame = self.frame()
        as_list = cuelib.MaskSpec.from_dict({"band_rows": [30, 60]})
        as_tuple = cuelib.MaskSpec(band_rows=(30, 60))
        self.assertTrue((cuelib.text_mask(frame, as_list)
                         == cuelib.text_mask(frame, as_tuple)).all())


if __name__ == "__main__":
    unittest.main()
