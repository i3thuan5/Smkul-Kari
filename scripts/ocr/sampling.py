"""Pick the frames the cue cutter looks at: one per 0.2 s, real pts.

The target grid is `start + k * interval`, computed from k each time, and
each target takes the source frame nearest to it.  Two shortcuts this
replaces, both measured wrong:

* the `fps=5` filter hands out frames about 0.067 s behind the time it
  stamps on them, and the lag drifts over an episode;
* "every 6th frame" at 29.97 fps is 0.2002 s a step, 0.6 s off by the end
  of a 48-minute episode.

The time handed out is the chosen frame's own pts, so a `sample_ts` in
cues.json always extracts the very frame that was judged.
"""

FALLBACK_FPS = 30000 / 1001
INTERVAL = 0.2


def source_fps(declared):
    """The declared frame rate, or 29.97 when the file gives none (0/0).

    Only for sizing buffers and estimates -- never for timestamps.
    """
    if not declared or declared <= 0:
        return FALLBACK_FPS
    return float(declared)


def nearest_samples(frames, interval=INTERVAL, start=0.0, tolerance=None):
    """Yield (pts, frame) nearest to each target time, each frame once.

    `frames` is (pts, frame) in pts order.  When a gap in the source leaves
    one frame nearest to several targets, it is yielded only for the first.

    A target is normally settled by the first frame at or after it.  At
    the two edges of the stream there is no frame on one side, so there a
    target is filled only by a frame within `tolerance` (half a source
    frame, from the caller): targets before the first frame are skipped
    unless it is that close, and the one after the last frame is filled
    only if the last frame is.  That keeps the result the same whether
    ffmpeg passed every frame or only the nearest ones.  `tolerance=None`
    turns the edge rules off (first frame always taken, nothing past the
    last frame).
    """
    step = 0
    target = start
    previous = None
    last = None
    for pts, frame in frames:
        while previous is None and tolerance is not None and \
                pts - target > tolerance + 1e-9:
            step += 1
            target = start + step * interval
        while pts >= target - 1e-9:
            pick = (pts, frame)
            if previous is not None and \
                    target - previous[0] <= pts - target:
                pick = previous
            if last is None or pick[0] != last:
                last = pick[0]
                yield pick
            step += 1
            target = start + step * interval
        previous = (pts, frame)
    if previous is None or previous[0] == last or tolerance is None:
        return
    if target - previous[0] <= tolerance + 1e-9:
        yield previous
