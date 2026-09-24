"""namebars：受訪者名條 → 段落表「受訪者語言別代號」。

單元語別看語別牌，是這集ê族；受訪者毋一定是。2024-12 段落確認時讀者
一再報：邵語那集的受訪者名條標 Cou、排灣那集標 Atayal、布農那集的撒奇
萊雅族人專題……講ê可能是別族語抑是華語（使用者裁定 2026-09-24 愛另外
標）。

2024-08 起ê版型：受訪者名條是純紅（`shots` 量ê `name` 比例 ≥0.47），
右爿黃字「莊良賢(pasuya) Cou」，族名是節目目錄ê英文拼法。2024-12 一集
平均出現 43 擺，仝一个人講幾若擺就出現幾若擺，所以仝款ê名條干焦讀一擺。
"""
import unittest

import numpy as np

from scripts.errors import PipelineError
from scripts.news import namebars
from scripts.news import segments


class TestAppearances(unittest.TestCase):

    def test_each_run_of_the_bar_is_grabbed_once_in_its_middle(self):
        # 名條有ê一字一字淡入，要幾若秒族名才出現：2024-12 頭 20 集
        # 截「出現了後 1 秒」，754 張內底 14 張族名猶未出來抑是賰半透明
        # （12-02 午間 111 秒「Abaliusu(杜張梅莊) R…」）。截中央彼秒。
        name = np.zeros(60, dtype=np.float32)
        name[10:20] = 0.6
        name[30:31] = 0.6             # 干焦一秒：抓彼秒本身
        name[40:55] = 0.3             # 主播段標題條（偏粉）毋是名條
        self.assertEqual(namebars.appearances(name), [15, 30])

    def test_the_other_name_of_yami_and_screen_typos_map(self):
        # 名條實際印ê：「Yami(Tao)」「Yami/Tao」；錯字「Ruaki」（12-08
        # 午間伍麗華等 4 人，同一人別集攏標 Rukai）、「Pinuyummayan」。
        for word in ("Yami(Tao)", "Yami/Tao", "Tao"):
            self.assertEqual(namebars.code_of(word), "tao", word)
        self.assertEqual(namebars.code_of("Ruaki"), "dru")
        self.assertEqual(namebars.code_of("Pinuyummayan"), "pyu")


class TestShortBars(unittest.TestCase):
    """`name` 特徵比名條本身早落：12-02 午間 111 秒只算一秒名條，畫面
    上 112–114 秒名條猶佇，族名「Rukai」112 秒才淡入完成。2024-12 頭
    30 集 1127 張內底 62 張看無族名，大部份是這款短 run。"""

    def test_a_short_run_also_tries_later_seconds(self):
        name = np.zeros(60, dtype=np.float32)
        name[10:11] = 0.6             # 一秒
        name[30:50] = 0.6             # 20 秒：中央就夠
        self.assertEqual(namebars.tries(name), [[10, 12, 14], [40]])

    def test_the_crop_with_the_most_yellow_wins(self):
        half = crop(range(20, 60))
        full = crop(range(20, 160))
        empty = crop([])
        self.assertEqual(namebars.fullest([half, full, empty]), 1)


class TestOldLayout(unittest.TestCase):
    """2021-11～2024-07 ê版型：名條是白字，上排細字職稱（y 860–900），
    下排置中人名＋族名（y 930–1000）；新聞標題是大字、干焦下排。
    `20211101_305_晚間_Amis_阿美` 逐秒量：名條職稱 2100–2800、人名
    1 萬–1.3 萬；標題職稱 0、人名 3.5 萬；亮背景紅條 0。"""

    def signals(self, n=40):
        title = np.zeros(n)
        name = np.zeros(n)
        red = np.full(n, 0.41)
        return title, name, red

    def test_a_title_over_a_name_is_a_name_bar(self):
        title, name, red = self.signals()
        title[10:20] = 2500
        name[10:20] = 12000
        self.assertEqual(namebars.old_tries(title, name, red), [[15]])

    def test_a_headline_is_not(self):
        title, name, red = self.signals()
        name[10:20] = 35000                # 大字標題，職稱排空ê
        self.assertEqual(namebars.old_tries(title, name, red), [])

    def test_a_bright_picture_without_the_red_strip_is_not(self):
        title, name, red = self.signals()
        title[10:20] = 3093
        name[10:20] = 7212
        red[10:20] = 0.0
        self.assertEqual(namebars.old_tries(title, name, red), [])

    def test_the_layout_follows_the_preset(self):
        self.assertEqual(namebars.style_for("titv-news-2024-08"), "new")
        self.assertEqual(namebars.style_for("titv-news-848"), "old")
        self.assertEqual(namebars.style_for("titv-news"), "old")
        self.assertIsNone(namebars.style_for("aiyalaeho-bilingual"))


class TestRegion(unittest.TestCase):

    def test_the_whole_red_bar_is_cropped(self):
        # 名條短ê時族名毋是靠正爿：頭 20 集干焦裁 x 900 起，讀者看著
        # 「an」「mis」「tayal」——族名頭前半截落佇 900 左爿。紅條本身
        # 是 x≈360–1810。
        # 閣來：長名條ê黃字會排到畫面正爿邊，裁到 1830 為止，12-19 午間
        # 「Panay(徐婉玉) A…」族名干焦賰頭一字母。裁到畫面邊 1920。
        x, _y, w, _h = namebars.REGION
        self.assertLessEqual(x, 360)
        self.assertEqual(x + w, 1920)


def crop(text_columns, height=40, width=200):
    """合成名條：紅底，指定ê欄位是黃字。"""
    rgb = np.zeros((height, width, 3), dtype=np.uint8)
    rgb[:, :] = (180, 20, 20)
    for column in text_columns:
        rgb[10:30, column] = (240, 210, 40)
    return rgb


class TestSamePerson(unittest.TestCase):

    def test_the_same_bar_again_is_read_once(self):
        a = crop(range(20, 80))
        b = crop(range(120, 190))
        groups = namebars.group([a, b, a.copy(), b.copy()])
        self.assertEqual(groups, [0, 1, 0, 1])

    def test_a_bar_without_yellow_text_is_its_own_group(self):
        # 無名字ê紅條（跑馬、錯抓）袂使佮別張黏做伙。
        empty = crop([])
        groups = namebars.group([empty, crop(range(20, 80)), empty])
        self.assertEqual(groups[1], 1)
        self.assertNotEqual(groups[0], groups[1])


class TestCodes(unittest.TestCase):

    def test_the_programme_spelling_and_the_chinese_name_both_map(self):
        self.assertEqual(namebars.code_of("Cou"), "tsu")
        self.assertEqual(namebars.code_of("SaySiyat"), "xsy")
        self.assertEqual(namebars.code_of("太魯閣"), "trv-x-truku")
        self.assertEqual(namebars.code_of("Kaxabu"), "pzh-x-kaxabu")

    def test_a_vs_bar_gives_both_codes(self):
        # 12-03 午間 2573 秒「… Amis VS. … Sakizaya」，讀者寫兩个族別。
        self.assertEqual(namebars.codes_of("Amis Sakizaya"), ["ami", "szy"])
        self.assertEqual(namebars.codes_of("Yami(Tao)"), ["tao"])
        self.assertEqual(namebars.codes_of(""), [])

    def test_chinese_with_the_zu_suffix_and_bracketed_forms_map(self):
        # 12-15 晚間 VS 名條「朱日妹 布農族 VS 張彩蓉 Bunun」；
        # 「李淑媛 Silaya(西拉雅族)」這款英文加括號中文。
        self.assertEqual(namebars.code_of("布農族"), "bnn")
        self.assertEqual(namebars.code_of("Amis(阿美族)"), "ami")

    def test_no_tribe_on_the_bar_is_empty(self):
        self.assertEqual(namebars.code_of(""), "")

    def test_an_unknown_word_is_named(self):
        with self.assertRaises(PipelineError) as caught:
            namebars.code_of("Hakka")
        self.assertIn("Hakka", str(caught.exception))


def table():
    rows = []
    for start, end, kind in ((0, 60, "攝影棚"), (60, 200, "外景新聞"),
                             (200, 260, "攝影棚"), (260, 400, "外景新聞")):
        rows.append({"起秒": str(start), "迄秒": str(end), "類型": kind,
                     "單元語別": "邵", "字幕上緣y": "722", "字幕下緣y": "848",
                     "依據": "自動", segments.INTERVIEWEE: ""})
    return rows


class TestAssign(unittest.TestCase):

    def test_codes_land_in_the_segment_they_were_seen_in(self):
        rows = namebars.assign(table(), {70: "ssf", 90: "tsu", 120: "tsu",
                                         300: "tay"})
        got = []
        for row in rows:
            got.append(row[segments.INTERVIEWEE])
        self.assertEqual(got, ["無", "ssf tsu", "無", "tay"])

    def test_two_codes_seen_at_once_both_land(self):
        rows = namebars.assign(table(), {70: "ami szy", 90: "szy"})
        self.assertEqual(rows[1][segments.INTERVIEWEE], "ami szy")

    def test_a_bar_without_a_tribe_does_not_add_a_code(self):
        # 漢人受訪者名條無族名；彼段猶是「查過」，毋是空ê。
        rows = namebars.assign(table(), {70: ""})
        self.assertEqual(rows[1][segments.INTERVIEWEE], "無")

    def test_the_result_passes_the_table_check(self):
        rows = namebars.assign(table(), {70: "ssf", 300: "tsu"})
        rows[-1]["迄秒"] = "400.000"
        self.assertEqual(segments.check(rows, "x", 400.0), [])


if __name__ == "__main__":
    unittest.main()
