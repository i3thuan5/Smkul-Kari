"""bisrt: the three renders, and what each one is for.

`2-srt-raw` is the delivered one: two lines, 族語：／華語：, short labels
because it is the thing that gets used. `3-srt-ai` and `4-srt-quality`
are for analysis, so their labels say where each line came from
(使用者裁定 2026-09-04) -- reading one of those files, you are asking
which engine said what, and a bare 族語： does not answer that.

All three carry the same entries at the same timestamps as the delivered
subtitle SRT, because all three render off the same chain rows.

The two analysis renders take their extra line from a lookup rather than
from the entry: the same render has to work while the translation is
being fetched (the lookup calls the service) and during offline rebuild
verification (the lookup only reads the cache, and a miss is an error
naming the entry).
"""
import unittest

from scripts.asrmt import bisrt
from scripts.srtlib import assemble
from scripts.srtlib import srt
from scripts.errors import PipelineError


def entry(index=1, formosan="mikeriday anini", subtitle="今天主持",
          zh_ailabs="今天負責主持", zh_claude="今天由我主持",
          f_ailabs="mikeriday kako", f_claude="o mikeriday",
          srt_start=9.5, srt_end=12.5):
    return {
        "index": index, "srt_start": srt_start, "srt_end": srt_end,
        "true_start": 10.0, "true_end": 12.0,
        "formosan": formosan, "subtitle": subtitle,
        "zh": {"ailabs": zh_ailabs, "claude": zh_claude},
        "formosan_from_zh": {"ailabs": f_ailabs, "claude": f_claude},
    }


class TestRawRender(unittest.TestCase):
    def test_same_format_as_the_deliverable(self):
        # 對照版與正式版同格式（族語：／華語：），方便直接比較
        body = bisrt.raw_body([entry()])
        block = srt.parse_srt(body)[0][2].split("\n")
        self.assertEqual(block, ["族語：mikeriday anini",
                                 "華語：今天主持"])

    def test_timestamps_come_from_the_chain_display_window(self):
        got = srt.parse_srt(bisrt.raw_body([entry()]))
        self.assertEqual((got[0][0], got[0][1]), (9.5, 12.5))


class TestAiRender(unittest.TestCase):
    """3-srt-ai：三逝，標籤講明每一逝對佗來。"""

    def _body(self, rows, table):
        def translate(text):
            if text not in table:
                raise PipelineError("快取內底無這逝")
            return table[text]
        return bisrt.ai_body(rows, translate)

    def test_three_labelled_lines_in_the_agreed_order(self):
        body = self._body([entry()], {"mikeriday anini": "今天負責主持"})
        block = srt.parse_srt(body)[0][2].split("\n")
        self.assertEqual(block, ["族語ASR結果：mikeriday anini",
                                 "華語OCR字幕：今天主持",
                                 "族語ASR結果翻譯華語-ailabs：今天負責主持"])

    def test_a_no_speech_entry_keeps_the_prefix_and_asks_nobody(self):
        asked = []

        def translate(text):
            asked.append(text)
            return "毋著"
        body = bisrt.ai_body([entry(formosan="")], translate)
        block = srt.parse_srt(body)[0][2].split("\n")
        self.assertEqual(block[0], "族語ASR結果：")
        self.assertEqual(block[2], "族語ASR結果翻譯華語-ailabs：")
        self.assertEqual(asked, [])

    def test_timestamps_are_the_chain_display_window(self):
        body = self._body([entry()], {"mikeriday anini": "x"})
        got = srt.parse_srt(body)
        self.assertEqual((got[0][0], got[0][1]), (9.5, 12.5))

    def test_the_translation_is_written_in_this_corpus_character_forms(self):
        """服務ê輸出摻著日文字形佮簡體；交付檔愛照語料ê字形。

        正規化做佇遮，毋是做佇快取——快取ê意義是「服務講啥」ê忠實
        紀錄。逐 byte 重建袂受影響，因為正規化是 render ê一部份。
        """
        body = self._body([entry()], {"mikeriday anini": "他説没这样"})
        self.assertIn("他說沒这樣", body)
        self.assertNotIn("説", body)
        self.assertNotIn("没", body)

    def test_a_cache_miss_names_the_entry(self):
        with self.assertRaises(PipelineError) as caught:
            self._body([entry(index=7)], {})
        self.assertIn("條目 7", str(caught.exception))


class TestQualityRender(unittest.TestCase):
    """4-srt-quality：族語、字幕、品質——譯文袂使入去。"""

    def _body(self, rows, table):
        def grade(row):
            if row["index"] not in table:
                raise PipelineError("猶未判")
            return table[row["index"]]
        return bisrt.quality_body(rows, grade)

    def test_three_lines_ending_in_the_grade(self):
        block = srt.parse_srt(self._body([entry()], {1: "高"}))[0][2]
        self.assertEqual(block.split("\n"),
                         ["族語ASR結果：mikeriday anini",
                          "華語OCR字幕：今天主持",
                          "族華對應品質：高"])

    def test_no_translation_leaks_into_it(self):
        body = self._body([entry()], {1: "中"})
        self.assertNotIn("今天負責主持", body)
        self.assertNotIn("ailabs", body)

    def test_an_ungraded_entry_names_itself(self):
        with self.assertRaises(PipelineError) as caught:
            self._body([entry(index=12)], {})
        self.assertIn("條目 12", str(caught.exception))


class TestCoaxial(unittest.TestCase):
    def test_same_chain_rows_as_the_delivered_srt(self):
        # Delivered SRT and the bilingual renders both consume
        # chain_with_spans rows, so index count and timestamps line up
        # pair by pair (同軸 requirement).
        cues = [(10.0, 12.0, "第一句"), (12.0, 14.0, "第一句"),
                (20.0, 22.0, "第二句")]
        rows = assemble.chain_with_spans(cues)
        delivered = []
        for row in rows:
            delivered.append((row["srt_start"], row["srt_end"],
                              row["text"]))
        want = srt.parse_srt(srt.render_srt(delivered))

        bi = []
        for row in rows:
            item = entry(index=row["index"], subtitle=row["text"],
                         srt_start=row["srt_start"],
                         srt_end=row["srt_end"])
            bi.append(item)
        got = srt.parse_srt(bisrt.raw_body(bi))
        self.assertEqual(len(got), len(want))
        for a, b in zip(got, want):
            self.assertEqual((a[0], a[1]), (b[0], b[1]))


if __name__ == "__main__":
    unittest.main()
