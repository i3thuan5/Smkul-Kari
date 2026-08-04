"""Two lessons pinned as regressions, both measured on the February batch.

1. No interpolation. Filling the cues between two confident anchors scored
   0/9 against hand reads -- a news programme almost always has something
   unscripted in the gap (a promo, a headline, an anchor link). resolve()
   must leave unmatched cues empty rather than share the script out.

2. No paragraph slicing. A cue that lands inside a narration paragraph can
   only be cut by character offset, and the cut lands mid-phrase --
   `000多種的植物種類` for `孕育出高達4000多種的植物種類`. Spans snapped as
   "slice" are dropped, not guessed.
"""
import json
import os
import tempfile
import unittest

from scripts.news import align
from tests.rtf.test_rtf_decode import big5_escapes, write_rtf


def make_work(tmp, texts):
    """A minimal work dir: cues.json + transcripts.json for `texts`."""
    work = os.path.join(tmp, "ep.work")
    os.makedirs(work)
    cues = []
    transcripts = {}
    for i, text in enumerate(texts):
        cues.append({"index": i + 1, "start": 10.0 + i * 5.0,
                     "end": 13.0 + i * 5.0})
        transcripts[str(i + 1)] = {"han": text}
    with open(os.path.join(work, "cues.json"), "w",
              encoding="utf-8") as handle:
        json.dump({"cues": cues}, handle, ensure_ascii=False)
    with open(os.path.join(work, "transcripts.json"), "w",
              encoding="utf-8") as handle:
        json.dump(transcripts, handle, ensure_ascii=False)
    return work


def make_script(tmp, lines):
    folder = os.path.join(tmp, "script")
    os.makedirs(folder)
    parts = []
    for text in lines:
        parts.append(big5_escapes(text))
    write_rtf(folder, "稿.rtf", "{\\rtf1 %s}" % "\\par ".join(parts))
    return folder


class TestNoInterpolation(unittest.TestCase):
    def test_cue_between_anchors_stays_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = make_work(tmp, [
                "春天的花開在山坡上面田野邊",       # anchor, in script
                "完全沒有出現在稿子裡的插播內容",   # unscripted middle cue
                "秋天的風吹過部落廣場的看台",       # anchor, in script
            ])
            folder = make_script(tmp, [
                "春天的花開在山坡上面田野邊",
                "夏天的雨落在稻田中間的水渠",       # script the middle never used
                "秋天的風吹過部落廣場的看台",
            ])
            records, size, filled = align.resolve(work, folder)

        self.assertEqual(filled, 0)
        self.assertEqual(records[0]["aligned"], "春天的花開在山坡上面田野邊")
        self.assertEqual(records[2]["aligned"], "秋天的風吹過部落廣場的看台")
        # the unscripted cue keeps its own text and stays unaligned
        self.assertEqual(records[1]["aligned"], "")
        self.assertEqual(records[1]["source"], "")

    def test_paragraph_slice_is_dropped_not_guessed(self):
        paragraph = ("這座森林的環境非常特殊經過了數萬年的演變"
                     "孕育出高達4000多種的植物種類在整個區域都很罕見"
                     "也吸引了許多研究人員前來調查")
        with tempfile.TemporaryDirectory() as tmp:
            # the cue read more characters than it matched, so the span is
            # short and would need slicing a paragraph to widen -- forbidden
            work = make_work(tmp, ["孕育出高達4000多種的植物種類真是了不起的自然"])
            folder = make_script(tmp, [paragraph])
            records, _, _ = align.resolve(work, folder)

        self.assertEqual(records[0]["aligned"], "")
        self.assertEqual(records[0]["source"], "")


if __name__ == "__main__":
    unittest.main()
