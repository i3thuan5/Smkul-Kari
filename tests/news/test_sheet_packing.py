"""titv-news 的列高決定一張 contact sheet 裝幾條 cue。

`build_sheets` 以 1.10 megapixel 為預算裝箱。一條 cue 的 block 是
`gap + Σ(列高 + 2)`——titv-news 單列 122，block 134。

**sheet 寬是逐集不同的**，這裡算的是**最壞的那一集**。`_sheet_width` 取
的是 `108 + 該集最寬的 ink bbox + 16`，而圖條會先照 `ink_bbox` 裁掉左右
的空白，所以只有「有一條字幕滿版」的集數才會到上界 108+1920+16 = 2044
（`int(1.10e6/2044) = 538` 列）。字幕都不滿版的集數 bbox 較窄、預算較鬆。

實測 74 集：26 集正好是 2044（上界會碰到，不是純理論），另外 48 集是
1320。所以測試釘的是**上界**：預算取最小的那個，是最嚴的方向，過得了
這關的高度每一集都過得了。

**上界之下 4 × 134 = 536，餘裕只有 2 px。** 列高多 1 px，每張就從 4 條
掉到 3 條，sheet 數與視覺辨識成本一次多三成——而且圖條照樣正確，只是
變多，**沒有任何地方會報錯**。

這條容易被踩到：README「★ 字幕帶有兩个列位」那節記著一個還沒做的改法
（逐條 cue 自己挑上沿或偏下），動到的就是這個高度。

**這條護欄只擋「變高」，不是叫你「變矮」。** 兩個方向各有一種不會報錯
的代價，而且矮的那邊更難救：

- 太高 → 每張少裝一條，成本多三成（這條測試擋的）
- 太矮 → **裁到字**，讀者從此讀不到被削掉的部分

titv-news 這 122 px **剛好容兩逝**（README 量過：偏上 y 721–787、偏下
y 778–845），縮帶就是把偏上那逝剁掉幾成——README 已經明講「袂使用縮帶
來解決，縮著就剁著字」。所以這條紅了的時候，要退回去的是**你剛才調高
的那個改動**，不是把原本的 122 調小。

（《開會了》那條線同一天遇到鏡像的情形：族語列縮 4 px 就能全批 4 條、
省三分之一閱讀量，但族語正字法的 `^` 就在字身最上緣，縮下去正好削掉
它。他們選擇不縮。成本換不過拼寫正確。）

2026-08-31 由做《開會了》那條線量出來的（他們把華語列槽 60→66 為了 2 px
的字腳，sheet 數 160→213）。同一天 `rescan_band` 也真的踩下去了，見下面
那條測試。
"""
import json
import unittest

from scripts.news import paths
from scripts.news import rescan_band

# build_sheets 內部的數字（在那個函式裡是區域變數，抓不到，只能抄）。
MEGAPIXELS = 1.10
LABEL_GUTTER = 108   # 印 cue 編號與時間的左欄
TILE_PAD = 16        # _sheet_width 在圖條右邊留的
BLOCK_GAP = 10       # cue 與 cue 之間
PER_TILE = 2         # 每條圖條自己的分隔線
WANT_PER_SHEET = 4


def block_height(preset):
    """一條 cue 佔幾列：gap + Σ(列高 + 2)。"""
    block = BLOCK_GAP
    for line in preset["lines"]:
        block += line["h"] + PER_TILE
    return block


def sheet_budget(preset):
    """最壞情況下，一張 sheet 有幾列可用。

    用 `region[2]`（滿版）算，是 `_sheet_width` 的**上界**：實際取的是該
    集最寬的 ink bbox，會比這個窄或相等。寬取上界＝預算取下界＝判準最
    嚴，所以這裡過得了的高度，每一集都過得了。
    """
    sheet_w = LABEL_GUTTER + preset["region"][2] + TILE_PAD
    return int(MEGAPIXELS * 1000000 / sheet_w)


class TestSheetPacking(unittest.TestCase):
    def setUp(self):
        with open(paths.ENGINE_PRESETS, encoding="utf-8") as handle:
            self.presets = json.load(handle)

    def test_four_cues_still_fit_on_one_sheet(self):
        for name in self.presets:
            preset = self.presets[name]
            block = block_height(preset)
            budget = sheet_budget(preset)
            self.assertLessEqual(
                block * WANT_PER_SHEET, budget,
                "%s：一條 cue 的 block %d px，%d 條就 %d px，超過每張 %d px "
                "的預算——每張會掉到 %d 條，sheet 數與辨識成本多三成，"
                "而且不會報錯"
                % (name, block, WANT_PER_SHEET, block * WANT_PER_SHEET,
                   budget, budget // block))

    def test_the_worst_case_geometry_has_not_moved(self):
        # 上界的數字（滿版字幕：sheet 2044 寬、預算 538 列、block 134，
        # 每張剛好 4 條，餘裕 2 px）。實測 74 集有 26 集正好落在這裡。
        # 對不起來就是版型或裝箱改過了，這個檔案開頭的分析要重做一次。
        preset = self.presets["titv-news"]
        self.assertEqual(sheet_budget(preset), 538)
        self.assertEqual(block_height(preset), 134)

    def test_the_rescan_band_fits_four_to_a_sheet_too(self):
        """`rescan_band.REGION` 也要守，而且**預算不是它自己的寬度**。

        重切的分析區窄（1500），但它切出來的圖條跟整集其他 1920 寬的
        圖條**放在同一個 work dir**，而 `_sheet_width` 取的是全部圖條裡
        最寬的那個。所以預算照 1920 那條算（538 列），不是照 1500 算
        （677 列）——照自己的寬度算會鬆掉，剛好放過真正發生過的那次。

        踩過了：頭六集重切用 h=135，每張掉到 3 條，972 條 cue 開了 328
        張圖條，照 4 條算只要 243 張——多開 85 張、約 18 萬 token，
        而且圖條看起來完全正常，沒有一個地方會報錯。
        """
        height = int(rescan_band.REGION.split(",")[3])
        budget = sheet_budget(self.presets["titv-news"])
        block = BLOCK_GAP + height + PER_TILE
        self.assertLessEqual(
            block * WANT_PER_SHEET, budget,
            "rescan_band.REGION 的高 %d：一條 cue 的 block %d px，%d 條就 "
            "%d px，超過每張 %d px 的預算——每張會掉到 %d 條。上限是 "
            "h <= %d"
            % (height, block, WANT_PER_SHEET, block * WANT_PER_SHEET, budget,
               budget // block, budget // WANT_PER_SHEET - BLOCK_GAP
               - PER_TILE))


if __name__ == "__main__":
    unittest.main()
