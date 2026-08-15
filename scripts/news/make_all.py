#!/usr/bin/env python3
"""Turn every finished work dir into an SRT and record progress in smkul.csv.

Safe to re-run at any point: episodes still decoding are simply reported as
待處理, so the tracker can be refreshed while the long pass is running.
"""
import json
import os
import sys

from scripts.news import make_srt
from scripts.news import paths
from scripts.news import tracker

WORK = paths.WORK
SRT_DIR = paths.SRT_DIR


def vision_complete(work):
    """True when every cue of a plan-B dir has actually been read.

    A part-finished vision pass is normal -- it is designed to be resumable --
    but only a finished one may replace the 文稿/tesseract output wholesale,
    so this insists on every cue being marked verified rather than merely on
    the directory existing.

    It compares the two sets of cue numbers rather than their sizes. Counting
    is not checking: rebuilding the contact sheets renumbers the cues, so a
    verified.json can carry rows for numbers that no longer exist, reach the
    total, and hide real cues that nobody has read. The episode would then be
    assembled and published with subtitles simply missing from it.
    """
    cues = os.path.join(work, "cues.json")
    verified = os.path.join(work, "verified.json")
    if not (os.path.exists(cues) and os.path.exists(verified)):
        return False
    with open(cues, encoding="utf-8") as handle:
        wanted = set()
        for cue in json.load(handle)["cues"]:
            wanted.add(str(cue["index"]))
    with open(verified, encoding="utf-8") as handle:
        marked = json.load(handle)
    read = set()
    for index in marked:
        if marked[index]:
            read.add(str(index))
    return bool(wanted) and wanted <= read


def make_one(entry):
    """Build one episode's SRT; return its status line."""
    slug = entry["slug"]
    work = os.path.join(WORK, slug + ".work")
    if not os.path.exists(os.path.join(work, "cues.json")):
        return "待處理（尚未切cue）"

    # The vision pass is where the text comes from: read off the contact
    # sheets by a human, cue by cue. An episode is only assembled once every
    # one of its cues has been read -- a half-read pass is a normal state
    # (the pass is designed to be resumable) but not a deliverable one.
    vision = os.path.join(WORK, slug + ".B.work")
    if not vision_complete(vision):
        return "待處理（已切cue，尚未校讀完）"

    out = os.path.join(SRT_DIR, entry["srt_name"] + ".srt")
    qc = make_srt.run(vision, out)
    return tracker.vision_status(qc["srt_lines"], qc["cues"])


def main():
    entries = json.load(open(paths.INVENTORY,
                             encoding="utf-8"))
    os.makedirs(SRT_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(paths.TRACKER_CACHE), exist_ok=True)

    # Every episode gets a row here, pending ones included -- that is the
    # point of the working copy: it is where you look to see how far the
    # batch has got. Do NOT reach for tracker.tracker_rows(), which drops
    # pending episodes; that rule is for the delivered table, whose every
    # row has to be rebuildable from the store.
    rows = []
    for entry in entries:
        if entry["truncated"]:
            status = tracker.skipped_status(entry["truncated"])
        else:
            status = make_one(entry)
        rows.append(tracker.tracker_row(entry, status))
        print("%-46s %s" % (entry["srt_name"], status))

    # The working copy, not the deliverable. `publish` writes the one in
    # Kari-SRT, and only once every episode in the batch is finished -- see
    # paths.TRACKER_CACHE for why a mid-batch table cannot live in the store.
    tracker.write_tracker(rows, paths.TRACKER_CACHE)
    print("\nwrote", paths.TRACKER_CACHE)
    print("(Kari-SRT/news/smkul.csv is written by `publish`, once the whole "
          "batch is done)")


if __name__ == "__main__":
    sys.exit(main())
