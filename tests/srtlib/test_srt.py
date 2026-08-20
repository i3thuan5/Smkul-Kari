"""SRT timestamps, rendering, and the render/parse round trip."""
import unittest

from scripts.srtlib import srt


class TestSrtFormat(unittest.TestCase):
    def test_timestamp_formatting(self):
        self.assertEqual(srt.srt_timestamp(0), "00:00:00,000")
        self.assertEqual(srt.srt_timestamp(1.5), "00:00:01,500")
        self.assertEqual(srt.srt_timestamp(3661.234), "01:01:01,234")
        self.assertEqual(srt.srt_timestamp(-5), "00:00:00,000")

    def test_timestamp_rounds_not_truncates(self):
        self.assertEqual(srt.srt_timestamp(0.0006), "00:00:00,001")

    def test_render_skips_empty_text(self):
        body = srt.render_srt([(0, 1, "hi"), (1, 2, "   "),
                               (2, 3, "there")])
        self.assertIn("1\n", body)
        self.assertIn("2\n", body)
        self.assertNotIn("3\n", body)

    def test_render_parse_round_trip(self):
        entries = [(0.5, 2.25, "Ati han ako"),
                   (2.25, 4.0, "line one\nline two")]
        got = srt.parse_srt(srt.render_srt(entries))
        self.assertEqual(len(got), 2)
        for original, parsed in zip(entries, got):
            self.assertAlmostEqual(original[0], parsed[0], places=3)
            self.assertAlmostEqual(original[1], parsed[1], places=3)
            self.assertEqual(original[2], parsed[2])


if __name__ == "__main__":
    unittest.main()
