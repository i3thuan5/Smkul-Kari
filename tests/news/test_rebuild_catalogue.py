"""新聞 `rebuild`（含 `--verify`）開頭愛真正跑 `row_problems` 整組。

`catalogue_checks.row_problems` 本底全 repo 干焦《開會了》ê
`rebuild` 有呼叫，新聞這爿 `rebuild --verify` 佮 `name_catalogue --check`
攏無——「成果檔名不得重複」、「節目名稱佮播出日期對會著」、語言別代號、
列序，新聞目錄從來無人檢查過。
"""
import io
import sys
import unittest
from contextlib import redirect_stdout
from unittest import mock

from scripts.errors import PipelineError
from scripts.news import rebuild

ROW = {"成果檔名": "20210101_001_午間_Rukai_魯凱",
       "節目名稱": "午間族語新聞", "年度": "2021", "集數": "1",
       "播出日期": "2021-01-01", "族語別(英)": "Rukai",
       "族語別(中)": "魯凱", "語言別": "", "語言別代號": "dru",
       "原始影片檔案位置": "ilrdf-corpus/魯凱語.mp4", "備註": ""}


def another():
    two = dict(ROW)
    two.update({"成果檔名": "20210102_002_午間_Rukai_魯凱", "集數": "2",
                "播出日期": "2021-01-02"})
    return two


class TestCatalogueProblems(unittest.TestCase):

    def problems(self, rows):
        with mock.patch.object(rebuild.episodes, "rows",
                               return_value=rows):
            return rebuild.catalogue_problems()

    def test_a_clean_catalogue_has_none(self):
        self.assertEqual(self.problems([ROW, another()]), [])

    def test_a_duplicate_name_is_named_by_line(self):
        got = self.problems([ROW, dict(ROW)])
        self.assertEqual(len(got), 1)
        self.assertIn("第 3 逝", got[0])
        self.assertIn("重複", got[0])

    def test_a_programme_name_that_disagrees_with_the_date_is_named(self):
        bad = dict(ROW, 成果檔名="20240802_005_午間_Rukai_魯凱",
                   年度="2024", 集數="5", 播出日期="2024-08-02")
        got = self.problems([bad])
        self.assertEqual(len(got), 1)
        self.assertIn("看見族語（午間）", got[0])


class TestMainStopsOnTheCatalogueFirst(unittest.TestCase):
    """目錄有問題就佇頭前停，毋免等 6 分鐘ê重建才發現。"""

    def run_main(self, rows):
        out = io.StringIO()
        with mock.patch.object(sys, "argv", ["rebuild", "--verify"]), \
                mock.patch.object(rebuild.episodes, "rows",
                                  return_value=rows), \
                mock.patch.object(rebuild.episodes, "load",
                                  return_value=[]), \
                mock.patch.object(
                    rebuild.datadirs, "stage_problems",
                    side_effect=AssertionError("目錄檢查愛佇階段檢查進前")), \
                redirect_stdout(out):
            with self.assertRaises(PipelineError) as caught:
                rebuild.main()
        return out.getvalue(), str(caught.exception)

    def test_a_duplicate_name_stops_the_rebuild_and_is_printed(self):
        text, error = self.run_main([ROW, dict(ROW)])
        self.assertIn("CATALOGUE:", text)
        self.assertIn("重複", text)
        self.assertIn("1", error)


if __name__ == "__main__":
    unittest.main()
