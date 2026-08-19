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
                 band_probe=None):
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

    @classmethod
    def from_dict(cls, data):
        spec = cls()
        for key in ("white_min", "max_spread", "dark_max", "outline",
                    "outline_size", "thin", "thin_size", "band_probe"):
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
    if not spec.outline:
        return mask
    dark = luma_of(rgb) < spec.dark_max
    mask &= dilate(dark, spec.outline_size)
    if spec.thin:
        white = (low > spec.white_min) & ((high - low) < spec.max_spread)
        mask &= ~erode(white, spec.thin_size)
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
