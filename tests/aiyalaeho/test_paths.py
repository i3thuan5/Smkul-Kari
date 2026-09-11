"""aiyalaeho paths: store layout, the naming key, and the argument guards.

The store layout is asserted here rather than left to each program because
eleven call sites index into it; the news side learned that the symptom of
one of them building a path by hand is an episode that assembles with no
text, which nothing reports.
"""
import json
import os
import unittest

from scripts.aiyalaeho import paths
from scripts.errors import PipelineError
from scripts.ocr import sheets


NAME = "開會了_068_Amis_阿美"


class TestStoreLayout(unittest.TestCase):
    def test_corpus_sits_beside_news_at_the_top_of_the_store(self):
        self.assertEqual(paths.AIYA_STORE,
                         os.path.join(paths.KARI, "aiyalaeho"))

    def test_layout_is_corpus_technique_stage(self):
        ocr = os.path.join(paths.AIYA_STORE, "1-ocr")
        self.assertEqual(paths.OCR_STORE, ocr)
        self.assertEqual(paths.KARI_CUES, os.path.join(ocr, "1-cues"))
        self.assertEqual(paths.KARI_VISION, os.path.join(ocr, "2-vision"))
        self.assertEqual(paths.SRT_DIR, os.path.join(ocr, "3-srt"))

    def test_the_language_check_is_a_stage_of_the_picture_side(self):
        # 逐條語言判定只吃 3-srt/，所以編號接在它後面、住 1-ocr/ 底下，
        # 毋是另開一層——伊是仝一條線ê下游，毋是另外一種技術。
        ocr = os.path.join(paths.AIYA_STORE, "1-ocr")
        check = os.path.join(ocr, "4-語言檢查")
        self.assertEqual(paths.LANGCHECK_STORE, check)
        self.assertEqual(paths.LEXICON_DIR, os.path.join(check, "詞庫"))
        self.assertEqual(paths.LANGCHECK_MARKS,
                         os.path.join(check, "逐條語言標記.csv"))
        self.assertEqual(paths.LANGCHECK_DIST,
                         os.path.join(check, "逐集語言分布.csv"))

    def test_one_lexicon_per_tribe_under_the_lexicon_folder(self):
        self.assertEqual(paths.lexicon_path("阿美"),
                         os.path.join(paths.LEXICON_DIR, "阿美.txt"))

    def test_a_lexicon_name_may_not_carry_path_components(self):
        for bad in ("../阿美", "阿美/x", ""):
            with self.assertRaises(PipelineError):
                paths.lexicon_path(bad)

    def test_the_dictionaries_are_fetched_not_stored(self):
        # 辭典原檔 50 MB、二進位，留佇 SFTP；store 內底囥ê是蒸餾過ê詞庫。
        self.assertTrue(paths.LEXICON_REMOTE.startswith("/"))
        self.assertNotIn(paths.KARI, paths.LEXICON_REMOTE)

    def test_tables_live_at_the_corpus_level(self):
        self.assertEqual(paths.TRACKER_STORE,
                         os.path.join(paths.AIYA_STORE, "smkul.csv"))

    def test_there_is_no_speech_side(self):
        # 交付雙列 SRT 的族語文字來自畫面，無語音辨識這條線。
        for name in dir(paths):
            self.assertNotIn("ASR", name)

    def test_work_and_cache_live_in_the_workspace(self):
        # 工作區全部可重生，所以佇 kithann/（gitignore）底下。
        for value in (paths.WORK, paths.LOGS, paths.TRACKER_CACHE):
            self.assertTrue(value.startswith(paths.KITHANN + os.sep), value)

    def test_the_delivered_table_is_not_the_work_copy(self):
        self.assertNotEqual(paths.TRACKER_STORE, paths.TRACKER_CACHE)

    def test_the_preset_file_ships_beside_the_code(self):
        self.assertEqual(paths.ENGINE_PRESETS,
                         os.path.join(os.path.dirname(paths.__file__),
                                      "presets.json"))
        with open(paths.ENGINE_PRESETS, encoding="utf-8") as handle:
            presets = json.load(handle)
        self.assertIn("aiyalaeho-bilingual", presets)


class TestPresetPacking(unittest.TestCase):
    """The preset's row heights decide how many cues fit on a sheet.

    `build_sheets` grows a page until one more strip would push it past
    what the reader can take in at full size: at most 4784 visual tokens
    of 28x28 patches, and at most 2000px on the long edge because the tool
    that delivers the image resizes anything longer (measured 2026-09-09:
    an 818x2484 sheet arrived annotated "displayed at 659x2000"). With the
    sheet width measured on 068 (1970px) that is 1876 rows, and a cue's
    block is `gap + sum(row height + 2)`.

    Four blocks a sheet used to be the whole margin -- the 1.10 megapixel
    budget this test was written against gave 558 rows against 552 of
    block, and the difference between 160 sheets an episode and 213. The
    budget is three times looser now, so the number to guard is no longer
    "four": it is that a height change cannot quietly take a sheet past
    the point where the reader receives a shrunken page. Nothing else
    guards this: the sheets still come out correct, only smaller, so the
    reading gets worse silently.
    """

    # build_sheets' own numbers (they are locals in that function).
    GUTTER = 10          # vertical gap between cue blocks
    PER_TILE = 2         # each strip is drawn with a 2px separator
    WANT_PER_SHEET = 4

    # Sheet width is `108 + widest ink-cropped tile + 16`, and since
    # 2026-09-09 it belongs to the *sheet*, not to the episode: only the
    # strips on one page decide how wide that page is. 068's widest line
    # is 1846px, so its widest possible page is 1970; a line running the
    # full frame would make one page 2044 and no other. The worst case is
    # what this guards, because it is the tightest height budget any page
    # can be given.
    SHEET_WIDTH = 1970
    WIDEST_POSSIBLE = 1920 + 108 + 16

    def _blocks(self):
        """(preset name, block height) for every preset in the file.

        Every preset, not just the first one: a second layout added for
        the episodes whose band sits lower has the same budget to meet,
        and nothing else would notice it missing it.
        """
        with open(paths.ENGINE_PRESETS, encoding="utf-8") as handle:
            presets = json.load(handle)
        out = []
        for name in sorted(presets):
            block = self.GUTTER
            for line in presets[name]["lines"]:
                block += line["h"] + self.PER_TILE
            out.append((name, block))
        return out

    def test_four_cues_fit_on_a_sheet(self):
        budget = sheets._height_bound(self.SHEET_WIDTH)
        for name, block in self._blocks():
            self.assertLessEqual(
                block * self.WANT_PER_SHEET, budget,
                "%s：一个 cue ê block %d px，%d 條就 %d px，超過每張 %d px"
                "ê預算——sheet 數會加三成，而且袂報錯"
                % (name, block, self.WANT_PER_SHEET,
                   block * self.WANT_PER_SHEET, budget))

    def test_even_a_full_width_line_keeps_three_cues_a_sheet(self):
        """The worst case, recorded so the next height change sees it."""
        worst = sheets._height_bound(self.WIDEST_POSSIBLE)
        for name, block in self._blocks():
            self.assertGreaterEqual(worst // block, 3, name)

    def test_no_page_of_these_rows_arrives_shrunken(self):
        """The failure that replaced the old one, and is quieter than it.

        Past 4784 patches or 2000px of long edge the page is scaled down
        before the reader ever sees it -- the glyphs with it -- and a
        Formosan line loses the `^` and the apostrophes first. The two
        readers given 2484px pages on 2026-09-09 both ended up cropping
        and enlarging every one of them to tell `I` from `l`.
        """
        for name, block in self._blocks():
            for width in (self.SHEET_WIDTH, self.WIDEST_POSSIBLE):
                height = sheets._height_bound(width)
                self.assertGreaterEqual(height // block, 1, name)
                patches = (-(-width // sheets.PATCH)
                           * -(-height // sheets.PATCH))
                self.assertLessEqual(patches, sheets.VISUAL_TOKENS, name)
                self.assertLessEqual(height, sheets.LONG_EDGE, name)


class TestLowBandPreset(unittest.TestCase):
    """The band does not sit at the same height in every episode.

    Measured over 750 frames each: 087 puts its rows at 918..943 and
    966..1003, 094 at 923..951 and 974..1011 -- both about 14px below
    `aiyalaeho-bilingual`'s slots (888..948 / 948..1012), so the split at
    948 lands inside 094's Formosan row. `verify_band` refused both, which
    is the gate working: the cue timings would have come from ink changes
    in the wrong rows.

    The valley between the two rows measures y=962 on 087, so that is
    where this preset splits.
    """

    # (episode, formosan row, han row) as measured off the masters.
    MEASURED = (
        ("087", (918, 943), (966, 1003)),
        ("094", (923, 951), (974, 1011)),
    )
    NAME = "aiyalaeho-bilingual-low"

    def setUp(self):
        with open(paths.ENGINE_PRESETS, encoding="utf-8") as handle:
            self.presets = json.load(handle)

    def test_the_low_band_preset_exists(self):
        self.assertIn(self.NAME, self.presets)

    def test_each_measured_row_sits_inside_its_slot(self):
        preset = self.presets[self.NAME]
        top = preset["region"][1]
        slots = {}
        for line in preset["lines"]:
            slots[line["name"]] = (top + line["y"],
                                   top + line["y"] + line["h"])
        for episode, formosan, han in self.MEASURED:
            for name, row in (("formosan", formosan), ("han", han)):
                lo, hi = slots[name]
                self.assertLessEqual(
                    lo, row[0],
                    "%s ê %s 逝對 y=%d 起，佇槽 %d..%d 頂懸"
                    % (episode, name, row[0], lo, hi))
                self.assertGreaterEqual(
                    hi, row[1],
                    "%s ê %s 逝到 y=%d，超出槽 %d..%d"
                    % (episode, name, row[1], lo, hi))

    def test_it_stays_inside_the_region(self):
        preset = self.presets[self.NAME]
        top, height = preset["region"][1], preset["region"][3]
        for line in preset["lines"]:
            self.assertLessEqual(line["y"] + line["h"], height,
                                 "%s 超出 region（%d..%d）"
                                 % (line["name"], top, top + height))

    def test_it_has_no_match_so_it_must_be_chosen_explicitly(self):
        # 檔名無通用ê字頭，選毋著 preset 就是切毋著——愛用 --preset。
        self.assertNotIn("match", self.presets[self.NAME])


class TestSrtName(unittest.TestCase):
    def test_the_key_names_the_programme_episode_and_language(self):
        self.assertEqual(paths.check_srt_name(NAME), NAME)

    def test_three_digit_episode_number(self):
        # 集數愛零補三碼，SRT 才會照集數排。
        for bad in ("開會了_68_Amis_阿美", "開會了_0068_Amis_阿美"):
            self.assertRaises(PipelineError, paths.check_srt_name, bad)

    def test_a_news_key_is_not_one_of_ours(self):
        self.assertRaises(PipelineError, paths.check_srt_name,
                          "20210201_032_午間_Atayal_泰雅")

    def test_the_two_corpora_keys_cannot_collide(self):
        # 一爿是 8 碼數字開頭、一爿是「開會了_」開頭，永遠分得開。
        self.assertTrue(NAME.startswith(paths.KEY_PREFIX))
        self.assertFalse("20210201_032_午間_Atayal_泰雅"
                         .startswith(paths.KEY_PREFIX))

    def test_a_name_may_not_carry_path_components(self):
        for bad in ("開會了_068_Amis_阿美/x", "../開會了_068_Amis_阿美", ""):
            self.assertRaises(PipelineError, paths.check_srt_name, bad)


class TestStagePath(unittest.TestCase):
    def test_one_episode_sits_directly_under_the_stage_folder(self):
        # 四十外集爾爾，無需要閣分一層（news 分月是為著千外集）。
        for base in (paths.KARI_CUES, paths.KARI_VISION, paths.SRT_DIR):
            self.assertEqual(paths.stage_path(base, NAME),
                             os.path.join(base, NAME))

    def test_the_suffix_is_appended_to_the_name(self):
        self.assertEqual(paths.stage_path(paths.SRT_DIR, NAME, ".srt"),
                         os.path.join(paths.SRT_DIR, NAME + ".srt"))

    def test_stage_path_checks_the_name(self):
        self.assertRaises(PipelineError, paths.stage_path,
                          paths.KARI_CUES, "../etc/passwd")

    def test_the_work_dir_is_the_srt_name(self):
        # slug＝srt_name：新語料無 news 彼段「work dir 改名會孤兒化」ê歷史。
        self.assertEqual(paths.work_dir(NAME),
                         os.path.join(paths.WORK, NAME + ".work"))


class TestAbnormalTablePaths(unittest.TestCase):
    def test_the_second_table_sits_beside_the_first(self):
        self.assertEqual(
            paths.ABNORMAL_STORE,
            os.path.join(paths.AIYA_STORE, "smkul-字幕版型異常.csv"))

    def test_it_has_a_work_copy_like_the_first(self):
        self.assertEqual(
            paths.ABNORMAL_CACHE,
            os.path.join(paths.WORK, "smkul-字幕版型異常.csv"))

    def test_the_two_tables_are_different_files(self):
        self.assertNotEqual(paths.ABNORMAL_STORE, paths.TRACKER_STORE)
        self.assertNotEqual(paths.ABNORMAL_CACHE, paths.TRACKER_CACHE)


class TestBandJson(unittest.TestCase):
    """`verify_band` 量著ê帶範圍——工作區ê快取，無入 store。

    入 store ê是 `cues.json` ê `mask.band_rows`（切 cue ê時陣寫入去ê）。
    這隻檔干焦是予批次佇兩步中間傳話用ê。
    """

    def test_it_lives_in_the_episodes_work_dir(self):
        self.assertEqual(paths.band_json(NAME),
                         os.path.join(paths.work_dir(NAME), "band.json"))

    def test_it_is_not_in_the_store(self):
        self.assertNotIn(paths.KARI, paths.band_json(NAME))

    def test_the_name_is_checked(self):
        self.assertRaises(PipelineError, paths.band_json, "../x")


class TestTextLayout(unittest.TestCase):
    """上字文稿是獨立ê一層，佮 1-ocr/ 平行、無共款ê編號規則。

    這層無 srt_name 這个鍵（001–045 ê集號佮上字文稿無影片，袂使照
    check_srt_name ê格式驗），所以毋免、嘛袂使共 stage_path()。
    """

    def test_it_sits_beside_1_ocr_not_inside_it(self):
        self.assertEqual(paths.TEXT_STORE,
                         os.path.join(paths.AIYA_STORE, "text"))
        self.assertNotIn(paths.OCR_STORE, paths.TEXT_STORE)
        self.assertNotIn(paths.TEXT_STORE, paths.OCR_STORE)

    def test_the_pair_csv_is_under_the_text_store(self):
        self.assertEqual(paths.TEXT_PAIRS,
                         os.path.join(paths.TEXT_STORE, "1-句對.csv"))

    def test_work_copy_is_under_kithann_not_the_store(self):
        self.assertTrue(paths.TEXT_WORK.startswith(paths.KITHANN + os.sep),
                        paths.TEXT_WORK)
        self.assertNotIn(paths.KARI, paths.TEXT_WORK)

    def test_work_copy_lands_inside_the_allowed_roots(self):
        # check_under() 是規个 repo 仝一个防線，這條干焦確認 TEXT_WORK
        # 無漏共這條防線出去。
        from scripts.datadirs import check_under
        self.assertEqual(check_under(paths.TEXT_WORK, "text 工作區"),
                         paths.TEXT_WORK)

    def test_remote_is_the_upstream_folder_not_a_local_path(self):
        self.assertTrue(paths.TEXT_REMOTE.startswith("/"))
        self.assertIn("開會了", paths.TEXT_REMOTE)
        self.assertIn("上字文稿", paths.TEXT_REMOTE)


if __name__ == "__main__":
    unittest.main()
