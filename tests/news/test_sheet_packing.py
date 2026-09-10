"""一張 Claude Vision 輸入組合圖裝幾條 cue，以及它會不會被縮圖。

`build_sheets` 現在的高度上限不是寫死的百萬畫素，是**送到讀者手上不會
被縮小**的那個邊界：Claude 用 28×28 的 patch 看圖，一張圖花
`⌈寬/28⌉ × ⌈高/28⌉` 個視覺 token，Opus 5 屬高解析層，上限 4784；長邊
的 2000 px 則是**送圖那支工具**的上限，不是模型的（模型自己是 2576）
——2026-09-09 實測：818×2484 的組合圖送過去，回來自己註明「displayed
at 659×2000」。超過任一個就等比例縮小整張，字跟著小。

**寬度是逐張各自算的**（`108 + 該張最寬的圖條 + 16`），這裡算的是**最壞
的那一張**。整條字幕滿版會做出 108+1920+16 = 2044，超過送圖那端的 2000，
所以圖條最寬剪到 `MAX_TILE`（2000 − 108 − 16 − 10 = 1866，剪的是左邊的
背景），最壞的一張就是 1990。寬取上界＝高度預算取下界＝判準最嚴，過得了
這關的列高每一集都過得了。

這條護欄擋的是**變高**，不是叫你**變矮**。兩個方向各有一種不會報錯的代
價，而且矮的那邊更難救：

- 太高 → 每張少裝幾條，張數與閱讀成本跟著多（這條測試擋的）
- 太矮 → **裁到字**，讀者從此讀不到被削掉的部分

titv-news 這 122 px **剛好容兩逝**（README 量過：偏上 y 721–787、偏下
y 778–845），縮帶就是把偏上那逝剁掉幾成——README 已經明講「袂使用縮帶
來解決，縮著就剁著字」。所以這條紅了的時候，要退回去的是**你剛才調高
的那個改動**，不是把原本的 122 調小。

（《開會了》那條線同一天遇到鏡像的情形：族語列縮 4 px 就能全批多裝一
條、省三分之一閱讀量，但族語正字法的 `^` 就在字身最上緣，縮下去正好削
掉它。他們選擇不縮。成本換不過拼寫正確。）

2026-08-31 由做《開會了》那條線量出來的（他們把華語列槽 60→66 為了 2 px
的字腳，sheet 數 160→213）。同一天 `rescan_band` 也真的踩下去了，見下面
那條測試。2026-09-09 高度規則換成解析層邊界之後改寫：舊的「上界 2044 寬
之下 4 條 × 134 = 536、餘裕 2 px」那個懸崖沒有了（同樣的版型現在一張裝
13 條），但**被縮圖**這個新的、一樣不會報錯的失敗換了進來。
"""
import json
import math
import unittest

from scripts.news import paths
from scripts.news import rescan_band
from scripts.ocr import sheets

LABEL_GUTTER = 108   # 印 cue 編號與時間的左欄
TILE_PAD = 16        # _sheet_width 在圖條右邊留的
BLOCK_GAP = 10       # cue 與 cue 之間
PER_TILE = 2         # 每條圖條自己的分隔線
WANT_PER_SHEET = 4   # 低消：一張裝不到這麼多條，就是版型出事了
DELIVERY_LIMIT_PX = 2000  # 送圖彼端ê長邊上限，超過就縮細


def block_height(preset):
    """一條 cue 佔幾列：gap + Σ(列高 + 2)。"""
    block = BLOCK_GAP
    for line in preset["lines"]:
        block += line["h"] + PER_TILE
    return block


def widest_sheet(preset):
    """最壞情況的張寬。

    整條字幕滿版、欄裁切一個畫素都裁不掉的時候，圖條就是 `MAX_TILE`
    ——2026-09-10 加ê規矩：圖條上闊到遮，超過ê對倒手爿剪掉，按呢一張
    上闊就是 1990，穩在送圖彼端ê 2000 以內。**毋是** region ê 1920
    （彼款會做出 2044，超過線）。
    """
    return LABEL_GUTTER + min(preset["region"][2], sheets.MAX_TILE) + TILE_PAD


class TestSheetPacking(unittest.TestCase):
    def setUp(self):
        with open(paths.ENGINE_PRESETS, encoding="utf-8") as handle:
            self.presets = json.load(handle)

    def test_a_sheet_of_four_cues_is_never_scaled_down(self):
        for name in self.presets:
            preset = self.presets[name]
            block = block_height(preset)
            width = widest_sheet(preset)
            budget = sheets._height_bound(width)
            self.assertLessEqual(
                block * WANT_PER_SHEET, budget,
                "%s：一條 cue 的 block %d px，%d 條就 %d px，超過 %d px 寬"
                "的組合圖能有的高度 %d px——再高就被辨識端等比例縮小，"
                "字跟著小，而且沒有任何地方會報錯"
                % (name, block, WANT_PER_SHEET, block * WANT_PER_SHEET,
                   width, budget))

    def test_the_page_the_packer_makes_stays_inside_both_limits(self):
        # 闊度是圖條決定ê，裝箱改袂了（滿版彼款就是 2044，超過送圖彼
        # 端ê 2000，見下面彼條）。裝箱管會著ê是**懸度**：兩个上限攏
        # 袂使去挵著。
        for name in self.presets:
            preset = self.presets[name]
            width = widest_sheet(preset)
            height = sheets._height_bound(width)
            patches = (math.ceil(width / sheets.PATCH)
                       * math.ceil(height / sheets.PATCH))
            self.assertLessEqual(patches, sheets.VISUAL_TOKENS, name)
            self.assertLessEqual(height, sheets.LONG_EDGE, name)

    def test_the_worst_case_geometry_has_not_moved(self):
        # 上界的數字：上闊ê圖條 1866（`MAX_TILE`），一張 1990 寬，高度
        # 上限 1848 px（⌈1990/28⌉=72 个 patch 闊，4784÷72=66 个 patch
        # 懸），block 134，一張 13 條。對不起來就是版型、裝箱規則、抑是
        # **送圖／辨識彼端ê上限**改過矣，這个檔案頭前彼段分析愛重做一
        # 遍——彼幾个數字是別人兜ê服務條件，毋是咱保證會著ê。
        preset = self.presets["titv-news"]
        self.assertEqual(widest_sheet(preset), 1990)
        self.assertEqual(sheets._height_bound(1990), 1848)
        self.assertEqual(block_height(preset), 134)
        self.assertEqual(sheets._height_bound(1990) // 134, 13)

    def test_no_sheet_can_be_over_the_delivery_limit(self):
        """連上闊彼張都愛佇送圖彼端ê 2000 px 以內。

        送圖ê工具會kā長邊超過 2000 ê圖等比例縮細（2026-09-09 量ê：
        818x2484 ê組合圖送過去，家己註「displayed at 659x2000」），
        字綴咧糊，**無一个所在會報錯**。畫面本身是 1920 闊，加 gutter
        佮留白是 2044，拄仔好超過——所以圖條上闊剪到 `MAX_TILE`
        （2000 − 108 − 16 − 10），剪ê是倒手爿ê背景。

        剪10 px ê餘裕（`SPARE`）是刁工留ê：拄拄好 2000 傷ân，隨位
        振動幾个畫素就恬恬過線。
        """
        for name in self.presets:
            self.assertLessEqual(widest_sheet(self.presets[name]),
                                 DELIVERY_LIMIT_PX, name)
        self.assertEqual(sheets.GUTTER + sheets.MAX_TILE
                         + sheets.TILE_MARGIN,
                         sheets.LONG_EDGE - sheets.SPARE)

    def test_the_rescan_band_still_packs_like_the_rest(self):
        """`rescan_band.REGION` 也要守，而且**預算不是它自己的寬度**。

        重切的分析區窄（1500），但它切出來的圖條跟整集其他 1920 寬的圖條
        **放在同一個 work dir**。逐張各自算寬之後，窄的那幾條會被排到一
        起、量到自己的寬度，可是只要有一張混到滿版的圖條，那一張就照
        2044 算。所以這裡照最壞的那一張算，不是照 1500 算。

        踩過了：頭六集重切用 h=135，每張掉到 3 條，972 條 cue 開了 328
        張圖條，照 4 條算只要 243 張——多開 85 張、約 18 萬 token，而且
        圖條看起來完全正常，沒有一個地方會報錯。
        """
        height = int(rescan_band.REGION.split(",")[3])
        budget = sheets._height_bound(widest_sheet(self.presets["titv-news"]))
        block = BLOCK_GAP + height + PER_TILE
        self.assertLessEqual(
            block * WANT_PER_SHEET, budget,
            "rescan_band.REGION 的高 %d：一條 cue 的 block %d px，%d 條就 "
            "%d px，超過每張 %d px 的高度上限——上限是 h <= %d"
            % (height, block, WANT_PER_SHEET, block * WANT_PER_SHEET, budget,
               budget // WANT_PER_SHEET - BLOCK_GAP - PER_TILE))


if __name__ == "__main__":
    unittest.main()
