"""`rebuild` 提ê嘛干焦是 `b*.tsv`，佮 `ingest` 仝款。

Store 內底 644 个 TSV 有 643 个號做 `b<N>.tsv`；賰彼一个是
20210209_040 ê `sample.tsv`——逐 72 條抽 4 條ê抽查檔。

伊 sort 起來排佇 `b*.tsv` **後壁**，所以 `episode_transcripts` 會kā
彼幾條**蓋過去**。舊編號ê時看袂出來：`sample.tsv` 本底就是對 `b*.tsv`
抄ê，蓋過去ê內容佮原本仝款。**重新編號了後就現形矣**——伊猶原照舊
編號索引，蓋著ê是別條 cue，20210209_040 ê SRT 差 1,070 逝。

`ingest` 彼爿嘛有仝一个 glob（`tests/news/test_ingest.py`
`TestOnlyBatchFiles`）。兩爿愛做伙改，無ê話 `rebuild --verify` 佮
交付ê SRT 會兩爿對袂起來。
"""
import os
import tempfile
import unittest
from unittest import mock

from scripts import datadirs
from scripts.news import paths, rebuild


class TestOnlyBatchTsvs(unittest.TestCase):

    def _stage(self, *files):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        folder = os.path.join(tmp.name, "2021-02", "20210209_040_午間_X_甲")
        os.makedirs(folder)
        for name, body in files:
            with open(os.path.join(folder, name), "w",
                      encoding="utf-8") as handle:
                handle.write(body)
        return tmp.name

    def _read(self, stage):
        with mock.patch.object(paths, "KARI_VISION", stage):
            return rebuild.episode_transcripts("20210209_040_午間_X_甲")

    def test_a_stray_tsv_does_not_overwrite_a_batch(self):
        stage = self._stage(("b01.tsv", "73\thàn\t著ê\n"),
                            ("sample.tsv", "73\thàn\t舊編號ê\n"))
        self.assertEqual(self._read(stage)["73"]["han"], "著ê")

    def test_batch_files_are_still_read(self):
        stage = self._stage(("b01.tsv", "1\thàn\t甲\n"),
                            ("b02.tsv", "2\thàn\t乙\n"))
        got = self._read(stage)
        self.assertEqual(got["1"]["han"], "甲")
        self.assertEqual(got["2"]["han"], "乙")


if __name__ == "__main__":
    unittest.main()


class TestStageContainment(unittest.TestCase):
    """下跤ê階段愛是頂懸階段ê子集。

    一集一个階段做煞就家己入 Kari-SRT（時間軸幾點鐘、Claude Vision 幾
    十點鐘），所以「`1-cues` 有 75 集、`3-srt` 才 40 集」是正常狀態，
    毋是缺件。倒轉來就是錯：`3-srt` 有一份 SRT，`1-cues` 無彼集ê時間
    軸，彼份交付物重建袂出來——伊毋知影對佗位來ê。

    孤兒檔嘛是按呢掠ê。
    """

    def test_downstream_missing_upstream_is_named(self):
        problems = datadirs.stage_problems([
            ("1-cues", {"a", "b"}),
            ("2-vision", {"a", "b"}),
            ("3-srt", {"a", "b", "c"}),
        ])
        # 只比頂懸彼一站：鏈仔家己會傳遞，比規組ê話仝一个名會講三擺
        self.assertEqual(len(problems), 1)
        self.assertIn("c", problems[0])
        self.assertIn("2-vision", problems[0])

    def test_it_says_which_layer_is_missing(self):
        problems = datadirs.stage_problems([
            ("1-cues", {"a", "b"}),
            ("2-vision", {"a"}),
            ("3-srt", {"a", "b"}),
        ])
        self.assertEqual(len(problems), 1)
        self.assertIn("2-vision", problems[0])
        self.assertIn("b", problems[0])

    def test_upstream_running_ahead_is_fine(self):
        # 1-cues 75 集、3-srt 40 集——分階段入庫就是按呢。
        self.assertEqual(datadirs.stage_problems([
            ("1-cues", set("abcdefgh")),
            ("2-vision", set("abcd")),
            ("3-srt", set("ab")),
        ]), [])

    def test_all_equal_is_fine(self):
        self.assertEqual(datadirs.stage_problems([
            ("1-cues", {"a"}), ("2-vision", {"a"}), ("3-srt", {"a"}),
        ]), [])

    def test_every_missing_name_is_named_not_just_the_first(self):
        problems = datadirs.stage_problems([
            ("1-cues", set()),
            ("3-srt", {"x", "y"}),
        ])
        self.assertEqual(len(problems), 2)
        self.assertIn("x", " ".join(problems))
        self.assertIn("y", " ".join(problems))
