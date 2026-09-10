#!/usr/bin/env python3
"""Print the reading batches for an episode's gap sheets.

Each line is one subagent's worth of work: the sheet files to read, the cue
numbers they carry, and where the TSV should be written. Cue numbers in a gap
sheet are discontinuous by design -- the 文稿-aligned cues are missing -- so
the range is printed as a list of what is actually present, and a reader must
take the number from each strip's gutter rather than counting.
"""
import argparse
import json
import os

from scripts.news import paths
from scripts.news.vision_tools import prompt
from scripts.errors import PipelineError

WORK = paths.WORK
OUT = paths.KARI_VISION


def pending_sheets(work):
    """Sheets whose cues are not all verified yet."""
    with open(os.path.join(work, "sheets.json"), encoding="utf-8") as handle:
        sheets = json.load(handle)
    verified = {}
    path = os.path.join(work, "verified.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as handle:
            verified = json.load(handle)
    out = []
    for name in sorted(sheets):
        todo = []
        for index in sheets[name]:
            if not verified.get(str(index)):
                todo.append(index)
        if todo:
            out.append((name, sheets[name]))
    return out


def spans(count, size=None):
    """Where to cut `count` pending sheets into batches: a list of (lo, hi).

    Delegates to the reader brief's own planner instead of cutting here, so
    the two cannot drift: this module hands out the TSV names (b01, b02...)
    and `prompt` writes the brief for each of those numbers. They used to
    disagree about a short tail -- 51 sheets came out as three batches here
    and two there -- which sent two readers at the same cues under two
    names, and `ingest` refuses the episode ("cue X appears in both").

    `size` defaults to `prompt.SIZE` rather than to a number of its own,
    for the same reason: one knob, not two that have to be kept equal.
    """
    return prompt.plan(count, size or prompt.SIZE, prompt.MIN_TAIL)


def srt_name_of(slug):
    """The name Kari-SRT files this episode's transcripts under.

    It has to come from the inventory, not from chopping up the slug: the two
    names carry the same fields in a different order, and `ingest.py` and
    `rebuild.py` both look the TSVs up by srt_name. A guessed folder name
    means readers write where nothing will ever look, and the first sign of it
    is an episode that assembles with no text.
    """
    for entry in paths.load_inventory():
        if entry["slug"] == slug:
            return entry["srt_name"]
    raise PipelineError("slug %r is not in inventory.json" % slug)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("--size", type=int, default=None)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    args.slug = paths.check_name(args.slug, "slug")

    work = os.path.join(WORK, args.slug + ".B.work")
    tag = srt_name_of(args.slug)
    sheets = pending_sheets(work)
    print("# %s: %d sheet(s) pending" % (args.slug, len(sheets)))
    made = 0
    for lo, hi in spans(len(sheets), args.size):
        batch = sheets[lo:hi]
        made += 1
        if args.limit and made > args.limit:
            break
        names = []
        cues = []
        for name, on in batch:
            names.append(name)
            cues += on
        cues = sorted(cues)
        print("\n=== batch %02d  (%d sheets, %d cues) ===" %
              (made, len(names), len(cues)))
        print("DIR %s/sheets/" % work)
        print("SHEETS %s" % " ".join(names))
        print("CUES %d..%d" % (cues[0], cues[-1]))
        print("TSV %s/b%02d.tsv" % (paths.stage_path(OUT, tag), made))


if __name__ == "__main__":
    main()
