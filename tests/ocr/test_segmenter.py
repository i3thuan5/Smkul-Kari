"""Cue segmentation, median compositing, and the per-cue callback."""
import unittest

import numpy as np

from scripts.ocr import cuelib


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


if __name__ == "__main__":
    unittest.main()


class TestCompareWindowDoesNotReachTheStrips(unittest.TestCase):
    """The window decides cut points and nothing else.

    The segmenter is handed two separate things per frame: the RGB it keeps
    for the strip, and the mask it compares. Narrowing the mask must not
    narrow the strip. If it ever does, Claude Vision is shown the right-hand
    slice of a right-aligned line and reads a sentence with its first half
    missing -- and it looks like a perfectly ordinary short subtitle, so
    nobody downstream can tell.
    """

    def _frames(self):
        """Six frames of one steady line, with picture on the left."""
        out = []
        for index in range(6):
            rgb = np.zeros((8, 60, 3), dtype=np.uint8)
            rgb[:, :, :] = index * 7          # left picture keeps moving
            rgb[2:6, 40:56] = 255             # the line itself, on the right
            out.append(rgb)
        return out

    def _cut(self, spec):
        seg = cuelib.Segmenter(frame_dt=0.2, min_ink=4, change=0.35,
                               min_stable=2, min_duration=0.30)
        for index, rgb in enumerate(self._frames()):
            seg.feed(index * 0.2, rgb, cuelib.frame_mask(rgb, spec))
        return seg.finish(6 * 0.2)

    def test_composite_is_identical_with_and_without_a_window(self):
        plain = self._cut(cuelib.MaskSpec(outline=False))
        windowed = self._cut(cuelib.MaskSpec(outline=False,
                                             compare_cols=(36, 60)))
        self.assertEqual(len(plain), 1)
        self.assertEqual(len(windowed), 1)
        self.assertTrue(np.array_equal(plain[0].composite(),
                                       windowed[0].composite()))

    def test_a_line_wholly_outside_the_window_opens_no_cue(self):
        cues = self._cut(cuelib.MaskSpec(outline=False, compare_cols=(0, 20)))
        self.assertEqual(cues, [])


class TestWindowStopsPictureFromSplittingOneLine(unittest.TestCase):
    """Why the window exists at all.

    A line that never changes still gets cut apart when the picture beside
    it changes: measured on one episode, 24.9% of all cues repeat the
    previous cue's text, and the mask distance of an unchanged line runs
    0.17-0.43 against a 0.35 threshold. Comparing only the columns the text
    occupies removes the noise instead of raising the threshold -- raising
    it was measured to trade repeats away for swallowed sentences roughly
    one for one.

    The picture here changes in steps, not every frame, because that is what
    footage does (a shot cut) and because a mask that changes every single
    frame trips a different fault entirely: nothing ever confirms and the
    segmenter returns no cues at all.
    """

    def _cut(self, spec):
        seg = cuelib.Segmenter(frame_dt=0.2, min_ink=4, change=0.35,
                               min_stable=2, min_duration=0.30)
        for index in range(12):
            rgb = np.zeros((8, 60, 3), dtype=np.uint8)
            shot = index // 3                 # the picture cuts every 3
            rgb[:, shot * 6:shot * 6 + 14] = 255   # stays left of 36
            rgb[2:6, 40:56] = 255             # the line, never changing
            seg.feed(index * 0.2, rgb, cuelib.frame_mask(rgb, spec))
        return seg.finish(12 * 0.2)

    def test_whole_band_splits_the_steady_line(self):
        self.assertGreater(len(self._cut(cuelib.MaskSpec(outline=False))), 1)

    def test_window_keeps_it_as_one_cue(self):
        cues = self._cut(cuelib.MaskSpec(outline=False,
                                         compare_cols=(36, 60)))
        self.assertEqual(len(cues), 1)
