"""namebars：受訪者名條 → 段落表「受訪者語言別代號」。

單元語別看語別牌，是這集ê族；受訪者毋一定是。2024-12 段落確認時讀者
一再報：邵語那集的受訪者名條標 Cou、排灣那集標 Atayal、布農那集的撒奇
萊雅族人專題……講ê可能是別族語抑是華語（使用者裁定 2026-09-24 愛另外
標）。

2024-08 起ê版型：受訪者名條是純紅（`shots` 量ê `name` 比例 ≥0.47），
右爿黃字「莊良賢(pasuya) Cou」，族名是節目目錄ê英文拼法。2024-12 一集
平均出現 43 擺，仝一个人講幾若擺就出現幾若擺，所以仝款ê名條干焦讀一擺。
"""
import os
import unittest
from unittest import mock

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


class TestScanStreams(unittest.TestCase):
    """舊版型逐秒掃描袂使規支影片讀入記憶體。

    2026-09-25 早起：一集 2910 秒 × 1920×180×3 ＝ 3 GB 原始資料一擺讀入、
    閣轉 int16 陣列，切 cue 六集同齊走，記憶體食了，VS Code 予 OOM 刣
    （kill -9）。愛一格一格讀、算了就放掉。
    """

    def test_it_reads_one_frame_at_a_time(self):
        import subprocess
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            video = os.path.join(tmp, "v.mp4")
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
                            "-i", "color=c=0xB01010:s=1920x1080:r=5:d=4",
                            "-c:v", "libx264", "-pix_fmt", "yuv420p", video],
                           check=True)
            seen = []
            real = namebars._frames

            def counting(stream, size):
                for frame in real(stream, size):
                    seen.append(len(frame))
                    yield frame

            with mock.patch.object(namebars, "_frames", counting):
                title, name, red = namebars.scan_old(video)
        self.assertEqual(len(red), 4)
        self.assertGreater(float(red[0]), 0.9)
        self.assertEqual(seen, [1920 * 180 * 3] * 4)


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

    def test_groups_outside_the_sixteen_map(self):
        # 使用者裁定 2026-09-25：畢甘布 xbe、西拉雅 fos（ISO 639-3），
        # 馬卡道 ISO 查無，代號就寫漢字「馬卡道」。名條實際寫法：
        # 「Pikangcu」「畢甘布族」「Silaya(西拉雅族)」「Makataw(馬卡道族)」
        # 「Makatao」「Makatau」。
        for word, code in (("Pikangcu", "xbe"), ("畢甘布族", "xbe"),
                           ("Silaya(西拉雅族)", "fos"), ("西拉雅族", "fos"),
                           ("Makataw(馬卡道族)", "馬卡道"),
                           ("Makatao", "馬卡道"), ("Makatau", "馬卡道")):
            self.assertEqual(namebars.code_of(word), code, word)

    def test_the_2021_screen_spellings_map(self):
        # 2021-11 舊版型名條實際印ê：「Yami(達悟)族」（英文、括號中文、
        # 閣加「族」，3 條）；錯字「Kanakanvu」（11-04 晚間 217 秒）、
        # 「Seeidq」（Walis Pawan，641 秒）。
        self.assertEqual(namebars.code_of("Yami(達悟)族"), "tao")
        self.assertEqual(namebars.code_of("Kanakanvu"), "xnb")
        self.assertEqual(namebars.code_of("Seeidq"), "trv")
        # 2022-01 名條印「Seetiq」（2537 秒）。
        self.assertEqual(namebars.code_of("Seetiq"), "trv")
        # 2023-06-23 午間松東隆 342 秒印「Bunu」，仝一人別擺印 Bunun。
        self.assertEqual(namebars.code_of("Bunu"), "bnn")

    def test_foreign_groups_on_the_bars_have_codes(self):
        # 名條印ê外國族群，本底對無代號、受訪者欄空咧（使用者裁定
        # 2026-09-25：先寫入 OTHER_GROUPS，報告時才列）：
        # 2021-11-13 晚間 2004／2039 秒「Māori」、11-12 晚間 2637 秒
        # 「彝族」、2022-01-03 2702／2779 秒「Dolgan」、2023-06-22
        # 2472 秒「祖魯族」。
        self.assertEqual(namebars.code_of("Māori"), "mri")
        self.assertEqual(namebars.code_of("Maori"), "mri")
        self.assertEqual(namebars.code_of("彝族"), "iii")
        self.assertEqual(namebars.code_of("Dolgan"), "dlg")
        self.assertEqual(namebars.code_of("祖魯族"), "zul")

    def test_the_2023_07_plains_and_foreign_names_map(self):
        # 2023-07 名條：「潘英傑 Pacay」（巴宰）、「潘正浩 kahabu」（噶哈巫，
        # 小寫）、「Katrina Esau San」（南非桑人；桑人無單一 ISO 代號，
        # 比照馬卡道寫漢字）。
        self.assertEqual(namebars.code_of("Pacay"), "pzh")
        self.assertEqual(namebars.code_of("kahabu"), "pzh-x-kaxabu")
        self.assertEqual(namebars.code_of("San"), "桑")

    def test_taivoan_has_its_own_code(self):
        # 2022-01 名條「潘鄔奈 大武壠族」。SIL 有 Taivoan（tvx）。
        self.assertEqual(namebars.code_of("大武壠族"), "tvx")
        self.assertEqual(namebars.code_of("Taivoan"), "tvx")

    def test_nlakapamux_is_thompson_salish(self):
        # 2022-01 紐西蘭紋身藝術節，名條「Dion Kaszas Nlaka'pamux」
        # （加拿大）。SIL：Thompson River Salish（thp）。無通行漢譯，
        # 鍵照原文。
        self.assertEqual(namebars.code_of("Nlaka'pamux"), "thp")

    def test_the_2023_07_08_foreign_groups_map(self):
        # 2023-07／08 名條：「Scott Wabano Cree」（加拿大）、「Carmen・
        # Montupil・Curin Mapuche a binacadan」（智利）、「Pepe・Pakarati
        # Rapa Nui a binacadan」（復活節島，名條欄以空白分族名，寫
        # SIL 名 Rapanui）、「Sergio Muti Tembé Tembé/Tenetehara」（巴西）、
        # 「Melissa Mills, Garingbal Ghungulu族」（澳洲）。無通行漢譯ê
        # 鍵照原文。
        self.assertEqual(namebars.code_of("Cree"), "cre")
        self.assertEqual(namebars.code_of("Mapuche"), "arn")
        self.assertEqual(namebars.code_of("Rapanui"), "rap")
        self.assertEqual(namebars.code_of("Tembé"), "tqb")
        self.assertEqual(namebars.code_of("Garingbal"), "xgi")

    def test_papora_and_carib_have_codes(self):
        # 2023-07-02 晚間 442 秒名條「張麗盆 拍瀑拉族」（平埔族群，SIL
        # Papora `ppu`）；2023-07 2180–2250 秒三人名條「… Carib」
        # （蓋亞那，SIL Galibi Carib `car`）。
        self.assertEqual(namebars.code_of("拍瀑拉族"), "ppu")
        self.assertEqual(namebars.code_of("Carib"), "car")

    def test_kebalan_is_kavalan(self):
        # 20230718_199 午間 826、930 秒名條印全小寫「kebalan」（林進展、
        # 江素珍），同集別條寫 Kavalan。Kebalan 是噶瑪蘭族自稱；無別名
        # 時 apply 規集 SKIP，受訪者欄攏空。
        self.assertEqual(namebars.code_of("kebalan"), "ckv")
        self.assertEqual(namebars.code_of("Kebalan"), "ckv")

    def test_navajo_ngardi_wiradjuri_have_codes(self):
        # 2023-08-27／28 名條：「Jayne Sandoval 納瓦霍族」（SIL Navajo
        # `nav`）、「Dale Huddleston, Ngardi/Wiradjuri」（SIL Ngardi
        # `rxd`、Wiradjuri `wrh`）。無對照時 apply 規集 SKIP。
        self.assertEqual(namebars.code_of("納瓦霍族"), "nav")
        self.assertEqual(namebars.code_of("Ngardi"), "rxd")
        self.assertEqual(namebars.code_of("Wiradjuri"), "wrh")

    def test_shoshone_and_kuki_have_codes(self):
        # 2023-09 名條：「Gary McKinney Shoshone-Paiute」（SIL Shoshoni
        # `shh`，一人兩族記頭一个）、「Nengjahat Kuki」「Ngaineikim Kuki」
        # （Kuki-Chin 一群語言，SIL 無單一代號，代號寫族名）。
        self.assertEqual(namebars.code_of("Shoshone"), "shh")
        self.assertEqual(namebars.code_of("Kuki"), "Kuki")

    def test_maasai_wakka_wakka_and_aliases(self):
        # 2023-09-19～23 名條：「Ole Iguanani Maasai」（SIL Masai `mas`）、
        # 「Corey Appo Wakka Wakka」（SIL Wakawaka `wkw`；族名中央有空白，
        # 莫當做兩人）、巴宰族語自稱「Pacaicu」（愛蘭教會 150 週年）、
        # 毛利族語拼法「Maulii」。無對照時 apply 規集 SKIP。
        self.assertEqual(namebars.code_of("Maasai"), "mas")
        self.assertEqual(namebars.code_of("Wakka Wakka"), "wkw")
        # 讀者答案以空白隔兩人（VS 名條）；族名本身有空白ê愛先整个查，
        # 無就會切做兩个「Wakka」，apply 規集 SKIP（265 晚間踏過）。
        self.assertEqual(namebars.codes_of("Wakka Wakka"), ["wkw"])
        self.assertEqual(namebars.codes_of("Amis Sakizaya"), ["ami", "szy"])
        self.assertEqual(namebars.code_of("Pacaicu"),
                         namebars.code_of("Pacay"))
        self.assertEqual(namebars.code_of("Maulii"),
                         namebars.code_of("Māori"))

    def test_nisgaa_has_code(self):
        # 2023-09 名條「Sim'oogit Ni'isjoohl Nisga'a」（加拿大原住民），
        # SIL Nisga'a `ncg`；族名有撇號。無對照時 apply 規集 SKIP。
        self.assertEqual(namebars.code_of("Nisga'a"), "ncg")
        self.assertEqual(namebars.codes_of("Nisga'a"), ["ncg"])

    def test_tembe_has_code(self):
        # 2023-10 名條「Sergio Muti Tembé  Tembé /Tenetehara」（巴西），
        # SIL Tembé `tqb`；名條斜線後是 Tenetehara 別稱，嘛愛對會著。
        self.assertEqual(namebars.code_of("Tembé"), "tqb")
        self.assertEqual(namebars.code_of("Tenetehara"), "tqb")

    def test_paipulacu_is_papora(self):
        # 2023-10 名條拍瀑拉族寫羅馬字「Paipulacu」（第 67 批 s010 第 7–9 列），
        # 2023-07 名條寫漢字「拍瀑拉族」，兩種攏愛對著 Papora `ppu`。
        self.assertEqual(namebars.code_of("Paipulacu"), "ppu")
        self.assertEqual(namebars.code_of("拍瀑拉族"), "ppu")

    def test_paiwang_typo_is_paiwan(self):
        # 20230824_236 午間 1788 秒蔡靜婷ê名條印「Paiwang」（加一个 g）；
        # 無別名時 apply 規集 SKIP。
        self.assertEqual(namebars.code_of("Paiwang"),
                         namebars.code_of("Paiwan"))

    def test_2023_11_spellings(self):
        # 第 68 批（2023-11）名條印過ê拼法：「Rukay」（s090 第 14、17 列）、
        # 「Paywang」（s091 第 2 列）、「Tao/Yami」（s092 第 9 列，已有
        # 「Yami/Tao」毋過斜線倒反）、「Makadaw」（s004 第 8 列潘信州，
        # 馬卡道）。無別名時 apply 規集 SKIP。
        self.assertEqual(namebars.code_of("Rukay"),
                         namebars.code_of("Rukai"))
        self.assertEqual(namebars.code_of("Paywang"),
                         namebars.code_of("Paiwan"))
        self.assertEqual(namebars.code_of("Tao/Yami"),
                         namebars.code_of("Yami"))
        self.assertEqual(namebars.code_of("Makadaw"),
                         namebars.code_of("Makatao"))

    def test_2023_12_spellings(self):
        # 第 69 批（2023-12）名條印過ê拼法：「Aatayal」（s082 三列，濟一个
        # a）、「Paiawn」（s103 第 9 列江雅蕾）、「Paypula」（s066 第 4 列
        # 潘明燈，仝人另一條寫「拍瀑拉族」）、「Taukas」（s100 第 17 列
        # 王商益，道卡斯）、「Seejiq」（賽德克自稱ê另一種拼法）。
        self.assertEqual(namebars.code_of("Aatayal"),
                         namebars.code_of("Atayal"))
        self.assertEqual(namebars.code_of("Paiawn"),
                         namebars.code_of("Paiwan"))
        self.assertEqual(namebars.code_of("Paypula"),
                         namebars.code_of("拍瀑拉族"))
        self.assertEqual(namebars.code_of("Taukas"),
                         namebars.code_of("道卡斯族"))
        self.assertEqual(namebars.code_of("Seejiq"),
                         namebars.code_of("Seediq"))

    def test_aymara_has_code(self):
        # 2024-02 名條第 70 批：「Marcelina Choque Aymara」「Maria Choque
        # Aymara」（玻利維亞），s042 另一則仝兩人印「Aymara cuku」——cuku
        # 是卡那卡那富語ê「族」，毋是第二个人。照空白切會變做 Aymara＋
        # 對無ê cuku，規集 SKIP。SIL 總稱代號 `aym`（比照 Cree `cre`）。
        self.assertEqual(namebars.code_of("Aymara"), "aym")
        self.assertEqual(namebars.codes_of("Aymara cuku"), ["aym"])

    def test_2024_03_spellings(self):
        # 第 71 批（2024-03）名條：「Puyuma」（s026 林志興、s049 潘調志，
        # 卑南ê另一種拼法）、「Ta'urung」（s052 李文瑞，仝人 s041 印
        # 「大武壠族」）、「makataw」（s004 潘玉燕，小寫）。對無ê時陣規集
        # SKIP，段落表受訪者欄就空ê。
        self.assertEqual(namebars.code_of("Puyuma"),
                         namebars.code_of("Pinuyumayan"))
        self.assertEqual(namebars.code_of("Ta'urung"),
                         namebars.code_of("大武壠族"))
        self.assertEqual(namebars.code_of("makataw"),
                         namebars.code_of("Makatao"))

    def test_ainu_and_sami_have_codes(self):
        # 第 71 批外國族群：「愛努族」（s032、s040 富菜栄子、熊谷カネ，
        # 日本）→ SIL Ainu (Japan) `ain`；「薩米族」（s079 Mariela
        # Idivuoma，NRK Sápmi）→ ISO 639-3 無薩米總稱，比照彝用上濟人講ê
        # 北薩米 `sme`。
        self.assertEqual(namebars.code_of("愛努族"), "ain")
        self.assertEqual(namebars.code_of("薩米族"), "sme")

    def test_seejiq_truku_is_one_person(self):
        # s050 第 17、19 列 Awi Walis、Awe Sing(沈惠美) 印「Seejiq Truku」：
        # 一个人一个族名（德鹿谷群ê賽德克），毋是 VS 兩人。照空白切會變做
        # 賽德克＋太魯閣兩个代號，段落表就寫兩族。
        self.assertEqual(namebars.codes_of("Seejiq Truku"),
                         [namebars.code_of("Seediq")])

    def test_dawulong_is_taivoan(self):
        # 20230810_222 午間 633–677 秒三人名條「張惠慈 Dawulong」，頂排
        # 「Riguang Siyawrin」（小林）。Dawulong 是大武壠ê華語音譯，毋是
        # 地名；無別名時讀者判「?」、apply 規集 SKIP。
        self.assertEqual(namebars.code_of("Dawulong"), "tvx")

    def test_kahabu_capitalised_is_kaxabu(self):
        # 2023-07 黃子豪、周珈萱、林智文ê名條「Kahabu」，大寫開頭；
        # 小寫 kahabu 早就有別名。
        self.assertEqual(namebars.code_of("Kahabu"), "pzh-x-kaxabu")

    def test_taokas_is_written_in_han_like_makatao(self):
        # 劉新苗ê名條：11-24 晚間 2439 秒「Tawkase」、11-27 晨間 2734 秒
        # 「Taukat」。SIL 代碼表查無 Taokas，比照馬卡道寫漢字。
        self.assertEqual(namebars.code_of("Tawkase"), "道卡斯")
        self.assertEqual(namebars.code_of("Taukat"), "道卡斯")
        self.assertEqual(namebars.code_of("道卡斯族"), "道卡斯")

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
                     "依據": "自動", segments.INTERVIEWEE: "",
                     segments.SPEECH: ""})
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

    def test_what_they_speak_is_left_open(self):
        # 名條干焦講伊是佗一族，講族語抑是華語看袂出來；先標「族語或
        # 華語」，後壁用華語 ASR 判（使用者裁定 2026-09-25）。
        rows = namebars.assign(table(), {70: "tsu"})
        got = []
        for row in rows:
            got.append(row[segments.SPEECH])
        self.assertEqual(got, [segments.NONE_SEEN, segments.UNSURE,
                               segments.NONE_SEEN, segments.NONE_SEEN])

    def test_the_result_passes_the_table_check(self):
        rows = namebars.assign(table(), {70: "ssf", 300: "tsu"})
        rows[-1]["迄秒"] = "400.000"
        self.assertEqual(segments.check(rows, "x", 400.0), [])


if __name__ == "__main__":
    unittest.main()
