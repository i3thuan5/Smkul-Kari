"""Contact sheets named by when they start, not by what number they are.

`sheet_003.png` reads like an identifier and is not one: cue numbers move
whenever a cue is split (`safe_resplit`, `rescan_band`, `split_cue`), the
sheets are rebuilt from the new numbering, and sheet three is then a
different piece of programme than it was. Measured on strips, which had
the same problem: **46,665 of 75,290 files carried a number that was not
their cue's** -- and the README had recorded strip numbers as cue numbers,
which would have edited cues a hundred rows away with nothing reporting it.

A start time does not move when some other cue is split, and `t00551400`
does not read as an ordinal, so nobody reaches for it as one. Same shape
as `stripname.of`, minus the line: a sheet holds several cues and several
lines, so the only thing it can be named after is where it begins.

`sheets.json` is still the one place that maps a sheet to its cues -- that
was true under either naming.
"""
import unittest

from scripts.ocr import stripname
from scripts.errors import PipelineError


class TestSheetName(unittest.TestCase):
    def test_it_is_the_start_time_in_milliseconds(self):
        self.assertEqual(stripname.sheet_of(551.4), "t00551400.png")

    def test_zero_is_padded_not_empty(self):
        self.assertEqual(stripname.sheet_of(0), "t00000000.png")

    def test_a_late_start_still_fits_eight_digits(self):
        """一齣 48 分鐘ê節目到 2,880,000 毫秒，八位數夠額。"""
        self.assertEqual(stripname.sheet_of(2879.999), "t02879999.png")

    def test_it_rounds_rather_than_truncates(self):
        self.assertEqual(stripname.sheet_of(1.2345), "t00001234.png")
        self.assertEqual(stripname.sheet_of(1.2355), "t00001236.png")

    def test_a_negative_start_is_refused(self):
        with self.assertRaises(PipelineError):
            stripname.sheet_of(-1)

    def test_two_sheets_starting_apart_get_different_names(self):
        self.assertNotEqual(stripname.sheet_of(10.0),
                            stripname.sheet_of(10.2))


class TestTellingTheOldNamingApart(unittest.TestCase):
    """遷移愛分會出佗一種——兩種攏會佇磁碟頂懸khiā一站仔。"""

    def test_the_old_sheet_naming_is_recognised(self):
        self.assertTrue(stripname.is_ordinal_sheet("sheet_003.png"))

    def test_a_time_named_sheet_is_not(self):
        self.assertFalse(stripname.is_ordinal_sheet("t00551400.png"))

    def test_a_strip_is_not_a_sheet(self):
        self.assertFalse(stripname.is_ordinal_sheet("00844_han.png"))


if __name__ == "__main__":
    unittest.main()
