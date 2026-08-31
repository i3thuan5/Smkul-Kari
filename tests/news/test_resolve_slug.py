"""resolve_slug: 目錄索引（用整條路徑）佮命名（srt_name／slug）。

索引改用**整條相對路徑**是為著一个會恬恬做毋著的 bug：舊版對整串
`a.mxf;b.mp4` 取 basename，只切著上尾彼條，全語料 78 个檔名因此查無；
查無就退去檔名 stem，slug 佮 metadata 攏空，而且袂報錯。
"""
import os
import tempfile
import unittest

from scripts.news import resolve_slug
from scripts.errors import PipelineError

HEAD = ("節目名稱,年度,集數,播出日期,播出時段,族語別(英),族語別(中),"
        "有無影片,影片檔案位置,音檔位置(mp3),音檔位置(wav),文稿位置,備註")

MXF = "ilrdf-corpus/族語新聞/110.1-110.10/2月原始mxf檔/21NL004_37晚間族語新聞.mxf"
MP4 = "ilrdf-corpus/族語新聞/110.1-110.10/7月/21NL004_37晚間族語新聞.mp4"


def catalogue_file(test, rows):
    handle = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False,
                                         encoding="utf-8-sig")
    handle.write(HEAD + "\n")
    for line in rows:
        handle.write(line + "\n")
    handle.close()
    test.addCleanup(os.unlink, handle.name)
    return handle.name


class TestIndex(unittest.TestCase):
    ROW = ("晚間族語新聞,2021,37,2021-02-06,晚間,Paiwan,排灣,是,"
           + MXF + ";" + MP4 + ",,,,")

    def _load(self, rows=None):
        path = catalogue_file(self, rows if rows is not None else [self.ROW])
        return resolve_slug.load(path)

    def test_both_halves_of_a_semicolon_pair_resolve(self):
        cat = self._load()
        for path in (MXF, MP4):
            row, problem = cat.row_for(path)
            self.assertEqual(problem, "")
            self.assertEqual(row["族語別(中)"], "排灣")

    def test_the_three_ways_of_writing_a_path_are_one_file(self):
        # 目錄寫 `ilrdf-corpus/…`，伺服器服 `/docker/ilrdf-corpus/…`，
        # fetch_sftp 傳的是 `族語新聞/…`——三款攏是仝一支檔。
        cat = self._load()
        tail = "族語新聞/110.1-110.10/7月/21NL004_37晚間族語新聞.mp4"
        for given in (MP4, "/docker/" + MP4, tail, "/" + tail):
            row, problem = cat.row_for(given)
            self.assertEqual(problem, "", given)
            self.assertEqual(row["集數"], "37")

    def test_a_bare_file_name_still_resolves_when_it_is_unambiguous(self):
        cat = self._load()
        row, problem = cat.row_for("21NL004_37晚間族語新聞.mxf")
        self.assertEqual(problem, "")
        self.assertEqual(row["集數"], "37")

    def test_a_file_name_two_episodes_claim_is_refused_not_guessed(self):
        # 2021-03-21：拉阿魯哇佮卡那卡那富兩逝指著仝一支檔。舊版
        # `setdefault` 是頭一逝贏，贏的是「誰排代先」。
        shared = "ilrdf-corpus/族語新聞/110.1-110.10/3月/21NL003_80五間族語新聞.mp4"
        rows = ["午間族語新聞,2021,80,2021-03-21,午間,Hla'alua,拉阿魯哇,是,"
                + shared + ",,,,",
                "午間族語新聞,2021,80,2021-03-21,午間,Kanakanavu,卡那卡那富,是,"
                + shared + ",,,,"]
        cat = self._load(rows)
        row, problem = cat.row_for("21NL003_80五間族語新聞.mp4")
        self.assertIsNone(row)
        self.assertIn("兩集以上", problem)

    def test_an_unknown_file_says_so(self):
        cat = self._load()
        row, problem = cat.row_for("readme.mxf")
        self.assertIsNone(row)
        self.assertIn("目錄", problem)

    def test_a_missing_catalogue_is_an_empty_index_not_a_crash(self):
        cat = resolve_slug.load(os.path.join(tempfile.gettempdir(),
                                             "no-such-catalogue.csv"))
        row, problem = cat.row_for(MP4)
        self.assertIsNone(row)
        self.assertTrue(problem)


class TestNames(unittest.TestCase):
    """srt_name 佮 slug 是兩个無仝的名，刁工分開的。"""

    ROW = {
        "年度": "2021",
        "播出日期": "2021-02-01",
        "播出時段": "午間",
        "族語別(英)": "Atayal",
        "族語別(中)": "泰雅",
    }

    def test_srt_name_format(self):
        self.assertEqual(resolve_slug.srt_name(self.ROW, "32"),
                         "20210201_032_午間_Atayal_泰雅")

    def test_episode_is_zero_padded_to_sort_in_broadcast_order(self):
        self.assertIn("_005_", resolve_slug.srt_name(dict(self.ROW), "5"))

    def test_slug_keeps_the_dashed_date(self):
        self.assertEqual(resolve_slug.slugify(self.ROW, "32"),
                         "2021_032_2021-02-01_午間_Atayal_泰雅")

    def test_a_row_missing_a_field_says_which_one(self):
        row = dict(self.ROW)
        del row["族語別(英)"]
        with self.assertRaisesRegex(PipelineError, "族語別"):
            resolve_slug.srt_name(row, "32")


if __name__ == "__main__":
    unittest.main()
