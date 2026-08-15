#!/usr/bin/env python3
"""Refine cue boundaries from the 0.2s coarse grid to a high-fps re-read.

    python3 -m scripts.news.refine_cues VIDEO CUES_JSON            # in place
    python3 -m scripts.news.refine_cues VIDEO CUES_JSON --dry-run  # report

The coarse pass sampled at 5fps, so every boundary sits on a 0.2s grid and
the true switch point lies somewhere inside +/-0.2s of it. This pass decodes
only those windows again at 25fps (0.04s grid) and classifies each frame
against the two sides the coarse pass already identified -- it never
re-segments, so the cue set, numbering and text mapping cannot change. Only
start/end values move, each by at most MAX_SHIFT.

Classification leans on a guarantee of the coarse grid: at 0.24s outside a
coarse boundary the window edge is provably still inside the neighbouring
cue (its true edge is within 0.2s of the coarse one), so the window's own
edge frames supply the reference masks and no extra decoding is needed.

Atomicity: an episode is validated in full -- every refined boundary within
MAX_SHIFT of its coarse value, starts before ends, no overlap -- before its
cues.json is rewritten. Any violation names the cue and leaves the file
untouched. Boundaries whose window cannot be classified (occluders, missing
landmarks) keep their coarse value and are counted in the report.

The manifest gains `"refined": true` and (via ffprobe, since the coarse
manifests never stored it) `"duration"`, which the SRT padding rule needs.
"""
import argparse
import json
import os
import subprocess
import sys

from scripts.ocr import cuelib

FPS = 25.0
WINDOW = 0.24
CONFIRM = 2          # consecutive frames before a side is believed
MAX_SHIFT = 0.2


def probe_duration(video):
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", video], capture_output=True, text=True)
    try:
        return float(proc.stdout.strip())
    except ValueError:
        raise SystemExit("cannot probe duration of %s" % video)


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
        mask = cuelib.text_mask(rgb, spec)
        masks.append(mask)
        inks.append(int(mask.sum()))
    labels = []

    if kind == "start":
        ref = masks[-1]
        if inks[-1] < min_ink:
            return None              # right edge should show the cue
        for i in range(len(masks)):
            if inks[i] < min_ink:
                labels.append("L")
            elif cuelib.mask_distance(masks[i], ref) <= change:
                labels.append("R")
            else:
                labels.append("?")
        return labels

    if kind == "end":
        ref = masks[0]
        if inks[0] < min_ink:
            return None              # left edge should show the cue
        for i in range(len(masks)):
            if inks[i] < min_ink:
                labels.append("R")
            elif cuelib.mask_distance(masks[i], ref) <= change:
                labels.append("L")
            else:
                labels.append("?")
        return labels

    ref_l = masks[0]
    ref_r = masks[-1]
    if inks[0] < min_ink or inks[-1] < min_ink:
        return None                  # both edges should show text
    if cuelib.mask_distance(ref_l, ref_r) <= change:
        return None                  # sides indistinguishable: keep coarse
    for i in range(len(masks)):
        if inks[i] < min_ink:
            labels.append("?")
        else:
            d_l = cuelib.mask_distance(masks[i], ref_l)
            d_r = cuelib.mask_distance(masks[i], ref_r)
            if d_l <= change and d_l < d_r:
                labels.append("L")
            elif d_r <= change and d_r < d_l:
                labels.append("R")
            else:
                labels.append("?")
    return labels


def refine_boundary(video, region, spec, min_ink, change, t0, kind,
                    duration):
    lo = max(0.0, t0 - WINDOW)
    hi = min(duration, t0 + WINDOW)
    if hi - lo < 2.0 / FPS:
        return None
    frames = []
    for t, rgb in cuelib.stream_region(video, region, FPS, start=lo,
                                       duration=hi - lo):
        frames.append((t, rgb))
    if len(frames) < 2 * CONFIRM + 1:
        return None
    labels = label_frames(frames, kind, spec, min_ink, change)
    if labels is None:
        return None
    times = []
    for t, _rgb in frames:
        times.append(t)
    return transition_time(times, labels)


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


def refine_episode(video, cues_path, dry_run=False):
    with open(cues_path, encoding="utf-8") as handle:
        manifest = json.load(handle)
    cues = manifest["cues"]
    region = manifest["region"]
    spec = cuelib.MaskSpec.from_dict(manifest.get("mask", {}))
    seg = manifest.get("segmenter", {})
    min_ink = seg.get("min_ink", 120)
    change = seg.get("change", 0.35)
    duration = probe_duration(video)

    new_start = {}
    new_end = {}
    kept = 0
    refined = 0
    shifts = []
    problems = []
    for positions, kind, t0 in boundaries_of(cues):
        t = refine_boundary(video, region, spec, min_ink, change, t0, kind,
                            duration)
        if t is None:
            kept += 1
            continue
        if abs(t - t0) > MAX_SHIFT + 1e-9:
            problems.append("cue %s %s: shift %.3fs exceeds %.1fs"
                            % (cues[positions[0]]["index"], kind,
                               t - t0, MAX_SHIFT))
            continue
        refined += 1
        shifts.append(t - t0)
        if kind == "start":
            new_start[positions[0]] = t
        elif kind == "end":
            new_end[positions[0]] = t
        else:
            new_end[positions[0]] = t
            new_start[positions[1]] = t

    result = []
    for i, cue in enumerate(cues):
        start = new_start.get(i, cue["start"])
        end = new_end.get(i, cue["end"])
        result.append((round(start, 3), round(end, 3)))

    for i, (start, end) in enumerate(result):
        if start >= end:
            problems.append("cue %s: start %.3f >= end %.3f"
                            % (cues[i]["index"], start, end))
        if i and result[i - 1][1] > start + 1e-9:
            problems.append("cue %s overlaps its predecessor"
                            % cues[i]["index"])

    stats = {
        "episode": os.path.basename(cues_path)[:-5],
        "boundaries": kept + refined + len(problems),
        "refined": refined,
        "kept_coarse": kept,
        "max_shift": round(max(map(abs, shifts)), 3) if shifts else 0.0,
        "mean_shift": (round(sum(map(abs, shifts)) / len(shifts), 3)
                       if shifts else 0.0),
        "duration": round(duration, 3),
    }

    if problems:
        for line in problems:
            print("FAIL:", line)
        raise SystemExit(1)
    if dry_run:
        return stats

    for i, cue in enumerate(cues):
        cue["start"], cue["end"] = result[i]
    manifest["refined"] = True
    manifest["duration"] = round(duration, 3)
    with open(cues_path, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False)
    return stats


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("video")
    ap.add_argument("cues", help="cues.json to refine in place")
    ap.add_argument("--dry-run", action="store_true",
                    help="report the shifts, write nothing")
    args = ap.parse_args()
    stats = refine_episode(args.video, args.cues, dry_run=args.dry_run)
    print(json.dumps(stats, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
