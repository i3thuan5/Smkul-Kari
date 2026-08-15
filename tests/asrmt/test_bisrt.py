"""bisrt: the default deliverable -- the two-line raw SRT.

Pins the asr-bilingual-srt spec: 族語/華語 lines built only from source
material, and coaxial timestamps with the delivered SRT (both render
through the same chain rows). The review and merged renders live in the
align extension and are pinned in tests/asrmt/align/test_render.py.
"""
import unittest

from scripts.asrmt import bisrt
from scripts.srtlib import assemble
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
