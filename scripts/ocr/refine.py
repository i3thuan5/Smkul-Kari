"""Boundary refinement: where exactly a subtitle appears or goes.

The coarse cut judges one frame per 0.2 s, so every boundary it reports is
within 0.2 s of the true switch. This module re-reads a +/-WINDOW stretch
around each boundary at the source's own frame rate (0.033 s at 29.97 fps)
and classifies each frame against the two sides the coarse cut already
identified -- it never re-segments, so the cue set cannot change.

All windows of an episode go through one ffmpeg run (`decode.stream_frames`
with a select filter), not one run per boundary.

Classification leans on a guarantee of the coarse grid: at WINDOW outside a
coarse boundary the window edge is provably still inside the neighbouring
cue (its true edge is within 0.2 s of the coarse one), so the window's own
edge frames supply the reference masks and no extra decoding is needed.
"""
from scripts.ocr import cuelib
from scripts.ocr import decode

WINDOW = 0.24
CONFIRM = 2          # consecutive frames before a side is believed
MIN_FRAMES = 2 * CONFIRM + 1

# Why a boundary kept its coarse value. Counted apart: frames missing is a
# file-edge or decoding matter, unclear is the picture itself.
NO_FRAMES = "no_frames"
UNCLEAR = "unclear"


def confirmed_runs(labels, confirm):
    """[(label, first_index, last_index)] for runs of length >= confirm."""
    runs = []
    i = 0
    while i < len(labels):
        j = i
        while j + 1 < len(labels) and labels[j + 1] == labels[i]:
            j += 1
        if labels[i] != "?" and j - i + 1 >= confirm:
            runs.append((labels[i], i, j))
        i = j + 1
    return runs


def transition_time(times, labels, confirm=CONFIRM):
    """Where the window switches from its left side to its right side.

    `labels` marks each frame 'L' (still the left side), 'R' (already the
    right side) or '?'. The window must open on a confirmed L run and close
    on a confirmed R run; the boundary is the MIDPOINT between the last L
    frame and the first R frame. One rule covers both shapes: with the runs
    adjacent the true switch lies somewhere in that one frame interval and
    the midpoint centres the error (+/-0.02s instead of 0-0.04s late);
    with unclassifiable frames between them (interlaced transition frames)
    it is the midpoint of that stretch, per the spec.

    (The first delivery of the 35-episode back-refinement used the older
    first-R-frame rule -- a systematic 0-0.04s late bias, still within the
    0.05s budget. Not re-run; this rule applies from the next batch on.)

    Returns None when the window does not show that shape -- the caller
    keeps the coarse value.
    """
    runs = confirmed_runs(labels, confirm)
    if len(runs) < 2:
        return None
    if runs[0][0] != "L" or runs[-1][0] != "R":
        return None
    last_l = None
    first_r = None
    for label, first, last in runs:
        if label == "L":
            if first_r is not None:
                return None          # R before an L: not a clean switch
            last_l = last
        else:
            if first_r is None:
                first_r = first
    if last_l is None or first_r is None:
        return None
    return (times[last_l] + times[first_r]) / 2.0


def label_frames(frames, kind, spec, min_ink, change):
    """'L'/'R'/'?' per frame for one boundary window.

    kind:  'start'  blank -> cue        (L = blank, R = the cue)
           'end'    cue -> blank        (L = the cue, R = blank)
           'joint'  cue A -> cue B      (L = A, R = B)

    Reference masks come from the window's own edges: the first frame is
    guaranteed inside the left side, the last inside the right side.
    """
    masks = []
    inks = []
    for _t, rgb in frames:
        mask = cuelib.frame_mask(rgb, spec)
        masks.append(mask)
        inks.append(int(mask.sum()))

    if kind == "start":
        if inks[-1] < min_ink:
            return None              # right edge should show the cue
        return _label_one_sided(masks, inks, masks[-1], min_ink, change,
                                blank="L", cue="R")
    if kind == "end":
        if inks[0] < min_ink:
            return None              # left edge should show the cue
        return _label_one_sided(masks, inks, masks[0], min_ink, change,
                                blank="R", cue="L")
    return _label_joint(masks, inks, min_ink, change)


def _label_one_sided(masks, inks, ref, min_ink, change, blank, cue):
    """Labels when one side is blank ('start' and 'end' windows)."""
    labels = []
    for i in range(len(masks)):
        if inks[i] < min_ink:
            labels.append(blank)
        elif cuelib.mask_distance(masks[i], ref) <= change:
            labels.append(cue)
        else:
            labels.append("?")
    return labels


def _nearer_side(mask, ref_l, ref_r, change):
    d_l = cuelib.mask_distance(mask, ref_l)
    d_r = cuelib.mask_distance(mask, ref_r)
    if d_l <= change and d_l < d_r:
        return "L"
    if d_r <= change and d_r < d_l:
        return "R"
    return "?"


def _label_joint(masks, inks, min_ink, change):
    """Labels for a shared edge: cue A on the left, cue B on the right."""
    ref_l = masks[0]
    ref_r = masks[-1]
    if inks[0] < min_ink or inks[-1] < min_ink:
        return None                  # both edges should show text
    if cuelib.mask_distance(ref_l, ref_r) <= change:
        return None                  # sides indistinguishable: keep coarse
    labels = []
    for i in range(len(masks)):
        if inks[i] < min_ink:
            labels.append("?")
        else:
            labels.append(_nearer_side(masks[i], ref_l, ref_r, change))
    return labels


def boundaries_of(cues):
    """[(cue_index_positions, kind, coarse_time)] in play order.

    A shared edge (cue ends exactly where the next begins) is one 'joint'
    boundary updating both sides; everything else is a plain start or end.
    """
    out = []
    for i, cue in enumerate(cues):
        prev = cues[i - 1] if i else None
        if prev is not None and abs(prev["end"] - cue["start"]) < 1e-9:
            pass                     # handled as the previous cue's joint
        else:
            out.append(((i,), "start", cue["start"]))
        nxt = cues[i + 1] if i + 1 < len(cues) else None
        if nxt is not None and abs(cue["end"] - nxt["start"]) < 1e-9:
            out.append(((i, i + 1), "joint", cue["end"]))
        else:
            out.append(((i,), "end", cue["end"]))
    return out


def windows_of(boundaries, duration):
    """(lo, hi) around each boundary, clipped to the file."""
    windows = []
    for _positions, _kind, t0 in boundaries:
        windows.append((max(0.0, t0 - WINDOW), min(duration, t0 + WINDOW)))
    return windows


def judge_window(frames, kind, spec, min_ink, change):
    """(time, None) for a clean switch, else (None, reason)."""
    if len(frames) < MIN_FRAMES:
        return (None, NO_FRAMES)
    labels = label_frames(frames, kind, spec, min_ink, change)
    if labels is None:
        return (None, UNCLEAR)
    times = []
    for t, _rgb in frames:
        times.append(t)
    found = transition_time(times, labels)
    if found is None:
        return (None, UNCLEAR)
    return (found, None)


def refine_all(video, region, spec, min_ink, change, boundaries, duration,
               threads=decode.DEFAULT_THREADS):
    """[(time or None, reason)] per boundary, from one decoder run.

    A decoder failure raises (RuntimeError from `decode`); nothing is
    returned half done.
    """
    windows = windows_of(boundaries, duration)
    results = [(None, NO_FRAMES)] * len(boundaries)
    if not boundaries:
        return results
    frames = decode.stream_frames(video, region, windows=windows,
                                  threads=threads)
    for index, got in decode.window_frames(frames, windows):
        _positions, kind, _t0 = boundaries[index]
        results[index] = judge_window(got, kind, spec, min_ink, change)
    return results
