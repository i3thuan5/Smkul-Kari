#!/usr/bin/env python3
"""Correctness checks for the burned-in-subtitle pipeline.

Two layers:

* unit tests over the deterministic pieces (morphology, mask distance, cue
  segmentation, SRT formatting) driven by hand-built arrays, so a failure
  points at one function;
* an end-to-end round trip that burns a known SRT into a synthetic 1080p
  video, runs the real pipeline over it, and diffs the recovered cues against
  the ground truth. This is the only way to check the timing maths against
  something other than itself.

    python3 selftest.py            # everything
    python3 selftest.py --quick    # unit tests only (no ffmpeg encode)
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cuelib  # noqa: E402
import subs2srt  # noqa: E402

CJK_FONT = "Noto Sans CJK TC"


# ------------------------------------------------------------ unit tests


class TestMorphology(unittest.TestCase):
    def test_dilate_grows_by_radius(self):
        mask = np.zeros((9, 9), dtype=bool)
        mask[4, 4] = True
        grown = cuelib.dilate(mask, 5)
        self.assertEqual(int(grown.sum()), 25)
        self.assertTrue(grown[2:7, 2:7].all())

    def test_dilate_noop_for_size_below_three(self):
        mask = np.zeros((4, 4), dtype=bool)
        mask[1, 1] = True
        self.assertTrue((cuelib.dilate(mask, 1) == mask).all())

    def test_erode_removes_thin_strokes(self):
        mask = np.zeros((11, 11), dtype=bool)
        mask[5, :] = True            # a 1px horizontal stroke
        self.assertEqual(int(cuelib.erode(mask, 3).sum()), 0)

    def test_erode_keeps_blob_interior(self):
        mask = np.zeros((11, 11), dtype=bool)
        mask[2:9, 2:9] = True
        eroded = cuelib.erode(mask, 3)
        self.assertTrue(eroded[3:8, 3:8].all())
        self.assertFalse(eroded[2, 2])

    def test_dilate_does_not_wrap_edges(self):
        mask = np.zeros((5, 5), dtype=bool)
        mask[0, 0] = True
        grown = cuelib.dilate(mask, 3)
        self.assertFalse(grown[4, 4])
        self.assertEqual(int(grown.sum()), 4)


class TestCropChain(unittest.TestCase):
    """Every crop must carry exact=1, or ffmpeg re-rounds it behind us."""

    def test_chain_orders_args_as_w_h_x_y(self):
        self.assertEqual(cuelib.crop_chain((10, 20, 300, 40)),
                         "crop=300:40:10:20:exact=1")

    def test_extra_filters_are_appended(self):
        self.assertEqual(cuelib.crop_chain((0, 0, 2, 2), "format=rgb24"),
                         "crop=2:2:0:0:exact=1,format=rgb24")

    def test_exact_flag_is_always_present(self):
        for box in ((0, 0, 1920, 138), (439, 845, 1044, 107)):
            self.assertIn("exact=1", cuelib.crop_chain(box))

    def test_odd_dimensions_are_passed_through_verbatim(self):
        # exact=1 means we may ask for an odd box and get exactly it back
        self.assertEqual(cuelib.crop_chain((1, 3, 1044, 107)),
                         "crop=1044:107:1:3:exact=1")


class TestNormalizeRegion(unittest.TestCase):
    """Belt-and-braces beside exact=1, for older ffmpeg without the flag."""

    def test_odd_values_snap_down_to_even(self):
        self.assertEqual(cuelib.normalize_region((439, 845, 1044, 107)),
                         [438, 844, 1044, 106])

    def test_even_values_are_untouched(self):
        self.assertEqual(cuelib.normalize_region((0, 876, 1920, 138)),
                         [0, 876, 1920, 138])

    def test_clipped_to_frame(self):
        got = cuelib.normalize_region((1900, 1000, 400, 400), 1920, 1080)
        self.assertEqual(got, [1900, 1000, 20, 80])

    def test_never_returns_zero_extent(self):
        got = cuelib.normalize_region((0, 0, 1, 1), 1920, 1080)
        self.assertEqual(got[2] % 2, 0)
        self.assertEqual(got[3] % 2, 0)
        self.assertGreaterEqual(got[2], 2)
        self.assertGreaterEqual(got[3], 2)

    def test_negative_origin_is_clamped(self):
        self.assertEqual(cuelib.normalize_region((-5, -3, 100, 100))[:2],
                         [0, 0])

    def test_all_outputs_are_even(self):
        for box in ((1, 3, 5, 7), (439, 845, 1044, 107), (11, 0, 3, 999)):
            got = cuelib.normalize_region(box, 1920, 1080)
            for value in got:
                self.assertEqual(value % 2, 0, "%s -> %s" % (box, got))


class TestMaskDistance(unittest.TestCase):
    def test_identical_is_zero(self):
        mask = np.zeros((8, 8), dtype=bool)
        mask[2:5, 2:5] = True
        self.assertEqual(cuelib.mask_distance(mask, mask.copy()), 0.0)

    def test_disjoint_is_one(self):
        a = np.zeros((8, 8), dtype=bool)
        b = np.zeros((8, 8), dtype=bool)
        a[0:3, 0:3] = True
        b[5:8, 5:8] = True
        self.assertEqual(cuelib.mask_distance(a, b), 1.0)

    def test_both_empty_is_zero(self):
        empty = np.zeros((4, 4), dtype=bool)
        self.assertEqual(cuelib.mask_distance(empty, empty), 0.0)

    def test_half_overlap(self):
        a = np.zeros((1, 4), dtype=bool)
        b = np.zeros((1, 4), dtype=bool)
        a[0, 0:2] = True
        b[0, 1:3] = True
        # union 3, symmetric difference 2
        self.assertAlmostEqual(cuelib.mask_distance(a, b), 2.0 / 3.0)


class TestTextMask(unittest.TestCase):
    def _canvas(self, colour, size=(60, 60)):
        return np.full((size[0], size[1], 3), colour, dtype=np.uint8)

    def test_outlined_glyph_is_kept(self):
        frame = self._canvas(30)                 # dark background
        frame[28:32, 10:50] = 255                # white stroke on it
        spec = cuelib.MaskSpec()
        mask = cuelib.text_mask(frame, spec)
        self.assertGreater(int(mask.sum()), 100)

    def test_large_flat_white_is_rejected(self):
        frame = self._canvas(255)                # nothing but white
        spec = cuelib.MaskSpec()
        self.assertEqual(int(cuelib.text_mask(frame, spec).sum()), 0)

    def test_yellow_band_is_rejected_but_glyph_is_not(self):
        frame = np.zeros((60, 60, 3), dtype=np.uint8)
        frame[:, :] = (255, 220, 40)             # saturated yellow band
        spec = cuelib.MaskSpec(outline=False)
        self.assertEqual(int(cuelib.text_mask(frame, spec).sum()), 0)
        frame[28:32, 10:50] = 255
        self.assertEqual(int(cuelib.text_mask(frame, spec).sum()), 4 * 40)

    def test_luma_matches_bt601(self):
        frame = np.zeros((1, 1, 3), dtype=np.uint8)
        frame[0, 0] = (255, 255, 255)
        self.assertGreaterEqual(int(cuelib.luma_of(frame)[0, 0]), 250)
        frame[0, 0] = (0, 0, 0)
        self.assertEqual(int(cuelib.luma_of(frame)[0, 0]), 0)


class TestRegionFromProfile(unittest.TestCase):
    """Guard the profile->crop-box arithmetic in detect_band.

    The bug this pins: the candidate loop used `height` for a band's height,
    shadowing the 1080 frame height, so `y1 = min(top + hi + pad, height)`
    clamped the box down to nothing. Detection itself was fine -- the ranked
    candidates printed correctly -- which is exactly why nothing caught it.
    """

    WIDTH = 1920
    HEIGHT = 1080
    TOP = 594

    def _profiles(self):
        rows = np.zeros(self.HEIGHT - self.TOP, dtype=np.float64)
        # strongest band, but deliberately NOT the last one in row order
        rows[300:350] = 100.0
        # a weaker, shorter band below it -- the last loop iteration, and
        # the value that used to leak out and clamp the result
        rows[360:400] = 50.0
        cols = np.zeros(self.WIDTH, dtype=np.float64)
        cols[100:1800] = 10.0
        return rows, cols

    def test_box_covers_the_strongest_band(self):
        rows, cols = self._profiles()
        region, _ = subs2srt.region_from_profile(
            rows, cols, self.TOP, self.WIDTH, self.HEIGHT)
        x, y, w, h = region
        self.assertEqual(y, self.TOP + 300 - 6)
        self.assertEqual(h, 50 + 2 * 6)

    def test_box_is_not_clamped_by_a_later_shorter_band(self):
        rows, cols = self._profiles()
        region, _ = subs2srt.region_from_profile(
            rows, cols, self.TOP, self.WIDTH, self.HEIGHT)
        # the trailing band is 40px tall; a collapsed box would be <= that
        self.assertGreater(region[3], 40)

    def test_ranked_candidates_are_ordered_by_weight(self):
        rows, cols = self._profiles()
        _, ranked = subs2srt.region_from_profile(
            rows, cols, self.TOP, self.WIDTH, self.HEIGHT)
        self.assertEqual(len(ranked), 2)
        self.assertEqual(ranked[0]["y"], self.TOP + 300)
        self.assertGreater(ranked[0]["weight"], ranked[1]["weight"])

    def test_box_stays_inside_the_frame(self):
        rows = np.zeros(self.HEIGHT - self.TOP, dtype=np.float64)
        rows[-40:] = 100.0                    # band flush with the bottom
        cols = np.zeros(self.WIDTH, dtype=np.float64)
        cols[:] = 10.0
        region, _ = subs2srt.region_from_profile(
            rows, cols, self.TOP, self.WIDTH, self.HEIGHT)
        self.assertLessEqual(region[1] + region[3], self.HEIGHT)
        self.assertLessEqual(region[0] + region[2], self.WIDTH)

    def test_collapsed_box_is_refused_rather_than_returned(self):
        rows, cols = self._profiles()
        with self.assertRaises(RuntimeError):
            # a frame height smaller than the band forces the collapse the
            # shadowing bug used to cause, and it must not pass silently
            subs2srt.region_from_profile(rows, cols, self.TOP,
                                         self.WIDTH, 40)


class TestBandPresence(unittest.TestCase):
    """Titles and credit rolls must not be mistaken for subtitles."""

    PROBE = {"x": 0, "w": 60, "min_saturation": 60}

    def _band(self):
        frame = np.zeros((40, 200, 3), dtype=np.uint8)
        frame[:, :] = (247, 190, 117)          # the orange/yellow bar
        return frame

    def _footage(self):
        frame = np.zeros((40, 200, 3), dtype=np.uint8)
        frame[:, :] = (75, 77, 100)            # a dull, near-grey shot
        return frame

    def test_saturated_band_counts_as_present(self):
        self.assertTrue(cuelib.band_present(self._band(), self.PROBE))

    def test_desaturated_footage_counts_as_absent(self):
        self.assertFalse(cuelib.band_present(self._footage(), self.PROBE))

    def test_no_probe_always_present(self):
        self.assertTrue(cuelib.band_present(self._footage(), None))

    def test_mask_is_empty_when_band_is_gone(self):
        frame = self._footage()
        frame[18:24, 80:160] = 255             # white credit text
        spec = cuelib.MaskSpec(outline=False, band_probe=self.PROBE)
        self.assertEqual(int(cuelib.text_mask(frame, spec).sum()), 0)

    def test_same_text_is_kept_when_band_is_there(self):
        frame = self._band()
        frame[18:24, 80:160] = 255
        spec = cuelib.MaskSpec(outline=False, band_probe=self.PROBE)
        self.assertEqual(int(cuelib.text_mask(frame, spec).sum()), 6 * 80)

    def test_probe_survives_round_trip_through_dict(self):
        spec = cuelib.MaskSpec.from_dict({"band_probe": self.PROBE})
        self.assertEqual(spec.to_dict()["band_probe"], self.PROBE)


class TestSegmenter(unittest.TestCase):
    """Drive the segmenter with synthetic masks so timing is exact."""

    def _run(self, pattern, dt=0.2, **kwargs):
        options = {"min_ink": 10, "change": 0.35, "min_stable": 2,
                   "min_duration": 0.30}
        options.update(kwargs)
        seg = cuelib.Segmenter(frame_dt=dt, **options)
        frames = []
        for slot in pattern:
            frames.append(slot)
        for index, slot in enumerate(frames):
            mask = np.zeros((4, 40), dtype=bool)
            if slot is not None:
                mask[:, slot * 10:slot * 10 + 10] = True
            rgb = np.zeros((4, 40, 3), dtype=np.uint8)
            seg.feed(index * dt, rgb, mask)
        return seg.finish(len(frames) * dt)

    def test_single_cue_bounds(self):
        # blank, blank, A x5, blank, blank
        cues = self._run([None, None, 0, 0, 0, 0, 0, None, None])
        self.assertEqual(len(cues), 1)
        self.assertAlmostEqual(cues[0].start, 0.4, places=6)
        self.assertAlmostEqual(cues[0].end, 1.4, places=6)

    def test_two_cues_back_to_back(self):
        cues = self._run([None, 0, 0, 0, 1, 1, 1, None])
        self.assertEqual(len(cues), 2)
        self.assertAlmostEqual(cues[0].start, 0.2, places=6)
        self.assertAlmostEqual(cues[0].end, 0.8, places=6)
        self.assertAlmostEqual(cues[1].start, 0.8, places=6)
        self.assertAlmostEqual(cues[1].end, 1.4, places=6)

    def test_single_noisy_frame_does_not_split(self):
        # one stray frame mid-cue must not create a third cue
        cues = self._run([None, 0, 0, 0, 2, 0, 0, 0, None])
        self.assertEqual(len(cues), 1)
        self.assertAlmostEqual(cues[0].start, 0.2, places=6)

    def test_flash_shorter_than_min_duration_is_dropped(self):
        # min_stable=2 means a cue always spans at least 2 frames (0.4s
        # here), so min_duration only bites above that.
        cues = self._run([None, None, 0, 0, None, None, None],
                         min_duration=0.5)
        self.assertEqual(len(cues), 0)

    def test_flash_at_exactly_min_duration_is_kept(self):
        cues = self._run([None, None, 0, 0, None, None, None],
                         min_duration=0.4)
        self.assertEqual(len(cues), 1)

    def test_trailing_blank_ends_cue_before_eof(self):
        # one unconfirmed blank frame still marks where the text vanished
        cues = self._run([None, 0, 0, 0, None])
        self.assertEqual(len(cues), 1)
        self.assertAlmostEqual(cues[0].end, 0.8, places=6)

    def test_run_open_at_eof_is_closed(self):
        cues = self._run([None, 0, 0, 0, 0])
        self.assertEqual(len(cues), 1)
        self.assertAlmostEqual(cues[0].end, 1.0, places=6)

    def test_blank_gap_separates_cues(self):
        cues = self._run([0, 0, 0, None, None, 0, 0, 0])
        self.assertEqual(len(cues), 2)

    def test_identical_adjacent_text_cannot_be_split(self):
        """Documented limitation, pinned so it cannot regress silently.

        Two consecutive subtitles carrying identical pixels with no blank
        frame between them are indistinguishable from one long subtitle.
        """
        cues = self._run([None, 0, 0, 0, 0, 0, 0, None])
        self.assertEqual(len(cues), 1)


class TestMedianComposite(unittest.TestCase):
    """A moving occluder must not survive into the exported strip."""

    def _cue_with(self, frames):
        cue = cuelib.Cue(0.0, np.zeros((4, 4), dtype=bool), 1, frames[0], 0.0)
        for frame in frames[1:]:
            cue.add_sample(frame)
        return cue

    def test_moving_blob_is_removed(self):
        # glyph column stays bright in every frame; the blob moves each time
        frames = []
        for step in range(5):
            frame = np.full((4, 8, 3), 240, dtype=np.uint8)
            frame[:, 2] = 255                    # the "glyph"
            frame[:, step] = 10                  # occluder, different column
            frames.append(frame)
        out = self._cue_with(frames).composite()
        # the glyph column survives; no column is left dark
        self.assertGreater(int(out[:, 2].min()), 200)
        self.assertGreater(int(out.min()), 200)

    def test_static_content_is_preserved(self):
        frame = np.full((4, 8, 3), 128, dtype=np.uint8)
        frame[:, 3] = 255
        frames = []
        for _ in range(6):
            frames.append(frame.copy())
        out = self._cue_with(frames).composite()
        self.assertTrue((out == frame).all())

    def test_too_few_samples_falls_back_to_best_frame(self):
        frame = np.full((4, 8, 3), 77, dtype=np.uint8)
        cue = cuelib.Cue(0.0, np.zeros((4, 4), dtype=bool), 1, frame, 0.0)
        self.assertTrue((cue.composite() == frame).all())

    def test_sample_buffer_is_capped(self):
        frame = np.zeros((2, 2, 3), dtype=np.uint8)
        cue = cuelib.Cue(0.0, np.zeros((2, 2), dtype=bool), 1, frame, 0.0)
        for _ in range(200):
            cue.add_sample(frame)
        self.assertLessEqual(len(cue.samples), cuelib.Cue.MAX_SAMPLES)


class TestSegmenterCallback(unittest.TestCase):
    """Cue frames must be handed over and released, not accumulated."""

    def _feed(self, pattern, on_cue, dt=0.2):
        seg = cuelib.Segmenter(frame_dt=dt, min_ink=10, change=0.35,
                               min_stable=2, min_duration=0.30,
                               on_cue=on_cue)
        for index, slot in enumerate(pattern):
            mask = np.zeros((4, 40), dtype=bool)
            if slot is not None:
                mask[:, slot * 10:slot * 10 + 10] = True
            rgb = np.zeros((4, 40, 3), dtype=np.uint8)
            seg.feed(index * dt, rgb, mask)
        return seg, seg.finish(len(pattern) * dt)

    def test_callback_fires_once_per_cue_in_order(self):
        seen = []
        self._feed([None, 0, 0, 0, 1, 1, 1, None],
                   lambda n, c: seen.append((n, round(c.start, 2))))
        self.assertEqual(seen, [(1, 0.2), (2, 0.8)])

    def test_frames_released_after_callback(self):
        _, cues = self._feed([None, 0, 0, 0, None, None],
                             lambda n, c: None)
        self.assertEqual(len(cues), 1)
        self.assertIsNone(cues[0].best_rgb)

    def test_frames_kept_when_no_callback(self):
        seg = cuelib.Segmenter(frame_dt=0.2, min_ink=10, change=0.35,
                               min_stable=2, min_duration=0.30)
        for index in range(5):
            mask = np.zeros((4, 40), dtype=bool)
            if index > 0:
                mask[:, 0:10] = True
            seg.feed(index * 0.2, np.zeros((4, 40, 3), dtype=np.uint8), mask)
        cues = seg.finish(1.0)
        self.assertEqual(len(cues), 1)
        self.assertIsNotNone(cues[0].best_rgb)

    def test_dropped_short_cue_does_not_fire_callback(self):
        seen = []
        self._feed([None, None, 0, 0, None, None, None],
                   lambda n, c: seen.append(n))
        self.assertEqual(seen, [1])


class TestSrtFormat(unittest.TestCase):
    def test_timestamp_formatting(self):
        self.assertEqual(cuelib.srt_timestamp(0), "00:00:00,000")
        self.assertEqual(cuelib.srt_timestamp(1.5), "00:00:01,500")
        self.assertEqual(cuelib.srt_timestamp(3661.234), "01:01:01,234")
        self.assertEqual(cuelib.srt_timestamp(-5), "00:00:00,000")

    def test_timestamp_rounds_not_truncates(self):
        self.assertEqual(cuelib.srt_timestamp(0.0006), "00:00:00,001")

    def test_render_skips_empty_text(self):
        body = cuelib.render_srt([(0, 1, "hi"), (1, 2, "   "),
                                  (2, 3, "there")])
        self.assertIn("1\n", body)
        self.assertIn("2\n", body)
        self.assertNotIn("3\n", body)

    def test_render_parse_round_trip(self):
        entries = [(0.5, 2.25, "Ati han ako"),
                   (2.25, 4.0, "line one\nline two")]
        got = cuelib.parse_srt(cuelib.render_srt(entries))
        self.assertEqual(len(got), 2)
        for original, parsed in zip(entries, got):
            self.assertAlmostEqual(original[0], parsed[0], places=3)
            self.assertAlmostEqual(original[1], parsed[1], places=3)
            self.assertEqual(original[2], parsed[2])


class TestGapRules(unittest.TestCase):
    def test_overlap_is_trimmed(self):
        fixed = subs2srt.apply_gap_rules(
            [(0.0, 2.0, "a"), (1.9, 3.0, "b")], 0.04)
        self.assertLessEqual(fixed[0][1], 1.9 - 0.04 + 1e-9)

    def test_non_overlapping_is_untouched(self):
        entries = [(0.0, 1.0, "a"), (2.0, 3.0, "b")]
        self.assertEqual(subs2srt.apply_gap_rules(entries, 0.04), entries)


class TestGlossaryTokens(unittest.TestCase):
    """Words later batches are most likely to spell differently."""

    def test_marks_are_collected(self):
        got = subs2srt.glossary_tokens("nga'ay ho^ i Po:long")
        self.assertIn("nga'ay", got)
        self.assertIn("ho^", got)
        self.assertIn("Po:long", got)

    def test_proper_nouns_are_collected(self):
        got = subs2srt.glossary_tokens("ci Kinci ato Angcoh")
        self.assertIn("Kinci", got)
        self.assertIn("Angcoh", got)

    def test_plain_lowercase_words_are_ignored(self):
        got = subs2srt.glossary_tokens("kako ato mita a demak")
        self.assertEqual(got, [])

    def test_trailing_punctuation_stripped(self):
        self.assertIn("Aray", subs2srt.glossary_tokens("Aray."))

    def test_single_characters_ignored(self):
        self.assertEqual(subs2srt.glossary_tokens("i o a"), [])

    def test_double_quote_word_is_collected(self):
        got = subs2srt.glossary_tokens("to 'a\"iyalaeho: a kamok")
        self.assertIn("'a\"iyalaeho:", got)


class TestMergeRepeats(unittest.TestCase):
    def test_identical_neighbours_fuse(self):
        got = subs2srt.merge_repeats(
            [(0.0, 1.0, "耆老表示"), (1.2, 2.4, "耆老表示")], 1.0)
        self.assertEqual(got, [(0.0, 2.4, "耆老表示")])

    def test_far_apart_repeats_stay_separate(self):
        entries = [(0.0, 1.0, "a"), (30.0, 31.0, "a")]
        self.assertEqual(subs2srt.merge_repeats(entries, 1.0), entries)

    def test_different_text_is_untouched(self):
        entries = [(0.0, 1.0, "a"), (1.1, 2.0, "b")]
        self.assertEqual(subs2srt.merge_repeats(entries, 1.0), entries)

    def test_three_in_a_row_fuse_into_one(self):
        got = subs2srt.merge_repeats(
            [(0.0, 1.0, "x"), (1.1, 2.0, "x"), (2.1, 3.0, "x")], 1.0)
        self.assertEqual(got, [(0.0, 3.0, "x")])

    def test_empty_input(self):
        self.assertEqual(subs2srt.merge_repeats([], 1.0), [])


class TestParseTranscriptTsv(unittest.TestCase):
    def test_two_column_uses_default_line(self):
        got, errors = subs2srt.parse_transcript_tsv("3\thello", "han")
        self.assertEqual(errors, [])
        self.assertEqual(got, {"3": {"han": "hello"}})

    def test_three_column_names_the_line(self):
        got, errors = subs2srt.parse_transcript_tsv(
            "7\tami\tAti han ako\n7\than\t我就請", "han")
        self.assertEqual(errors, [])
        self.assertEqual(got["7"]["ami"], "Ati han ako")
        self.assertEqual(got["7"]["han"], "我就請")

    def test_comments_and_blanks_ignored(self):
        got, errors = subs2srt.parse_transcript_tsv(
            "# a note\n\n  \n1\ttext", "han")
        self.assertEqual(errors, [])
        self.assertEqual(list(got), ["1"])

    def test_bad_index_is_reported_not_swallowed(self):
        got, errors = subs2srt.parse_transcript_tsv("x\ttext", "han")
        self.assertEqual(got, {})
        self.assertEqual(len(errors), 1)

    def test_missing_text_column_is_reported(self):
        _, errors = subs2srt.parse_transcript_tsv("5", "han")
        self.assertEqual(len(errors), 1)

    def test_text_may_contain_tabs_after_line_name(self):
        got, _ = subs2srt.parse_transcript_tsv("1\than\ta\tb", "han")
        self.assertEqual(got["1"]["han"], "a\tb")


class TestCleanText(unittest.TestCase):
    def test_chinese_spaces_are_dropped(self):
        line = {"lang": "chi_tra"}
        self.assertEqual(subs2srt.clean_text("我 就 請", line), "我就請")

    def test_latin_spaces_are_collapsed_not_dropped(self):
        line = {"lang": "eng"}
        self.assertEqual(subs2srt.clean_text("Ati  han   ako", line),
                         "Ati han ako")


# ----------------------------------------------------- end-to-end fixture


GROUND_TRUTH = [
    (2.0, 5.0, "Ati han ako ko singsi"),
    (5.0, 8.5, "Hay na ilisin hananay"),          # back-to-back with above
    (10.0, 10.9, "mako"),                          # short cue
    (12.0, 18.0, "kafana'an no mako a demak"),     # long cue
    (19.5, 22.0, "Kinci ko somowalay"),
    (22.5, 25.0, "o kafana'an no niyam"),
    (26.0, 29.0, "sowal no Pangcah"),
]

GROUND_TRUTH_HAN = [
    (2.0, 5.0, "我就請我們的老師"),
    (5.0, 8.5, "關於豐年祭從小到現在"),
    (10.0, 10.9, "是的"),
    (12.0, 18.0, "我所經歷過的事情"),
    (19.5, 22.0, "來說明這部分"),
    (22.5, 25.0, "我們所知道的"),
    (26.0, 29.0, "阿美族的語言"),
]


def write_srt(entries, path):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(cuelib.render_srt(entries))
        handle.write("\n")


def build_fixture(path, entries, band=False, duration=31):
    """Burn `entries` into a synthetic 1080p clip with moving content."""
    srt_path = path + ".srt"
    write_srt(entries, srt_path)

    style = ("FontName=%s,FontSize=40,PrimaryColour=&H00FFFFFF,"
             "OutlineColour=&H00000000,BorderStyle=1,Outline=3,Shadow=0,"
             "Alignment=2,MarginV=30" % CJK_FONT)
    chain = []
    if band:
        # Mimic video A: an opaque yellow bar *behind* the text. libass puts
        # a MarginV=30 Alignment=2 line at roughly y=830..945, so the bar has
        # to cover that, not merely sit near the bottom of the frame.
        chain.append("drawbox=x=0:y=815:w=1920:h=150:"
                     "color=yellow@1.0:t=fill")
    escaped = srt_path.replace(":", r"\:")
    chain.append("subtitles=%s:force_style='%s'" % (escaped, style))

    cmd = [
        "ffmpeg", "-v", "error", "-y",
        "-f", "lavfi",
        "-i", "testsrc2=size=1920x1080:rate=30:duration=%d" % duration,
        "-vf", ",".join(chain),
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20",
        "-pix_fmt", "yuv420p", path,
    ]
    subprocess.run(cmd, check=True, stderr=subprocess.PIPE)
    return srt_path


def match_cues(truth, found, tolerance):
    """Pair ground-truth cues with detected cues by start time."""
    pairs = []
    unmatched = []
    remaining = list(found)
    for start, end, text in truth:
        best = None
        for candidate in remaining:
            delta = abs(candidate["start"] - start)
            if best is None or delta < best[0]:
                best = (delta, candidate)
        if best is not None and best[0] <= tolerance:
            pairs.append(((start, end, text), best[1]))
            remaining.remove(best[1])
        else:
            unmatched.append((start, end, text))
    return pairs, unmatched, remaining


def run_end_to_end(tmpdir, band, entries, lang, label, fps=5.0):
    video = os.path.join(tmpdir, "fixture_%s.mp4" % label)
    build_fixture(video, entries, band=band)

    work = os.path.join(tmpdir, "work_%s" % label)
    os.makedirs(work, exist_ok=True)
    args = argparse.Namespace(
        video=video, out=work, region=None, autodetect=True, fps=fps,
        start=0.0, duration=None, min_ink=120, change=0.35, min_stable=2,
        min_duration=0.30, samples=60, lang=lang, sheets=False,
        sheet_megapixels=1.1, progress=False)
    subs2srt.stage_cues(args)

    with open(os.path.join(work, "cues.json"), encoding="utf-8") as handle:
        manifest = json.load(handle)

    tolerance = 1.0 / fps + 0.05
    pairs, missed, extra = match_cues(entries, manifest["cues"], tolerance)

    print("\n--- end-to-end [%s] ---" % label)
    print("region detected : %s" % manifest["region"])
    print("truth cues      : %d" % len(entries))
    print("detected cues   : %d" % len(manifest["cues"]))
    print("matched         : %d" % len(pairs))
    print("missed          : %d" % len(missed))
    print("spurious        : %d" % len(extra))

    start_errs = []
    end_errs = []
    for (t_start, t_end, _), cue in pairs:
        start_errs.append(cue["start"] - t_start)
        end_errs.append(cue["end"] - t_end)
    if start_errs:
        print("start error     : mean %+.3fs  max |%.3f|s"
              % (float(np.mean(start_errs)), float(np.max(np.abs(
                  start_errs)))))
        print("end error       : mean %+.3fs  max |%.3f|s"
              % (float(np.mean(end_errs)), float(np.max(np.abs(end_errs)))))
    for item in missed:
        print("  MISSED  %.2f-%.2f  %s" % item)
    for cue in extra:
        print("  EXTRA   %.2f-%.2f" % (cue["start"], cue["end"]))

    # Build these through the real parser rather than by hand: a
    # hand-rolled Namespace silently rots the moment the CLI grows an
    # option, and the stage then dies on a missing attribute instead of
    # testing anything.
    parser = subs2srt.build_parser()
    ocr_args = parser.parse_args(["ocr", work])
    ocr_args.progress = False
    subs2srt.stage_ocr(ocr_args)

    srt_out = os.path.join(tmpdir, "out_%s.srt" % label)
    srt_args = parser.parse_args(["srt", work, "-o", srt_out])
    subs2srt.stage_srt(srt_args)

    with open(os.path.join(work, "transcripts.json"), encoding="utf-8") as fh:
        texts = json.load(fh)
    line_name = manifest["lines"][0]["name"]

    exact = 0
    print("  text comparison (tesseract):")
    for (t_start, _, truth_text), cue in pairs:
        got = (texts.get(str(cue["index"]), {}).get(line_name) or "").strip()
        want = truth_text.strip()
        if lang.startswith("chi"):
            want = want.replace(" ", "")
        flag = "ok " if got == want else "DIFF"
        if got == want:
            exact += 1
        else:
            print("    %s want=%r got=%r" % (flag, want, got))
    print("  exact text matches: %d/%d" % (exact, len(pairs)))

    with open(srt_out, encoding="utf-8") as handle:
        reparsed = cuelib.parse_srt(handle.read())
    print("  final SRT parses back to %d entries" % len(reparsed))

    return {
        "label": label,
        "truth": len(entries),
        "detected": len(manifest["cues"]),
        "matched": len(pairs),
        "missed": len(missed),
        "extra": len(extra),
        "exact_text": exact,
        "start_errs": start_errs,
        "end_errs": end_errs,
        "srt_entries": len(reparsed),
    }


def check_odd_region(video, fps=5.0):
    """Pin the vf_crop rounding bug: an all-odd box must not desynchronise.

    vf_crop is zero-copy, so for yuv420p it rounds width/height/x/y down to
    even -- 107 becomes 106 -- and says nothing above -v verbose. A reader
    consuming w*h*3 bytes then slips a row per frame and every frame is a
    torn blend of two, which looks like plausible cue boundaries rather than
    a crash. crop_chain() asks for `exact=1`; if that ever stops being
    applied, stream_region() raises here instead of corrupting quietly.
    """
    region = (101, 845, 1043, 107)
    seen = 0
    for _, frame in cuelib.stream_region(video, region, fps, start=0.0,
                                         duration=6.0):
        if frame.shape != (107, 1043, 3):
            raise AssertionError("frame shape %s, wanted (107, 1043, 3)"
                                 % (frame.shape,))
        seen += 1
    return seen


def end_to_end(keep=None):
    tmpdir = keep or tempfile.mkdtemp(prefix="subs2srt-selftest-")
    os.makedirs(tmpdir, exist_ok=True)
    print("fixture directory: %s" % tmpdir)
    results = []
    results.append(run_end_to_end(tmpdir, False, GROUND_TRUTH, "eng",
                                  "plain-latin"))
    results.append(run_end_to_end(tmpdir, True, GROUND_TRUTH_HAN, "chi_tra",
                                  "band-chinese"))

    odd_ok = True
    fixture = os.path.join(tmpdir, "fixture_band-chinese.mp4")
    try:
        frames = check_odd_region(fixture)
        print("\nodd-region crop check: %d frames of 1043x107, no desync"
              % frames)
    except Exception as exc:
        odd_ok = False
        print("\nodd-region crop check FAILED: %s" % exc)

    print("\n=================== end-to-end summary ===================")
    ok = True
    for item in results:
        timing_ok = (item["missed"] == 0 and item["extra"] == 0
                     and item["matched"] == item["truth"])
        if item["start_errs"]:
            worst = float(np.max(np.abs(item["start_errs"])))
        else:
            worst = 99.0
            timing_ok = False
        if worst > 0.30:
            timing_ok = False
        ok = ok and timing_ok
        print("%-14s cues %d/%d  missed %d  extra %d  worst-start %.3fs  "
              "text %d/%d  %s"
              % (item["label"], item["matched"], item["truth"],
                 item["missed"], item["extra"], worst, item["exact_text"],
                 item["matched"], "PASS" if timing_ok else "FAIL"))
    if keep is None:
        shutil.rmtree(tmpdir, ignore_errors=True)
    return ok and odd_ok


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true",
                        help="unit tests only, skip the video round trip")
    parser.add_argument("--keep", help="keep fixtures in this directory")
    args = parser.parse_args()

    suite = unittest.defaultTestLoader.loadTestsFromModule(
        sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        return 1
    if args.quick:
        return 0
    return 0 if end_to_end(keep=args.keep) else 1


if __name__ == "__main__":
    sys.exit(main())
