"""Strip ê檔名用**起始時間**號，莫用 cue ê序號。

因端是量出來ê：全批 75,290 條 cue 內底，**46,665 條（62%）ê檔名
佮伊ê cue 編號無仝**，散佇 48 集。`safe_resplit` 重讀ê時拆過 cue、
規排重新編號，毋過 strip ê檔名是拆進前號ê。兩爿ê號碼攏四位數、
範圍相疊，看起來完全正常——`strips/00844_han.png` 對著ê是 cue 951。

時間袂綴重新編號走（別條 cue 拆開ê時，這條ê起止時間原封不動），
而且 `t01874700` 看起來就無成 cue 號碼，人佮 agent 攏袂順手kā伊
當做 cue 編號用。使用者裁定 2026-08-31。

改名這件事本身**無碰撞ê風險**：序號名佮時間名是兩个無相交ê空間，
`00844_han.png` 佮 `t01874700_han.png` 無可能撞。彼佮 `rescan_band`
內底彼種「仝一个編號空間內底搬」（400→402 會蓋去猶佇咧ê 402）
完全無仝。
"""
import unittest

from scripts.errors import PipelineError
from scripts.ocr import stripname


class TestName(unittest.TestCase):
    def test_seconds_become_milliseconds(self):
        self.assertEqual(stripname.of(1874.700, "han"), "t01874700_han.png")

    def test_zero_is_padded(self):
        self.assertEqual(stripname.of(0.0, "han"), "t00000000_han.png")

    def test_it_sorts_in_time_order(self):
        """檔名照字面排＝照時間排，`ls` 就是時間順。"""
        seconds = [2.0, 10.0, 100.5, 1874.7]
        names = []
        for one in seconds:
            names.append(stripname.of(one, "han"))
        self.assertEqual(names, sorted(names))

    def test_the_line_name_is_kept(self):
        self.assertEqual(stripname.of(5.0, "line0"), "t00005000_line0.png")

    def test_milliseconds_are_rounded_not_truncated(self):
        self.assertEqual(stripname.of(1.0006, "han"), "t00001001_han.png")

    def test_a_negative_time_is_an_error(self):
        with self.assertRaises(PipelineError):
            stripname.of(-0.1, "han")

    def test_two_cues_a_frame_apart_get_different_names(self):
        """上短ê cue 是 0.2 秒，毫秒ê精度綽綽有餘。"""
        self.assertNotEqual(stripname.of(10.0, "han"),
                            stripname.of(10.034, "han"))

    def test_it_does_not_look_like_a_cue_number(self):
        """這就是換名ê理由：袂使閣是四五位ê赤裸數字。"""
        name = stripname.of(1874.700, "han")
        self.assertTrue(name.startswith("t"))
        self.assertFalse(name.split("_")[0].lstrip("t").isdigit()
                         and len(name.split("_")[0]) <= 6)


class TestLooksOld(unittest.TestCase):
    """遷移ê時愛分會出舊名新名——兩套會同時佇咧一站仔。"""

    def test_an_ordinal_name_is_recognised(self):
        self.assertTrue(stripname.is_ordinal("00844_han.png"))

    def test_a_time_name_is_not(self):
        self.assertFalse(stripname.is_ordinal("t01874700_han.png"))

    def test_a_path_works_too(self):
        self.assertTrue(stripname.is_ordinal("strips/00844_han.png"))
        self.assertFalse(stripname.is_ordinal("strips/t01874700_han.png"))

    def test_something_else_is_not_ordinal(self):
        self.assertFalse(stripname.is_ordinal("sheet_001.png"))


if __name__ == "__main__":
    unittest.main()
