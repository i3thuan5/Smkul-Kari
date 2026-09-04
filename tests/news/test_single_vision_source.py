"""One vision source, and the proof that dropping the second changed nothing.

`4-vision-rtf/` was a second transcript folder that `rebuild` merged over
`3-vision/`, the rtf side winning. It was measured on 2026-08-31 before
being deleted: **all 4,151 of its cues across 16 episodes carried the same
text the vision side already had** -- 0 cues only it held, 0 where the two
disagreed -- and `episode_transcripts` run with and without it gave
identical output for 16 of 16 episodes. The merge could not have been
doing anything.

So the transcripts come from one folder now, and these say so. A second
source quietly merged back in fails them.

疊層彼爿毋是無代價ê：`split_cue` 重編號ê時漏改伊，`ingest` 無出聲
（伊干焦行 `3-vision`），是 `rebuild --verify` 才掠著——彼工切ê四集
內底，拄好就是有 rtf 彼兩集歹去。單一來源了後，彼類ê失誤無所在通生。
"""
import os
import tempfile
import unittest
from unittest import mock

from scripts.news import paths
from scripts.news import rebuild

NAME = "20210209_040_午間_Kavalan_噶瑪蘭"


class TestOneSourceIsWhatTheMergeSaid(unittest.TestCase):
    def _stage(self, *rows):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        folder = os.path.join(tmp.name, "2021-02", NAME)
        os.makedirs(folder)
        with open(os.path.join(folder, "b01.tsv"), "w",
                  encoding="utf-8") as handle:
            for cue, text in rows:
                handle.write("%s\thàn\t%s\n" % (cue, text))
        return tmp.name

    def _read(self, stage):
        with mock.patch.object(paths, "KARI_VISION", stage):
            return rebuild.episode_transcripts(NAME)

    def test_the_vision_side_alone_answers(self):
        got = self._read(self._stage((1, "頭一句"), (2, "第二句")))
        self.assertEqual(got["1"]["han"], "頭一句")
        self.assertEqual(got["2"]["han"], "第二句")

    def test_a_blank_third_column_stays_blank(self):
        self.assertEqual(self._read(self._stage((1, "")))["1"]["han"], "")

    def test_only_batch_files_are_read(self):
        """`sample.tsv` 彼款抽查檔袂使算——伊照舊編號索引。"""
        stage = self._stage((73, "著ê"))
        folder = os.path.join(stage, "2021-02", NAME)
        with open(os.path.join(folder, "sample.tsv"), "w",
                  encoding="utf-8") as handle:
            handle.write("73\thàn\t舊編號ê\n")
        self.assertEqual(self._read(stage)["73"]["han"], "著ê")

    def test_there_is_no_second_source_constant_left(self):
        """常數若閣佇咧，就表示閣有一爿通合——彼就是欲提掉ê物件。"""
        self.assertFalse(hasattr(paths, "KARI_VISION_RTF"))


if __name__ == "__main__":
    unittest.main()
