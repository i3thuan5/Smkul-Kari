"""split_cue：一條 cue 內底有兩句ê時，佇量出來ê彼點kā伊剖開。

重讀掠著 6 句「畫面頂懸有、既有資料無記」ê字幕，攏是仝一款：
cue 邊界硩佇兩句中央，切段器切袂開（氣象圖傷光、抑是兩句換ê時
背景無振動），所以一條 cue 內底實在有兩句，讀者干焦寫會落一句。

剖開就會kā後壁ê cue 攏重新編號，所以佮 `rescan_band` 仝款危險。
兩項無仝：

- 這遍**無重切**，時間點是量出來ê（0.03 秒內），毋是閣走一遍切段器。
- **`images` 愛留原本ê**。Strip ê檔名是舊編號，若綴新編號改寫，
  規排 strip 就會對毋著 cue——彼是 `safe_resplit` 留落來ê坑
  （`strips/00844_han.png` 對著ê是 cue 951）。留原本ê，對照就
  永遠著。
"""
import unittest

from scripts.errors import PipelineError
from scripts.news import split_cue


def cue(index, start, end, strip=None):
    return {"index": index, "start": start, "end": end,
            "images": {"han": "strips/%05d_han.png" % (strip or index)}}


def run(count):
    out = []
    for i in range(count):
        out.append(cue(i + 1, float(i), float(i + 1)))
    return out


class TestSplit(unittest.TestCase):
    def test_the_list_grows_by_one(self):
        got = split_cue.split(run(5), 3, 2.4)
        self.assertEqual(len(got), 6)

    def test_everything_is_renumbered_from_one(self):
        got = split_cue.split(run(5), 3, 2.4)
        self.assertEqual([c["index"] for c in got], [1, 2, 3, 4, 5, 6])

    def test_the_two_halves_meet_at_the_split(self):
        got = split_cue.split(run(5), 3, 2.4)
        self.assertEqual((got[2]["start"], got[2]["end"]), (2.0, 2.4))
        self.assertEqual((got[3]["start"], got[3]["end"]), (2.4, 3.0))

    def test_the_other_cues_keep_their_times(self):
        got = split_cue.split(run(5), 3, 2.4)
        self.assertEqual((got[0]["start"], got[0]["end"]), (0.0, 1.0))
        self.assertEqual((got[-1]["start"], got[-1]["end"]), (4.0, 5.0))

    def test_untouched_cues_keep_their_original_strip(self):
        """這條是重點：strip ê檔名袂使綴新編號走。"""
        got = split_cue.split(run(5), 3, 2.4)
        self.assertEqual(got[4]["images"]["han"], "strips/00004_han.png")
        self.assertEqual(got[5]["images"]["han"], "strips/00005_han.png")

    def test_the_first_half_keeps_the_original_strip(self):
        got = split_cue.split(run(5), 3, 2.4)
        self.assertEqual(got[2]["images"]["han"], "strips/00003_han.png")

    def test_the_second_half_has_no_strip_yet(self):
        """後半是新ê，圖愛另外切；先留空較好過指去毋著彼張。"""
        got = split_cue.split(run(5), 3, 2.4)
        self.assertEqual(got[3]["images"], {})

    def test_a_split_at_the_start_is_an_error(self):
        with self.assertRaises(PipelineError):
            split_cue.split(run(5), 3, 2.0)

    def test_a_split_at_the_end_is_an_error(self):
        with self.assertRaises(PipelineError):
            split_cue.split(run(5), 3, 3.0)

    def test_a_split_outside_the_cue_is_an_error(self):
        with self.assertRaises(PipelineError):
            split_cue.split(run(5), 3, 4.5)

    def test_an_index_off_the_end_is_an_error(self):
        with self.assertRaises(PipelineError):
            split_cue.split(run(5), 9, 2.4)

    def test_times_stay_in_order(self):
        got = split_cue.split(run(5), 3, 2.4)
        for before, after in zip(got, got[1:]):
            self.assertLessEqual(before["end"], after["start"])


class TestRows(unittest.TestCase):
    """TSV：後壁ê逝退一號，剖開彼條ê兩半各家己一逝。"""

    ROWS = [(1, "一"), (2, "二"), (3, "三"), (4, "四"), (5, "五")]

    def test_rows_before_the_split_do_not_move(self):
        got = dict(split_cue.remap_rows(self.ROWS, 3, "頭", "尾"))
        self.assertEqual(got[1], "一")
        self.assertEqual(got[2], "二")

    def test_the_split_cue_becomes_two_rows(self):
        got = dict(split_cue.remap_rows(self.ROWS, 3, "頭", "尾"))
        self.assertEqual(got[3], "頭")
        self.assertEqual(got[4], "尾")

    def test_later_rows_shift_by_one(self):
        got = dict(split_cue.remap_rows(self.ROWS, 3, "頭", "尾"))
        self.assertEqual(got[5], "四")
        self.assertEqual(got[6], "五")

    def test_the_row_count_grows_by_one(self):
        got = split_cue.remap_rows(self.ROWS, 3, "頭", "尾")
        self.assertEqual(len(got), len(self.ROWS) + 1)

    def test_it_comes_back_in_cue_order(self):
        got = split_cue.remap_rows(list(reversed(self.ROWS)), 3, "頭", "尾")
        self.assertEqual([n for n, _ in got], sorted(n for n, _ in got))

    def test_a_missing_split_row_is_still_created(self):
        """彼條 cue 若本底無佇 TSV 內底，兩半猶原愛寫出來。"""
        got = dict(split_cue.remap_rows([(1, "一"), (5, "五")], 3, "頭", "尾"))
        self.assertEqual(got[3], "頭")
        self.assertEqual(got[4], "尾")


class TestFolders(unittest.TestCase):
    """Cue 徙位ê時，逐个用號碼做鍵ê物件攏愛綴leh徙。

    本底有兩个 vision 目錄：`rebuild` 是對 `3-vision` **佮**
    `4-vision-rtf` 兩爿組ê，rtf 彼爿贏。剖開了後干焦徙頭一个，rtf 彼
    爿ê號碼就差一號——而且 **`ingest` 袂出聲**（伊干焦看 `3-vision`），
    是 `rebuild --verify` 才掠著ê：036午 佮 049午 拄好就是有 rtf 檔彼
    兩集。「五項用號碼做鍵ê物件」彼張清單算漏一項，就出這款代誌。

    疊層量過是全然重複ê，已經提掉矣，所以chit-má賰一个目錄——彼類ê
    失誤無所在通生。清單本身改用測試守（見 test_cue_key_registry）。
    """

    def test_the_one_vision_folder_is_listed(self):
        got = split_cue.vision_folders("20210205_036_午間_Rukai_魯凱")
        self.assertEqual(len(got), 1)
        self.assertTrue(got[0].endswith("2-vision/2021-02/"
                                        "20210205_036_午間_Rukai_魯凱"))


class TestSheets(unittest.TestCase):
    """`sheets.json` 嘛是用 cue 號碼做鍵ê，愛綴leh徙。

    `ingest` 用伊把關「這條 cue 敢有予讀者看過」。剖開了後濟一條，
    `sheets.json` 若無更新，`ingest` 就講「cue N 無佇任何一張圖條
    頂懸」——**彼道把關是著ê**，伊拄好擋牢「憑空塞一條無人看過ê
    cue 入去」。所以愛更新，毋是kā把關關掉。

    新彼半囥佇**佮頭半仝一張**：畫面頂懸彼兩句本底就佇仝一格內底，
    讀者看著ê就是彼張。
    """

    SHEETS = {"sheet_001.png": [1, 2, 3, 4],
              "sheet_002.png": [5, 6, 7, 8]}

    def test_later_cues_shift(self):
        got = split_cue.remap_sheets(self.SHEETS, 3)
        self.assertEqual(got["sheet_002.png"], [6, 7, 8, 9])

    def test_the_new_half_joins_its_own_sheet(self):
        got = split_cue.remap_sheets(self.SHEETS, 3)
        self.assertEqual(got["sheet_001.png"], [1, 2, 3, 4, 5])

    def test_earlier_sheets_are_untouched(self):
        got = split_cue.remap_sheets(self.SHEETS, 6)
        self.assertEqual(got["sheet_001.png"], [1, 2, 3, 4])

    def test_the_total_grows_by_one(self):
        got = split_cue.remap_sheets(self.SHEETS, 3)
        before = sum(len(v) for v in self.SHEETS.values())
        self.assertEqual(sum(len(v) for v in got.values()), before + 1)

    def test_every_cue_appears_once(self):
        got = split_cue.remap_sheets(self.SHEETS, 3)
        seen = []
        for cues in got.values():
            seen += cues
        self.assertEqual(sorted(seen), list(range(1, len(seen) + 1)))

    def test_cues_stay_sorted_inside_a_sheet(self):
        got = split_cue.remap_sheets(self.SHEETS, 3)
        for cues in got.values():
            self.assertEqual(cues, sorted(cues))


if __name__ == "__main__":
    unittest.main()
