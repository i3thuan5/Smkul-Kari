"""aiyalaeho paths: store layout, the naming key, and the argument guards.

The store layout is asserted here rather than left to each program because
eleven call sites index into it; the news side learned that the symptom of
one of them building a path by hand is an episode that assembles with no
text, which nothing reports.
"""
import json
import os
import tempfile
import unittest

from scripts.aiyalaeho import paths
from scripts.errors import PipelineError


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

    def test_tables_live_at_the_corpus_level(self):
        self.assertEqual(paths.INVENTORY,
                         os.path.join(paths.AIYA_STORE, "inventory.json"))
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

    `build_sheets` packs to 1.10 megapixels: with the sheet width measured
    on 068 (1970px) that is 558 rows, and a cue's block is
    `gap + sum(row height + 2)`. Four blocks fitting or not is the whole
    difference between 160 sheets an episode and 213 -- a third more
    reading, for pixels nobody sees. Nothing else guards this: the sheets
    still come out correct, only more of them, so the cost rises silently.
    """

    # build_sheets' own numbers (they are locals in that function).
    MEGAPIXELS = 1.10
    GUTTER = 10          # vertical gap between cue blocks
    PER_TILE = 2         # each strip is drawn with a 2px separator
    WANT_PER_SHEET = 4

    # Sheet width is `108 + widest ink-cropped tile + 16`, so it belongs to
    # the episode, not to the preset: 068 measures 1970 (its widest line is
    # 1846px). An episode whose line ran the full frame would measure 2044
    # and get a tighter budget -- 538 rows against 068's 558 -- which at
    # these row heights is three cues a sheet rather than four. That is a
    # cost difference, not a correctness one, so the worst case is recorded
    # below rather than asserted; each episode's sheets.json says what it
    # actually got.
    SHEET_WIDTH = 1970
    WIDEST_POSSIBLE = 1920 + 108 + 16

    def test_four_cues_fit_on_a_sheet(self):
        with open(paths.ENGINE_PRESETS, encoding="utf-8") as handle:
            preset = json.load(handle)["aiyalaeho-bilingual"]
        block = self.GUTTER
        for line in preset["lines"]:
            block += line["h"] + self.PER_TILE
        budget = int(self.MEGAPIXELS * 1000000 / self.SHEET_WIDTH)
        self.assertLessEqual(
            block * self.WANT_PER_SHEET, budget,
            "一个 cue ê block %d px，%d 條就 %d px，超過每張 %d px ê預算"
            "——sheet 數會加三成，而且袂報錯"
            % (block, self.WANT_PER_SHEET, block * self.WANT_PER_SHEET,
               budget))

    def test_even_a_full_width_line_keeps_three_cues_a_sheet(self):
        """The worst case, recorded so the next height change sees it."""
        with open(paths.ENGINE_PRESETS, encoding="utf-8") as handle:
            preset = json.load(handle)["aiyalaeho-bilingual"]
        block = self.GUTTER
        for line in preset["lines"]:
            block += line["h"] + self.PER_TILE
        worst = int(self.MEGAPIXELS * 1000000 / self.WIDEST_POSSIBLE)
        self.assertGreaterEqual(worst // block, 3)


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


class TestInventory(unittest.TestCase):
    def _entry(self, **over):
        entry = {
            "file": "068-阿美語-秀姑巒-雙語字幕.mp4",
            "video": "ilrdf-corpus/族語節目/開會了/"
                     "068-阿美語-秀姑巒-雙語字幕.mp4",
            "srt_name": NAME,
            "節目名稱": "開會了",
            "集數": "68",
            "族語別(英)": "Amis",
            "族語別(中)": "阿美",
            "語言別": "秀姑巒",
            "語言代號": "ami-x-skl",
            "pending": True,
        }
        entry.update(over)
        return entry

    def _write(self, entries):
        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False, encoding="utf-8")
        json.dump(entries, handle, ensure_ascii=False)
        handle.close()
        return handle.name

    def test_a_full_entry_loads(self):
        got = paths.load_inventory(self._write([self._entry()]))
        self.assertEqual(got[0]["srt_name"], NAME)
        self.assertEqual(got[0]["語言代號"], "ami-x-skl")

    def test_a_missing_field_says_which(self):
        entry = self._entry()
        del entry["語言代號"]
        with self.assertRaises(PipelineError) as caught:
            paths.load_inventory(self._write([entry]))
        self.assertIn("語言代號", str(caught.exception))

    def test_an_undeclared_field_is_refused(self):
        # 條目是照宣告一欄一欄重建ê，無宣告ê會佇寫轉去 store 時無去。
        entry = self._entry(播出日期="2021-01-01")
        self.assertRaises(PipelineError, paths.load_inventory,
                          self._write([entry]))

    def test_optional_fields_may_be_absent(self):
        entry = self._entry()
        del entry["pending"]
        del entry["file"]
        got = paths.load_inventory(self._write([entry]))
        self.assertNotIn("pending", got[0])

    def test_the_name_is_checked_on_the_way_in(self):
        entry = self._entry(srt_name="../x")
        self.assertRaises(PipelineError, paths.load_inventory,
                          self._write([entry]))


if __name__ == "__main__":
    unittest.main()
