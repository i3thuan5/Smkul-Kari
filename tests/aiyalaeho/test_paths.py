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
        budget = int(self.MEGAPIXELS * 1000000 / self.SHEET_WIDTH)
        for name, block in self._blocks():
            self.assertLessEqual(
                block * self.WANT_PER_SHEET, budget,
                "%s：一个 cue ê block %d px，%d 條就 %d px，超過每張 %d px"
                "ê預算——sheet 數會加三成，而且袂報錯"
                % (name, block, self.WANT_PER_SHEET,
                   block * self.WANT_PER_SHEET, budget))

    def test_even_a_full_width_line_keeps_three_cues_a_sheet(self):
        """The worst case, recorded so the next height change sees it."""
        worst = int(self.MEGAPIXELS * 1000000 / self.WIDEST_POSSIBLE)
        for name, block in self._blocks():
            self.assertGreaterEqual(worst // block, 3, name)


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


class TestAbnormalFields(TestInventory):
    """字幕版型異常集ê兩个新欄位：理由、影片長度秒。

    理由非空就是異常集——伊行袂過這个節目雙列雙語ê流程，毋管理由是
    檔名標ê（`無字幕`／`僅華語字幕`）、量測判ê（`版型不符：…`）抑是
    人看 sheet 判ê（`人工判定：…`）。

    長度ê欄名寫做「影片長度秒」，佮 smkul.csv 彼欄「影片長度」分開：
    表彼欄是「時:分:秒」，inventory 這欄是浮點ê秒數。仝名無仝款式，
    人拍開檔案會看無——`Kari-SRT/` ê物件愛人讀有。
    """

    def test_the_two_new_fields_are_last(self):
        # 條目是照這張表一欄一欄重建ê，順序換去等於規份 diff，所以
        # 新欄位干焦會使加佇尾溜。
        self.assertEqual(paths.INVENTORY_FIELDS[-2:],
                         ("理由", "影片長度秒"))

    def test_both_are_optional(self):
        # 雙語集無這兩欄；舊條目嘛無。
        for field in ("理由", "影片長度秒"):
            self.assertIn(field, paths.INVENTORY_OPTIONAL)

    def test_an_entry_carrying_them_loads(self):
        got = paths.load_inventory(self._write([
            self._entry(理由="無字幕", 影片長度秒=2969.967)]))
        self.assertEqual(got[0]["理由"], "無字幕")
        self.assertEqual(got[0]["影片長度秒"], 2969.967)

    def test_an_entry_without_them_still_loads(self):
        got = paths.load_inventory(self._write([self._entry()]))
        self.assertNotIn("理由", got[0])
        self.assertNotIn("影片長度秒", got[0])

    def test_the_reason_survives_the_round_trip(self):
        # `catalogue` 佮 `publish` kā條目原樣寫轉去 store——理由若佇
        # 重建ê時無去，異常表隔轉工就空一半。
        reason = "版型不符：字幕逝 y=1005..1014 無囥佇任何一个宣告ê槽內"
        got = paths.load_inventory(self._write([self._entry(理由=reason)]))
        self.assertEqual(got[0]["理由"], reason)


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


if __name__ == "__main__":
    unittest.main()
