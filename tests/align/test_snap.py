"""snap(): widening a matched span to the unit the script stores; tidy()."""
import unittest

from scripts.news import align


def line(start, end, text=""):
    return {"start": start, "end": end, "text": text or "字" * (end - start)}


class TestSnap(unittest.TestCase):
    def test_full_length_span_is_left_exact(self):
        lines = [line(0, 20)]
        lo, hi, how = align.snap(lines, 2, 14, 12)
        self.assertEqual(how, "exact")
        self.assertEqual((lo, hi), (2, 14))

    def test_short_span_on_subtitle_lines_takes_whole_lines(self):
        # 沒有把它澈底 -> 沒有把它澈底澆熄: matching stopped early, but the
        # touched script lines are subtitle-sized, so take them whole
        lines = [line(0, 8), line(8, 16)]
        lo, hi, how = align.snap(lines, 2, 10, 14)
        self.assertEqual(how, "line")
        self.assertEqual((lo, hi), (0, 16))

    def test_short_span_in_a_paragraph_is_sliced(self):
        # one long narration line: the script does not record where the
        # subtitler broke it, so the span can only be grown by arithmetic
        lines = [line(0, 80)]
        lo, hi, how = align.snap(lines, 30, 40, 20)
        self.assertEqual(how, "slice")
        self.assertEqual(hi - lo, 20)

    def test_span_touching_no_line_is_left_alone(self):
        lines = [line(0, 10)]
        lo, hi, how = align.snap(lines, 50, 55, 12)
        self.assertEqual(how, "exact")
        self.assertEqual((lo, hi), (50, 55))


class TestTidy(unittest.TestCase):
    def test_lone_close_bracket_is_dropped(self):
        # slicing an interview cue routinely takes a lone `）` with it
        self.assertEqual(align.tidy("受訪者這麼說）"), "受訪者這麼說")

    def test_lone_open_bracket_is_dropped(self):
        self.assertEqual(align.tidy("（受訪者這麼說"), "受訪者這麼說")

    def test_matched_pair_is_kept(self):
        self.assertEqual(align.tidy("他（大聲）回答"), "他（大聲）回答")

    def test_internal_whitespace_is_collapsed(self):
        self.assertEqual(align.tidy("前半  後半"), "前半 後半")


if __name__ == "__main__":
    unittest.main()
