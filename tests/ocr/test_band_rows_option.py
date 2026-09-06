"""`cues --band-rows LO,HI`：叫參數用絕對列，寫入 manifest 用 region 內偏移。

呼叫ê人手頭有ê是**絕對列**（`verify_band` 量出來ê `band.json` 就是絕對
列，親像 083 ê y924..1014），所以參數收絕對列。毋過寫入 `cues.json` ê
`mask` 愛是**region 內ê偏移**：region 予 `normalize_region` 掠去偶數界，
絕對值可能差一列；偏移綴 region 走，寫落去了後就無倚靠任何外部數字。

`refine_cues` 對 manifest 重起 `MaskSpec`，所以切 cue 佮精修用ê遮罩
天生仝款——干焦新參數嘛愛入 `to_dict`（見 test_cuelib_band_rows）。
"""
import unittest

from scripts.ocr import cli
from scripts.errors import PipelineError


def parse(*extra):
    argv = ["cues", "v.mp4", "-o", "work"] + list(extra)
    return cli.build_parser().parse_args(argv)


class TestTheOption(unittest.TestCase):
    def test_cues_accepts_it(self):
        self.assertEqual(parse("--band-rows", "924,1014").band_rows,
                         "924,1014")

    def test_it_defaults_to_nothing(self):
        self.assertIsNone(parse().band_rows)

    def test_auto_accepts_it_too(self):
        # `auto` ＝ cues＋ocr＋srt；伊愛收 `cues` 收ê逐項，無ê話會恬恬
        # 落勾（`--preset` 就按呢予人漏過）。tests/ocr/test_auto_options.py
        # 有規則性ê守門，這條是講予人看ê。
        argv = ["auto", "v.mp4", "-o", "out.srt", "--band-rows", "924,1014"]
        self.assertEqual(cli.build_parser().parse_args(argv).band_rows,
                         "924,1014")


class TestToOffsets(unittest.TestCase):
    """絕對列 → region 內偏移。region 是 (x, y, w, h)。"""

    REGION = (0, 876, 1920, 138)

    def test_the_083_case(self):
        # 帶 y924..1014、region 對 876 起算 → 偏移 48..138。
        self.assertEqual(cli.band_rows_of("924,1014", self.REGION),
                         (48, 138))

    def test_the_whole_region(self):
        self.assertEqual(cli.band_rows_of("876,1014", self.REGION), (0, 138))

    def test_it_is_clamped_to_the_region(self):
        # 量著ê帶伸出 region 外口ê時，剪佇 region ê邊，莫做負數抑是
        # 超過長度——後壁彼段是 numpy ê索引。
        self.assertEqual(cli.band_rows_of("800,1200", self.REGION), (0, 138))

    def test_nothing_given_is_none(self):
        self.assertIsNone(cli.band_rows_of("", self.REGION))
        self.assertIsNone(cli.band_rows_of(None, self.REGION))

    def test_spaces_are_allowed(self):
        self.assertEqual(cli.band_rows_of(" 924 , 1014 ", self.REGION),
                         (48, 138))


class TestItRefusesNonsense(unittest.TestCase):
    """歹參數愛當場出聲——恬恬用預設值會切著毋著ê所在。"""

    REGION = (0, 876, 1920, 138)

    def _refuse(self, text):
        self.assertRaises(PipelineError, cli.band_rows_of, text, self.REGION)

    def test_one_number(self):
        self._refuse("924")

    def test_three_numbers(self):
        self._refuse("924,1014,1100")

    def test_not_a_number(self):
        self._refuse("924,ten")

    def test_upside_down(self):
        self._refuse("1014,924")

    def test_empty_after_clamping(self):
        # 規段攏佇 region 外口——剪了是空ê，切落去遮罩會規塊烏。
        self._refuse("500,700")


if __name__ == "__main__":
    unittest.main()
