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
