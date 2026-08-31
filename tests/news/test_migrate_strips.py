"""migrate_strips：舊ê序號名換做起始時間名。

**上要緊ê一點**：換名愛**照磁碟頂ê檔案**走，袂使照 cue 走。
`safe_resplit` kā一條 cue 拆做幾若條ê時，逐半攏指仝一張原圖
（20210201_032_午間_Atayal_泰雅 cue 108–111 四條攏指
`strips/00103_han.png`）。若逐條 cue 家己算一个新名，仝一支檔案
會hőng要求改做四个無仝ê名。

所以：一支舊檔對一个新名（用**指伊ê彼幾條內底上頭前彼條**ê起始
時間），紲落去kā逐个指伊ê `images` 做伙改。
"""
import unittest

from scripts.news import migrate_strips


def cue(index, start, image):
    return {"index": index, "start": start, "end": start + 1.0,
            "images": {"han": image}}


class TestPlan(unittest.TestCase):
    def test_one_cue_one_file(self):
        cues = [cue(1, 1.5, "strips/00001_han.png")]
        got = migrate_strips.plan(cues)
        self.assertEqual(got, {"strips/00001_han.png":
                               "strips/t00001500_han.png"})

    def test_shared_files_get_one_name_from_the_earliest_cue(self):
        """四條指仝一張——彼張干焦一个新名，用上早彼條ê時間。"""
        cues = [cue(108, 300.0, "strips/00103_han.png"),
                cue(109, 301.0, "strips/00103_han.png"),
                cue(110, 302.0, "strips/00103_han.png")]
        got = migrate_strips.plan(cues)
        self.assertEqual(got, {"strips/00103_han.png":
                               "strips/t00300000_han.png"})

    def test_cue_order_does_not_matter(self):
        cues = [cue(110, 302.0, "strips/00103_han.png"),
                cue(108, 300.0, "strips/00103_han.png")]
        got = migrate_strips.plan(cues)
        self.assertEqual(got["strips/00103_han.png"],
                         "strips/t00300000_han.png")

    def test_already_migrated_files_are_left_alone(self):
        cues = [cue(1, 1.5, "strips/t00001500_han.png")]
        self.assertEqual(migrate_strips.plan(cues), {})

    def test_a_mixed_work_dir_only_moves_the_old_ones(self):
        cues = [cue(1, 1.5, "strips/00001_han.png"),
                cue(2, 2.5, "strips/t00002500_han.png")]
        got = migrate_strips.plan(cues)
        self.assertEqual(list(got), ["strips/00001_han.png"])

    def test_the_line_name_survives(self):
        cues = [cue(1, 1.5, "strips/00001_line0.png")]
        got = migrate_strips.plan(cues)
        self.assertEqual(got["strips/00001_line0.png"],
                         "strips/t00001500_line0.png")

    def test_no_two_old_files_map_to_one_new_name(self):
        """新名撞號＝改名ê時會蓋去，愛佇動手進前就掠著。"""
        cues = [cue(1, 5.0, "strips/00001_han.png"),
                cue(2, 5.0, "strips/00002_han.png")]
        with self.assertRaises(Exception):
            migrate_strips.plan(cues)

    def test_a_cue_with_no_image_is_skipped(self):
        cues = [cue(1, 1.5, "strips/00001_han.png")]
        cues.append({"index": 2, "start": 2.0, "end": 3.0, "images": {}})
        got = migrate_strips.plan(cues)
        self.assertEqual(len(got), 1)


class TestRewrite(unittest.TestCase):
    def test_every_reference_is_updated(self):
        cues = [cue(108, 300.0, "strips/00103_han.png"),
                cue(109, 301.0, "strips/00103_han.png")]
        moves = migrate_strips.plan(cues)
        got = migrate_strips.rewrite(cues, moves)
        for one in got:
            self.assertEqual(one["images"]["han"],
                             "strips/t00300000_han.png")

    def test_untouched_entries_keep_their_value(self):
        cues = [cue(1, 1.5, "strips/t00001500_han.png")]
        got = migrate_strips.rewrite(cues, {})
        self.assertEqual(got[0]["images"]["han"], "strips/t00001500_han.png")

    def test_times_and_indices_are_not_touched(self):
        cues = [cue(7, 300.0, "strips/00103_han.png")]
        got = migrate_strips.rewrite(cues, migrate_strips.plan(cues))
        self.assertEqual(got[0]["index"], 7)
        self.assertEqual(got[0]["start"], 300.0)


class TestAlreadyRenamed(unittest.TestCase):
    """`.B.work/strips` 是 symlink 指去 `.work/strips`——兩爿公家一批檔。

    Migrate `.B.work` ê時，改名是**穿過 symlink** 改著實體檔ê，毋過
    干焦 `.B.work/cues.json` 有更新。輪著 `.work` ê時，舊名ê檔案
    「無佇咧」——**因為已經改好矣**，賰 cues.json 愛綴。

    分會出「已經改好」佮「實在無去」ê法度：**新名彼支敢佇咧**。
    新名有、舊名無 → 改好矣，更新 cues.json 就好。
    兩爿攏無 → 實在無去，愛出聲。
    """

    def test_a_move_whose_target_exists_is_done_already(self):
        self.assertTrue(migrate_strips.already_done(
            lambda p: p == "w/strips/t00001500_han.png",
            "w", "strips/00001_han.png", "strips/t00001500_han.png"))

    def test_a_move_with_neither_file_is_a_real_loss(self):
        self.assertFalse(migrate_strips.already_done(
            lambda p: False,
            "w", "strips/00001_han.png", "strips/t00001500_han.png"))

    def test_a_move_whose_source_exists_is_not_done(self):
        self.assertFalse(migrate_strips.already_done(
            lambda p: p == "w/strips/00001_han.png",
            "w", "strips/00001_han.png", "strips/t00001500_han.png"))


class TestWorkDirs(unittest.TestCase):
    """兩款 work dir 攏愛掃著。

    `ocr-cli cues` 寫ê是 `<slug>.work`，`gap_sheets` 對伊生
    `<slug>.B.work`；`fetch_sftp.sh` 有ê時陣直接切入去 `.B.work`。
    頭一擺遷移我干焦掃 `.B.work`，1 月拄抓落來、猶未做圖條ê 006午
    彼 1,149 張就無徙著。
    """

    def test_both_suffixes_are_matched(self):
        self.assertTrue(migrate_strips.is_work_dir("a.work"))
        self.assertTrue(migrate_strips.is_work_dir("a.B.work"))

    def test_something_else_is_not(self):
        self.assertFalse(migrate_strips.is_work_dir("a.recut"))
        self.assertFalse(migrate_strips.is_work_dir("a.work.bak"))

    def test_the_stem_drops_either_suffix(self):
        self.assertEqual(migrate_strips.stem_of("a.B.work"), "a")
        self.assertEqual(migrate_strips.stem_of("a.work"), "a")


if __name__ == "__main__":
    unittest.main()
