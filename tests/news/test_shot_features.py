"""shots：影片 → 逐秒畫面特徵（160×90 縮圖）。

特徵是判段落（`segments`）的材料：左下角節目框在不在、紅色標題條、
跟棚內參考格像不像、跟前一格差多少、單元標誌。判段規則會一直調，
特徵存落來就毋免逐擺重新解碼。

fixture 攏是合成ê縮圖陣列；干焦時間對應彼條愛真正解碼一支合成影片。
"""
import json
import os
import subprocess
import tempfile
import unittest

import numpy as np

from scripts.news import paths
from scripts.news import shots


def frames(n, seed=0):
    """n 格 90×160 ê「外景」：逐格攏無仝ê雜色。"""
    rng = np.random.default_rng(seed)
    return rng.integers(0, 256, size=(n, 90, 160, 3), dtype=np.uint8)


def with_box(thumbs, glyph_seed=None):
    """左下角 kā節目框貼起去：深藍底，內底有會變ê字。"""
    out = thumbs.copy()
    rows, cols = shots.BOX
    out[:, rows, cols] = (20, 40, 120)
    if glyph_seed is not None:
        rng = np.random.default_rng(glyph_seed)
        for index in range(len(out)):
            # 天氣框：城市、溫度逐段換，干焦佔框內一細部份
            y = rows.start + int(rng.integers(1, 5))
            x = cols.start + int(rng.integers(2, 16))
            out[index, y:y + 2, x:x + 5] = 255
    return out


class TestFrameBox(unittest.TestCase):
    """第一層：左下角ê節目框在毋在，毋比框內ê內容。

    2021 年彼塊是天氣框＋語別牌，城市、溫度一直換；提台標樣板比內容，
    會kā 26 分鐘ê新聞判做「其他」。2023 年起是固定台標，嘛仝款干焦問
    在毋在。
    """

    def test_changing_weather_text_still_counts_as_present(self):
        thumbs = with_box(frames(60), glyph_seed=3)
        box = shots.box_distance(thumbs)
        self.assertTrue((box < shots.BOX_ABSENT).all(), box.max())

    def test_footage_where_the_box_should_be_is_absent(self):
        thumbs = with_box(frames(60), glyph_seed=3)
        thumbs[50:] = frames(10, seed=9)          # 片尾：無框
        box = shots.box_distance(thumbs)
        self.assertTrue((box[50:] > shots.BOX_ABSENT).all(), box[50:].min())
        self.assertTrue((box[:50] < shots.BOX_ABSENT).all())


class TestPureRed(unittest.TestCase):
    """紅色標題條用「純紅」判：綠、藍接近 0。

    紅條從 y 852 起ê上段是暗紅（R 30–100、G=B=0），R>150 ê亮紅干焦佇
    y≈904 零星幾格——用 R>150 判，4 支 2024 影片干焦揣著 3–9 格，位置
    閣毋著。
    """

    def _bar(self, colour):
        thumbs = frames(4)
        rows = slice(*shots.RED_ROWS)
        thumbs[:, rows, shots.RIGHT:] = colour
        return thumbs

    def test_dark_red_is_the_bar(self):
        share = shots.red_share(self._bar((60, 0, 0)))
        self.assertTrue((share > 0.9).all(), share)

    def test_dark_grey_is_not(self):
        share = shots.red_share(self._bar((60, 60, 60)))
        self.assertTrue((share < 0.1).all(), share)

    def test_the_rule_is_the_one_the_sheets_use(self):
        # 組合圖排除紅條列佮這爿判紅條，愛是仝一組數字。
        with open(paths.ENGINE_PRESETS, encoding="utf-8") as handle:
            presets = json.load(handle)
        rule = presets["titv-news-848"]["sheet"]["row_slots"]["exclude"]
        self.assertEqual(shots.PURE_RED, rule)


class TestTheLayoutSaysWhereTheBarIs(unittest.TestCase):
    """2024-08 起紅條落到 y 938–1010；舊位置 852–912 變成字幕。"""

    def test_the_red_rows_come_from_the_layout(self):
        thumbs = frames(3)
        thumbs[:, 938 // shots.SCALE:1010 // shots.SCALE, shots.RIGHT:] = (
            60, 0, 0)
        old = shots.red_share(thumbs)
        new = shots.red_share(thumbs, rows=(938, 1010))
        self.assertTrue((old < 0.1).all(), old)
        self.assertTrue((new > 0.9).all(), new)

    def test_the_box_and_badge_come_from_the_layout(self):
        # 2024-08 起：節目框 y 900–1010、x 130–360；語別牌 y 852–884、
        # x 210–310（舊版型 y 924–1008、x 36–324；語別牌佇框頂懸）。
        thumbs = frames(40)
        thumbs[:, 900 // shots.SCALE:1010 // shots.SCALE,
               130 // shots.SCALE:360 // shots.SCALE] = (240, 240, 240)
        thumbs[:, 852 // shots.SCALE:884 // shots.SCALE,
               210 // shots.SCALE:310 // shots.SCALE] = (200, 30, 30)
        thumbs[30:, 852 // shots.SCALE:884 // shots.SCALE,
               210 // shots.SCALE:310 // shots.SCALE] = (30, 30, 200)
        layout = {"box": [[900, 1010], [130, 360]],
                  "badge": [[852, 884], [210, 310]]}
        got = shots.features(thumbs, {"studio": [], "units": {}},
                             layout=layout)
        self.assertTrue((got["box"] < shots.BOX_ABSENT).all(), got["box"])
        self.assertTrue((got["badge"][:30] < 0.05).all())
        self.assertTrue((got["badge"][30:] > 0.2).all())

    def test_the_centred_layout_measures_both_reds(self):
        # 2024-08 起紅條：標題條偏粉紅（140,56,55），人名條純紅
        # （132,12,0）。紅條用「R 明顯較懸」判，另外量純紅比例。
        layout = {"red_rows": [938, 1010],
                  "red_rule": {"r_minus_g": 40, "r_minus_b": 40},
                  "name_rule": shots.PURE_RED}
        thumbs = frames(4)
        rows = slice(938 // shots.SCALE, 1010 // shots.SCALE)
        thumbs[:2, rows, shots.RIGHT:] = (140, 56, 55)
        thumbs[2:, rows, shots.RIGHT:] = (132, 12, 0)
        got = shots.features(thumbs, {"studio": [], "units": {}},
                             layout=layout)
        self.assertTrue((got["red"] > 0.9).all(), got["red"])
        self.assertTrue((got["name"][:2] < 0.1).all(), got["name"])
        self.assertTrue((got["name"][2:] > 0.9).all(), got["name"])

    def test_a_layout_can_switch_the_box_and_badge_off(self):
        # 2024-08 起「族語」框佮語別小字攏半透明、閣會換內容，距離分布
        # 無兩峰（2024-12-01 晚間卑南 2880 格：0.03–0.5 平平分佈），分
        # 袂出在毋在——彼个版型關掉：規集當做框在、語別牌無換。
        thumbs = frames(10)
        got = shots.features(thumbs, {"studio": [], "units": {}},
                             layout={"box": False, "badge": False})
        self.assertTrue((got["box"] == 0).all())
        self.assertTrue((got["badge"] == 0).all())

    def test_the_old_layouts_have_no_name_feature(self):
        got = shots.features(frames(3), {"studio": [], "units": {}})
        self.assertNotIn("name", got)

    def test_features_follow_the_layout(self):
        thumbs = with_box(frames(20), glyph_seed=2)
        thumbs[:, 938 // shots.SCALE:1010 // shots.SCALE, shots.RIGHT:] = (
            60, 0, 0)
        got = shots.features(thumbs, {"studio": [], "units": {}},
                             layout={"red_rows": [938, 1010]})
        self.assertTrue((got["red"] > 0.9).all())


class TestLeftQuarterIsIgnored(unittest.TestCase):
    """第二層干焦看 x ≥ 480（縮圖 x ≥ 40）、y 0–700。

    左下角 2021 年是會變ê天氣框、2023 年是台標，兩年欲用仝一套規則，
    倒爿四分之一就毋看。
    """

    def test_changes_left_of_480_do_not_move_the_studio_distance(self):
        ref = frames(1, seed=1)[0]
        thumbs = np.repeat(ref[None], 5, axis=0)
        thumbs[:, :, :shots.RIGHT] = frames(5, seed=2)[:, :, :shots.RIGHT]
        got = shots.reference_distance(thumbs, [ref])
        self.assertTrue((got < 1e-6).all(), got)

    def test_changes_left_of_480_do_not_move_the_step(self):
        ref = frames(1, seed=1)[0]
        thumbs = np.repeat(ref[None], 5, axis=0)
        thumbs[:, :, :shots.RIGHT] = frames(5, seed=2)[:, :, :shots.RIGHT]
        self.assertTrue((shots.step(thumbs)[1:] < 1e-6).all())

    def test_the_red_bar_is_read_right_of_480_too(self):
        thumbs = frames(2)
        thumbs[:, slice(*shots.RED_ROWS), :shots.RIGHT] = (60, 0, 0)
        self.assertTrue((shots.red_share(thumbs) < 0.1).all())


class TestStudioScreenChanges(unittest.TestCase):
    """棚內右爿ê虛擬大螢幕會換內容；比參考格愛用區塊差ê中位數。

    規格平均距離會隨螢幕內容起落，超過門檻就判做「主播外景」。
    """

    def test_a_new_picture_on_the_screen_still_matches(self):
        ref = frames(1, seed=4)[0]
        now = ref.copy()
        now[5:45, 90:150] = frames(1, seed=5)[0][5:45, 90:150]
        got = shots.reference_distance(now[None], [ref])[0]
        self.assertLess(got, shots.STUDIO_MATCH)

    def test_a_screen_over_half_the_picture_still_matches(self):
        # 2021 年ê棚：右爿大螢幕佔第二層範圍一半以上。區塊差ê中位數綴
        # 螢幕內容走（棚內段量著 0.07–0.15，佮戶外主播 0.19 起相黏）。
        ref = frames(1, seed=4)[0]
        now = ref.copy()
        now[0:56, 40:120] = frames(1, seed=5)[0][0:56, 40:120]
        got = shots.reference_distance(now[None], [ref])[0]
        self.assertLess(got, shots.STUDIO_MATCH)

    def test_a_different_set_does_not_match(self):
        ref = frames(1, seed=4)[0]
        other = frames(1, seed=6)[0]
        got = shots.reference_distance(other[None], [ref])[0]
        self.assertGreater(got, shots.STUDIO_MATCH)

    def test_no_references_means_no_answer(self):
        got = shots.reference_distance(frames(3), [])
        self.assertTrue(np.isnan(got).all())


class TestFrameTime(unittest.TestCase):
    """縮圖第 t 格是 t+0.5 秒ê畫面，毋是 t 秒。

    ffmpeg `fps=1` 取ê是逐秒區間中央彼格。截判不準ê原圖若用 `-ss t`，
    會差半秒，拄好換鏡頭ê時陣截著隔壁彼个鏡頭。
    """

    def test_the_thumbnail_is_taken_mid_second(self):
        self.assertEqual(shots.frame_time(0), 0.5)
        self.assertEqual(shots.frame_time(12), 12.5)

    def test_a_decoded_thumbnail_matches_its_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            video = os.path.join(tmp, "t.mp4")
            # 逐秒內底亮度照十分之一秒升：看亮度就知影是第幾十分之一秒
            subprocess.run(
                ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                 "color=c=black:s=320x180:r=25:d=4,format=gray,"
                 "geq=lum='25*floor(10*mod(T,1))'",
                 "-c:v", "libx264", "-pix_fmt", "yuv420p", video],
                check=True)
            thumbs = shots.thumbnails(video)
        self.assertEqual(len(thumbs), 4)
        for index in range(len(thumbs)):
            tenth = int(round(float(thumbs[index].mean()) / 25))
            want = int(10 * (shots.frame_time(index) % 1))
            self.assertLessEqual(abs(tenth - want), 1, (index, tenth, want))


class TestFeaturesRoundTrip(unittest.TestCase):
    """特徵存 `7-shots/features.npz`，判段規則改了毋免重新解碼。"""

    def test_what_is_saved_is_what_is_loaded(self):
        thumbs = with_box(frames(30), glyph_seed=1)
        got = shots.features(thumbs, {"studio": [thumbs[3]], "units": {}})
        with tempfile.TemporaryDirectory() as work:
            shots.save(work, got)
            back = shots.load(work)
            self.assertTrue(os.path.exists(os.path.join(
                paths.shots_dir(work), "features.npz")))
        self.assertEqual(sorted(back), sorted(got))
        for key in got:
            np.testing.assert_array_equal(back[key], got[key])

    def test_the_picture_is_kept_small(self):
        # 主播段愛修到鏡頭邊界，需要逐格ê畫面；存縮圖傷大（一集 2,900
        # 格），存 8×8 區塊平均：x ≥ 480、y 0–700 是 15×7 塊。
        thumbs = with_box(frames(30), glyph_seed=1)
        got = shots.features(thumbs, {"studio": [], "units": {}})
        self.assertEqual(got["picture"].shape, (30, 105, 3))
        self.assertEqual(got["picture"].dtype, np.float16)

    def test_every_feature_has_one_value_per_second(self):
        thumbs = with_box(frames(30), glyph_seed=1)
        got = shots.features(thumbs, {"studio": [], "units": {}})
        for key, values in got.items():
            self.assertEqual(len(values), 30, key)


if __name__ == "__main__":
    unittest.main()
