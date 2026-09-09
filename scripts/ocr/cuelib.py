"""Shared helpers for lifting burned-in (hardcoded) subtitles out of video.

The pipeline never asks an OCR engine "where is the text" -- burned-in
broadcast subtitles sit in a fixed band, so we find that band once, then
spend all the effort on two things an OCR engine is bad at:

* deciding *when* a subtitle starts and stops (timing), and
* deciding *which* frames are the same subtitle (dedup).

Both are pixel problems, not language problems, so they are solved here with
plain numpy and stay fully deterministic and testable. Text recognition is
left to a pluggable backend -- see cli.py.
"""

import json
import subprocess

import numpy as np

# ---------------------------------------------------------------- probing


def probe_video(path):
    """Return {width, height, duration, fps} for the first video stream."""
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,avg_frame_rate",
        "-show_entries", "format=duration",
        "-of", "json", path,
    ]
    out = subprocess.run(cmd, stdout=subprocess.PIPE, check=True).stdout
    info = json.loads(out)
    stream = info["streams"][0]
    num, _, den = stream["avg_frame_rate"].partition("/")
    fps = 0.0
    if float(den or 1) != 0:
        fps = float(num) / float(den or 1)
    return {
        "width": int(stream["width"]),
        "height": int(stream["height"]),
        "duration": float(info["format"]["duration"]),
        "fps": fps,
    }


# Why crop needs babysitting, from reading libavfilter/vf_crop.c:
#
# crop is zero-copy -- filter_frame() never touches a pixel, it only advances
# frame->data[] and rewrites width/height. For a subsampled format the chroma
# planes are advanced by `(y >> vsub) * linesize`, and that shift is the whole
# story: half a chroma row is not expressible as a pointer. So by default
# vf_crop.c does
#     s->w &= ~((1 << s->hsub) - 1);      /* and the same for h, x, y */
# which for yuv420p (hsub = vsub = 1) rounds a 107px request down to 106.
# Nothing is logged above -v verbose and nothing fails, so a reader consuming
# w*h*3 bytes per frame just quietly slips one row per frame.
#
# `exact=1` (added 2016, FFmpeg >= 3.2) opts out of the rounding. Measured
# here it costs nothing -- the wall-clock is all H.264 decode -- so we ask
# for it, snap the box ourselves anyway, and still verify the byte count.
# Three independent guards, because the failure mode is silent corruption.
CROP_EXACT = "exact=1"


def crop_chain(region, extra=None):
    """Build a crop filter string that ffmpeg cannot silently reinterpret."""
    x, y, w, h = region
    chain = "crop=%d:%d:%d:%d:%s" % (w, h, x, y, CROP_EXACT)
    if extra:
        chain = chain + "," + extra
    return chain


def normalize_region(region, width=None, height=None):
    """Snap a crop box to even coordinates and clip it to the frame.

    Belt-and-braces next to CROP_EXACT: an even box is what ffmpeg would use
    under either setting, so the region recorded in cues.json means the same
    thing to an older ffmpeg that has no `exact` option.
    """
    x, y, w, h = region
    x = max(int(x), 0) & ~1
    y = max(int(y), 0) & ~1
    w = max(int(w), 2) & ~1
    h = max(int(h), 2) & ~1
    if width is not None:
        w = max(min(w, (int(width) - x) & ~1), 2)
    if height is not None:
        h = max(min(h, (int(height) - y) & ~1), 2)
    return [x, y, w, h]


def stream_region(path, region, fps, start=0.0, duration=None):
    """Yield (timestamp, rgb) for `region` sampled at `fps` frames/second.

    `region` is (x, y, w, h). Timestamps are relative to the start of the
    file. Only the cropped region crosses the pipe, so a 1080p feature-length
    video costs little more than its decode time.
    """
    x, y, w, h = region
    args = ["ffmpeg", "-v", "error"]
    if start:
        args += ["-ss", "%.3f" % start]
    if duration is not None:
        args += ["-t", "%.3f" % duration]
    args += ["-i", path]
    chain = "fps=%s,%s" % (fps, crop_chain((x, y, w, h), "format=rgb24"))
    args += ["-vf", chain, "-f", "rawvideo", "-"]

    proc = subprocess.Popen(args, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL)
    nbytes = w * h * 3
    index = 0
    tail = 0
    try:
        while True:
            buf = proc.stdout.read(nbytes)
            if len(buf) < nbytes:
                tail = len(buf)
                break
            frame = np.frombuffer(buf, dtype=np.uint8).reshape(h, w, 3)
            yield (start + index / float(fps), frame)
            index += 1
    finally:
        proc.stdout.close()
        proc.wait()

    if tail:
        # A partial frame at EOF means ffmpeg's frames are not w*h*3 bytes,
        # so every frame we handed out was misaligned. Never let that pass
        # quietly -- it corrupts silently rather than crashing.
        raise RuntimeError(
            "raw stream desynchronised: %d trailing bytes after %d frames "
            "of %dx%d -- ffmpeg's frames are not %d bytes, so every frame "
            "handed out was misaligned. vf_crop rounds odd sizes down for "
            "subsampled formats; this build may predate crop's `exact` "
            "option (FFmpeg 3.2, 2016). Pass the region through "
            "normalize_region() to make it even."
            % (tail, index, w, h, nbytes))


# ------------------------------------------------------------ morphology


def dilate(mask, size):
    """Box dilation of a boolean mask, done separably in O(n * size)."""
    if size < 3:
        return mask
    radius = size // 2
    wide = mask.copy()
    for step in range(1, radius + 1):
        wide[:, step:] |= mask[:, :-step]
        wide[:, :-step] |= mask[:, step:]
    tall = wide.copy()
    for step in range(1, radius + 1):
        tall[step:, :] |= wide[:-step, :]
        tall[:-step, :] |= wide[step:, :]
    return tall


def erode(mask, size):
    """Box erosion -- dilation of the complement."""
    return ~dilate(~mask, size)


# ------------------------------------------------------------- text mask


class MaskSpec(object):
    """Tuning for `text_mask`.

    Broadcast subtitles are near-white glyphs carrying a dark outline or drop
    shadow. `white_min`/`max_spread` catch the glyph body; `outline` demands a
    dark pixel within `outline_size` px, which is what rejects sky, white
    shirts and other large pale areas of the underlying footage.
    """

    def __init__(self, white_min=185, max_spread=45, dark_max=95,
                 outline=True, outline_size=9, thin=False, thin_size=7,
                 band_probe=None, band_rows=None, scale=1,
                 compare_cols=None, compare_rows=None):
        self.white_min = white_min
        self.max_spread = max_spread
        self.dark_max = dark_max
        self.outline = outline
        self.outline_size = outline_size
        self.thin = thin
        self.thin_size = thin_size
        # {"x", "w", "min_saturation"}: a slice of the region that is always
        # backdrop and never glyph. When the backdrop stops being there, the
        # subtitle is not on screen at all -- see band_present().
        self.band_probe = band_probe
        # (lo, hi) rows within the region that the coloured band actually
        # covers, or None for "all of it". Rows outside take no part in
        # deciding where a cue starts and ends.
        #
        # 083 is why: its band covers only the lower half of the region and
        # the 36 rows above it are picture. A frame's mask came out 88.3%
        # white shirt and 11.7% glyph, so a line change moved the mask by
        # 0.21-0.27 against a 0.35 threshold -- one cue ran through four
        # sentences. Measured with the rows cropped, the same stretch splits
        # at exactly the times a person reads off the video.
        #
        # This is the SEGMENTER's view, not the reader's: strips are cut
        # from the preset's `lines` and are not affected.
        self.band_rows = band_rows
        # How far to subsample before masking: 1 is every pixel, 2 is every
        # other row and column. The mask is the expensive half of cutting a
        # cue -- measured 17.62 ms a frame over a 1920x122 band -- and a
        # subtitle's strokes are far wider than one pixel, so halving costs
        # a quarter of the work and leaves the cut points where they were.
        self.scale = scale
        # (lo, hi) columns and rows the segmenter compares, or None for all
        # of them. Distinct from `band_rows`: that one is MEASURED per
        # episode and therefore recorded in the timeline; these two are
        # DECLARED by the layout preset and stay there (ruled 2026-09-09,
        # the timeline gains no new keys).
        #
        # News subtitles are flush right: measured over 27 episodes the ink's
        # right edge sits at x=1735-1737 with a standard deviation of 31-70
        # px, while the left edge wanders by 460-470. Everything left of the
        # text is therefore picture, and picture is what pushes the mask
        # distance of an unchanged line up to 0.17-0.43 against a 0.35
        # threshold -- which is how one sentence became several cues, 24.9%
        # of the whole store. Comparing only the columns the text actually
        # occupies cut repeated cues by 44-69% on four episodes AND cut
        # swallowed sentences at the same time (87 to 43 on one), because
        # this raises the signal rather than moving the threshold.
        #
        # 開會了 declares neither: its subtitles are centred on an opaque
        # band, so no picture reaches the mask and there is nothing to gain.
        self.compare_cols = compare_cols
        self.compare_rows = compare_rows

    def scaled(self, factor):
        """A copy of this spec measured in subsampled pixels.

        Thresholds are intensities and do not move; every length does.
        `scale` is set to 1 in the copy because the sampling it asks for has
        already happened by the time this copy is used -- scaling twice
        would crop the wrong rows.
        """
        step = int(factor)
        if step <= 1:
            return self
        out = MaskSpec(
            white_min=self.white_min, max_spread=self.max_spread,
            dark_max=self.dark_max, outline=self.outline,
            outline_size=_odd_size(self.outline_size // step),
            thin=self.thin, thin_size=_odd_size(self.thin_size // step),
            band_rows=_halve_span(self.band_rows, step),
            compare_cols=_halve_span(self.compare_cols, step),
            compare_rows=_halve_span(self.compare_rows, step))
        if self.band_probe:
            probe = dict(self.band_probe)
            probe["x"] = int(probe.get("x", 0)) // step
            probe["w"] = max(int(probe.get("w", 60)) // step, 1)
            out.band_probe = probe
        return out

    @classmethod
    def from_dict(cls, data):
        spec = cls()
        for key in ("white_min", "max_spread", "dark_max", "outline",
                    "outline_size", "thin", "thin_size", "band_probe",
                    "band_rows"):
            if key in data:
                setattr(spec, key, data[key])
        return spec

    def to_dict(self):
        return {
            "white_min": self.white_min,
            "max_spread": self.max_spread,
            "dark_max": self.dark_max,
            "outline": self.outline,
            "outline_size": self.outline_size,
            "thin": self.thin,
            "thin_size": self.thin_size,
            "band_probe": self.band_probe,
            "band_rows": self.band_rows,
        }


def luma_of(rgb):
    """Integer BT.601 luma, kept in uint16 to avoid a float conversion."""
    acc = rgb[:, :, 0].astype(np.uint16) * 77
    acc += rgb[:, :, 1].astype(np.uint16) * 150
    acc += rgb[:, :, 2].astype(np.uint16) * 29
    return acc >> 8


def band_present(rgb, probe):
    """Is the subtitle's coloured backdrop actually on screen?

    Video A paints its subtitles on an opaque orange-to-yellow bar. When the
    bar is gone the programme is showing titles or a credit roll, and any
    white text in the region is *not* a subtitle -- reading it produces
    convincing-looking junk cues at both ends of the file. The bar is
    strongly saturated (mean channel spread ~125) while footage in the same
    strip measures ~11-26, so one threshold separates them cleanly.
    """
    if not probe:
        return True
    x0 = int(probe.get("x", 0))
    width = int(probe.get("w", 60))
    strip = rgb[:, x0:x0 + width, :].astype(np.int16)
    if strip.size == 0:
        return True
    spread = strip.max(axis=2) - strip.min(axis=2)
    return float(spread.mean()) >= float(probe.get("min_saturation", 60))


def text_mask(rgb, spec):
    """Boolean mask of pixels that look like subtitle glyph body."""
    if spec.band_probe and not band_present(rgb, spec.band_probe):
        return np.zeros(rgb.shape[:2], dtype=bool)
    low = rgb.min(axis=2).astype(np.int16)
    high = rgb.max(axis=2).astype(np.int16)
    mask = (low > spec.white_min) & ((high - low) < spec.max_spread)
    if spec.outline:
        dark = luma_of(rgb) < spec.dark_max
        mask &= dilate(dark, spec.outline_size)
        if spec.thin:
            white = (low > spec.white_min) & ((high - low) < spec.max_spread)
            mask &= ~erode(white, spec.thin_size)
    return _within_band(mask, spec.band_rows)


def _odd_size(size):
    """A box size `dilate` can use: odd, and below 3 it is a no-op anyway."""
    size = int(size)
    if size < 3:
        return 1
    return size | 1


def _halve_span(span, step):
    """(lo, hi) in subsampled pixels, or None."""
    if span is None:
        return None
    return (int(span[0]) // step, int(span[1]) // step)


def segment_spec(preset):
    """The mask spec for cutting, with the preset's sampling and window on it.

    `MaskSpec.from_dict` deliberately does not know about `scale`,
    `compare_cols` or `compare_rows`: those three are declared by the layout
    and stay in the preset, so that the timeline gains no new keys (ruled
    2026-09-09). Lifting them off the preset is therefore this function's
    whole job, and forgetting to call it is a silent fall back to
    full-resolution, whole-band comparison.
    """
    mask = preset.get("mask", {}) if preset else {}
    spec = MaskSpec.from_dict(mask)
    spec.scale = int(mask.get("scale", 1) or 1)
    spec.compare_cols = mask.get("compare_cols")
    spec.compare_rows = mask.get("compare_rows")
    return spec


def effective_min_ink(declared, spec, region):
    """`--min-ink` is quoted for the whole band unsampled; convert it.

    The number is 120 in the README, the skill and the notes, and it stays
    120 in the manifest. What the segmenter actually receives is a mask of
    only the compared window, at only `scale` resolution, so the threshold
    has to come down by the same area. `refine_cues` runs the identical
    conversion off the identical preset -- if the two ever disagree, one of
    them reads every frame as blank and says nothing about it.
    """
    height, width = int(region[3]), int(region[2])
    rows = spec.compare_rows or (0, height)
    cols = spec.compare_cols or (0, width)
    kept = max(int(rows[1]) - int(rows[0]), 0) * \
        max(int(cols[1]) - int(cols[0]), 0)
    whole = height * width
    if whole <= 0:
        return declared
    step = max(int(getattr(spec, "scale", 1) or 1), 1)
    scaled = declared * (float(kept) / whole) / (step * step)
    return max(int(scaled), 1)


def frame_mask(rgb, spec):
    """The mask the segmenter compares two frames on.

    `text_mask` answers "which pixels look like glyph"; this answers "which
    of those the cut point is allowed to depend on". Keeping them apart is
    deliberate: `verify_band`, `blank_runs` and `reread` all want the plain,
    full-resolution answer, and `text_mask` stays theirs.

    At `scale` 1 with no window this returns exactly what `text_mask`
    returns, bit for bit. That equivalence is the regression anchor for the
    whole sampling change -- `rebuild --verify` rebuilds delivered SRTs from
    stored timelines and never calls a mask, so nothing else downstream
    would notice the day it stopped holding.
    """
    step = int(getattr(spec, "scale", 1) or 1)
    if step > 1:
        rgb = rgb[::step, ::step]
        spec = spec.scaled(step)
    mask = text_mask(rgb, spec)
    return _within_window(mask, spec.compare_rows, spec.compare_cols)


def _within_window(mask, rows, cols):
    """Blank everything outside the compared window; `None` leaves it be.

    The `None` path returns the very same array it was handed, which is what
    keeps `frame_mask` bit-identical to `text_mask` for every caller that
    declares no window (all of 開會了, and news before this change).
    """
    if rows is None and cols is None:
        return mask
    if rows is not None:
        lo = max(int(rows[0]), 0)
        hi = min(int(rows[1]), mask.shape[0])
        mask[:lo, :] = False
        mask[hi:, :] = False
    if cols is not None:
        lo = max(int(cols[0]), 0)
        hi = min(int(cols[1]), mask.shape[1])
        mask[:, :lo] = False
        mask[:, hi:] = False
    return mask


def _within_band(mask, band_rows):
    """Blank every row the band does not cover; `None` leaves the mask be.

    Applied last, after the outline and thinning passes, so that what it
    drops is exactly "rows the band does not reach" and nothing else. The
    `None` path returns the very same array, which is what keeps the news
    side byte-for-byte identical.
    """
    if band_rows is None:
        return mask
    lo, hi = int(band_rows[0]), int(band_rows[1])
    lo = max(lo, 0)
    hi = min(hi, mask.shape[0])
    if lo <= 0 and hi >= mask.shape[0]:
        return mask
    mask[:lo, :] = False
    mask[hi:, :] = False
    return mask


def mask_distance(a, b):
    """Jaccard distance between two masks: 0.0 identical, 1.0 disjoint."""
    union = int((a | b).sum())
    if union == 0:
        return 0.0
    return float((a ^ b).sum()) / union


# -------------------------------------------------------- cue segmenting


class Cue(object):
    #: how many samples to keep for the median composite; 15-24 is plenty
    MAX_SAMPLES = 24

    def __init__(self, start, mask, ink, rgb, ts):
        self.start = start
        self.end = start
        self.mask = mask
        self.ink = ink
        self.best_rgb = rgb
        self.best_ink = ink
        self.best_ts = ts
        self.frames = 1
        # Samples kept for compositing. A subtitle is frozen for its whole
        # cue while anything passing in front of it is not, so the per-pixel
        # median across the cue erases occluders and leaves the glyphs. That
        # is what recovers text a single frame cannot show -- picking the
        # "best" single frame cannot beat a bird crossing the band.
        self.samples = [rgb]

    def add_sample(self, rgb):
        if len(self.samples) < self.MAX_SAMPLES:
            self.samples.append(rgb)

    def composite(self):
        """Per-pixel median of the kept samples, or the best single frame."""
        if len(self.samples) < 3:
            return self.best_rgb
        stack = np.stack(self.samples)
        return np.median(stack, axis=0).astype(np.uint8)

    def as_dict(self, index):
        return {
            "index": index,
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "sample_ts": round(self.best_ts, 3),
            "ink": int(self.best_ink),
            "frames": self.frames,
        }


class _Pending(object):
    def __init__(self, mask, ink, rgb, ts, blank):
        self.mask = mask
        self.ink = ink
        self.rgb = rgb
        self.start = ts
        self.last = ts
        self.blank = blank
        self.count = 1


class Segmenter(object):
    """Turn a stream of frame masks into timed cues.

    A frame only opens or closes a cue once it has repeated `min_stable`
    times. That hysteresis is what stops a cross-fade between two subtitles,
    or one noisy frame, from spawning a phantom cue.

    TWO GATES, DIFFERENT REFERENCES
    -------------------------------
    `_extend_current` measures the frame against `current.mask`, which is
    fixed when the cue opens and never updated. `_track_pending` measures it
    against `pending.mask`, i.e. the previous frame. Failing the first is not
    a boundary; a boundary needs `min_stable` consecutive frames that resemble
    *each other*, which is a separate question.

    Both jam together when the background moves. `text_mask` is a brightness
    threshold, so gravel, water and white clothing enter the mask; if that
    background also moves, no two frames resemble each other, the cue never
    extends AND no change is ever confirmed, so the cue never closes.
    Measured on 20210220_051 cue 735: 138 frames, distance to the frozen mask
    median 0.938, to the previous frame 0.726, ink median 12751 against a
    subtitle's 2000-4000 -- one cue holding sixteen sentences, `frames=2`.

    The failure is an under-split, which is the lossy direction. Abundant ink
    is not the signal -- cue 125 of the same episode segments cleanly at ink
    38076 (a static document) -- unstable ink is. `scripts/news/blind_cues.py`
    finds both this and the opposite static-bright case after the fact.
    """

    def __init__(self, frame_dt, min_ink=120, change=0.35, min_stable=2,
                 min_duration=0.30, on_cue=None):
        self.frame_dt = frame_dt
        self.min_ink = min_ink
        self.change = change
        self.min_stable = min_stable
        self.min_duration = min_duration
        self.on_cue = on_cue
        self.current = None
        self.pending = None
        self.cues = []

    def _close(self, end_ts):
        cue = self.current
        self.current = None
        if cue is None:
            return
        cue.end = end_ts
        if (cue.end - cue.start) + 1e-9 >= self.min_duration:
            self.cues.append(cue)
            # Hand the frame over at once so the caller can write it out.
            # Holding every cue's frame until the end of the pass costs
            # ~800KB per cue, which on a 50-minute video is most of a
            # gigabyte and grows with the video -- an OOM waiting to happen.
            if self.on_cue is not None:
                cue.best_rgb = cue.composite()
                cue.samples = []
                self.on_cue(len(self.cues), cue)
                cue.best_rgb = None
        # The mask only matters while the cue is the open one.
        cue.mask = None

    def _extend_current(self, ts, rgb, mask, ink):
        """True when the frame is the same cue still on screen."""
        if self.current is None:
            return False
        if mask_distance(mask, self.current.mask) >= self.change:
            return False
        self.current.end = ts + self.frame_dt
        self.current.frames += 1
        self.current.add_sample(rgb.copy())
        if ink > self.current.best_ink:
            self.current.best_ink = ink
            self.current.best_rgb = rgb.copy()
            self.current.best_ts = ts
        self.pending = None
        return True

    def _track_pending(self, ts, rgb, mask, ink, blank):
        """Grow the pending change, or start a new one."""
        same_pending = False
        if self.pending is not None and self.pending.blank == blank:
            if blank or mask_distance(mask, self.pending.mask) < self.change:
                same_pending = True
        if not same_pending:
            self.pending = _Pending(mask, ink, rgb.copy(), ts, blank)
            return
        self.pending.count += 1
        self.pending.last = ts
        if not blank and ink > self.pending.ink:
            self.pending.ink = ink
            self.pending.mask = mask
            self.pending.rgb = rgb.copy()

    def _confirm_pending(self, ts):
        """Once stable long enough, the pending change becomes real."""
        if self.pending.count < self.min_stable:
            return
        self._close(self.pending.start)
        if self.pending.blank:
            self.current = None
        else:
            self.current = Cue(self.pending.start, self.pending.mask,
                               self.pending.ink, self.pending.rgb,
                               self.pending.start)
            self.current.end = ts + self.frame_dt
            self.current.frames = self.pending.count
        self.pending = None

    def feed(self, ts, rgb, mask):
        ink = int(mask.sum())
        blank = ink < self.min_ink

        if not blank and self._extend_current(ts, rgb, mask, ink):
            return
        if self.current is None and blank:
            self.pending = None
            return
        self._track_pending(ts, rgb, mask, ink, blank)
        self._confirm_pending(ts)

    def finish(self, end_ts):
        # A change still sitting in `pending` at end of stream is real
        # evidence, just never confirmed. Honour it, otherwise the last cue
        # bleeds all the way to EOF instead of ending where the text went.
        if self.pending is not None and self.current is not None:
            self._close(min(self.pending.start, end_ts))
        else:
            self._close(end_ts)
        return self.cues
