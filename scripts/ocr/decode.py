"""ffmpeg reading: crop boxes, native-rate streams, select windows.

Two ways to pull the subtitle band out of a video:

* `stream_region` -- resampled to a fixed rate with the `fps` filter.
  Timestamps are `start + index / fps`.  Kept for the tools that only
  want "a frame every so often" (rereads, band checks).
* `stream_frames` -- every source frame (or only those inside `windows`),
  each paired with its real pts from `showinfo`.  Cue cutting and boundary
  refinement use this, because the `fps` filter's picks sit about 0.067 s
  behind their stamped time and drift over an episode.

Pitfalls met while building `stream_frames`, each guarded below:

* rawvideo output defaults to a constant frame rate, so ffmpeg pads the
  gaps `select` leaves with duplicate frames (832 frames for 166 pts).
  `-fps_mode passthrough` turns that off; the pairing check catches it
  anyway.
* the progress line and showinfo share a line on stderr unless `-nostats`
  is given, and a line-anchored parser then misses timestamps.
* a whole episode's windows make a ~25 KB filter, which goes through
  `-filter_script:v` instead of the command line.
"""

import json
import math
import os
import queue
import re
import subprocess
import tempfile
import threading

import numpy as np

DEFAULT_THREADS = 2
FILTER_INLINE_MAX = 4000

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


def _desync_error(tail, index, w, h):
    # A partial frame at EOF means ffmpeg's frames are not w*h*3 bytes,
    # so every frame we handed out was misaligned. Never let that pass
    # quietly -- it corrupts silently rather than crashing.
    return RuntimeError(
        "raw stream desynchronised: %d trailing bytes after %d frames "
        "of %dx%d -- ffmpeg's frames are not %d bytes, so every frame "
        "handed out was misaligned. vf_crop rounds odd sizes down for "
        "subsampled formats; this build may predate crop's `exact` "
        "option (FFmpeg 3.2, 2016). Pass the region through "
        "normalize_region() to make it even."
        % (tail, index, w, h, w * h * 3))


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
        raise _desync_error(tail, index, w, h)


# ------------------------------------------------------ real-pts streams

TIME_BASE_RE = re.compile(r"config in time_base:\s*(\d+)/(\d+)")
PTS_RE = re.compile(r"(?<![A-Za-z_])pts:\s*(-?\d+|NOPTS)")


class ShowinfoParser(object):
    """Frame times out of showinfo's stderr, however lines were split.

    The time is the integer `pts` times the input time_base, never the
    printed `pts_time`: that is `%g`, six significant digits, so past
    1000 s it is only good to 10 ms (1082.983 prints as 1082.98) and two
    neighbouring frames look equally near a grid point.
    """

    def __init__(self):
        self.time_base = None

    def feed(self, text):
        found = []
        events = []
        for match in TIME_BASE_RE.finditer(text):
            events.append((match.start(), "base", match))
        for match in PTS_RE.finditer(text):
            events.append((match.start(), "pts", match))
        events.sort(key=lambda event: event[0])
        for _at, kind, match in events:
            if kind == "base":
                self.time_base = (int(match.group(1)), int(match.group(2)))
                continue
            if match.group(1) == "NOPTS":
                raise RuntimeError("showinfo 印出一格 NOPTS，這格沒有時間")
            if self.time_base is None:
                raise RuntimeError("showinfo 還沒印 time_base 就先印了畫面")
            num, den = self.time_base
            found.append(int(match.group(1)) * num / den)
        return found


def _merged(windows):
    spans = []
    for start, end in sorted(windows):
        start = max(float(start), 0.0)
        end = float(end)
        if spans and start <= spans[-1][1]:
            spans[-1][1] = max(spans[-1][1], end)
        else:
            spans.append([start, end])
    return spans


def select_expr(windows):
    """One `select` expression covering `windows`; overlaps are merged."""
    terms = []
    for start, end in _merged(windows):
        terms.append("between(t,%.3f,%.3f)" % (start, end))
    return "+".join(terms)


# How far off a grid point a frame may sit and still be let through: half a
# frame plus 1 ms, because containers with a 1/1000 timebase (mkv) round
# every pts to the millisecond -- with only half a frame, 158 of an
# episode's 14,400 grid points lost their frame.
PTS_SLACK = 0.001


def grid_half(fps):
    """Half a frame plus the pts rounding slack, rounded up to 0.1 ms."""
    return math.ceil(round((0.5 / fps + PTS_SLACK) * 1e4, 6)) / 1e4


def grid_expr(interval, fps):
    """A `select` letting through the frames nearest each grid point.

    A frame passes when it lies within half a frame of `k * interval`, so
    every grid point keeps its nearest frame (two at an exact tie; the
    Python side picks one; see `grid_half` for the slack). None when the
    rate is unknown -- then every
    frame goes through and the Python side does all the choosing.
    """
    if not fps or fps <= 0:
        return None
    half = grid_half(fps)
    return "lte(abs(t-%g*floor(t/%g+0.5)),%.6f)" % (interval, interval, half)


def _chain(region, windows, grid=None):
    parts = [crop_chain(region)]
    if windows is not None:
        parts.append("select='%s'" % select_expr(windows))
    if grid is not None:
        expr = grid_expr(*grid)
        if expr:
            parts.append("select='%s'" % expr)
    parts.append("showinfo")
    parts.append("format=rgb24")
    return ",".join(parts)


def _read_stderr(stream, found, lines, failed):
    """Push each pts onto `found`, keep the other text for error reports.

    A parse failure is kept in `failed` for the reading side to raise;
    the stream is still drained so ffmpeg never blocks on a full pipe.
    """
    parser = ShowinfoParser()
    pending = ""
    while True:
        chunk = stream.read1(65536)
        if not chunk:
            break
        pending += chunk.decode("utf-8", "replace")
        # a record ends at \n or \r; keep the unfinished tail for next read
        cut = max(pending.rfind("\n"), pending.rfind("\r"))
        if cut < 0:
            continue
        done, pending = pending[:cut + 1], pending[cut + 1:]
        _consume(parser, done, found, lines, failed)
    if pending:
        _consume(parser, pending, found, lines, failed)
    found.put(None)


def _consume(parser, text, found, lines, failed):
    if not failed:
        try:
            for pts in parser.feed(text):
                found.put(pts)
        except RuntimeError as exc:
            failed.append(exc)
    for line in re.split(r"[\r\n]+", text):
        if line and "pts_time:" not in line and "showinfo" not in line:
            lines.append(line)
            del lines[:-20]


def stream_frames(path, region, windows=None, threads=DEFAULT_THREADS,
                  start=0.0, duration=None, grid=None):
    """Yield (pts, rgb) for every source frame, or only those in `windows`.

    `start`/`duration` seek on the input; ffmpeg then counts pts from the
    seek point, so `start` is added back and every pts is file time.

    `grid=(interval, fps)` drops, inside ffmpeg, every frame not nearest a
    multiple of `interval` (counted from `start`) -- converting and piping
    all of them only for Python to throw five in six away cost ~20% more
    CPU. The caller still picks the nearest frame per target; this only
    thins what reaches it.

    `windows` is a list of (start, end) seconds; overlapping windows are
    merged, so a frame is decoded once however many windows want it (see
    `window_frames` for handing it to each).  Raises RuntimeError naming
    the video if ffmpeg fails or frames and timestamps do not pair up.
    """
    if grid is not None and windows is not None:
        raise ValueError("grid and windows are separate uses; pick one")
    x, y, w, h = region
    chain = _chain((x, y, w, h), windows, grid)
    args = ["ffmpeg", "-hide_banner", "-nostats", "-v", "info"]
    if threads:
        args += ["-threads", str(int(threads))]
    if start:
        args += ["-ss", "%.3f" % start]
    if duration is not None:
        args += ["-t", "%.3f" % duration]
    args += ["-i", path]
    script = None
    if len(chain) > FILTER_INLINE_MAX:
        handle, script = tempfile.mkstemp(prefix="decode-", suffix=".filter")
        with os.fdopen(handle, "w", encoding="utf-8") as f:
            f.write(chain)
        args += ["-filter_script:v", script]
    else:
        args += ["-vf", chain]
    args += ["-an", "-fps_mode", "passthrough",
             "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]

    try:
        proc = subprocess.Popen(args, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)
        found = queue.Queue()
        lines = []
        failed = []
        reader = threading.Thread(target=_read_stderr,
                                  args=(proc.stderr, found, lines, failed),
                                  daemon=True)
        reader.start()
        for pts, frame in _pair(proc, reader, found, lines, failed, path,
                                w, h):
            yield (pts + start, frame)
    finally:
        if script:
            os.unlink(script)


def _pair(proc, reader, found, lines, failed, path, w, h):
    nbytes = w * h * 3
    index = 0
    tail = 0
    stamps_over = False
    finished = False
    try:
        while True:
            buf = proc.stdout.read(nbytes)
            if len(buf) < nbytes:
                tail = len(buf)
                break
            pts = found.get()
            if pts is None:
                stamps_over = True
                index += 1
                break
            frame = np.frombuffer(buf, dtype=np.uint8).reshape(h, w, 3)
            yield (pts, frame)
            index += 1
        finished = not stamps_over
    finally:
        if not finished:
            proc.kill()
        proc.stdout.close()
        code = proc.wait()
        reader.join()
        proc.stderr.close()

    extra = 0
    if not stamps_over:
        while True:
            pts = found.get()
            if pts is None:
                break
            extra += 1
    if failed:
        raise RuntimeError("%s：%s" % (path, failed[0]))
    if stamps_over:
        raise RuntimeError(
            "%s：畫面比時間戳多（第 %d 格沒有時間戳）——rawvideo 可能補了"
            "重複格，要加 -fps_mode passthrough" % (path, index))
    if code != 0:
        raise RuntimeError("ffmpeg 讀 %s 失敗（結束碼 %d）：%s"
                           % (path, code, " | ".join(lines[-5:])))
    if tail:
        raise _desync_error(tail, index, w, h)
    if extra:
        raise RuntimeError("%s：時間戳比畫面多 %d 筆（畫面 %d 格）"
                           % (path, extra, index))


def window_frames(frames, windows):
    """Hand each window the (pts, rgb) pairs that fall inside it.

    `frames` must be in pts order.  Yields (window index, pairs) as soon as
    a window closes -- that is, once a frame past its end arrives -- so
    only frames still wanted by an open window stay in memory.  A frame
    inside two overlapping windows is given to both (the same object).
    Windows the stream never reaches are yielded last, possibly empty.
    """
    order = sorted(range(len(windows)), key=lambda i: windows[i][0])
    by_end = sorted(range(len(windows)), key=lambda i: windows[i][1])
    collected = {}
    started = 0
    closed = 0
    for pts, frame in frames:
        while closed < len(by_end) and windows[by_end[closed]][1] < pts:
            index = by_end[closed]
            yield (index, collected.pop(index, []))
            closed += 1
        while started < len(order) and windows[order[started]][0] <= pts:
            index = order[started]
            if windows[index][1] >= pts:
                collected[index] = []
            started += 1
        for index in list(collected):
            start, end = windows[index]
            if start <= pts <= end:
                collected[index].append((pts, frame))
    while closed < len(by_end):
        index = by_end[closed]
        yield (index, collected.pop(index, []))
        closed += 1
