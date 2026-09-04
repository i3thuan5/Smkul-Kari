"""Moving old work dirs onto the staged cue layout, without losing one.

The write side puts new timelines in `1-cues/` and `2-refined/`; the work
dirs cut before that still have a flat `<work>/cues.json`. `cues_to_read`
reads both, which is what let the two live side by side -- and this is
the sweep that ends the transition so the fallback can go.

Which stage a flat file belongs in is **what it says about itself**: a
timeline carrying `refined` has been through the 25fps pass and belongs
in `2-refined/`, one without it is coarse and belongs in `1-cues/`.
Guessing wrong in the coarse direction would be quiet and bad -- the
episode would look un-refined and get re-refined off a video that is no
longer on disk.

冪等是硬需求：規批掃到一半予人斷去是正常ê，閣走一擺愛照常收煞。
"""
import json
import os
import tempfile
import unittest

from scripts.news import migrate_workdirs
from scripts.news import paths

COARSE = {"cues": [{"index": 1, "start": 1.0, "end": 2.0}]}
REFINED = dict(COARSE, refined=True)


class Fixture(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = tmp.name

    def _work(self, name, body=None, staged=None):
        work = os.path.join(self.root, name)
        os.makedirs(work, exist_ok=True)
        if body is not None:
            with open(os.path.join(work, "cues.json"), "w",
                      encoding="utf-8") as handle:
                json.dump(body, handle, ensure_ascii=False)
        if staged is not None:
            path = staged(work)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(REFINED, handle, ensure_ascii=False)
        return work


class TestWhereAFlatTimelineGoes(Fixture):
    def test_a_coarse_one_moves_to_the_coarse_stage(self):
        work = self._work("a.work", COARSE)
        migrate_workdirs.migrate(work)
        self.assertTrue(os.path.exists(paths.coarse_cues(work)))
        self.assertFalse(os.path.exists(paths.refined_cues(work)))

    def test_a_refined_one_moves_to_the_refined_stage(self):
        """檔案家己講伊精修過，就袂使當做粗切ê——無ê話會閣去精修
        一擺，而且影片已經無佇磁碟頂矣。"""
        work = self._work("b.work", REFINED)
        migrate_workdirs.migrate(work)
        self.assertTrue(os.path.exists(paths.refined_cues(work)))
        self.assertFalse(os.path.exists(paths.coarse_cues(work)))

    def test_the_flat_file_is_gone_afterwards(self):
        work = self._work("c.work", COARSE)
        migrate_workdirs.migrate(work)
        self.assertFalse(os.path.exists(os.path.join(work, "cues.json")))

    def test_the_content_survives_unchanged(self):
        work = self._work("d.work", REFINED)
        migrate_workdirs.migrate(work)
        with open(paths.refined_cues(work), encoding="utf-8") as handle:
            self.assertEqual(json.load(handle), REFINED)

    def test_the_reader_finds_it_where_it_landed(self):
        work = self._work("e.work", COARSE)
        migrate_workdirs.migrate(work)
        self.assertEqual(paths.cues_to_read(work), paths.coarse_cues(work))


class TestItIsSafeToRunTwice(Fixture):
    def test_a_work_dir_already_staged_is_left_alone(self):
        work = self._work("f.work", staged=paths.refined_cues)
        self.assertFalse(migrate_workdirs.migrate(work))
        self.assertTrue(os.path.exists(paths.refined_cues(work)))

    def test_running_twice_changes_nothing_the_second_time(self):
        work = self._work("g.work", COARSE)
        self.assertTrue(migrate_workdirs.migrate(work))
        self.assertFalse(migrate_workdirs.migrate(work))

    def test_a_work_dir_with_no_timeline_is_skipped(self):
        work = self._work("h.work")
        self.assertFalse(migrate_workdirs.migrate(work))

    def test_a_flat_file_beside_a_staged_one_is_not_moved_over_it(self):
        """兩爿攏有ê時，新版面彼份是正本——舊ê袂使kā伊蓋掉。"""
        work = self._work("i.work", COARSE, staged=paths.refined_cues)
        migrate_workdirs.migrate(work)
        with open(paths.refined_cues(work), encoding="utf-8") as handle:
            self.assertEqual(json.load(handle), REFINED)


class TestSweep(Fixture):
    def test_it_reports_what_it_moved_and_what_it_skipped(self):
        self._work("one.work", COARSE)
        self._work("two.work", REFINED)
        self._work("three.work", staged=paths.coarse_cues)
        self._work("four.work")
        moved, skipped = migrate_workdirs.sweep(self.root)
        self.assertEqual(moved, 2)
        self.assertEqual(skipped, 2)

    def test_a_second_sweep_moves_nothing(self):
        self._work("one.work", COARSE)
        migrate_workdirs.sweep(self.root)
        self.assertEqual(migrate_workdirs.sweep(self.root)[0], 0)


class TestSheetNames(Fixture):
    """Contact sheets get the same treatment strips did, for one reason.

    `sheet_003.png` is a position in a batch, and positions move: split a
    cue, rebuild the sheets, and sheet three is a different piece of
    programme. `sheets.json` is the map either way, so nothing that reads
    it cares -- but a person looking at file names does, and that is who
    the naming is for.

    改名愛佮 `sheets.json` ê鍵做伙改，無ê話對照就斷去矣。
    """

    def _sheets(self, name, mapping, cues):
        work = os.path.join(self.root, name)
        os.makedirs(os.path.join(work, "sheets"), exist_ok=True)
        for sheet in mapping:
            open(os.path.join(work, "sheets", sheet), "w").close()
        with open(os.path.join(work, "sheets.json"), "w",
                  encoding="utf-8") as handle:
            json.dump(mapping, handle)
        timeline = paths.coarse_cues(work)
        os.makedirs(os.path.dirname(timeline), exist_ok=True)
        with open(timeline, "w", encoding="utf-8") as handle:
            json.dump({"cues": cues}, handle)
        return work

    CUES = [{"index": 1, "start": 10.0, "end": 11.0},
            {"index": 2, "start": 12.5, "end": 13.0},
            {"index": 3, "start": 20.0, "end": 21.0}]

    def test_a_sheet_is_renamed_for_its_first_cue(self):
        work = self._sheets("a.work", {"sheet_001.png": [1, 2]}, self.CUES)
        migrate_workdirs.migrate_sheets(work)
        self.assertTrue(os.path.exists(
            os.path.join(work, "sheets", "t00010000.png")))

    def test_the_old_file_is_gone(self):
        work = self._sheets("b.work", {"sheet_001.png": [1, 2]}, self.CUES)
        migrate_workdirs.migrate_sheets(work)
        self.assertFalse(os.path.exists(
            os.path.join(work, "sheets", "sheet_001.png")))

    def test_the_map_is_rewritten_with_the_new_keys(self):
        work = self._sheets("c.work", {"sheet_001.png": [1, 2],
                                       "sheet_002.png": [3]}, self.CUES)
        migrate_workdirs.migrate_sheets(work)
        with open(os.path.join(work, "sheets.json"), encoding="utf-8") as h:
            got = json.load(h)
        self.assertEqual(got, {"t00010000.png": [1, 2],
                               "t00020000.png": [3]})

    def test_running_twice_changes_nothing(self):
        work = self._sheets("d.work", {"sheet_001.png": [1]}, self.CUES)
        self.assertTrue(migrate_workdirs.migrate_sheets(work))
        self.assertFalse(migrate_workdirs.migrate_sheets(work))

    def test_a_work_dir_with_no_sheets_is_skipped(self):
        work = os.path.join(self.root, "e.work")
        os.makedirs(work)
        self.assertFalse(migrate_workdirs.migrate_sheets(work))

    def test_a_sheet_naming_a_cue_the_timeline_lost_is_left_alone(self):
        """Cue 予人剖掉、編號徙位ê時，對袂著ê彼張莫烏白改名——
        改毋著就是kā別段ê時間安佇伊頭殼頂。"""
        work = self._sheets("f.work", {"sheet_001.png": [99]}, self.CUES)
        migrate_workdirs.migrate_sheets(work)
        self.assertTrue(os.path.exists(
            os.path.join(work, "sheets", "sheet_001.png")))


if __name__ == "__main__":
    unittest.main()
