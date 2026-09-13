"""The sheet→TSV→import loop: transcript parsing and glossary tokens."""
import json
import os
import tempfile
import unittest

import numpy as np
from PIL import Image

from scripts.news import gap_sheets
from scripts.ocr import cuelib
from scripts.ocr import sheets
from scripts.ocr import stripname
from scripts.ocr import transcripts


class TestParseTranscriptTsv(unittest.TestCase):
    def test_two_column_uses_default_line(self):
        got, errors = transcripts.parse_transcript_tsv("3\thello", "han")
        self.assertEqual(errors, [])
        self.assertEqual(got, {"3": {"han": "hello"}})

    def test_three_column_names_the_line(self):
        got, errors = transcripts.parse_transcript_tsv(
            "7\tami\tAti han ako\n7\than\t我就請", "han")
        self.assertEqual(errors, [])
        self.assertEqual(got["7"]["ami"], "Ati han ako")
        self.assertEqual(got["7"]["han"], "我就請")

    def test_comments_and_blanks_ignored(self):
        got, errors = transcripts.parse_transcript_tsv(
            "# a note\n\n  \n1\ttext", "han")
        self.assertEqual(errors, [])
        self.assertEqual(list(got), ["1"])

    def test_bad_index_is_reported_not_swallowed(self):
        got, errors = transcripts.parse_transcript_tsv("x\ttext", "han")
        self.assertEqual(got, {})
        self.assertEqual(len(errors), 1)

    def test_missing_text_column_is_reported(self):
        _, errors = transcripts.parse_transcript_tsv("5", "han")
        self.assertEqual(len(errors), 1)

    def test_text_may_contain_tabs_after_line_name(self):
        got, _ = transcripts.parse_transcript_tsv("1\than\ta\tb", "han")
        self.assertEqual(got["1"]["han"], "a\tb")


class TestGlossaryTokens(unittest.TestCase):
    """Words later batches are most likely to spell differently."""

    def test_marks_are_collected(self):
        got = transcripts.glossary_tokens("nga'ay ho^ i Po:long")
        self.assertIn("nga'ay", got)
        self.assertIn("ho^", got)
        self.assertIn("Po:long", got)

    def test_proper_nouns_are_collected(self):
        got = transcripts.glossary_tokens("ci Kinci ato Angcoh")
        self.assertIn("Kinci", got)
        self.assertIn("Angcoh", got)

    def test_plain_lowercase_words_are_ignored(self):
        got = transcripts.glossary_tokens("kako ato mita a demak")
        self.assertEqual(got, [])

    def test_trailing_punctuation_stripped(self):
        self.assertIn("Aray", transcripts.glossary_tokens("Aray."))

    def test_single_characters_ignored(self):
        self.assertEqual(transcripts.glossary_tokens("i o a"), [])

    def test_double_quote_word_is_collected(self):
        got = transcripts.glossary_tokens("to 'a\"iyalaeho: a kamok")
        self.assertIn("'a\"iyalaeho:", got)


if __name__ == "__main__":
    unittest.main()


class TestSlotCrop(unittest.TestCase):
    """Which half of the band this cue's line is in, if it can be told.

    News puts each line in one of two fixed slots inside the band, so half
    of every strip is blank -- measured over 27 episodes, 79.8% of lines sit
    in the lower slot and 10.8% in the upper. Dropping the empty half is
    what fits more cues on one Claude Vision input sheet.

    The fallback is the whole point of the ratio. It is NOT there for "both
    slots hold subtitle" -- scanning 3,339 strips found no such case, and
    the layout does not produce one. It is there for the picture's own text
    competing with the subtitle: 051's cue 223 has a red banner reading
    屏東縣瑪家鄉舊筏灣 in the upper slot and the actual line in the lower,
    at a ratio of 1.10. Crop to the wrong slot there and the subtitle is
    gone, and Claude Vision is told to leave banners blank, so it comes back
    as an empty row that looks like an ordinary silent shot.
    """

    SLOTS = {"split": 65, "pad": 6, "min_ratio": 2.0, "min_ink": 200}

    def _mask(self, upper_ink, lower_ink, height=122, width=400):
        mask = np.zeros((height, width), dtype=bool)
        if upper_ink:
            mask[10:10 + max(upper_ink // width, 1), :upper_ink] = True
        if lower_ink:
            mask[80:80 + max(lower_ink // width, 1), :lower_ink] = True
        return mask

    def _ink(self, upper, lower, height=122, width=400):
        mask = np.zeros((height, width), dtype=bool)
        rows_up = max(upper // width, 0)
        rows_low = max(lower // width, 0)
        if rows_up:
            mask[10:10 + rows_up, :] = True
        if rows_low:
            mask[80:80 + rows_low, :] = True
        return mask

    def test_line_in_the_upper_slot_crops_to_it(self):
        got = sheets.slot_crop(self._ink(4000, 0), self.SLOTS)
        self.assertEqual(got, (0, 71))

    def test_line_in_the_lower_slot_crops_to_it(self):
        got = sheets.slot_crop(self._ink(0, 8000), self.SLOTS)
        self.assertEqual(got, (59, 122))

    def test_comparable_ink_in_both_slots_falls_back(self):
        self.assertIsNone(sheets.slot_crop(self._ink(6400, 8000),
                                           self.SLOTS))

    def test_too_little_ink_to_tell_falls_back(self):
        self.assertIsNone(sheets.slot_crop(self._ink(80, 40), self.SLOTS))

    def test_no_slots_declared_means_no_crop(self):
        self.assertIsNone(sheets.slot_crop(self._ink(4000, 0), None))
        self.assertIsNone(sheets.slot_crop(self._ink(4000, 0), {}))

    def test_a_split_outside_the_strip_is_ignored(self):
        slots = dict(self.SLOTS, split=400)
        self.assertIsNone(sheets.slot_crop(self._ink(4000, 0), slots))


class TestUndecidedShare(unittest.TestCase):
    """How often this episode could not tell -- reported, never acted on.

    Measured normal range, blank strips excluded: median 2.9%, p90 9.1%,
    highest 12.5%. A number well above that says the band has drifted up or
    down across the split, which is the one layout change nothing else
    notices: it passes the band check (the dialogue plateau is still inside
    the region) and it passes the column check (the right edge has not
    moved). Blank strips are excluded because how much of an episode is
    silent has nothing to do with its layout -- counting them turned a 3.5
    point spread into 5.7.
    """

    def test_share_ignores_the_blank_strips(self):
        self.assertAlmostEqual(sheets.undecided_share(3, 97, 40), 0.03)

    def test_an_episode_with_nothing_to_decide_is_zero(self):
        self.assertEqual(sheets.undecided_share(0, 0, 12), 0.0)


class TestCueBlocksCropping(unittest.TestCase):
    """The crop over real strips: rows by slot, columns by run.

    Neither crop may take a subtitle pixel with it. The column rule is no
    longer "any ink at all" -- it picks the run of strong ink the line
    sits in and then grows outwards over any ink at all, so that far-away
    background goes and faint strokes at the line's own edge stay; see
    `TestInkColumns` for the two halves of that. What matters here is the
    part that has not changed: whatever the strip holds, the tile that
    comes out still contains every lit pixel of the line. Both are checked
    against the mask rather than by eye, because the failure looks like an
    ordinary short line to everyone downstream.
    """

    SLOTS = {"split": 65, "pad": 6, "min_ratio": 2.0, "min_ink": 200}

    def _workdir(self, upper_rows, lower_rows):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        os.makedirs(os.path.join(tmp.name, "strips"))
        frame = np.full((122, 400, 3), 20, dtype=np.uint8)
        for lo, hi in (upper_rows, lower_rows):
            if hi > lo:
                frame[lo:hi, 120:360] = 255
        Image.fromarray(frame).save(
            os.path.join(tmp.name, "strips", "a.png"))
        manifest = {
            "lines": [{"name": "han", "y": 0, "h": 122}],
            "mask": {},
            "cues": [{"index": 1, "start": 3.0, "end": 5.0,
                      "images": {"han": os.path.join("strips", "a.png")}}],
        }
        return tmp.name, manifest

    def _tile(self, upper, lower, **kwargs):
        workdir, manifest = self._workdir(upper, lower)
        spec = cuelib.MaskSpec.from_dict({})
        blocks, undecided, decided, blank = sheets._cue_blocks(
            workdir, manifest, spec, **kwargs)
        return blocks[0][2][0], (undecided, decided, blank)

    def test_a_lower_line_loses_the_empty_upper_half(self):
        tile, counts = self._tile((0, 0), (80, 96), row_slots=self.SLOTS)
        self.assertEqual(tile.height, 122 - 59)
        self.assertEqual(counts, (0, 1, 0))

    def test_every_lit_pixel_survives_the_crop(self):
        tile, _ = self._tile((0, 0), (80, 96), row_slots=self.SLOTS)
        spec = cuelib.MaskSpec.from_dict({})
        kept = int(cuelib.text_mask(np.asarray(tile), spec).sum())
        whole, _ = self._tile((0, 0), (80, 96))
        full = int(cuelib.text_mask(np.asarray(whole), spec).sum())
        self.assertEqual(kept, full)

    def test_without_slots_the_tile_keeps_the_whole_band(self):
        tile, counts = self._tile((0, 0), (80, 96))
        self.assertEqual(tile.height, 122)
        self.assertEqual(counts, (0, 0, 0))

    def test_ink_in_both_slots_keeps_the_whole_band(self):
        tile, counts = self._tile((20, 40), (80, 100), row_slots=self.SLOTS)
        self.assertEqual(tile.height, 122)
        self.assertEqual(counts, (1, 0, 0))

    def test_columns_are_trimmed_without_losing_the_line(self):
        tile, _ = self._tile((0, 0), (80, 96), row_slots=self.SLOTS)
        self.assertLess(tile.width, 400)
        self.assertGreaterEqual(tile.width, 240)


class TestAnchorComesFromThePreset(unittest.TestCase):
    """`right_anchor` 是 preset 宣告ê，`_cue_blocks` 愛kā伊紮落去。

    寫佇 `_ink_columns` 猶未算好——若無人kā傳過去，實際做組合圖ê時
    照舊咧掉字，測試soah是青ê。這組掠ê就是彼段線路。
    """

    def _mask(self, data):
        return cuelib.MaskSpec.from_dict(data)

    def test_from_dict_reads_it(self):
        self.assertEqual(self._mask({"right_anchor": 1650}).right_anchor,
                         1650)

    def test_a_preset_that_says_nothing_has_none(self):
        self.assertIsNone(self._mask({}).right_anchor)

    def test_half_resolution_halves_it(self):
        """`scale` 2 ê時座標攏減半，anchor 綴leh減。

        無減ê話，半解析ê遮罩內底 1650 已經超過規條 strip ê闊度，逐
        段攏搆袂著，這條規則就恬恬失效。
        """
        got = self._mask({"right_anchor": 1650}).scaled(2)
        self.assertEqual(got.right_anchor, 825)

    def test_news_presets_declare_it_and_aiyalaeho_does_not(self):
        """置右是族語新聞ê性質，毋是逐个節目ê。"""
        with open("scripts/news/presets.json", encoding="utf-8") as handle:
            news = json.load(handle)
        for name, preset in news.items():
            self.assertIn("right_anchor", preset["mask"], name)
        with open("scripts/aiyalaeho/presets.json", encoding="utf-8") as fh:
            other = json.load(fh)
        for name, preset in other.items():
            self.assertNotIn("right_anchor", preset["mask"], name)

    def test_the_manifest_on_disk_does_not_carry_it(self):
        """組合圖ê版面事實對 preset 來，毋是對 `cues.json` 來。

        已經切好ê work dir 內底，`cues.json` ê `mask` 是切 cue 彼時
        寫ê，內底無 `compare_cols` 嘛無 `right_anchor`——`gap_sheets`
        本底就是家己去讀 preset kā in 傳落去ê。若干焦靠 manifest，
        重做組合圖ê時這條規則會恬恬無作用，圖照舊掉字。
        """
        slots, cols, anchor = gap_sheets.news_sheet_layout()
        self.assertEqual(anchor, 1650)
        self.assertEqual(cols, [1250, 1790])
        self.assertIsNotNone(slots)

    def test_cue_blocks_takes_it_as_an_argument(self):
        """規條線路：preset → `build_sheets` → `_cue_blocks` → 裁切。"""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        os.makedirs(os.path.join(tmp.name, "strips"))
        frame = np.full((122, 1920, 3), 20, dtype=np.uint8)
        frame[40:60, 598:1400] = 255          # 中央ê乾草，墨上濟
        frame[40:60, 1620:1760] = 255         # 置右ê字幕
        Image.fromarray(frame).save(os.path.join(tmp.name, "strips", "a.png"))
        manifest = {
            "lines": [{"name": "han", "y": 0, "h": 122}],
            "mask": {},
            "cues": [{"index": 1, "start": 3.0, "end": 5.0,
                      "images": {"han": os.path.join("strips", "a.png")}}],
        }
        plain = sheets._cue_blocks(
            tmp.name, manifest, self._mask({}))[0][0][2][0]
        anchored = sheets._cue_blocks(
            tmp.name, manifest, self._mask({}),
            right_anchor=1650)[0][0][2][0]
        self.assertLess(plain.width, 1000)
        self.assertGreater(anchored.width, plain.width)
        self.assertGreater(anchored.width, 1100)


class TestInkColumns(unittest.TestCase):
    """Which columns of a strip the tile keeps.

    The crop has to do two things that pull against each other. It must
    drop what is not the subtitle -- on news the mask catches bright
    background across the whole 1920, and on 開會了 the strip of the lower
    line catches the bottom edge of the line above it; measured on 111's
    cue 228, "any ink" gives 279..1725 for a seven-character line that
    actually occupies 799..1295. And it must keep every stroke of the
    subtitle, including the ones the mask barely registers: an apostrophe
    is three or four columns of one or two lit pixels, and a rule that
    wanted three lit pixels per column shaved 40 of 085's formosan lines --
    every one of them ending in `'`.

    So strong ink decides *which* run is the subtitle, and any ink decides
    *where that run ends*. Far-away ink is dropped; ink that touches the
    run is kept however faint.
    """

    WIDTH = 1920

    def _strip(self, blocks):
        """blocks: (x0, x1, lit-pixels-per-column) -> a boolean mask."""
        mask = np.zeros((122, self.WIDTH), dtype=bool)
        for x0, x1, lit in blocks:
            mask[40:40 + lit, x0:x1] = True
        return mask

    def test_background_far_from_the_line_is_dropped(self):
        """051-style: bright picture at the left, the line at the right."""
        mask = self._strip([(100, 300, 20), (1200, 1700, 20)])
        self.assertEqual(sheets._ink_columns(mask), (1194, 1706))

    def test_the_bleed_from_the_line_above_is_dropped(self):
        """開會了 111 cue 228: 799..1295 is the line, 1710 is bleed."""
        mask = self._strip([(799, 1295, 18), (1710, 1725, 18)])
        self.assertEqual(sheets._ink_columns(mask), (793, 1301))

    def test_a_faint_mark_touching_the_line_is_kept(self):
        """085's `kwara'`: the apostrophe lights one pixel per column."""
        mask = self._strip([(700, 1200, 20), (1206, 1210, 1)])
        self.assertEqual(sheets._ink_columns(mask), (694, 1216))

    def test_one_run_comes_back_untouched(self):
        """開會了's opaque band: nothing but the line is ever lit."""
        mask = self._strip([(700, 1200, 20)])
        self.assertEqual(sheets._ink_columns(mask), (694, 1206))

    def test_a_space_inside_the_line_does_not_split_it(self):
        """`台鐵 高鐵…` and romanised lines carry gaps of their own."""
        mask = self._strip([(700, 900, 20), (1000, 1200, 20)])
        self.assertEqual(sheets._ink_columns(mask), (694, 1206))

    def test_too_little_ink_to_choose_keeps_every_lit_column(self):
        """A near-blank strip has no run to pick; do not guess one."""
        mask = self._strip([(500, 503, 20), (1400, 1403, 20)])
        self.assertEqual(sheets._ink_columns(mask), (494, 1409))

    def test_no_ink_at_all_is_still_none(self):
        mask = np.zeros((122, self.WIDTH), dtype=bool)
        self.assertIsNone(sheets._ink_columns(mask))

    def test_the_widest_page_lands_on_a_patch_boundary(self):
        """The last patch column is paid for whole or not at all.

        A page is charged `ceil(w/28)` columns, so 1990px costs the same
        72 columns as 2016 would: 26px of it is bought and thrown away.
        Trimming two more pixels off the widest strip drops the page to
        1988, which is 71 columns exactly. It is small -- 0.2% on a news
        episode, nothing on 開會了, because hardly any strip is that wide
        -- but it costs nothing at all: what those two pixels held is
        background, on the side of the strip the subtitle never reaches.
        """
        page = sheets.GUTTER + sheets.MAX_TILE + sheets.TILE_MARGIN
        self.assertEqual(page % sheets.PATCH, 0)
        self.assertLessEqual(page, sheets.LONG_EDGE - sheets.SPARE)

    def test_a_strip_can_never_be_wider_than_a_page_allows(self):
        """The far left goes before anything else is decided.

        A page is `108 + widest strip + 16`, and a page over 2000px on its
        long edge is resized before the reader sees it. A strip lit right
        across the frame -- a full-screen graphic card, a newspaper page --
        made exactly that page: 108 + 1920 + 16 = 2044. Measured on three
        episodes, 1.2% of strips are like that, and every one of them has
        its ink starting at column 0, which is background: the subtitle is
        anchored at the right (x≈1736 on news) and the longest line
        measured, 23 characters at 62px, still starts at x≈310.
        """
        mask = self._strip([(0, self.WIDTH, 20)])
        box = sheets._ink_columns(mask)
        self.assertLessEqual(box[1] - box[0], sheets.MAX_TILE)
        self.assertEqual(box[1], self.WIDTH)
        self.assertLessEqual(box[1] - box[0] + 108 + 16, sheets.LONG_EDGE)

    def test_ink_in_the_dropped_left_edge_cannot_win_the_run(self):
        """Cut first, then choose -- not the other way round.

        Trimming afterwards would let a bright left edge win the run and
        take the crop with it, and the line would be gone with no error
        anywhere.
        """
        mask = self._strip([(0, 100, 80), (1400, 1700, 20)])
        self.assertEqual(sheets._ink_columns(mask), (1394, 1706))

    def test_a_right_anchored_line_beaten_by_the_background_is_kept(self):
        """006晚 cue 627「是的」：墨上濟彼段是一片乾草，字幕佇上倚右。

        新聞ê字幕是**置右**ê（27 集量ê墨水右緣中位數 1735–1737）。主
        播桌ê白檯面、全螢幕圖卡、乾草這款物件khiā佇畫面中央，墨比字幕
        濟，就kā裁切窗贏去，字幕規條落佇窗外——讀者看著ê是空白，**無
        一个所在會報錯**。六集 5,798 條內底按呢ê有 168 條（2.9%）。

        補救ê法是「墨上濟彼段ê左界，到上倚右彼段ê右界」，兩爿攏包入
        去：窗**擴大**，毋是換掉，所以本底看會著ê物件一件都袂失去。
        """
        mask = self._strip([(598, 1400, 20), (1620, 1760, 20)])
        self.assertEqual(sheets._ink_columns(mask), (592, 1406))
        self.assertEqual(sheets._ink_columns(mask, anchor=1650), (592, 1766))

    def test_the_widened_window_always_holds_the_old_one(self):
        """擴大，毋是換掉——這是這條改法唯一ê安全保證。

        別種改法（一律取上倚右、抑是出事才換）是kā窗**換**去，換了若
        毋著就比本底較歹。這條ê窗必定包含無 anchor 時ê窗，所以結構上
        袂使變較歹。六集 5,798 條實測：0 條變較細。
        """
        for blocks in ([(598, 1400, 20), (1620, 1760, 20)],
                       [(100, 300, 20), (1200, 1700, 20)],
                       [(0, 100, 80), (1400, 1700, 20)]):
            mask = self._strip(blocks)
            plain = sheets._ink_columns(mask)
            wide = sheets._ink_columns(mask, anchor=1650)
            self.assertLessEqual(wide[0], plain[0], blocks)
            self.assertGreaterEqual(wide[1], plain[1], blocks)

    def test_without_an_anchor_the_bleed_is_still_dropped(self):
        """開會了無宣告 anchor，行為愛一模一樣。

        開會了ê字幕是置中ê（111 cue 228 是 799..1295），1710 彼塊是
        頂一列滲落來ê墨，本底就愛掞掉。置右是**族語新聞ê性質**，毋是
        逐个節目ê，所以這條規則綴 preset 走：無宣告就照舊。
        """
        mask = self._strip([(799, 1295, 18), (1710, 1725, 18)])
        self.assertEqual(sheets._ink_columns(mask), (793, 1301))
        self.assertEqual(sheets._ink_columns(mask, anchor=None), (793, 1301))

    def test_an_anchor_no_run_reaches_changes_nothing(self):
        """字幕真正khiā佇中央（無到 anchor）ê時，莫硬去牽。"""
        mask = self._strip([(700, 1200, 20)])
        self.assertEqual(sheets._ink_columns(mask, anchor=1650),
                         sheets._ink_columns(mask))

    def test_the_anchor_never_reaches_past_the_dropped_left_edge(self):
        """Anchor 是絕對座標，比較ê時愛记得左爿已經先剪過矣。

        `MAX_TILE` 彼刀是佇揀段進前落ê（`dropped` 56 px），所以段ê
        座標是相對ê，anchor 是絕對ê。無換算就會揀著毋著段。
        """
        mask = self._strip([(0, 100, 80), (1700, 1760, 20)])
        box = sheets._ink_columns(mask, anchor=1650)
        self.assertEqual(box[1], 1766)
        self.assertLessEqual(box[1] - box[0], sheets.MAX_TILE)

    def test_a_strip_that_already_fits_is_not_touched(self):
        mask = self._strip([(700, 1200, 20)])
        self.assertEqual(sheets._ink_columns(mask), (694, 1206))


class SheetFixture(unittest.TestCase):
    """A work dir of synthetic strips, each cropping to a width you name."""

    def _workdir(self, widths, strip_h=122, flush_right=False):
        """`flush_right` lights the frame all the way to its right edge.

        That is the only way to make a strip as wide as a page can carry:
        the crop keeps the rightmost `MAX_TILE` columns, so a block of ink
        that stops short of the edge comes out narrower however wide it
        is. Real strips do reach the edge -- a full-screen graphic card
        lights all 1920 -- so this is not a contrivance.
        """
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        os.makedirs(os.path.join(tmp.name, "strips"))
        cues = []
        number = 0
        for width in widths:
            number += 1
            frame = np.full((strip_h, max(1920, width + 200), 3), 20,
                            dtype=np.uint8)
            if flush_right:
                frame[10:strip_h - 10, 100:] = 255
            else:
                frame[10:strip_h - 10, 100:100 + width - 12] = 255
            rel = os.path.join("strips", "%d.png" % number)
            Image.fromarray(frame).save(os.path.join(tmp.name, rel))
            cues.append({"index": number, "start": 10.0 * number,
                         "end": 10.0 * number + 4.0,
                         "images": {"han": rel}})
        manifest = {"lines": [{"name": "han", "y": 0, "h": strip_h}],
                    "mask": {}, "cues": cues}
        return tmp.name, manifest

    def _sheets(self, widths, strip_h=122, flush_right=False, **kwargs):
        """{sheet name: (width, height, [cue numbers on it])}."""
        workdir, manifest = self._workdir(widths, strip_h, flush_right)
        sheets.build_sheets(workdir, manifest, **kwargs)
        with open(os.path.join(workdir, "sheets.json"),
                  encoding="utf-8") as handle:
            index_map = json.load(handle)
        made = {}
        for name, covered in index_map.items():
            with Image.open(os.path.join(workdir, "sheets", name)) as page:
                made[name] = (page.width, page.height, covered)
        return made


class TestSheetWidth(SheetFixture):
    """How wide each Claude Vision input sheet comes out.

    Width used to be one number for a whole episode -- the widest strip
    anywhere in it. On 058晨 that made all 327 sheets 2044 px wide while
    the median strip was 1230, because 5% of the strips catch bright
    background (dry grass, a newspaper page) across the full 1920. Sheets
    are charged by area, so every one of them paid for that handful of
    strips' whitespace.
    """

    def test_one_full_width_strip_no_longer_widens_the_episode(self):
        widths = []
        for _ in range(20):
            widths.append(400)
        widths[9] = 1500
        narrow = []
        for _name, (width, _h, covered) in self._sheets(widths).items():
            if 10 in covered:
                self.assertEqual(width, 1500 + 108 + 16)
            else:
                narrow.append(width)
        self.assertTrue(narrow)
        for width in narrow:
            self.assertEqual(width, 400 + 108 + 16)

    def test_each_sheet_is_as_wide_as_its_own_widest_strip(self):
        widths = []
        for step in range(24):
            widths.append(300 + 60 * step)
        seen = set()
        for _name, (width, _h, covered) in self._sheets(widths).items():
            widest = 0
            for index in covered:
                widest = max(widest, widths[index - 1])
            self.assertEqual(width, widest + 108 + 16)
            seen.add(width)
        self.assertGreater(len(seen), 1)


class TestSheetHeight(SheetFixture):
    """How tall a sheet is allowed to grow.

    The old budget was a flat 1.10 megapixels, left over from the standard
    resolution tier (long edge 1568, 1568 visual tokens). Claude reads an
    image in 28x28 patches at `ceil(w/28) * ceil(h/28)` tokens, and Opus 5
    reads at the high tier -- 4784 tokens -- so the old budget left two
    thirds of a page unused. Past that limit the API scales the whole page
    down and the glyphs go with it, and nothing anywhere reports that it
    happened: the read just gets worse.

    The long edge is 2000, not the model's own 2576: the tool that hands
    a sheet to the reader resizes anything longer. Measured 2026-09-09 --
    an 818x2484 sheet came back annotated "displayed at 659x2000" -- and
    the readers of those sheets went on to crop and enlarge every page to
    tell `I` from `l`, which cost several times what the packing saved.
    """

    def _bound(self, page_w):
        """The tallest this page may be without the API scaling it down."""
        patches = -(-page_w // 28)
        return min(2000, (4784 // patches) * 28)

    def _rows(self, page_w, strip_h=122):
        return self._bound(page_w) // (10 + strip_h + 2)

    def _widest_sheet(self, made):
        most = 0
        for _name, (_w, _h, covered) in made.items():
            most = max(most, len(covered))
        return most

    def test_no_sheet_is_large_enough_to_be_scaled_down(self):
        """Including the strip that is lit right across the frame.

        Without one of those in the mix this test passes on any packing
        rule at all -- the widest page it can otherwise build is 1984, four
        pixels under the limit it means to be guarding.
        """
        widths = []
        for step in range(40):
            widths.append(300 + 40 * step)
        made = self._sheets(widths)
        made.update(self._sheets([2100, 2100], flush_right=True))
        for _name, (width, height, _covered) in made.items():
            patches = -(-width // 28) * -(-height // 28)
            self.assertLessEqual(patches, 4784)
            self.assertLessEqual(max(width, height), 2000)

    def test_a_narrow_sheet_is_filled_to_the_long_edge(self):
        widths = []
        for _ in range(40):
            widths.append(400)
        made = self._sheets(widths)
        self.assertEqual(self._widest_sheet(made), self._rows(400 + 124))

    def test_a_wide_sheet_holds_fewer_rows(self):
        """The widest page there can be, against a narrow one.

        2100 is past what a page may carry, so the strip comes back
        trimmed to `MAX_TILE` and its page is 1988: 71 patch columns
        across, so only 67 down (1876px), where a narrow page is stopped
        by the long edge at 2000.

        The rows have to be taller than a subtitle for that gap to show:
        124px of difference is less than one 134px block, so at the news
        layout both pages hold 14 either way. It is real for anything
        taller -- 200px rows are 10 against 9 -- and it is the reason the
        packing sorts by width in the first place.
        """
        wide = []
        narrow = []
        for _ in range(40):
            wide.append(2100)
            narrow.append(400)
        tall = 188
        widest = self._widest_sheet(
            self._sheets(wide, strip_h=tall, flush_right=True))
        self.assertLess(widest, self._widest_sheet(
            self._sheets(narrow, strip_h=tall)))
        self.assertEqual(widest, self._rows(sheets.MAX_PAGE, tall))

    def test_a_blank_strip_cannot_widen_a_page_either(self):
        """The strip with no ink at all takes the same trim.

        There is nothing to crop it to, so it used to come through at its
        full frame width -- and on news that is 1920, which is exactly the
        page the trim exists to prevent. 25 of 058晨's 1,284 strips are
        blank, so this is not a corner case; it kept one 2044px page in
        the episode after the trim had removed every other one.
        """
        workdir, manifest = self._workdir([400, 400])
        blank = np.full((122, 1920, 3), 20, dtype=np.uint8)
        Image.fromarray(blank).save(
            os.path.join(workdir, "strips", "1.png"))
        sheets.build_sheets(workdir, manifest)
        with open(os.path.join(workdir, "sheets.json"),
                  encoding="utf-8") as handle:
            index_map = json.load(handle)
        for name in index_map:
            with Image.open(os.path.join(workdir, "sheets", name)) as page:
                self.assertLessEqual(page.width, sheets.LONG_EDGE)

    def test_a_strip_taller_than_the_bound_still_gets_a_sheet(self):
        """No cue may be dropped for being too big to pack.

        One row of 2012 px does not fit under any bound, and the packer
        asks "does this still fit" before adding. Ask it of an empty sheet
        and the answer is always no, which is a sheet that never fills and
        a cue that never arrives.
        """
        made = self._sheets([400, 400, 400], strip_h=2000)
        self.assertEqual(len(made), 3)
        seen = []
        for _name, (_w, _h, covered) in made.items():
            seen.extend(covered)
        self.assertEqual(sorted(seen), [1, 2, 3])


class TestWidthSorting(SheetFixture):
    """Packing the strips widest-with-widest instead of in cue order.

    A sheet is as wide as its widest strip, so one wide strip in a tall
    sheet is paid for by every other strip on it. Sorting by width first
    empties that penalty out: measured on 058晨 it took the episode from
    59.2% of the current visual tokens to 40.4%, and a sheet of 14 cues
    then costs the same per cue as a sheet of 4 (142.0 against 142.7),
    so "fewer sheets" and "fewer tokens" stopped being a trade.

    What it costs is that a sheet no longer covers one stretch of
    programme. Nothing downstream may lean on that: `sheets.json` is the
    one sheet-to-cue map, `verified.json` is keyed by cue number, and the
    gutter carries each cue's own number and clock.
    """

    def _mixed(self):
        widths = []
        for step in range(60):
            widths.append(250 + 30 * ((step * 17) % 41))
        return widths

    def test_no_cue_is_lost_or_duplicated_by_the_sort(self):
        widths = self._mixed()
        seen = []
        for _name, (_w, _h, covered) in self._sheets(widths).items():
            seen.extend(covered)
        wanted = []
        for number in range(1, len(widths) + 1):
            wanted.append(number)
        self.assertEqual(sorted(seen), wanted)

    def test_each_sheet_holds_strips_of_one_width_range(self):
        widths = self._mixed()
        order = []
        for number in range(1, len(widths) + 1):
            order.append(number)
        order.sort(key=lambda number: (widths[number - 1], number))
        place = {}
        for spot, number in enumerate(order):
            place[number] = spot
        for _name, (_w, _h, covered) in self._sheets(widths).items():
            spots = []
            for number in covered:
                spots.append(place[number])
            self.assertEqual(sorted(spots),
                             list(range(min(spots), max(spots) + 1)))

    def test_the_strip_under_a_label_is_that_cue_s_own_strip(self):
        """The failure sorting could cause, and the reason it does not.

        Nothing reorders a cue's number away from its strip: they travel
        as one block. If they ever came apart, every line on the sheet
        would be transcribed against the wrong cue and the TSV would
        still import cleanly.
        """
        widths = self._mixed()
        workdir, manifest = self._workdir(widths)
        sheets.build_sheets(workdir, manifest)
        with open(os.path.join(workdir, "sheets.json"),
                  encoding="utf-8") as handle:
            index_map = json.load(handle)
        for name, covered in index_map.items():
            with Image.open(os.path.join(workdir, "sheets", name)) as page:
                pixels = np.asarray(page.convert("L"))
            row = 10
            for number in covered:
                # Right of the gutter only: the label printed in it is
                # dark too, and it is not part of the strip.
                band = pixels[row:row + 122, 108:]
                dark = np.nonzero((band < 100).any(axis=0))[0]
                self.assertEqual(int(dark.max()) - int(dark.min()) + 1,
                                 widths[number - 1])
                row += 122 + 2 + 10

    def test_a_sheet_is_named_after_its_earliest_cue(self):
        """`batch[0]` is now whatever sorted first, not the earliest cue.

        The name is a timestamp so that renumbering cues cannot make it
        point at a different piece of programme. Sorted packing keeps that
        property only if the timestamp is the sheet's own earliest one.
        """
        widths = self._mixed()
        made = self._sheets(widths)
        self.assertEqual(len(set(made.keys())), len(made))
        for name, (_w, _h, covered) in made.items():
            self.assertEqual(name, stripname.sheet_of(10.0 * min(covered)))
