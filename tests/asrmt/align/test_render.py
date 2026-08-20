"""align/render: the review SRT and the merged deliverable.

Both depend on translations and detection verdicts, so they belong to
the align extension -- the default pipeline stops at the raw SRT.
"""
import unittest

from scripts.asrmt.align import render
from scripts.srtlib import srt


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


class TestReviewRender(unittest.TestCase):
    def test_six_lines_in_the_agreed_order(self):
        body = render.review_body([entry()])
        block = srt.parse_srt(body)[0][2].split("\n")
        self.assertEqual(block, [
            "族語ASR結果：mikeriday anini",
            "華語OCR字幕翻譯成族語-ailabs：mikeriday kako",
            "華語OCR字幕翻譯成族語-claude：o mikeriday",
            "華語OCR字幕：今天主持",
            "族語ASR結果翻譯華語-ailabs：今天負責主持",
            "族語ASR結果翻譯華語-claude：今天由我主持",
        ])

    def test_no_speech_entry_keeps_prefixes_and_subtitle_lines(self):
        row = entry(formosan="", zh_ailabs="", zh_claude="")
        block = srt.parse_srt(render.review_body([row]))[0][2].split("\n")
        self.assertEqual(block[0], "族語ASR結果：")
        self.assertEqual(block[3], "華語OCR字幕：今天主持")
        self.assertEqual(block[4], "族語ASR結果翻譯華語-ailabs：")
        self.assertEqual(block[5], "族語ASR結果翻譯華語-claude：")

    def test_timestamps_come_from_the_chain_display_window(self):
        got = srt.parse_srt(render.review_body([entry()]))
        self.assertEqual((got[0][0], got[0][1]), (9.5, 12.5))


class TestCompleteRender(unittest.TestCase):
    def test_lines_come_only_from_source_material(self):
        # the deliverable carries no machine translation at all: the
        # Formosan line is the ASR words joined in time order, the
        # Chinese line is the delivered subtitle verbatim
        body = render.complete_body([entry()])
        block = srt.parse_srt(body)[0][2].split("\n")
        self.assertEqual(block, ["族語：mikeriday anini",
                                 "華語：今天主持"])

    def test_no_translation_text_leaks_into_the_deliverable(self):
        row = entry(zh_ailabs="翻譯機的話", zh_claude="另一台翻譯機的話")
        body = render.complete_body([row])
        self.assertNotIn("翻譯機", body)

    def test_a_block_with_a_problem_merges_into_one_sentence(self):
        # 使用者裁定：ok 維持逐條；mismatch 等依語意句塊整併——
        # 華語＝塊內字幕原文依序連接、族語＝塊內辨識詞依時序連接
        rows = [entry(index=1, formosan="niyaroʼ o sapi",
                      subtitle="花蓮原山奇美橋"),
                entry(index=2, formosan="kaʼayaw o kalingadan",
                      subtitle="可以說是當地居民",
                      srt_start=12.5, srt_end=15.0)]
        verdicts = {1: "offset", 2: "mismatch"}
        blocks = {1: 0, 2: 0}
        got = srt.parse_srt(render.complete_body(rows, verdicts, blocks))
        self.assertEqual(len(got), 1)
        self.assertEqual((got[0][0], got[0][1]), (9.5, 15.0))
        lines = got[0][2].split("\n")
        self.assertEqual(lines[0],
                         "族語：niyaroʼ o sapi kaʼayaw o kalingadan")
        self.assertEqual(lines[1], "華語：花蓮原山奇美橋可以說是當地居民")

    def test_an_all_ok_block_keeps_its_entries_separate(self):
        rows = [entry(index=1), entry(index=2, srt_start=12.5,
                                      srt_end=15.0)]
        verdicts = {1: "ok", 2: "ok"}
        blocks = {1: 0, 2: 0}
        got = srt.parse_srt(render.complete_body(rows, verdicts, blocks))
        self.assertEqual(len(got), 2)

    def test_merge_never_reorders_source_material(self):
        rows = [entry(index=1, formosan="早 講的", subtitle="前段"),
                entry(index=2, formosan="晚 講的", subtitle="後段",
                      srt_start=12.5, srt_end=15.0)]
        verdicts = {1: "mismatch", 2: "mismatch"}
        blocks = {1: 0, 2: 0}
        body = render.complete_body(rows, verdicts, blocks)
        self.assertIn("族語：早 講的 晚 講的", body)
        self.assertIn("華語：前段後段", body)


if __name__ == "__main__":
    unittest.main()
