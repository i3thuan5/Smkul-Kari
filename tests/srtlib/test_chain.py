"""chain_with_spans: the assembly chain, keeping each final entry's true
window (post-merge, pre-gap/pad) alongside its display window.

This is what makes the bilingual SRT coaxial with the delivered one: both
sides render from the same chain, and the speech side projects words into
the true windows (asr-bilingual-srt spec, 同軸 requirement).
"""
import unittest

from scripts.srtlib import assemble
from scripts.srtlib import srt


def old_chain(entries, merge_gap=1.0, min_gap=0.04, duration=None):
    """The pre-refactor pipeline, kept here as the behaviour oracle."""
    out = assemble.merge_repeats(entries, merge_gap)
    out = assemble.apply_gap_rules(out, min_gap)
    out = assemble.pad_edges(out, duration=duration)
    return out


class TestSpans(unittest.TestCase):
    def test_true_window_is_the_merged_span_before_padding(self):
        entries = [(10.0, 12.0, "同一句"), (12.0, 14.0, "同一句"),
                   (20.0, 22.0, "另一句")]
        rows = assemble.chain_with_spans(entries)
        self.assertEqual(len(rows), 2)
        self.assertEqual((rows[0]["true_start"], rows[0]["true_end"]),
                         (10.0, 14.0))
        self.assertEqual((rows[1]["true_start"], rows[1]["true_end"]),
                         (20.0, 22.0))

    def test_display_window_is_padded_but_true_window_is_not(self):
        rows = assemble.chain_with_spans([(10.0, 12.0, "字")])
        self.assertEqual((rows[0]["true_start"], rows[0]["true_end"]),
                         (10.0, 12.0))
        self.assertEqual((rows[0]["srt_start"], rows[0]["srt_end"]),
                         (9.5, 12.5))

    def test_indexes_are_sequential_from_one(self):
        entries = [(1.0, 2.0, "一"), (3.0, 4.0, "二"), (5.0, 6.0, "三")]
        rows = assemble.chain_with_spans(entries)
        got = []
        for row in rows:
            got.append(row["index"])
        self.assertEqual(got, [1, 2, 3])


class TestRenderEquality(unittest.TestCase):
    def test_render_from_spans_matches_the_old_pipeline_byte_for_byte(self):
        entries = [(1.0, 2.0, "一"), (2.0, 4.0, "二"), (4.0, 6.0, "二"),
                   (9.0, 11.0, "三"), (11.05, 13.0, "四")]
        want = srt.render_srt(old_chain(entries, duration=15.0))
        rows = assemble.chain_with_spans(entries, duration=15.0)
        rendered = []
        for row in rows:
            rendered.append((row["srt_start"], row["srt_end"], row["text"]))
        self.assertEqual(srt.render_srt(rendered), want)


if __name__ == "__main__":
    unittest.main()
