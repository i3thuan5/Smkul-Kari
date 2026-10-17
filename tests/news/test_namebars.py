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

    def test_kooma_and_bazii(self):
        # 2023-06 名條第 111 批：153 晚間「Brett Leavy Kooma」（澳洲 Kooma，
        # 族語 Guwamu，SIL `gwu`）、161 晨間 108 秒「潘英傑 Bazii」（巴宰
        # 另一款拼法）。無對照時 apply 規集 SKIP。
        self.assertEqual(namebars.code_of("Kooma"), "gwu")
        self.assertEqual(namebars.code_of("Bazii"),
                         namebars.code_of("Pacay"))
        # 161 晨間 512 秒「楊振綸 Silaiya」：西拉雅閣一款拼法。
        self.assertEqual(namebars.code_of("Silaiya"), "fos")

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

    def test_2024_04_and_05_spellings(self):
        # 第 72、73 批（2024-04、05）名條印走樣ê拼法：「Mawri」（b73-s103
        # 紐西蘭毛利）、「Paipura」（b73-s090 白俊忠，拍瀑拉）、「Piawan」
        # （b72-s096 達比烏蘭·古勒勒）、「SaySiyta」（b73-s008）、
        # 「Sámi」（b73-s078、s106 Mariela Idivuoma，字距拉開ê á）、
        # 「Taulong」（b73-s049 楊山樟，大武壠）。對無ê規集 SKIP，受訪者
        # 欄就空ê。
        self.assertEqual(namebars.code_of("Mawri"), namebars.code_of("Māori"))
        self.assertEqual(namebars.code_of("Paipura"),
                         namebars.code_of("拍瀑拉族"))
        self.assertEqual(namebars.code_of("Piawan"),
                         namebars.code_of("Paiwan"))
        self.assertEqual(namebars.code_of("SaySiyta"),
                         namebars.code_of("SaySiyat"))
        self.assertEqual(namebars.code_of("Sámi"), namebars.code_of("薩米族"))
        self.assertEqual(namebars.code_of("Taulong"),
                         namebars.code_of("大武壠族"))

    def test_ainu_and_sami_have_codes(self):
        # 第 71 批外國族群：「愛努族」（s032、s040 富菜栄子、熊谷カネ，
        # 日本）→ SIL Ainu (Japan) `ain`；「薩米族」（s079 Mariela
        # Idivuoma，NRK Sápmi）→ ISO 639-3 無薩米總稱，比照彝用上濟人講ê
        # 北薩米 `sme`。
        self.assertEqual(namebars.code_of("愛努族"), "ain")
        self.assertEqual(namebars.code_of("薩米族"), "sme")

    def test_2024_07_spellings(self):
        # 第 75 批（2024-07）名條：「嘎哈巫族」（b75-s013，20240706_188
        # 晚間 1479、1570 秒，「噶」寫做「嘎」）、「Daukas」（b75-s056、
        # 20240720_202 晨間 645 秒劉新苗、689 秒劉秋雲，道卡斯；仝兩人
        # b75-s040 印「道卡斯族」）、「Kwukasu」（b75-s030，20240713_195
        # 午間 343、397 秒仝兩人，頂排族語句印「Twukasu」）。對無ê規集
        # SKIP，受訪者欄就空ê。
        self.assertEqual(namebars.code_of("嘎哈巫族"),
                         namebars.code_of("噶哈巫族"))
        self.assertEqual(namebars.code_of("Daukas"),
                         namebars.code_of("道卡斯族"))
        self.assertEqual(namebars.code_of("Kwukasu"),
                         namebars.code_of("道卡斯族"))

    def test_2024_09_dawkas_and_yami_with_bracket(self):
        # 第 112 批（2024-09）名條：「Dawkas」（b112-s002，20240926_270
        # 午間 1280 秒張壽琴、1379 秒王商益，道卡斯；仝一則標題「道卡斯.
        # 邵族」，王商益 2023-12 印 Taukas）、「Yami(達悟)族」（b112-s015
        # 1233 秒夏曼．馬得能，族名後壁閣加括號中文佮「族」）。
        self.assertEqual(namebars.code_of("Dawkas"),
                         namebars.code_of("道卡斯族"))
        self.assertEqual(namebars.codes_of("Yami(達悟)族"),
                         [namebars.code_of("Yami")])

    def test_2024_01_foreign_groups_and_pwaiwan(self):
        # 第 114 批（2024-01）名條：「Hernando Prado/Pinon Tatuyo」（b114-s048
        # 第 4 列，20240115_015 午間 2667 秒，哥倫比亞亞馬遜）、「Noeleen
        # Lalara Anindilyakwa族」（b114-s064 第 9 列，20240121_021 晚間 791
        # 秒；b114-s079 仝人印「Anindilyakwa」，澳洲）、「Gennadiy
        # Buryatia」（b114-s030 第 14 列，20240110_010 晚間 2475 秒——
        # Buryatia 是布里亞特共和國ê地名，族名是 Buryat）、「陳偉哲
        # Pwaiwan」（b114-s061 第 6 列，20240120_020 午間 729 秒，Paiwan
        # 拍毋著）。
        self.assertEqual(namebars.code_of("Tatuyo"), "tav")
        self.assertEqual(namebars.code_of("Anindilyakwa"), "aoi")
        self.assertEqual(namebars.codes_of("Anindilyakwa族"), ["aoi"])
        self.assertEqual(namebars.code_of("Buryatia"), "bxr")
        self.assertEqual(namebars.code_of("Pwaiwan"),
                         namebars.code_of("Paiwan"))
        # 「Lowell Yellowhorn  Piikani cu」（b114-s015 第 5 列，
        # 20240106_006 午間 906 秒，加拿大 Lethbridge College），抽影片
        # 四格攏是「Piikani cu」，cu 毋是第二个人。
        self.assertEqual(namebars.codes_of("Piikani cu"), ["bla"])

    def test_babuza_and_mikmaq_have_codes(self):
        # 第 75 批外國／平埔族群：「巴布薩族」（b75-s013，20240706_188
        # 晚間 1645 秒）、「Babuza」（b75-s051，20240719_201 晚間 1765 秒
        # 乃俊廷）→ SIL Babuza `bzg`；「Mi'kmaq」（b75-s066，20240723_205
        # 晚間 136 秒 Brian Francis，加拿大）→ SIL Mi'kmaq `mic`，族名有
        # 撇號，照 Nisga'a 鍵照原文。
        self.assertEqual(namebars.code_of("巴布薩族"), "bzg")
        self.assertEqual(namebars.code_of("Babuza"), "bzg")
        self.assertEqual(namebars.code_of("Mi'kmaq"), "mic")

    def test_eastern_kuku_yalanji_is_one_group(self):
        # 第 76 批（2021-12）b76-s016 第 5 列 2677 秒「Desmond Tayley  Eastern
        # Kuku Yalanji」：澳洲原住民族群，族名本身有兩个空白，照空白切會變做
        # 三个對無ê字，規集 SKIP。SIL Kuku-Yalanji `gvn`。
        self.assertEqual(namebars.codes_of("Eastern Kuku Yalanji"), ["gvn"])
        self.assertEqual(namebars.codes_of("Kuku Yalanji"), ["gvn"])

    def test_2024_08_spellings(self):
        # 第 78 批（2024-08）名條：Ivatan（巴丹島，08-06 晚間、08-29 午間）、
        # 「凱達格蘭族」（08-23 晚間 3 人）、大武壠ê兩種轉寫 Taulun（08-17
        # 晨間小林村，王民亮仝人別條印「大武壠族」）佮 Ta`ulung（08-10 晨間，
        # 反引號）、巴西 Xakriabá（08-21 午間，名條小寫）、Tgdaya（德固達雅，
        # 賽德克語群）、拼毋著ê Paiwn、Pinuyunayan、Thao。
        self.assertEqual(namebars.codes_of("Ivatan"), ["ivv"])
        self.assertEqual(namebars.codes_of("Ivatan族"), ["ivv"])
        self.assertEqual(namebars.codes_of("凱達格蘭族"), ["kae"])
        self.assertEqual(namebars.codes_of("Taulun"), ["tvx"])
        self.assertEqual(namebars.codes_of("Ta`ulung"), ["tvx"])
        self.assertEqual(namebars.codes_of("xakriabá"), ["xkr"])
        self.assertEqual(namebars.codes_of("Tgdaya"), ["trv"])
        self.assertEqual(namebars.codes_of("Paiwn"), ["pwn"])
        self.assertEqual(namebars.codes_of("Thao"), ["ssf"])
        self.assertEqual(namebars.codes_of("Papura"),
                         namebars.codes_of("Paipura"))

    def test_2024_09_spellings(self):
        # 第 79 批（2024-09）：「Ruki」是 Rukai 漏一字（b79-s048 1992 秒柯浩軒，
        # 仝人 1241 秒印 Rukai）；「Kahau(噶哈巫族)」是噶哈巫另一款轉寫。
        self.assertEqual(namebars.codes_of("Ruki"),
                         namebars.codes_of("Rukai"))
        self.assertEqual(namebars.codes_of("Kahau"),
                         namebars.codes_of("Kaxabu"))

    def test_2024_10_11_spellings(self):
        # 第 80、81 批（2024-10、11）頭一擺套用規集 SKIP ê五款字樣：
        # 「Sakilaya(撒奇萊雅族)」（10-20 晚間 b80-s065 1159 秒）是 Sakizaya
        # 拼走；「Papula」（10-23 晚間 b80-s077 3 人）是拍瀑拉；凱達格蘭
        # 有「潘正育 Kaitakorangcu」（11-16 午間 b81-s067 2718 秒）佮
        # 「Kaitakʉran」（11-24 午間 b81-s102，ʉ）兩款自稱；加拿大「Metis」
        # （11-05 午間 b81-s018，無重音符）是 Métis，SIL 用 Michif `crg`。
        self.assertEqual(namebars.codes_of("Sakilaya"),
                         namebars.codes_of("Sakizaya"))
        self.assertEqual(namebars.codes_of("Papula"),
                         namebars.codes_of("拍瀑拉族"))
        self.assertEqual(namebars.codes_of("Kaitakorangcu"), ["kae"])
        self.assertEqual(namebars.codes_of("Kaitakʉran"), ["kae"])
        self.assertEqual(namebars.codes_of("Metis"), ["crg"])
        self.assertEqual(namebars.codes_of("Métis"), ["crg"])

    def test_2021_12_2022_01_foreign_groups(self):
        # 第 84、85 批頭一擺套用規集 SKIP ê外國族群：尼日 Wodaabe（12-06 晚間
        # b84-s009、12-24 午間 b84-s072，講 Fulfulde）、美國 Gullah Geechee
        # （12-17 晚間 b84-s047 三人，族名內底有空白，莫照空白切做兩族）、
        # 澳洲 Taungurung（12-25 午間 b84-s076，ISO 無代號，鍵照原文）、
        # 「Samoya」（01-05 晚間 b85-s009，薩摩亞）、美國 Yurok（01-13 晚間
        # b85-s024 三人）。
        self.assertEqual(namebars.codes_of("Wodaabe"), ["fuq"])
        self.assertEqual(namebars.codes_of("Gullah Geechee"), ["gul"])
        self.assertEqual(namebars.codes_of("Taungurung"), ["Taungurung"])
        self.assertEqual(namebars.codes_of("Samoya"), ["smo"])
        self.assertEqual(namebars.codes_of("Yurok"), ["yur"])

    def test_paiwani_extra_i(self):
        # 第 87 批 b87-s005 白惠蘭（2022-01-16 晨間，1208 秒）名條印做
        # 「Paiwani」，讀者放大確認是播出端加一个 i；無別名規集 SKIP。
        self.assertEqual(namebars.codes_of("Paiwani"), ["pwn"])

    def test_paypolacu_is_papora(self):
        # 第 88 批 b88-s006 白俊忠（2022-01-22 午間，2798 秒）名條族別印
        # 「paypolacu」，伊是台中拍瀑拉族ê推動者；規集 SKIP。
        self.assertEqual(namebars.codes_of("paypolacu"),
                         namebars.codes_of("Papura"))

    def test_kevalan_typo_is_kavalan(self):
        # 第 90 批 b90-s013 潘靜英(ipay)（2022-01-25 午間，1945 秒）名條印
        # 「Kevalan」，播出端打錯；規集 SKIP。
        self.assertEqual(namebars.codes_of("Kevalan"), ["ckv"])

    def test_bunum_typo_is_bunun(self):
        # 第 90 批 b90-s033 田春梅（2022-01-30 晚間，2001 秒）名條印
        # 「Bunum」；規集 SKIP。
        self.assertEqual(namebars.codes_of("Bunum"), ["bnn"])

    def test_dahman_is_taivoan(self):
        # 第 91 批潘資洲（2024-06-09 晚間、06-18 午間）名條印「大滿族」，
        # 大武壠ê另一種稱呼；兩集規集 SKIP。
        self.assertEqual(namebars.codes_of("大滿族"), ["tvx"])

    def test_2022_03_taurong_and_baka(self):
        # 第 94 批 b94-s036 王民亮（2022-03，2603 秒）名條印「Ta'urong」，
        # 大武壠ê另一種轉寫（仝人別條印「Taulun」「大武壠族」）；b94-s001
        # Elenga、Emile（342、420 秒）印「Baka族」，喀麥隆ê Baka 族，SIL
        # `bkc`。兩个攏對無代號，規集會 SKIP。
        self.assertEqual(namebars.codes_of("Ta'urong"), ["tvx"])
        self.assertEqual(namebars.codes_of("Baka族"), ["bkc"])

    def test_paiwa_missing_n_is_paiwan(self):
        # 第 93 批 b93-s015 giyu(郭復明)（2022-02，772 秒）名條印「Paiwa」，
        # 讀者確認字無予人裁著，是播出端漏一个 n。
        self.assertEqual(namebars.codes_of("Paiwa"), ["pwn"])

    def test_2022_03_typos_and_qeqchi(self):
        # 第 94 批：b94-s085 洪志彰、呂蓓蒂（364、444 秒）印「Pinuyumayyan」
        # 雙 y；b94-s062（2264 秒）印「SaySyat」漏 i；b94-s047 Rodrigo Tot
        # （549 秒）印「Q'eqchi'」，瓜地馬拉馬雅語族，SIL `kek`。攏對無代號，
        # 規集會 SKIP。
        self.assertEqual(namebars.codes_of("Pinuyumayyan"), ["pyu"])
        self.assertEqual(namebars.codes_of("SaySyat"), ["xsy"])
        self.assertEqual(namebars.codes_of("Q'eqchi'"), ["kek"])

    def test_2022_04_pajay_kvalan_and_foreign_groups(self):
        # 第 95 批：04-28 午間愛蘭教會彼則巴宰族受訪者 7 條印「Pajay」（巴宰ê
        # 音譯，仝一人 Xaolihih Pazeh 佇 96 批印「巴宰族」），b95-s085 一條閣
        # 拼做「Pajiay」；b95-s007 三條印「Kvalan」漏 a。外國族群：中非
        # Gaston Motambo、Angélique Manongo 印「Aka」（SIL 叫 Yaka (Central
        # African Republic)，`axk`）、Richard Sneed 印「Cherokee」（`chr`）、
        # 智利 Veronica Tuqui 印「Rapa Nui」（中央有空白，SIL Rapanui `rap`）。
        # 白俊忠 b95-s017 印「Paiouia」，仝一人 96 批 b96-s041 印「拍瀑拉族」。
        # 第 96 批閣有：Kawesqar（智利，SIL Qawasqar `alc`）、Munduruku、Baré
        # （巴西，`myu`、`bae`）、Nubia（埃及努比亞人，ISO 無族群總稱，比照薩米
        # 用上濟人講ê Nobiin `fia`）、Yoruba（`yor`）。攏對無代號，規集會 SKIP。
        self.assertEqual(namebars.codes_of("Paiouia"), ["ppu"])
        self.assertEqual(namebars.codes_of("Kawesqar"), ["alc"])
        self.assertEqual(namebars.codes_of("Munduruku"), ["myu"])
        self.assertEqual(namebars.codes_of("Baré"), ["bae"])
        self.assertEqual(namebars.codes_of("Nubia"), ["fia"])
        self.assertEqual(namebars.codes_of("Yoruba"), ["yor"])
        self.assertEqual(namebars.codes_of("Pajay"), ["pzh"])
        self.assertEqual(namebars.codes_of("Pajiay"), ["pzh"])
        self.assertEqual(namebars.codes_of("Kvalan"), ["ckv"])
        self.assertEqual(namebars.codes_of("Aka"), ["axk"])
        self.assertEqual(namebars.codes_of("Cherokee"), ["chr"])
        self.assertEqual(namebars.codes_of("Rapa Nui"), ["rap"])

    def test_batch_100_spellings(self):
        # 2022-06 名條第 100 批，四款對無代號、規集 SKIP：
        # 06-08 午間 b100-s006 陳小姐印「Rukia」（Rukai 字母倒反）；
        # 06-15 晚間 b100-s029 肯亞 Simon Kangele Wambua 等 2 人印
        # 「Kiswahili族」（SIL Swahili `swa`）；06-26 午間 b100-s065 平埔專題
        # 3 人印「Pacai」（巴宰，佮 Pacay、Pacaicu 仝族）；06-26 晚間
        # b100-s066 印「SaySiyal(賽夏族)」「SaySiyal」（t 印做 l）。
        self.assertEqual(namebars.codes_of("Rukia"), ["dru"])
        self.assertEqual(namebars.codes_of("Kiswahili族"), ["swa"])
        self.assertEqual(namebars.codes_of("Pacai"), ["pzh"])
        self.assertEqual(namebars.codes_of("SaySiyal"), ["xsy"])
        self.assertEqual(namebars.codes_of("SaySiyal(賽夏族)"), ["xsy"])

    def test_batch_101_cayuga(self):
        # 2022-07 名條第 101 批 b101-s020 第 11 列（07-07 午間 771 秒）：
        # 「Leroy Hill Cayu ga」，上排 Haudenosaunee。族名中央有空白會予
        # codes_of 拆做兩个族，讀者寫做 Cayuga；SIL Cayuga `cay`。
        self.assertEqual(namebars.codes_of("Cayuga"), ["cay"])

    def test_batch_102_saysiat(self):
        # 2022-07 名條第 102 批 b102-s001 第 3 列（266 秒）：畫面印
        # 「SaySiat」，SaySiyat 掉一个 y；毋加別名就規集 SKIP。
        self.assertEqual(namebars.codes_of("SaySiat"), ["xsy"])

    def test_batch_103_naabeeho(self):
        # 2022-07 名條第 103 批 b103-s019 第 10 列（2095 秒）：Jayne Sandoval
        # 下排印族語自稱「Naabeeh ó」（Navajo），2023-08 彼擺印「納瓦霍族」。
        # 自稱袂當 SKIP 規集，愛對著仝一个 `nav`。
        self.assertEqual(namebars.codes_of("Naabeehó"), ["nav"])

    def test_batch_104_roma(self):
        # 2022-07 名條第 104 批 b104-s010 第 4 列：匈牙利 Erika Varga 下排印
        # 「Roma」（羅姆人）；ISO 639-2 Romani `rom`。毋加就規集 SKIP。
        self.assertEqual(namebars.codes_of("Roma"), ["rom"])

    def test_batch_105_spellings(self):
        # 2022-08 名條第 105 批：b105-s060 等 4 列印「Yami/tao」（tao 小寫，
        # 斜線切開了後對無）；b105-s040 許鎧琳印「Paiwna」（Paiwan 拍毋著）；
        # b105-s084 Sacheen Littlefeather 印「Apaci」（Apache，ISO 639-2
        # 集體代號 `apa`）。三款攏會害規集 SKIP。
        self.assertEqual(namebars.codes_of("Yami/tao"), ["tao"])
        self.assertEqual(namebars.codes_of("Paiwna"), ["pwn"])
        self.assertEqual(namebars.codes_of("Apaci"), ["apa"])

    def test_batch_106_wailacki(self):
        # 2022-09 名條第 106 批 b106-s049 第 5 列：太空人 Nicole Aunapu Mann
        # 印「Wailacki」（加州 Round Valley 的 Wailaki 人，ISO 639-3 `wlk`）。
        # 毋加就規集 SKIP。
        self.assertEqual(namebars.codes_of("Wailacki"), ["wlk"])

    def test_batch_106_xukuru(self):
        # 2022-09 名條第 106 批 b106-s066 第 2 列：巴西 Marcos Luidson 印
        # 「Xukuru」（伯南布哥州 Xukuru 人，ISO 639-3 `xoo` Xukurú）。
        self.assertEqual(namebars.codes_of("Xukuru"), ["xoo"])

    def test_batch_107_spellings(self):
        # 2022-10 名條第 107 批：b107-s003 摩洛哥 Fatima Masoudi 印
        # 「Amazigh」（柏柏人，ISO 639-2 集體代號 `ber`）；b107-s037、s078
        # Tracie Revis、David Hill 印「Muscogee族」「Muscogee」（ISO 639-2
        # `mus` Creek）；b107-s057 Erika Varga 這擺印中文「羅姆人」（毋是
        # 「族」，尾字無剝）；b107-s005 印「Rukau」（Rukai 拍毋著）。四款
        # 攏會害規集 SKIP。
        self.assertEqual(namebars.codes_of("Amazigh"), ["ber"])
        self.assertEqual(namebars.codes_of("Muscogee"), ["mus"])
        self.assertEqual(namebars.codes_of("Muscogee族"), ["mus"])
        self.assertEqual(namebars.codes_of("羅姆人"), ["rom"])
        self.assertEqual(namebars.codes_of("Rukau"), ["dru"])

    def test_batch_108_spellings(self):
        # 2022-11 名條第 108 批：b108-s027、s028 Bauk é Dai'l、潘德興等 4 人
        # 印「Kehau」（噶哈巫自稱 Kaxabu ê另一款拼法）；b108-s032 加拿大
        # Rex Holwell 印「Inuit」，b108-s046 仝人印中文「因紐特族」（ISO
        # 639-3 `iku` Inuktitut）。三款攏會害規集 SKIP。
        self.assertEqual(namebars.codes_of("Kehau"), ["pzh-x-kaxabu"])
        self.assertEqual(namebars.codes_of("Inuit"), ["iku"])
        self.assertEqual(namebars.codes_of("因紐特族"), ["iku"])

    def test_batch_109_spellings(self):
        # 2022-12 名條第 109 批：b109-s037 潘仁和印「Kaha'u」（噶哈巫另一款
        # 拼法，仝人 s037 閣印「噶哈巫族」）；北美原住民 s020／s054 印
        # 「Ojibwe」（`oji`）、s025 印「Menominee族」（`mez`）、s085 印
        # 「Secwépemc」（`shs` Shuswap）、s082 Katrina Fuller 印「Sicangu
        # Lakota」（族名中央有空白，莫切做兩人；`lkt`）；澳洲 s089 Tarquin
        # Singleton 印「Yirrganydji」（Ethnologue 列 Yirrgay 做 Djabugay
        # 方言，`dyy`）。六款攏會害規集 SKIP。
        self.assertEqual(namebars.codes_of("Kaha'u"), ["pzh-x-kaxabu"])
        self.assertEqual(namebars.codes_of("Ojibwe"), ["oji"])
        self.assertEqual(namebars.codes_of("Menominee族"), ["mez"])
        self.assertEqual(namebars.codes_of("Secwépemc"), ["shs"])
        self.assertEqual(namebars.codes_of("Sicangu Lakota"), ["lkt"])
        self.assertEqual(namebars.codes_of("Yirrganydji"), ["dyy"])

    def test_slash_means_two_groups(self):
        # 第 78 批 b78-s032、s090 陳豪毅一人印「Pinuyumayan/Amis」（有一擺
        # 閣拼做 Pinuyunayan/Amis）：斜線兩爿是兩族，莫當做一个對無ê字
        # 規集 SKIP。「Tao/Yami」仝一族，切開猶原賰一个代號。
        self.assertEqual(namebars.codes_of("Pinuyumayan/Amis"), ["pyu", "ami"])
        self.assertEqual(namebars.codes_of("Pinuyunayan/Amis"), ["pyu", "ami"])
        self.assertEqual(namebars.codes_of("Tao/Yami"), ["tao"])

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
