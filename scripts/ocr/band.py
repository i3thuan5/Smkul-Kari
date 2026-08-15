#!/usr/bin/env python3
"""Deciding which strip of pixels holds the subtitle.

Two ways to arrive at a region, and the difference matters. A preset is the
caller stating the layout, from what the file sits in; detection is this
module guessing from the picture. On broadcast news the guess is not
trustworthy on its own -- it ranks the weather graphic and the station's
lower-third above the dialogue line -- so detection is a proposal to confirm
by eye, and a preset is what a batch run should be given.
"""
import json
import os
import subprocess

import numpy as np

from scripts.ocr import cuelib


# --------------------------------------------------------------- presets
#
# The engine holds no preset file of its own: presets describe a corpus
# (which programme, which layout), so the caller says where they live
# (`--presets`). See scripts/news/presets.json for the TITV news set.


def load_presets(path):
    if not path or not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def match_preset(video_path, presets_path):
    """Pick a preset whose `match` substring occurs in the file name."""
    name = os.path.basename(video_path)
    presets = load_presets(presets_path)
    for key in sorted(presets):
        preset = presets[key]
        needle = preset.get("match")
        if needle and needle in name:
            return key, preset
    return None, None


# ---------------------------------------------------------- band detect


def detect_band(video_path, samples=120, spec=None, search_top=0.55,
                min_hits=0.04, max_band=220):
    """Propose a subtitle band by asking which rows hold text most often.

    Sampling is spread across the whole file rather than taken from one
    stretch, so a band that only appears during interviews still registers.
    """
    if spec is None:
        spec = cuelib.MaskSpec()
    info = probe_or_die(video_path)
    width = info["width"]
    height = info["height"]
    top = int(height * search_top)
    region = cuelib.normalize_region((0, top, width, height - top),
                                     width, height)
    top = region[1]

    # Accumulate the full row x column profile, not just the two margins.
    # The horizontal extent has to be measured *inside* the band that ends up
    # being chosen -- measuring it across the whole search area lets a station
    # logo or a passing highlight elsewhere in the frame decide where the
    # subtitle starts and ends, which silently clips text off both sides.
    step = max(info["duration"] / float(samples), 0.5)
    profile = np.zeros((height - top, width), dtype=np.float64)
    taken = 0
    for index in range(samples):
        ts = step * index
        if ts >= info["duration"]:
            break
        frames = grab_burst(video_path, ts, region, count=2)
        if len(frames) < 2:
            continue
        mask = stable_text_mask(frames, spec)
        if mask is None:
            continue
        profile += mask
        taken += 1
    if taken == 0:
        raise RuntimeError("could not sample any frame from %s" % video_path)
    profile /= taken
    rows = profile.sum(axis=1)

    region, ranked = region_from_profile(profile, top, width, height,
                                         min_hits=min_hits,
                                         max_band=max_band)
    return {
        "region": region,
        "candidates": ranked,
        "row_profile": rows.tolist(),
        "row_offset": top,
        "samples": taken,
    }


def region_from_profile(profile, top, width, height,
                        min_hits=0.04, max_band=220, pad=6):
    """Turn a row x column ink profile into a proposed crop box.

    Split out of detect_band so it can be exercised without decoding a video.
    That matters: this is the arithmetic where a candidate band's height once
    shared the name `height` with the frame height, and shadowing it collapsed
    the returned box to 2px -- a bug no amount of reading the profile code
    would reveal, because the profile was right and only the last few lines
    were wrong.

    Takes the whole 2D profile rather than pre-summed margins because the
    horizontal extent must be measured inside the chosen band; a column
    profile summed over the entire search area lets ink from elsewhere in the
    frame decide where the subtitle begins and ends.
    """
    rows = profile.sum(axis=1)
    threshold = max(rows.max() * min_hits, 1.0)
    bands = []
    start = None
    for y in range(len(rows)):
        if rows[y] >= threshold and start is None:
            start = y
        elif rows[y] < threshold and start is not None:
            bands.append((start, y))
            start = None
    if start is not None:
        bands.append((start, len(rows)))

    # Keep the merge gap small: a news lower-third sitting just below the
    # dialogue is also text, and merging the two produces one 300px "band"
    # that is mostly station graphics.
    merged = merge_bands(bands, gap=8)
    candidates = []
    for lo, hi in merged:
        band_h = hi - lo
        if band_h < 16 or band_h > max_band:
            continue
        candidates.append((float(rows[lo:hi].sum()), lo, hi))
    if not candidates:
        for lo, hi in merged:
            candidates.append((float(rows[lo:hi].sum()), lo, hi))
    if not candidates:
        raise RuntimeError("no subtitle band found; pass --region manually")

    candidates.sort(reverse=True)
    ranked = []
    for weight, lo, hi in candidates:
        ranked.append({"y": top + lo, "h": hi - lo,
                       "weight": round(weight, 1)})

    _, lo, hi = candidates[0]
    y0 = max(top + lo - pad, 0)
    y1 = min(top + hi + pad, height)

    cols = profile[lo:hi, :].sum(axis=0)
    col_thresh = max(cols.max() * 0.02, 0.5)
    xs = np.nonzero(cols >= col_thresh)[0]
    if len(xs):
        x0 = max(int(xs[0]) - 12, 0)
        x1 = min(int(xs[-1]) + 13, width)
    else:
        x0, x1 = 0, width

    region = cuelib.normalize_region((x0, y0, x1 - x0, y1 - y0),
                                     width, height)
    if region[3] < 12:
        # The chosen band was tens of pixels tall; if the box that came out
        # is not, the arithmetic above lost track of the frame height.
        raise RuntimeError(
            "band detection produced a %dpx-tall region from a %dpx band "
            "-- refusing to return it" % (region[3], hi - lo))
    return region, ranked


def merge_bands(bands, gap):
    merged = []
    for lo, hi in bands:
        if merged and lo - merged[-1][1] <= gap:
            merged[-1] = (merged[-1][0], hi)
        else:
            merged.append((lo, hi))
    return merged


def split_lines(video_path, region, spec, samples=80, min_gap=10, pad=10):
    """Split a band into individual text lines by finding blank rows.

    Video A stacks Amis over Chinese in one band; each needs its own OCR
    language, so they have to be cut apart before recognition.

    The threshold has to stay low and the result has to be padded: a row
    holding only the dot of an `i` or the tail of a `g` carries a tiny
    fraction of the peak row's ink, and clipping those rows away hands the
    recogniser decapitated glyphs.
    """
    info = probe_or_die(video_path)
    step = max(info["duration"] / float(samples), 0.5)
    rows = np.zeros(region[3], dtype=np.float64)
    taken = 0
    for index in range(samples):
        ts = step * index
        if ts >= info["duration"]:
            break
        frames = grab_burst(video_path, ts, region, count=2)
        if len(frames) < 2:
            continue
        mask = stable_text_mask(frames, spec)
        if mask is None:
            continue
        rows += mask.sum(axis=1)
        taken += 1
    if taken:
        rows /= taken

    threshold = max(rows.max() * 0.03, 0.3)
    runs = []
    start = None
    for y in range(len(rows)):
        if rows[y] >= threshold and start is None:
            start = y
        elif rows[y] < threshold and start is not None:
            runs.append((start, y))
            start = None
    if start is not None:
        runs.append((start, len(rows)))

    runs = merge_bands(runs, gap=min_gap)
    kept = []
    for lo, hi in runs:
        if hi - lo >= 12:
            kept.append((lo, hi))

    # Pad to recover ascenders and descenders, but never by more than half
    # the gap to the neighbouring line -- otherwise video A's stacked Amis
    # and Chinese lines grow into each other and merge back into one band,
    # and they need separate OCR languages.
    padded = []
    for index, (lo, hi) in enumerate(kept):
        up = pad
        down = pad
        if index > 0:
            up = min(pad, max((lo - kept[index - 1][1]) // 2, 0))
        if index + 1 < len(kept):
            down = min(pad, max((kept[index + 1][0] - hi) // 2, 0))
        padded.append((max(lo - up, 0), min(hi + down, region[3])))
    return padded, rows.tolist()


# ------------------------------------------------------------- ffmpeg io


def probe_or_die(video_path):
    try:
        return cuelib.probe_video(video_path)
    except Exception as exc:
        raise SystemExit("ffprobe failed on %s: %s" % (video_path, exc))


def grab_frame(video_path, ts, region):
    x, y, w, h = cuelib.normalize_region(region)
    cmd = [
        "ffmpeg", "-v", "error", "-ss", "%.3f" % ts, "-i", video_path,
        "-frames:v", "1",
        "-vf", cuelib.crop_chain((x, y, w, h), "format=rgb24"),
        "-f", "rawvideo", "-",
    ]
    out = subprocess.run(cmd, stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL).stdout
    if len(out) < w * h * 3:
        return None
    return np.frombuffer(out[:w * h * 3], dtype=np.uint8).reshape(h, w, 3)


def grab_burst(video_path, ts, region, count=2, fps=5.0):
    """Grab `count` consecutive samples from one seek."""
    x, y, w, h = cuelib.normalize_region(region)
    span = (count + 0.5) / float(fps)
    cmd = [
        "ffmpeg", "-v", "error", "-ss", "%.3f" % ts, "-t", "%.3f" % span,
        "-i", video_path,
        "-vf", "fps=%s,%s" % (
            fps, cuelib.crop_chain((x, y, w, h), "format=rgb24")),
        "-f", "rawvideo", "-",
    ]
    out = subprocess.run(cmd, stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL).stdout
    nbytes = w * h * 3
    frames = []
    for index in range(count):
        chunk = out[index * nbytes:(index + 1) * nbytes]
        if len(chunk) < nbytes:
            break
        frames.append(np.frombuffer(chunk, dtype=np.uint8).reshape(h, w, 3))
    return frames


def stable_text_mask(frames, spec):
    """Mask of text pixels that held still across the whole burst.

    A subtitle is frozen for its entire cue; footage underneath it is not.
    Intersecting the masks of frames a fifth of a second apart therefore
    keeps glyphs and drops moving content -- which is what stops band
    detection from locking onto a busy background.
    """
    mask = None
    for frame in frames:
        current = cuelib.text_mask(frame, spec)
        if mask is None:
            mask = current
        else:
            mask &= current
    if mask is None:
        return None
    return mask
