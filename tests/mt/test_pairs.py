"""pairs: one episode's groups as the delivered CSV.

The column order is the user's (2026-09-24); the times are SRT stamps,
which carry a comma, and sapolita's Formosan often ends in one -- both
must survive a CSV round trip untouched."""
import csv
import io
import unittest

from scripts.mt import overlap
from scripts.mt import pairs

FIELDS = ["族語別", "語言別代號", "成果檔名", "開始時間", "結束時間", "族語",
          "華語", "信心層級", "辭典命中率", "chrF", "最像的族語別", "語音段數",
          "字幕條數", "不採用原因"]


def seg(i, start, end, formosan):
    return {"index": i, "start": start, "end": end, "formosan": formosan,
            "han": ""}


def ent(j, start, end, han):
    return {"index": j, "true_start": start, "true_end": end, "han": han,
            "formosan": "", "cues": [j]}


EPISODE = {"族語別": "魯凱", "語言別代號": "dru-x-ngdr",
           "成果檔名": "20210101_001_午間_Rukai_魯凱"}
SEGS = [seg(0, 26.22, 32.46, "kikai ka pathagilangeta kay singwen yae la "
            "tapathwalana dreele kai ki icungku sbaw,"),
        seg(1, 32.4, 36.2, "ʼinaciyani hosang ʼo")]
ENTS = [ent(0, 26.3, 29.0, "新聞一開始"), ent(1, 29.0, 32.0, "首先帶大家來看中國時報"),
        ent(2, 32.5, 36.0, "配合三級警戒")]


def row(group, level="高信心", reason="", rate=0.3077, chrf=0.0451,
        span=(26.22, 32.46)):
    return pairs.row(EPISODE, group, SEGS, ENTS,
                     {"lexicon_rate": rate, "chrf": chrf,
                      "best_tribe": "魯凱"}, level, reason, span)


def read(text):
    return list(csv.reader(io.StringIO(text)))


class TestRow(unittest.TestCase):
    def test_columns_in_the_users_order(self):
        text = pairs.render([row({"segs": [0], "entries": [0, 1]})])
        self.assertEqual(read(text)[0], FIELDS)

    def test_srt_stamps_and_trailing_comma_survive(self):
        text = pairs.render([row({"segs": [0], "entries": [0, 1]})])
        got = dict(zip(FIELDS, read(text)[1]))
        self.assertEqual(got["開始時間"], "00:00:26,220")
        self.assertEqual(got["結束時間"], "00:00:32,460")
        self.assertTrue(got["族語"].endswith("icungku sbaw,"))

    def test_text_verbatim_and_joined_by_one_space(self):
        got = dict(zip(FIELDS, read(pairs.render(
            [row({"segs": [0, 1], "entries": [0, 1, 2]})]))[1]))
        self.assertIn("sbaw, ʼinaciyani", got["族語"])
        self.assertEqual(got["華語"],
                         "新聞一開始 首先帶大家來看中國時報 配合三級警戒")
        self.assertEqual((got["語音段數"], got["字幕條數"]), ("2", "3"))

    def test_rates_have_three_decimals_and_kept_rows_no_reason(self):
        got = dict(zip(FIELDS, read(pairs.render(
            [row({"segs": [0], "entries": [0]})]))[1]))
        self.assertEqual((got["辭典命中率"], got["chrF"]), ("0.308", "0.045"))
        self.assertEqual(got["不採用原因"], "")

    def test_dropped_row_carries_its_reason(self):
        got = dict(zip(FIELDS, read(pairs.render(
            [row({"segs": [1], "entries": [2]}, "不採用", "詞數不足")]))[1]))
        self.assertEqual((got["信心層級"], got["不採用原因"]),
                         ("不採用", "詞數不足"))


class TestTime(unittest.TestCase):
    def test_writes_the_time_it_is_given_not_its_own(self):
        # the CSV shows the padded time; row must not fall back to the
        # true span (26.22-32.46) that it could compute from the segments
        got = dict(zip(FIELDS, read(pairs.render(
            [row({"segs": [0], "entries": [0, 1]},
                 span=(25.72, 32.43))]))[1]))
        self.assertEqual((got["開始時間"], got["結束時間"]),
                         ("00:00:25,720", "00:00:32,430"))


class TestFilledHoles(unittest.TestCase):
    def test_filled_segments_join_in_time_order_and_are_counted(self):
        segs = []
        for i, (start, end) in enumerate([(0.0, 4.0), (5.0, 6.0), (7.0, 8.0),
                                          (9.0, 10.0), (11.0, 14.0)]):
            segs.append(seg(i, start, end, "w%d" % i))
        ents = [ent(0, 0.5, 1.9, "甲"), ent(1, 2.0, 17.0, "乙")]
        groups, _, _ = overlap.max_overlap_groups(segs, ents,
                                                  straddle_frac=0.1)
        got = pairs.row(EPISODE, groups[0], segs, ents,
                        {"lexicon_rate": 0.5, "chrf": 0.1}, "高信心", "",
                        (0.0, 14.5))
        self.assertEqual(got["族語"], "w0 w1 w2 w3 w4")
        self.assertEqual(got["語音段數"], "5")


class TestFile(unittest.TestCase):
    def test_utf8_lf_no_bom_and_byte_stable(self):
        rows = [row({"segs": [0], "entries": [0, 1]}),
                row({"segs": [1], "entries": [2]})]
        first = pairs.render(rows).encode("utf-8")
        self.assertEqual(first, pairs.render(rows).encode("utf-8"))
        self.assertFalse(first.startswith(b"\xef\xbb\xbf"))
        self.assertNotIn(b"\r", first)
        self.assertTrue(first.endswith(b"\n"))

    def test_no_groups_is_still_a_file_with_its_header(self):
        self.assertEqual(read(pairs.render([])), [FIELDS])


if __name__ == "__main__":
    unittest.main()
