"""segments：逐秒特徵 → 段落表，佮段落表ê驗證。

逐秒特徵攏是合成ê陣列（`shots.features` 產出ê款），毋免解碼：
- `box`：左下角節目框距離，細過 `shots.BOX_ABSENT` 就是框在
- `red`：紅條純紅比例
- `studio`：佮棚內參考格ê距離（NaN＝無參考格）
- `step`：佮前一格ê距離
- `badge`：語別牌佮開頭ê距離
- `unit:<名>`：單元標誌距離
- `picture`：逐格畫面ê區塊色（合成：逐个鏡頭一組固定ê色）
"""
import os
import tempfile
import unittest

import numpy as np

from scripts.news import segments
from scripts.news import shots


class Episode(object):
    """組一集ê逐秒特徵：預設規集外景新聞、框在、無紅條。"""

    def __init__(self, seconds):
        self.n = seconds
        self.box = np.full(seconds, 0.03, dtype=np.float32)
        self.red = np.zeros(seconds, dtype=np.float32)
        self.studio = np.full(seconds, 0.3, dtype=np.float32)
        self.badge = np.full(seconds, 0.02, dtype=np.float32)
        self.units = {}
        # 逐格一个鏡頭代號；step 由伊算，相仝就 0、無仝就 1
        self.shot = np.arange(seconds)

    def anchor(self, start, end, studio=True, shot=-1):
        self.red[start:end] = 0.9
        self.shot[start:end] = shot
        if studio:
            self.studio[start:end] = 0.02
        return self

    def features(self):
        step = np.ones(self.n, dtype=np.float32)
        step[1:] = (self.shot[1:] != self.shot[:-1]).astype(np.float32)
        # 逐个鏡頭一組固定ê區塊色：仝鏡頭距離 0，無仝鏡頭差真遠
        picture = np.zeros((self.n, 16, 3), dtype=np.float16)
        for index in range(self.n):
            rng = np.random.default_rng(int(self.shot[index]) + 1000)
            picture[index] = rng.random((16, 3))
        out = {"box": self.box, "red": self.red, "studio": self.studio,
               "step": step, "badge": self.badge, "picture": picture}
        for name, values in self.units.items():
            out["unit:" + name] = values
        return out


def kinds(rows):
    out = []
    for row in rows:
        out.append((row["起秒"], row["迄秒"], row["類型"]))
    return out


def label_at(rows, second):
    for row in rows:
        if float(row["起秒"]) <= second < float(row["迄秒"]):
            return row
    raise AssertionError("第 %s 秒無段落" % second)


class TestAnchorComesFromTheRedBar(unittest.TestCase):

    def test_a_recurring_interviewee_is_not_an_anchor(self):
        # 176 嘉明湖專題：仝一位受訪者ê鏡位出現十幾擺，無紅條。
        ep = Episode(600)
        for start in range(100, 500, 30):
            ep.shot[start:start + 10] = -7
        rows = segments.classify(ep.features(), "卑南", 600.0)
        self.assertEqual(kinds(rows), [("0", "600.000", "外景新聞")])

    def test_a_long_red_run_matching_the_studio_is_studio(self):
        ep = Episode(300).anchor(60, 120)
        rows = segments.classify(ep.features(), "排灣", 300.0)
        self.assertEqual(label_at(rows, 90)["類型"], "攝影棚")
        self.assertEqual(label_at(rows, 90)["依據"], "自動")

    def test_a_long_red_run_elsewhere_is_asked_not_decided(self):
        # 2021 抽查：紅條長毋過毋像棚內ê段，有主播外景、嘛有「VS」
        # 受訪者（2021noon 第 12–15 格）、有棚內螢幕換做文化小辭典ê
        # （2021am 第 13 格）。像素分袂開，候選是主播外景，交讀者。
        ep = Episode(300).anchor(60, 120, studio=False)
        rows = segments.classify(ep.features(), "卑南", 300.0)
        self.assertEqual(label_at(rows, 90)["類型"], "主播外景")
        self.assertEqual(label_at(rows, 90)["依據"], segments.PENDING)


class TestTheCentredLayoutTellsNameBarsApart(unittest.TestCase):
    """2024-08 起：主播段標題條是偏粉ê紅（純紅比例 0.24–0.43），受訪
    者人名條是純紅（≥0.47）而且常掛 20 秒以上，紅色跑道、紅色圖卡這款
    背景純紅比例 <0.1。2024-12 三集量ê。
    """

    def episode(self, name_share, studio=False):
        ep = Episode(300).anchor(60, 120, studio=studio)
        feats = ep.features()
        feats["name"] = np.zeros(300, dtype=np.float32)
        feats["name"][60:120] = name_share
        return feats

    def test_a_name_bar_is_an_interview(self):
        rows = segments.classify(self.episode(0.6), "阿美", 300.0)
        row = label_at(rows, 90)
        self.assertEqual((row["類型"], row["依據"]), ("外景新聞", "自動"))

    def test_red_scenery_is_not_a_bar(self):
        rows = segments.classify(self.episode(0.07), "阿美", 300.0)
        self.assertEqual(label_at(rows, 90)["類型"], "外景新聞")

    def test_a_headline_bar_away_from_the_studio_is_asked(self):
        rows = segments.classify(self.episode(0.35), "阿美", 300.0)
        row = label_at(rows, 90)
        self.assertEqual((row["類型"], row["依據"]),
                         ("主播外景", segments.PENDING))

    def test_the_studio_wins_whatever_the_bar(self):
        rows = segments.classify(self.episode(0.47, studio=True), "卑南",
                                 300.0)
        self.assertEqual(label_at(rows, 90)["類型"], "攝影棚")


class TestStudioWithoutTheBar(unittest.TestCase):

    def test_a_flat_card_like_the_studio_is_asked(self):
        # 176 第 1272–1274 秒：全螢幕灰底圖卡，平坦ê區塊佮棚內佈景ê
        # 四分之一相仝（0.042–0.049），無紅條。
        ep = Episode(300)
        ep.studio[100:103] = 0.045
        rows = segments.classify(ep.features(), "卑南", 300.0)
        self.assertEqual(label_at(rows, 101)["依據"], segments.PENDING)


class TestNameSupers(unittest.TestCase):

    def test_two_seconds_without_the_bar_do_not_split_the_anchor(self):
        ep = Episode(300).anchor(60, 120)
        ep.red[85:87] = 0.0
        rows = segments.classify(ep.features(), "排灣", 300.0)
        anchor = label_at(rows, 70)
        self.assertEqual((anchor["起秒"], anchor["迄秒"]), ("60", "120"))

    def test_the_studio_screen_changing_does_not_cut_the_anchor(self):
        # 2024-12-01 晚間卑南 276–307：主播段 31 秒，右爿虛擬螢幕半中
        # 央換畫面。修鏡頭邊界用區塊差ê中位數，換畫面彼幾格算做「別个
        # 鏡頭」修掉，賰無 26 秒，判做判不準。
        ep = Episode(300).anchor(60, 120)
        feats = ep.features()
        picture = feats["picture"].astype("float32")
        rng = np.random.default_rng(7)
        picture[90:120, :10] = rng.random((30, 10, 3))   # 16 塊內底 10 塊換
        feats["picture"] = picture.astype(np.float16)
        rows = segments.classify(feats, "卑南", 300.0)
        anchor = label_at(rows, 100)
        self.assertEqual((anchor["類型"], anchor["依據"]), ("攝影棚", "自動"))
        self.assertEqual((anchor["起秒"], anchor["迄秒"]), ("60", "120"))

    def test_the_interview_after_the_anchor_is_not_swallowed(self):
        # 183 42:01–42:04：主播段了後 2 秒無紅條，隨接受訪者人名條（紅
        # 條閣出現）。紅條橋過 2 秒，主播段就吞入受訪者彼段。
        ep = Episode(300).anchor(60, 120)
        ep.red[122:135] = 0.9                    # 受訪者人名條
        rows = segments.classify(ep.features(), "排灣", 300.0)
        self.assertEqual(label_at(rows, 119)["類型"], "攝影棚")
        self.assertEqual(label_at(rows, 121)["類型"], "外景新聞")
        self.assertEqual(label_at(rows, 130)["類型"], "外景新聞")


class TestUncertainRuns(unittest.TestCase):

    def test_a_14_second_closing_anchor_is_flagged_not_dropped(self):
        # 183 結尾主播外景只掛 14 秒紅條，20 秒門檻會判做外景新聞。
        ep = Episode(300).anchor(280, 294, studio=False)
        rows = segments.classify(ep.features(), "卑南", 300.0)
        row = label_at(rows, 285)
        self.assertEqual(row["依據"], segments.PENDING)
        self.assertIn(row["類型"], ("主播外景", "攝影棚", "外景新聞"))

    def test_a_short_anchor_in_the_studio_is_decided(self):
        # 2024-12：主播導言 19–25 秒、比中棚內參考格（距離 0.000），
        # 照紅條長度判不準，一集十段交讀者。比中棚內就夠確定：舊版型
        # 棚內 ≤0.031、戶外主播 ≥0.069。
        ep = Episode(300).anchor(100, 120)
        rows = segments.classify(ep.features(), "阿美", 300.0)
        row = label_at(rows, 110)
        self.assertEqual((row["類型"], row["依據"]), ("攝影棚", "自動"))

    def test_the_uncertain_seconds_are_listed_for_grabbing(self):
        ep = Episode(300).anchor(280, 294, studio=False)
        rows = segments.classify(ep.features(), "卑南", 300.0)
        seconds = segments.judge_seconds(rows)
        self.assertTrue(seconds)
        for second in seconds:
            self.assertTrue(280 <= second < 294, second)

    def test_no_studio_references_means_ask(self):
        ep = Episode(300).anchor(60, 120)
        feats = ep.features()
        feats["studio"] = np.full(300, np.nan, dtype=np.float32)
        rows = segments.classify(feats, "排灣", 300.0)
        self.assertEqual(label_at(rows, 90)["依據"], segments.PENDING)


class TestTwentyTwentyOneVersus(unittest.TestCase):

    def test_a_50_second_vs_super_is_not_the_studio(self):
        # 2021 年「VS」雙人名條紅條約 50 秒；棚內參考格比袂著。
        ep = Episode(400).anchor(100, 150, studio=False)
        rows = segments.classify(ep.features(), "阿美", 400.0)
        self.assertNotEqual(label_at(rows, 120)["類型"], "攝影棚")


class TestUnitsAndOtherLanguages(unittest.TestCase):

    def test_island_time_is_its_own_segment_and_asks_for_its_language(self):
        # 7/14 拉阿魯哇那集ê島語時間教泰雅語：單元語別愛讀者看標誌講。
        ep = Episode(600)
        unit = np.full(600, 0.4, dtype=np.float32)
        unit[200:450] = 0.02
        ep.units["島語時間"] = unit
        rows = segments.classify(ep.features(), "拉阿魯哇", 600.0)
        row = label_at(rows, 300)
        self.assertEqual(row["類型"], "島語時間")
        self.assertEqual(row["依據"], segments.PENDING)
        answered = segments.apply(rows, {row["起秒"]: ("島語時間", "泰雅")})
        self.assertEqual(label_at(answered, 300)["單元語別"], "泰雅")
        self.assertEqual(label_at(answered, 300)["依據"],
                         "Claude Vision 確認")
        self.assertEqual(label_at(answered, 100)["單元語別"], "拉阿魯哇")

    def test_a_changed_badge_is_a_candidate_for_another_language(self):
        # 202409015S0800：第 2300 秒後語別牌換做排灣。
        ep = Episode(3281)
        ep.badge[2300:] = 0.4
        rows = segments.classify(ep.features(), "拉阿魯哇", 3281.0)
        row = label_at(rows, 2500)
        self.assertEqual(row["依據"], segments.PENDING)
        answered = segments.apply(rows, {row["起秒"]: ("他族插播", "排灣")})
        got = label_at(answered, 2500)
        self.assertEqual((got["類型"], got["單元語別"]), ("他族插播", "排灣"))

    def test_the_box_gone_means_other_with_no_subtitle_rows(self):
        ep = Episode(300)
        ep.box[:30] = 0.4
        rows = segments.classify(ep.features(), "泰雅", 300.0)
        row = label_at(rows, 10)
        self.assertEqual(row["類型"], "其他")
        self.assertEqual((row["字幕上緣y"], row["字幕下緣y"]), ("", ""))

    def test_ordinary_segments_carry_the_band_rows(self):
        rows = segments.classify(Episode(300).features(), "泰雅", 300.0,
                                 band=(722, 848))
        self.assertEqual((rows[0]["字幕上緣y"], rows[0]["字幕下緣y"]),
                         ("722", "848"))


class TestCheck(unittest.TestCase):
    """段落表入 store 進前ê把關，逐項指名檔佮逝。"""

    NAME = "20240915_259_晨間_Hla'alua_拉阿魯哇"

    def rows(self):
        return [
            {"起秒": "0", "迄秒": "1190", "類型": "外景新聞",
             "單元語別": "拉阿魯哇", "字幕上緣y": "722", "字幕下緣y": "848",
             "依據": "自動"},
            {"起秒": "1190", "迄秒": "3281.000", "類型": "他族插播",
             "單元語別": "排灣", "字幕上緣y": "722", "字幕下緣y": "848",
             "依據": "Claude Vision 確認"},
        ]

    def test_a_good_table_passes(self):
        self.assertEqual(segments.check(self.rows(), self.NAME, 3281.0), [])

    def test_a_gap_is_named(self):
        rows = self.rows()
        rows[1]["起秒"] = "1195"
        problems = segments.check(rows, self.NAME, 3281.0)
        self.assertEqual(len(problems), 1)
        self.assertIn(self.NAME, problems[0])
        self.assertIn("第 3 逝", problems[0])

    def test_an_overlap_is_named(self):
        rows = self.rows()
        rows[1]["起秒"] = "1185"
        self.assertEqual(len(segments.check(rows, self.NAME, 3281.0)), 1)

    def test_an_informal_type_is_named(self):
        rows = self.rows()
        rows[0]["類型"] = "棚內"
        problems = segments.check(rows, self.NAME, 3281.0)
        self.assertEqual(len(problems), 1)
        self.assertIn("棚內", problems[0])

    def test_a_full_screen_card_is_its_own_type(self):
        # 2024-12 段落確認：新聞包內底ê電話訪問卡、公文、統計圖卡，
        # 讀者分做「外景新聞」抑是「其他」兩派；使用者裁定 2026-09-24
        # 另立「全螢幕圖卡」。伊有旁白字幕，毋是無字幕ê「其他」。
        rows = self.rows()
        rows[0]["類型"] = "全螢幕圖卡"
        self.assertEqual(segments.check(rows, self.NAME, 3281.0), [])
        self.assertNotIn("全螢幕圖卡", segments.NO_SUBTITLE)

    def test_interviewee_codes_are_checked(self):
        # 受訪者名條尾ê族名（「莊良賢(pasuya) Cou」）→ 語言別代號。
        # 空＝猶未查、「無」＝查過無名條；毋捌ê代號愛指名。
        rows = self.rows()
        rows[0][segments.INTERVIEWEE] = "tsu bnn"
        rows[1][segments.INTERVIEWEE] = segments.NONE_SEEN
        self.assertEqual(segments.check(rows, self.NAME, 3281.0), [])
        rows[1][segments.INTERVIEWEE] = "Cou"
        problems = segments.check(rows, self.NAME, 3281.0)
        self.assertEqual(len(problems), 1)
        self.assertIn("第 3 逝", problems[0])
        self.assertIn("Cou", problems[0])

    def test_a_blank_language_is_named(self):
        rows = self.rows()
        rows[0]["單元語別"] = ""
        self.assertEqual(len(segments.check(rows, self.NAME, 3281.0)), 1)

    def test_an_unconfirmed_row_is_named(self):
        rows = self.rows()
        rows[1]["依據"] = segments.PENDING
        problems = segments.check(rows, self.NAME, 3281.0)
        self.assertEqual(len(problems), 1)
        self.assertIn(segments.PENDING, problems[0])

    def test_it_must_start_at_zero_and_end_at_the_video_length(self):
        rows = self.rows()
        rows[0]["起秒"] = "3"
        rows[1]["迄秒"] = "3000"
        self.assertEqual(len(segments.check(rows, self.NAME, 3281.0)), 2)


class TestJudgeSheets(unittest.TestCase):
    """判不準ê段逐段三格縮細拼一逝，一張 6 段。

    一集判不準約 10 段、29 張全解析原圖，逐張交讀者一集就八萬 token；
    縮做 480 闊、一張 6 段，一集兩張。
    """

    def test_six_segments_to_a_sheet_each_labelled(self):
        from PIL import Image
        rows = []
        for index in range(8):
            rows.append({"起秒": str(index * 100),
                         "迄秒": str(index * 100 + 100), "類型": "主播外景",
                         "單元語別": "阿美", "字幕上緣y": "722",
                         "字幕下緣y": "848", "依據": segments.PENDING})
        rows[-1]["迄秒"] = "800.000"
        with tempfile.TemporaryDirectory() as work:
            judge = os.path.join(work, "7-shots", "judge")
            os.makedirs(judge)
            for second in segments.judge_seconds(rows):
                Image.new("RGB", (1920, 1080), (9, 9, 9)).save(
                    os.path.join(judge, "%05d.png" % second))
            made = segments.judge_sheets(work, rows)
            self.assertEqual(len(made), 2)
            first = Image.open(made[0][0])
            self.assertLessEqual(first.width, 2000)
            self.assertLessEqual(first.height, 2000)
            self.assertEqual(made[0][1], ["0", "100", "200", "300", "400",
                                          "500"])


class TestFile(unittest.TestCase):

    def test_what_is_written_is_what_is_read(self):
        rows = segments.classify(Episode(120).anchor(10, 50).features(),
                                 "泰雅", 120.0)
        with tempfile.TemporaryDirectory() as work:
            segments.write(os.path.join(work, "0-segments.csv"), rows)
            back = segments.read(os.path.join(work, "0-segments.csv"))
        self.assertEqual(back, rows)

    def test_the_columns_are_the_ones_the_spec_names(self):
        self.assertEqual(segments.COLUMNS,
                         ("起秒", "迄秒", "類型", "單元語別", "字幕上緣y",
                          "字幕下緣y", "依據", "受訪者語言別代號"))

    def test_a_table_written_before_the_interviewee_column_still_reads(self):
        # 2026-09-24 以前入庫ê表無這欄；讀入來當做「猶未查」（空ê）。
        with tempfile.TemporaryDirectory() as work:
            path = os.path.join(work, "0-segments.csv")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("起秒,迄秒,類型,單元語別,字幕上緣y,字幕下緣y,依據\n"
                             "0,60.000,攝影棚,邵,722,848,自動\n")
            rows = segments.read(path)
        self.assertEqual(rows[0][segments.INTERVIEWEE], "")
        self.assertEqual(segments.check(rows, "x", 60.0), [])


class TestShotsMeasuresTheBadge(unittest.TestCase):
    """他族插播靠語別牌換：shots 愛量語別牌彼塊佮開頭ê距離。"""

    def test_the_badge_changes_after_the_switch(self):
        rng = np.random.default_rng(0)
        thumbs = rng.integers(0, 256, size=(200, 90, 160, 3), dtype=np.uint8)
        rows, cols = shots.BADGE
        thumbs[:, rows, cols] = (200, 30, 30)
        thumbs[150:, rows, cols] = (30, 30, 200)
        got = shots.badge_distance(thumbs)
        self.assertTrue((got[:150] < 0.05).all())
        self.assertTrue((got[150:] > 0.2).all())


if __name__ == "__main__":
    unittest.main()
