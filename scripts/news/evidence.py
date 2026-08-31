#!/usr/bin/env python3
"""Cut a clip for every problem found, with its source and seconds attached.

A library, not a command: what counts as a finding differs per kind, so
the caller says which cues and this cuts them.

WHY
---
A finding stated as a row of numbers cannot be checked by the person reading
it. A clip can: it carries the episode, the master it came from and the
second it starts at, so anyone can open the source and see the same thing.

The three kinds of trouble found so far are not the same size, so "one
finding" means something different in each:

  clipped   the line sits below the strip region, so the strip keeps only
            the top sliver of the glyphs. Sampling looks at every STEP-th
            cue, so neighbouring samples must be joined back into the run
            they came from -- otherwise one stretch of trouble is reported
            as a handful of unrelated cues.
  unseen    the median washed a short line out of a cue. One cue, one
            finding.
  gap       no cue covers the stretch at all. One gap, one finding.

The clip is cut from the archived mkv, which is the master re-encoded, so
the pixels are the master's. The manifest names the master anyway: the mkv
is a convenience, the master is the provenance.
"""
import os
import subprocess

from scripts.errors import PipelineError

# Seconds of lead-in and lead-out, so a viewer sees the line arrive and
# leave rather than opening mid-sentence.
PAD = 1.5


def runs(indices, step):
    """Join sampled cue numbers back into the stretches they came from.

    Sampling every `step`-th cue means two flagged samples `step` apart were
    almost certainly one continuous stretch, not two. Anything further apart
    is a separate finding.
    """
    got = sorted(set(indices))
    if not got:
        return []
    out = []
    first = got[0]
    last = got[0]
    for i in got[1:]:
        if i - last <= step:
            last = i
            continue
        out.append((first, last))
        first = i
        last = i
    out.append((first, last))
    return out


def window(cues, first, last, pad=PAD):
    """(start, end) seconds for a clip covering cues `first`..`last`."""
    start = None
    end = None
    for cue in cues:
        if cue["index"] == first:
            start = cue["start"]
        if cue["index"] == last:
            end = cue["end"]
    if start is None:
        raise PipelineError("揣無 cue %s" % first)
    if end is None:
        raise PipelineError("揣無 cue %s" % last)
    return max(0.0, start - pad), end + pad


def clip_name(srt_name, first, last, kind):
    """A file name that is its own index: episode, cues, kind."""
    if first == last:
        span = "cue%d" % first
    else:
        span = "cue%d-%d" % (first, last)
    return "%s_%s_%s.mp4" % (srt_name, span, kind)


# A row counts as carrying text once it stands this far above the quietest
# rows of the probe. Picture noise sits near the floor; a glyph body is an
# order of magnitude above it.
INK = 0.15

# Rows of blank allowed inside one line before it is read as two separate
# things. A line of glyphs has its own gaps -- between the character bodies
# and the stroke that hangs below -- so a strict run breaks one line up.
JOIN = 12


def _clusters(rows, y0):
    """The stretches of rows carrying ink, as (lo, hi) absolute rows."""
    floor = min(rows)
    ceiling = max(rows)
    if ceiling <= floor:
        return []
    level = floor + (ceiling - floor) * INK
    out = []
    lo = None
    last = None
    for i, value in enumerate(rows):
        if value < level:
            continue
        y = y0 + i
        if lo is None:
            lo = y
        elif y - last > JOIN:
            out.append((lo, last))
            lo = y
        last = y
    if lo is not None:
        out.append((lo, last))
    return out


def band_for(rows, y0, height, was):
    """Where the strip SHOULD start, measured off the ink instead of guessed.

    `rows` is ink per row over a probe starting at `y0`; `was` is where the
    pipeline actually cut. The band keeps the pipeline's height and centres
    on the ink nearest what it was already aiming at.

    Nearest, not brightest: the lower-third graphic is a bigger, brighter
    block of ink than any subtitle, so "centre of all the ink" walks the
    band down onto the graphic -- which is exactly what it did to
    20210208_039 cue 40, a cue the pipeline had cut correctly. A subtitle
    drifts by tens of pixels; the graphic sits hundreds away.
    """
    found = _clusters(rows, y0)
    if not found:
        raise PipelineError("這條 cue 量無墨，無法度講伊ê帶佇佗")
    aim = was + height // 2
    best = None
    for lo, hi in found:
        middle = (lo + hi) // 2
        gap = abs(middle - aim)
        if best is None or gap < best[0]:
            best = (gap, middle)
    return max(y0, best[1] - height // 2)


def cut(video, start, end, out_path):
    """Re-encode the window into a small mp4 anyone can open."""
    subprocess.run(
        ["ffmpeg", "-nostdin", "-loglevel", "error", "-y",
         "-ss", "%.2f" % start, "-i", video, "-t", "%.2f" % (end - start),
         "-c:v", "libx264", "-crf", "23", "-preset", "veryfast",
         "-c:a", "aac", "-b:a", "128k", out_path],
        check=True)
    if not os.path.exists(out_path):
        raise PipelineError("切袂出來：%s" % out_path)
    return out_path
