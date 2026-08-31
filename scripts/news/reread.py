#!/usr/bin/env python3
"""Split a cue the segmenter got wrong into one segment per sentence.

`blind_cues` says which cues need a second look; this says how to cut each
one up so the vision pass sees one sentence per strip instead of a median
that hides thirteen of them.

WHY NOT JUST DIFF ADJACENT FRAMES
---------------------------------
Because that is exactly what failed. `Segmenter` compares frame masks with
`mask_distance` against a 0.35 threshold, and on a moving background every
frame differs from every other: 20210220_051 cue 735 measures a median 0.726
between neighbours, so every one of its 138 frames reads as "changed" and
none as "changed *and* stable". The signal is buried in the noise, and no
choice of threshold digs it out -- 0.35 or 0.8, the noise clears it either
way.

TEMPORAL MEDIAN FIRST
---------------------
The noise moves, the subtitle does not. Take the per-pixel majority over a
window of frames and the moving speckle drops out while the glyphs survive.
Measured on cue 735: mask ink median 12,751 where a line of subtitle is
2,000-4,000; after a three-frame intersection, 3,964.

Compare the *cleaned* windows and the two populations separate: a real
sentence change scores >= 0.68, noise <= 0.33. That gap is wide enough that
`CHANGE` sits in the middle of it rather than on the edge of either. This is
the method the audit agents ran by hand over 051午 and 053午; this module is
that method written down.

WHAT IT DOES NOT FIX
--------------------
A median only removes noise that *moves*. A static bright background stays
put and stays in the mask: 20210220_051 cue 125 is a white document at ink
38,076 with the subtitle contributing about 2,500, so a sentence change
shifts under 7% of the mask -- near the threshold rather than over it. It
degrades rather than fails: measured, that cue splits into 3 where the text
holds 6 sentences. Duration (`blind_cues.LONG`) is what flags it; expect
partial splits there and check the strips rather than trusting the count.

The timeline is not touched. Segments are a reading aid: they say where to
point the camera, and `refine_cues` does the 25 fps boundary work afterwards
if the split is adopted.
"""
import argparse
import glob
import json
import os
import sys

import numpy as np

from scripts.errors import PipelineError
from scripts.news import blind_cues, paths
from scripts.ocr import cuelib

# Seconds of frames folded into one cleaned mask. Long enough to outvote the
# speckle, short enough that a sentence which is only on screen for a second
# still owns a window of its own. Swept against the hand-labelled boundaries
# of cue 735 (15 of them): every span from 0.4 to 0.8 recovers all 15, and
# 0.8 does it with the fewest extra cuts (21 segments against 0.6's 29).
SPAN = 0.8

# What `cuelib` samples the band at everywhere in this pipeline.
FPS = 5.0

# The band every titv-news episode uses; overridden by the timeline's own.
REGION = [0, 722, 1920, 122]

# Jaccard distance between two cleaned windows, above which they are holding
# different text. Measured on 051午/053午: real sentence changes land at 0.68
# and above, noise at 0.33 and below. 0.6 keeps every real boundary on cue
# 735 while cutting the spurious ones to 3, and leaves clean cues alone --
# cue 27 (17.22s, one sentence) stays one segment, cue 256 (two sentences)
# splits into exactly two.
#
# Over-splitting is the safe direction here and the pipeline already relies
# on it: `merge_repeats` fuses neighbours whose recognised text is identical,
# so an extra cut costs one strip to read, while a missed one loses a line.
CHANGE = 0.6

# A segment shorter than this cannot be holding a sentence of its own, so it
# is folded back into the one before it. `stream_region` hands back one more
# frame than `duration * fps` implies, which puts the last window's start
# inside the final fifth of a second and cuts a sliver -- and that sliver's
# single frame is already showing the NEXT cue's line. Measured on
# 20210215_046: segment 234.02 spans 0.08s and reads as cue 235's sentence,
# 311.02 the same for cue 312. Taking those at face value files a
# neighbour's line under the wrong cue, which is the error the audit spends
# its time undoing. 0.4s is two frames at 5 fps, and the shortest genuine
# subtitle measured anywhere in this corpus.
MIN_PART = 0.4

# Ink left after the cue's own static background is removed, below which
# subtracting it would do more harm than good. A *static* bright background
# survives the temporal median -- 20210222_053 cue 111 sits on a page of
# vertical newsprint at ink 57,126 and its five subtitle changes register as
# none at all (`frames=106`). Subtracting the whole-cue median exposes them.
#
# But a subtitle that never changes IS part of that median and gets
# subtracted with the background, leaving noise: 20210220_051 cue 27, one
# sentence over 17.2s, explodes into 14 segments that way. Measured
# foreground ink after subtraction separates the two cleanly --
#
#   worth it     cue 111  8,164    cue 125  5,504
#   not worth it cue  27     24    cue 960    234    cue 144  1,933
#
# -- and 3,000 sits in the gap. A line of subtitle is 2,000-4,000 strokes,
# so the rule reads: at least a line's worth of ink has to be changing.
MOVING = 3000

# How far a frame's mask may sit from the whole-cue median before the cue
# counts as one whose *background* is moving. Subtraction is only right when
# the background holds still and the subtitle changes; when it is the other
# way round -- 20210215_046 cue 148, one sentence over 2.54s while the camera
# pans through trees -- the steady subtitle IS the median, so subtracting it
# leaves the foliage and splits one sentence into three.
#
#   subtract     cue 111  0.205    cue 125  0.174
#   leave alone  cue 148  0.572    cue 735  0.982
#
# 0.35 is `Segmenter.change` itself: the distance at which the segmenter
# would still call two frames the same picture.
STEADY = 0.35


def median(frames):
    """Per-pixel majority of a window of masks.

    What every frame agrees on survives; what only some frames had does not.
    That is the whole trick -- the subtitle is in every frame, the speckle is
    not.
    """
    if not len(frames):
        raise PipelineError("無半格通做中位數")
    stack = np.stack(frames)
    return stack.sum(axis=0) * 2 > len(frames)


def windows(frames, frame_dt, span=SPAN):
    """Fold the frames into cleaned windows, each tagged with its first."""
    per = max(1, int(round(span / frame_dt)))
    out = []
    for first in range(0, len(frames), per):
        chunk = frames[first:first + per]
        if not len(chunk):
            continue
        out.append({"first": first, "mask": median(chunk)})
    return out


def foreground(masks):
    """The masks with whatever stays put for the whole cue removed."""
    bg = median(masks)
    out = []
    for m in masks:
        out.append(m & ~bg)
    return out


def worth_subtracting(masks, frame_dt, span=SPAN, floor=MOVING):
    """Is enough ink actually changing to justify removing the background?

    Two things have to hold: the background must be the part standing still
    (see `STEADY`), and enough ink must survive its removal (`MOVING`).

    Measured over the same windows the split will use. Asking it per frame
    instead skips the median that the whole method rests on, which inflates
    the answer with speckle: 20210215_046 cue 144 reads 1,933 over proper
    windows and passes the floor per frame, turning a correct single segment
    into eight.
    """
    bg = median(masks)
    apart = []
    for m in masks:
        apart.append(cuelib.mask_distance(m, bg))
    apart.sort()
    if apart[len(apart) // 2] > STEADY:
        return False              # 振動ê是背景，毋是字幕
    got = windows(foreground(masks), frame_dt=frame_dt, span=span)
    if not got:
        return False
    inks = []
    for w in got:
        inks.append(int(w["mask"].sum()))
    inks.sort()
    return inks[len(inks) // 2] >= floor


def boundaries(got, change=CHANGE):
    """Indices of the windows that start new text."""
    out = []
    for i in range(1, len(got)):
        if cuelib.mask_distance(got[i]["mask"], got[i - 1]["mask"]) >= change:
            out.append(i)
    return out


def segments(cue, frames, frame_dt, span=SPAN, change=CHANGE):
    """One dict per sentence found inside `cue`, covering it end to end.

    The segments abut: the first starts where the cue starts, the last ends
    where it ends, and nothing falls between them -- a hole would be text
    with nowhere to go, which is the failure this whole exercise is about.

    A static background is removed first when there is enough changing ink
    to make that safe (see `MOVING`); otherwise the masks are used as they
    come.
    """
    if worth_subtracting(frames, frame_dt, span):
        frames = foreground(frames)
    got = windows(frames, frame_dt, span)
    cuts = boundaries(got, change)
    starts = [0]
    for i in cuts:
        starts.append(got[i]["first"])
    spans = []
    for n, first in enumerate(starts):
        begin = cue["start"] + first * frame_dt
        if n + 1 < len(starts):
            finish = cue["start"] + starts[n + 1] * frame_dt
        else:
            finish = cue["end"]
        spans.append([begin, finish])
    kept = []
    for begin, finish in spans:
        if kept and finish - begin < MIN_PART:
            kept[-1][1] = finish          # 傷短：併轉去頂一段
            continue
        kept.append([begin, finish])
    out = []
    for n, (begin, finish) in enumerate(kept):
        out.append({"cue": cue["index"], "part": n + 1,
                    "start": begin, "end": finish})
    return out


# Ink left in a segment's cleaned mask, below which there is nothing to
# read. Not a brightness test -- the opening title animation is bright and
# inky, but it moves, so the median leaves almost nothing behind. Measured
# on 20210215_046: segments from cues that carry text sit at a median 6,481,
# segments from blank cues at 63. 400 keeps 58 of 64 real segments and drops
# 22 of 26 empty ones; the 6 it drops are stretches with no subtitle inside
# a cue that has one elsewhere, which is a correct answer rather than a loss.
INK = 400


def has_text(clean, floor=INK):
    """Is there anything in this cleaned mask worth sending to a reader?"""
    return int(clean.sum()) >= floor


# How many strips go on one contact sheet. Matches what the vision pass has
# always been given, so a reread batch is the same size of job as a first
# read and the measured throughput carries over.
PER_SHEET = 4


def label(seg):
    """The number printed in a strip's gutter: which cue, which part.

    The reader copies this back with the text, so it has to say where the
    line belongs. A plain running number would leave nothing to fold the
    answers back onto -- `fold` keys on exactly this.
    """
    return "%d.%02d" % (seg["cue"], seg["part"])


def pack(segs, per=PER_SHEET):
    """Split the segments into sheet-sized groups, in order."""
    out = []
    for first in range(0, len(segs), per):
        chunk = segs[first:first + per]
        if chunk:
            out.append(chunk)
    return out


def fold(read, after=None, before=None):
    """Join the parts read back into one string per cue.

    Ordered by `part`, because the parts are consecutive moments of one
    stretch of video: out of order the sentences come back scrambled. Blank
    parts contribute nothing rather than a gap -- a segment with no subtitle
    is a real answer, not a hole.

    `after` maps a cue to the text the NEXT cue holds. The LAST part of a
    cue split into two or more is dropped when it matches that: the cue's
    boundary is late and the next sentence's opening was swept into its
    tail. `before` is accepted and deliberately unused -- see below.

    Direction and position both matter, and getting that wrong is not a
    small error. "Drop any part a neighbour also has" empties the normal
    case: one line stays on screen across several cues and is written into
    each of them, 12,351 times across the delivered corpus. That rule blanked
    cue 31, 107, 144 and 148 of 20210215_046, all of them correct.

    A single-part cue is never touched. If such a cue really does hold a
    neighbour's sentence -- the single-frame fallback landing on the wrong
    line -- that is a rewrite to be made, not a part to drop; dropping would
    leave the cue empty. See `blind_cues`.

    A part that repeats the one before it is dropped. Splitting errs towards
    over-splitting, so one sentence can land in two consecutive segments and
    be read twice -- 20210215_046 segments 210.01 and 210.02 both read
    「學校有限制一星期26節」. Joining those makes a string that was never on
    screen. A repeat further along is kept: a sentence really can be said
    twice with something in between.
    """
    by_cue = {}
    for item in read:
        by_cue.setdefault(item["cue"], []).append(item)
    out = {}
    for cue, items in by_cue.items():
        items.sort(key=lambda i: i["part"])
        pieces = []
        for item in items:
            text = (item.get("text") or "").strip()
            if not text:
                continue
            if pieces and pieces[-1] == text:
                continue
            last = item["part"] == items[-1]["part"] and len(items) > 1
            if last and after and text == after.get(cue):
                continue
            pieces.append(text)
        out[cue] = "".join(pieces)
    return out


def masks_of(video, cue, region, spec, fps=FPS):
    """Every frame mask inside one cue, straight off the video."""
    out = []
    span = cue["end"] - cue["start"]
    for _ts, rgb in cuelib.stream_region(video, region, fps=fps,
                                         start=cue["start"], duration=span):
        out.append(cuelib.text_mask(rgb, spec))
    if not out:
        raise PipelineError("cue %s 解無半格" % cue.get("index"))
    return out


def plan(srt_name, video=None, floor=None, long=None):
    """Every segment the flagged cues of one episode should be read as.

    Reads from the archived mkv, which is the master re-encoded -- the
    subtitle pixels are the master's, and it is 2 GB against the master's 19.
    """
    doc = _timeline(srt_name)
    cues = doc["cues"]
    spec = cuelib.MaskSpec.from_dict(doc.get("mask", {}))
    region = tuple(doc.get("region", REGION))
    if video is None:
        video = os.path.join(paths.KITHANN, "out", "mkv", srt_name + ".mkv")
    if not os.path.exists(video):
        raise PipelineError("揣無影片：%s" % video)
    kwargs = {}
    if floor is not None:
        kwargs["floor"] = floor
    if long is not None:
        kwargs["long"] = long
    out = []
    for cue in blind_cues.risky(cues, **kwargs):
        got = masks_of(video, cue, region, spec)
        for seg in segments(cue, got, frame_dt=1.0 / FPS):
            seg["why"] = cue["why"]
            out.append(seg)
    return out


def _timeline(srt_name):
    """The cue timeline: from the store, or the work dir if unpublished.

    An episode still carrying `pending` has no timeline in the store yet --
    it is written by `publish`. Reading only the store silently skips exactly
    the episodes a batch is in the middle of, which is how the first band
    scan lost 20210222_053, the very episode it was written to examine.
    """
    path = os.path.join(paths.KARI, "news", "1-ocr", "1-cues",
                        paths.month_of(srt_name), srt_name + ".json")
    if not os.path.exists(path):
        hits = sorted(glob.glob(os.path.join(
            paths.KITHANN, "out", "mxf", "*.work", "cues.json")))
        for hit in hits:
            if srt_name.split("_")[1] in hit:
                path = hit
                break
    if not os.path.exists(path):
        raise PipelineError("揣無時間軸：%s" % srt_name)
    with open(path, encoding="utf-8") as handle:
        doc = json.load(handle)
    if isinstance(doc, list):
        return {"cues": doc}
    doc.setdefault("cues", [])
    return doc


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("srt_name")
    ap.add_argument("--video", default=None)
    ap.add_argument("--floor", type=float, default=None)
    ap.add_argument("--long", type=float, default=None)
    args = ap.parse_args(argv)
    name = paths.check_srt_name(args.srt_name)
    got = plan(name, args.video, args.floor, args.long)
    for seg in got:
        print("%s\t%d\t%d\t%.2f\t%.2f\t%s"
              % (name, seg["cue"], seg["part"], seg["start"], seg["end"],
                 seg["why"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
