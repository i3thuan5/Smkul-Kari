"""The sheet→TSV→import loop: transcript parsing and glossary tokens."""
import os
import tempfile
import unittest

import numpy as np
from PIL import Image

from scripts.ocr import cuelib
from scripts.ocr import sheets
from scripts.ocr import transcripts


class TestParseTranscriptTsv(unittest.TestCase):
    def test_two_column_uses_default_line(self):
        got, errors = transcripts.parse_transcript_tsv("3\thello", "han")
        self.assertEqual(errors, [])
        self.assertEqual(got, {"3": {"han": "hello"}})

    def test_three_column_names_the_line(self):
        got, errors = transcripts.parse_transcript_tsv(
            "7\tami\tAti han ako\n7\than\t我就請", "han")
        self.assertEqual(errors, [])
        self.assertEqual(got["7"]["ami"], "Ati han ako")
        self.assertEqual(got["7"]["han"], "我就請")

    def test_comments_and_blanks_ignored(self):
        got, errors = transcripts.parse_transcript_tsv(
            "# a note\n\n  \n1\ttext", "han")
        self.assertEqual(errors, [])
        self.assertEqual(list(got), ["1"])

    def test_bad_index_is_reported_not_swallowed(self):
        got, errors = transcripts.parse_transcript_tsv("x\ttext", "han")
        self.assertEqual(got, {})
        self.assertEqual(len(errors), 1)

    def test_missing_text_column_is_reported(self):
        _, errors = transcripts.parse_transcript_tsv("5", "han")
        self.assertEqual(len(errors), 1)

    def test_text_may_contain_tabs_after_line_name(self):
        got, _ = transcripts.parse_transcript_tsv("1\than\ta\tb", "han")
        self.assertEqual(got["1"]["han"], "a\tb")


class TestGlossaryTokens(unittest.TestCase):
    """Words later batches are most likely to spell differently."""

    def test_marks_are_collected(self):
        got = transcripts.glossary_tokens("nga'ay ho^ i Po:long")
        self.assertIn("nga'ay", got)
        self.assertIn("ho^", got)
        self.assertIn("Po:long", got)

    def test_proper_nouns_are_collected(self):
        got = transcripts.glossary_tokens("ci Kinci ato Angcoh")
        self.assertIn("Kinci", got)
        self.assertIn("Angcoh", got)

    def test_plain_lowercase_words_are_ignored(self):
        got = transcripts.glossary_tokens("kako ato mita a demak")
        self.assertEqual(got, [])

    def test_trailing_punctuation_stripped(self):
        self.assertIn("Aray", transcripts.glossary_tokens("Aray."))

    def test_single_characters_ignored(self):
        self.assertEqual(transcripts.glossary_tokens("i o a"), [])

    def test_double_quote_word_is_collected(self):
        got = transcripts.glossary_tokens("to 'a\"iyalaeho: a kamok")
        self.assertIn("'a\"iyalaeho:", got)


if __name__ == "__main__":
    unittest.main()


class TestSlotCrop(unittest.TestCase):
    """Which half of the band this cue's line is in, if it can be told.

    News puts each line in one of two fixed slots inside the band, so half
    of every strip is blank -- measured over 27 episodes, 79.8% of lines sit
    in the lower slot and 10.8% in the upper. Dropping the empty half is
    what fits more cues on one Claude Vision input sheet.

    The fallback is the whole point of the ratio. It is NOT there for "both
    slots hold subtitle" -- scanning 3,339 strips found no such case, and
    the layout does not produce one. It is there for the picture's own text
    competing with the subtitle: 051's cue 223 has a red banner reading
    屏東縣瑪家鄉舊筏灣 in the upper slot and the actual line in the lower,
    at a ratio of 1.10. Crop to the wrong slot there and the subtitle is
    gone, and Claude Vision is told to leave banners blank, so it comes back
    as an empty row that looks like an ordinary silent shot.
    """

    SLOTS = {"split": 65, "pad": 6, "min_ratio": 2.0, "min_ink": 200}

    def _mask(self, upper_ink, lower_ink, height=122, width=400):
        mask = np.zeros((height, width), dtype=bool)
        if upper_ink:
            mask[10:10 + max(upper_ink // width, 1), :upper_ink] = True
        if lower_ink:
            mask[80:80 + max(lower_ink // width, 1), :lower_ink] = True
        return mask

    def _ink(self, upper, lower, height=122, width=400):
        mask = np.zeros((height, width), dtype=bool)
        rows_up = max(upper // width, 0)
        rows_low = max(lower // width, 0)
        if rows_up:
            mask[10:10 + rows_up, :] = True
        if rows_low:
            mask[80:80 + rows_low, :] = True
        return mask

    def test_line_in_the_upper_slot_crops_to_it(self):
        got = sheets.slot_crop(self._ink(4000, 0), self.SLOTS)
        self.assertEqual(got, (0, 71))

    def test_line_in_the_lower_slot_crops_to_it(self):
        got = sheets.slot_crop(self._ink(0, 8000), self.SLOTS)
        self.assertEqual(got, (59, 122))

    def test_comparable_ink_in_both_slots_falls_back(self):
        self.assertIsNone(sheets.slot_crop(self._ink(6400, 8000),
                                           self.SLOTS))

    def test_too_little_ink_to_tell_falls_back(self):
        self.assertIsNone(sheets.slot_crop(self._ink(80, 40), self.SLOTS))

    def test_no_slots_declared_means_no_crop(self):
        self.assertIsNone(sheets.slot_crop(self._ink(4000, 0), None))
        self.assertIsNone(sheets.slot_crop(self._ink(4000, 0), {}))

    def test_a_split_outside_the_strip_is_ignored(self):
        slots = dict(self.SLOTS, split=400)
        self.assertIsNone(sheets.slot_crop(self._ink(4000, 0), slots))


class TestUndecidedShare(unittest.TestCase):
    """How often this episode could not tell -- reported, never acted on.

    Measured normal range, blank strips excluded: median 2.9%, p90 9.1%,
    highest 12.5%. A number well above that says the band has drifted up or
    down across the split, which is the one layout change nothing else
    notices: it passes the band check (the dialogue plateau is still inside
    the region) and it passes the column check (the right edge has not
    moved). Blank strips are excluded because how much of an episode is
    silent has nothing to do with its layout -- counting them turned a 3.5
    point spread into 5.7.
    """

    def test_share_ignores_the_blank_strips(self):
        self.assertAlmostEqual(sheets.undecided_share(3, 97, 40), 0.03)

    def test_an_episode_with_nothing_to_decide_is_zero(self):
        self.assertEqual(sheets.undecided_share(0, 0, 12), 0.0)


class TestCueBlocksCropping(unittest.TestCase):
    """The crop over real strips: rows by slot, columns as before.

    The row crop must never take a subtitle pixel with it, and the column
    crop must stay the "any ink at all" rule it has always been. Both are
    checked against the mask rather than by eye, because the failure looks
    like an ordinary short line to everyone downstream.
    """

    SLOTS = {"split": 65, "pad": 6, "min_ratio": 2.0, "min_ink": 200}

    def _workdir(self, upper_rows, lower_rows):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        os.makedirs(os.path.join(tmp.name, "strips"))
        frame = np.full((122, 400, 3), 20, dtype=np.uint8)
        for lo, hi in (upper_rows, lower_rows):
            if hi > lo:
                frame[lo:hi, 120:360] = 255
        Image.fromarray(frame).save(
            os.path.join(tmp.name, "strips", "a.png"))
        manifest = {
            "lines": [{"name": "han", "y": 0, "h": 122}],
            "mask": {},
            "cues": [{"index": 1, "start": 3.0, "end": 5.0,
                      "images": {"han": os.path.join("strips", "a.png")}}],
        }
        return tmp.name, manifest

    def _tile(self, upper, lower, **kwargs):
        workdir, manifest = self._workdir(upper, lower)
        spec = cuelib.MaskSpec.from_dict({})
        blocks, undecided, decided, blank = sheets._cue_blocks(
            workdir, manifest, spec, **kwargs)
        return blocks[0][2][0], (undecided, decided, blank)

    def test_a_lower_line_loses_the_empty_upper_half(self):
        tile, counts = self._tile((0, 0), (80, 96), row_slots=self.SLOTS)
        self.assertEqual(tile.height, 122 - 59)
        self.assertEqual(counts, (0, 1, 0))

    def test_every_lit_pixel_survives_the_crop(self):
        tile, _ = self._tile((0, 0), (80, 96), row_slots=self.SLOTS)
        spec = cuelib.MaskSpec.from_dict({})
        kept = int(cuelib.text_mask(np.asarray(tile), spec).sum())
        whole, _ = self._tile((0, 0), (80, 96))
        full = int(cuelib.text_mask(np.asarray(whole), spec).sum())
        self.assertEqual(kept, full)

    def test_without_slots_the_tile_keeps_the_whole_band(self):
        tile, counts = self._tile((0, 0), (80, 96))
        self.assertEqual(tile.height, 122)
        self.assertEqual(counts, (0, 0, 0))

    def test_ink_in_both_slots_keeps_the_whole_band(self):
        tile, counts = self._tile((20, 40), (80, 100), row_slots=self.SLOTS)
        self.assertEqual(tile.height, 122)
        self.assertEqual(counts, (1, 0, 0))

    def test_columns_are_still_trimmed_to_any_ink(self):
        tile, _ = self._tile((0, 0), (80, 96), row_slots=self.SLOTS)
        self.assertLess(tile.width, 400)
        self.assertGreaterEqual(tile.width, 240)
