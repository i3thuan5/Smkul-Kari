"""paragraph_srt: one episode's CSV rows -> 3-srt-paragraph SRT.

The CSV already carries the padded time, worked out with every VAD
segment as a neighbour. The SRT must copy it, never pad again from the
kept rows alone: with the dropped groups and the lonely segments gone,
the padding would reach into other people's speech (244 of 15,470 kept
edges in 2021-01..02)."""
import unittest

from scripts.mt import paragraph_srt
from scripts.srtlib import srt


def row(start, end, level="高信心", formosan="o kawas", han="華語",
        reason=""):
    return {"族語別": "阿美", "語言別代號": "ami",
            "成果檔名": "20210201_032_晚間_Amis_阿美",
            "開始時間": srt.srt_timestamp(start),
            "結束時間": srt.srt_timestamp(end), "族語": formosan,
            "華語": han, "信心層級": level, "不採用原因": reason}


class TestRows(unittest.TestCase):
    def test_dropped_groups_are_not_subtitles_and_numbers_run_on(self):
        rows = [row(10, 20), row(30, 40, "不採用", reason="幻覺"),
                row(50, 60, "中信心")]
        text = paragraph_srt.render(rows)
        self.assertTrue(text.startswith("1\n"))
        self.assertIn("\n2\n", text)
        self.assertEqual(len(srt.parse_srt(text)), 2)

    def test_time_is_copied_from_the_csv_not_padded_again(self):
        # a kept group ending at 10.0 next to a dropped one at 10.4: the
        # CSV says 10.2; re-padding the kept rows alone would give 10.5
        rows = [row(4.5, 10.2), row(10.2, 15.5, "不採用", reason="幻覺")]
        parsed = srt.parse_srt(paragraph_srt.render(rows))
        self.assertEqual(srt.srt_timestamp(parsed[0][1]), "00:00:10,200")
        self.assertEqual(srt.srt_timestamp(parsed[0][0]), "00:00:04,500")

    def test_two_labelled_lines_with_the_csv_text_verbatim(self):
        rows = [row(1, 2, formosan="paloa toki, ʼalo", han="奇美橋 早期")]
        lines = paragraph_srt.render(rows).split("\n")
        self.assertEqual(lines[2], "族語：paloa toki, ʼalo")
        self.assertEqual(lines[3], "華語：奇美橋 早期")

    def test_no_kept_group_is_an_empty_file(self):
        rows = [row(1, 2, "不採用", reason="詞數不足")]
        self.assertEqual(paragraph_srt.render(rows), "")

    def test_byte_stable_lf_and_trailing_newline(self):
        rows = [row(1, 2), row(3, 4, "中信心")]
        first = paragraph_srt.render(rows)
        self.assertEqual(first, paragraph_srt.render(rows))
        self.assertNotIn("\r", first)
        self.assertTrue(first.endswith("\n"))


if __name__ == "__main__":
    unittest.main()
