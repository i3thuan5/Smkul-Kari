"""Longest run of blank cues in each episode's vision TSVs, and when it was.

A subtitle stretch printed below `REGION` reaches the reader as a blank
strip, so it shows up here as an unusually long run of empty text. Ordinary
gaps -- an establishing shot, a graphic card -- run a handful of cues.
"""
import glob
import json
import os
import sys

sys.path.insert(0, "/workspaces/Smkul-Kari")
from scripts.news import paths          # noqa: E402


def blanks(name):
    """(cue, text) for the episode, in cue order."""
    month = paths.month_of(name)
    folder = os.path.join(paths.KARI_VISION, month, name)
    rows = {}
    for path in sorted(glob.glob(folder + "/b*.tsv")):
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                parts = line.rstrip("\n").split("\t")
                if len(parts) >= 3 and parts[0].isdigit():
                    rows[int(parts[0])] = parts[2].strip()
    return rows


def runs_of_blank(rows):
    """Contiguous stretches of empty text: list of (first, last)."""
    spans = []
    start = None
    last = None
    for cue in sorted(rows):
        # Strip here as well as on the way in: a reader who leaves one
        # space in the third column would otherwise read as text, and
        # this runs over stores written before that was tidied up.
        if not rows[cue].strip():
            if start is None:
                start = cue
            last = cue
        elif start is not None:
            spans.append((start, last))
            start = None
    if start is not None:
        spans.append((start, last))
    return spans


def when(name, first, last):
    """Seconds covered by cues `first`..`last`, off the store's cues.json."""
    path = os.path.join(paths.KARI_CUES, paths.month_of(name), name + ".json")
    if not os.path.exists(path):
        return None
    cues = json.load(open(path, encoding="utf-8"))["cues"]
    if last > len(cues):
        return None
    return cues[first - 1]["start"], cues[last - 1]["end"]


if __name__ == "__main__":
    out = []
    for folder in sorted(glob.glob(paths.KARI_VISION + "/*/*")):
        name = os.path.basename(folder)
        rows = blanks(name)
        if not rows:
            continue
        spans = runs_of_blank(rows)
        longest = 0
        where = None
        for first, last in spans:
            if last - first + 1 > longest:
                longest = last - first + 1
                where = (first, last)
        total = 0
        for first, last in spans:
            if last - first + 1 >= 20:
                total += last - first + 1
        out.append((total, longest, name, where, len(rows)))
    out.sort(reverse=True)
    print("空白≥20連\t上長連\t集\t上長彼段(cue)\t時間\t總 cue")
    for total, longest, name, where, size in out:
        if total == 0:
            continue
        span = when(name, where[0], where[1]) if where else None
        stamp = "%.0f–%.0fs" % span if span else "-"
        print("%d\t%d\t%s\t%d–%d\t%s\t%d"
              % (total, longest, name, where[0], where[1], stamp, size))
