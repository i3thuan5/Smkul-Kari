"""The two sides must agree about time, whenever both have delivered.

The speech side projects its words onto the picture side's timeline, so
`2-asr/3-srt-raw/` and `1-ocr/3-srt/` are supposed to carry the same
entries with the same timestamps -- same count, same index, same
start/end. Nothing checked it: `rebuild --verify` rebuilds the picture
side and never opens the speech side at all, so 47 of the delivered
episodes drifted apart and stayed that way for two months.

Two rules, and they are not symmetrical (使用者裁定 2026-09-03):

  both sides delivered   the sequences must match, and a mismatch is an
                         error to fix, not a warning. Two files claiming
                         different timings for one episode is a
                         contradiction, and nothing downstream can tell
                         which one is right.
  only the picture side  fine. The speech side is its own line running at
                         its own pace, and `smkul.csv` already says how
                         far it has got. Calling "not done yet" an error
                         makes the check red for weeks at a time, and a
                         permanently red check is one nobody reads.

比較ê是 (index, start, end)，毋是逐 byte——族語彼逝ê文字是辨識器出ê，
本底就袂佮字幕仝款。
"""
import os
import tempfile
import unittest

from scripts.news import coaxial

PICTURE = ("1\n00:00:01,000 --> 00:00:02,000\n甲\n\n"
           "2\n00:00:03,000 --> 00:00:04,000\n乙\n")
SPEECH = ("1\n00:00:01,000 --> 00:00:02,000\n族語：a\n華語：甲\n\n"
          "2\n00:00:03,000 --> 00:00:04,000\n族語：b\n華語：乙\n")
SHIFTED = ("1\n00:00:01,000 --> 00:00:02,000\n族語：a\n華語：甲\n\n"
           "2\n00:00:03,500 --> 00:00:04,000\n族語：b\n華語：乙\n")
SHORTER = "1\n00:00:01,000 --> 00:00:02,000\n族語：a\n華語：甲\n"


class Fixture(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = tmp.name

    def _srt(self, name, text):
        path = os.path.join(self.root, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path


class TestBothSidesDelivered(Fixture):
    def test_matching_timings_are_no_complaint(self):
        picture = self._srt("p.srt", PICTURE)
        speech = self._srt("s.srt", SPEECH)
        self.assertIsNone(coaxial.compare(picture, speech))

    def test_a_shifted_timestamp_is_reported_with_the_entry(self):
        picture = self._srt("p.srt", PICTURE)
        speech = self._srt("s.srt", SHIFTED)
        problem = coaxial.compare(picture, speech)
        self.assertIsNotNone(problem)
        self.assertIn("2", problem)

    def test_a_different_entry_count_is_reported(self):
        picture = self._srt("p.srt", PICTURE)
        speech = self._srt("s.srt", SHORTER)
        self.assertIsNotNone(coaxial.compare(picture, speech))

    def test_the_text_lines_are_not_compared(self):
        """族語彼逝是辨識器出ê，佮字幕本底就無仝，比伊會逐集攏紅。"""
        picture = self._srt("p.srt", PICTURE)
        speech = self._srt("s.srt", SPEECH.replace("族語：a", "族語：zzz"))
        self.assertIsNone(coaxial.compare(picture, speech))

    def test_it_names_the_first_entry_that_differs(self):
        picture = self._srt("p.srt", PICTURE)
        speech = self._srt("s.srt", SHIFTED)
        self.assertIn("條目 2", coaxial.compare(picture, speech))


class TestOnlyThePictureSide(Fixture):
    def test_a_missing_speech_side_is_not_a_problem(self):
        picture = self._srt("p.srt", PICTURE)
        missing = os.path.join(self.root, "nope.srt")
        self.assertIsNone(coaxial.compare(picture, missing))

    def test_and_it_does_not_warn_either(self):
        """語音側是家己ê一條線，猶未做袂使算做錯，嘛袂使報警告——
        規禮拜攏紅ê檢查無人會去看。"""
        picture = self._srt("p.srt", PICTURE)
        missing = os.path.join(self.root, "nope.srt")
        self.assertEqual(coaxial.problems([("x", picture, missing)]), [])


class TestSweep(Fixture):
    def test_it_collects_every_episode_that_differs(self):
        picture = self._srt("p.srt", PICTURE)
        good = self._srt("good.srt", SPEECH)
        bad = self._srt("bad.srt", SHIFTED)
        got = coaxial.problems([("ok", picture, good),
                                ("drifted", picture, bad)])
        self.assertEqual(len(got), 1)
        self.assertIn("drifted", got[0])


if __name__ == "__main__":
    unittest.main()
