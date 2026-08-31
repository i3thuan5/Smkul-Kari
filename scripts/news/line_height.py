#!/usr/bin/env python3
"""Report cues whose lettering is not the size this episode's subtitles are.

    python3 -m scripts.news.line_height                  # every episode
    python3 -m scripts.news.line_height <srt_name> ...   # just these

WHY
---
A news headline strap sits **inside** the subtitle band, in subtitle-ish
white-on-outline lettering, so neither "where is it" nor "what does it look
like" separates it from speech. 20210207_038_晚間_Pinuyumayan_卑南 carries
`大武鄉推生態旅遊 山豬窟"千年神榕"成焦點` across thirteen cues and 23.1
seconds of the delivered SRT because of that.

What does separate them is **size**: the strap is about half the height of
a dialogue line -- 46 px against this episode's median of 67. One reader
found the same thing independently on 20210228_059_晚間_Pinuyumayan_卑南
(~30 px against 59-60) and left the strap blank for that reason.

WHAT THIS DOES NOT DO
---------------------
It does not edit anything. The measurement is good enough to screen with
and not good enough to act on: a strip is a median composite, so a line
that is only on screen for part of its cue measures short, and on 038晚 the
run of thirteen only flagged three. Getting it wrong means deleting real
dialogue, which is worse than shipping one headline strap, so the output is
a list to look at.
"""
import argparse
import glob
import os
import sys

import numpy as np
from PIL import Image

from scripts.news import paths
from scripts.ocr import cuelib

RATIO = 0.7
MIN_ROW_INK = 12


def unusual(heights, ratio=RATIO):
    """Cue numbers whose lettering is shorter than `ratio` of the median.

    Only shorter: a *taller* line is two rows of subtitle, which is a
    different thing and a real one.
    """
    values = sorted(heights.values())
    if len(values) < 2:
        return []
    median = values[len(values) // 2]
    if not median:
        return []
    out = []
    for cue in sorted(heights):
        if heights[cue] < median * ratio:
            out.append(cue)
    return out


def runs(flagged):
    """Contiguous stretches of flagged cues, as (first, last).

    A lone flag is usually the composite measuring short; a run of them is
    a strap that stayed on screen.
    """
    out = []
    start = last = None
    for cue in flagged:
        if start is None:
            start = last = cue
        elif cue == last + 1:
            last = cue
        else:
            out.append((start, last))
            start = last = cue
    if start is not None:
        out.append((start, last))
    return out


def strip_height(path, spec=None):
    """Rows of ink in one strip, or 0 when there is none."""
    if not os.path.exists(path):
        return None
    spec = spec or cuelib.MaskSpec()
    mask = cuelib.text_mask(np.array(Image.open(path).convert("RGB")), spec)
    rows = np.where(mask.sum(axis=1) > MIN_ROW_INK)[0]
    if not len(rows):
        return 0
    return int(rows[-1] - rows[0] + 1)


def episode_text(name):
    """{cue: text} off the store's vision TSVs."""
    folder = os.path.join(paths.KARI_VISION, paths.month_of(name), name)
    out = {}
    for path in glob.glob(os.path.join(folder, "b*.tsv")):
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                parts = line.rstrip("\n").split("\t")
                if parts[0].isdigit():
                    out[int(parts[0])] = (parts[2] if len(parts) > 2
                                          else "").strip()
    return out


def workdir_of(slug):
    return os.path.join(paths.WORK, slug + ".B.work")


def measure(slug, text):
    """{cue: height} for the cues that carry text."""
    work = workdir_of(slug)
    spec = cuelib.MaskSpec()
    out = {}
    for cue in sorted(text):
        if not text[cue]:
            continue
        got = strip_height("%s/strips/%05d_han.png" % (work, cue), spec)
        if got is not None:
            out[cue] = got
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("names", nargs="*", help="srt_names; default every one")
    ap.add_argument("--ratio", type=float, default=RATIO)
    args = ap.parse_args(argv)

    total = 0
    for entry in paths.load_inventory():
        name = entry["srt_name"]
        if args.names and name not in args.names:
            continue
        if not os.path.isdir(workdir_of(entry["slug"]) + "/strips"):
            continue
        text = episode_text(name)
        if not text:
            continue
        heights = measure(entry["slug"], text)
        flagged = unusual(heights, args.ratio)
        if not flagged:
            continue
        values = sorted(heights.values())
        median = values[len(values) // 2]
        for first, last in runs(flagged):
            length = last - first + 1
            total += length
            print("%s  cue %d–%d（%d 條，%d px／中位 %d）  %s"
                  % (name, first, last, length,
                     heights[first], median, text[first][:30]))
    print("\n合計 %d 條愛看" % total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
