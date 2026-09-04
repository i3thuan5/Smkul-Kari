"""Everything that indexes cues by number, in one list a test can read.

Cue numbers move: `safe_resplit` during a reread, `rescan_band`,
`split_cue` all renumber every cue after the one they touch. Whatever
keys off those numbers has to move with them, and **missing one is
silent** -- `ingest` only walks the vision folder, so when `split_cue`
renumbered without touching the rtf overlay nothing said a word; it was
`rebuild --verify` that found it, and only because of the two episodes
out of four that happened to have overlay files.

The list used to live in a docstring, where it was wrong: it said five
items and the code moved four. So it lives in `paths.cue_keyed()` now,
and this reads it back.

過期ê疊層（`4-vision-rtf`）提掉了後賰四項。清單短去毋是這條無效矣
——顛倒是這條ê重點：**清單改ê時，改一位就好**。
"""
import os
import tempfile
import unittest

from scripts.news import paths

NAME = "20210201_032_午間_Atayal_泰雅"


class TestCueKeyedRegistry(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.work = tmp.name

    def test_it_names_every_cue_keyed_artefact(self):
        got = paths.cue_keyed(self.work, NAME)
        self.assertEqual(set(got),
                         {"timeline", "sheets", "transcripts", "vision"})

    def test_the_work_dir_side_sits_in_the_work_dir(self):
        got = paths.cue_keyed(self.work, NAME)
        for key in ("timeline", "sheets", "transcripts"):
            self.assertTrue(got[key].startswith(self.work + os.sep), key)

    def test_the_vision_side_is_the_store_folder_for_that_episode(self):
        got = paths.cue_keyed(self.work, NAME)
        self.assertEqual(got["vision"],
                         paths.stage_path(paths.KARI_VISION, NAME))

    def test_the_timeline_is_whichever_stage_this_work_dir_has(self):
        """粗切ê佮精修ê兩種版面攏愛揣會著——清單毋是寫死一條路。"""
        coarse = paths.coarse_cues(self.work)
        os.makedirs(os.path.dirname(coarse))
        open(coarse, "w").close()
        self.assertEqual(paths.cue_keyed(self.work, NAME)["timeline"],
                         coarse)
        refined = paths.refined_cues(self.work)
        os.makedirs(os.path.dirname(refined))
        open(refined, "w").close()
        self.assertEqual(paths.cue_keyed(self.work, NAME)["timeline"],
                         refined)

    def test_an_empty_work_dir_still_names_where_the_timeline_goes(self):
        """猶未切ê時嘛愛講會出「應該囥佗位」，才有法度做遷移佮建檔。"""
        self.assertEqual(paths.cue_keyed(self.work, NAME)["timeline"],
                         paths.coarse_cues(self.work))


if __name__ == "__main__":
    unittest.main()
