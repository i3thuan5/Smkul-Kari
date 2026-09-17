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

from scripts.news import episodes
from scripts.news import paths
from scripts.news.vision_tools import prompt
from scripts.errors import PipelineError

WORK = paths.WORK
OUT = paths.KARI_VISION


# One planner, one list: `prompt` both cuts the batches and names their TSVs,
# and this prints exactly that. See `prompt.batches_of` and
# `prompt.tsv_names` for why the two used to disagree.
pending_sheets = prompt.pending_sheets


def srt_name_of(slug):
    """The name Kari-SRT files this episode's transcripts under.

    It has to come from the inventory, not from chopping up the slug: the two
    names carry the same fields in a different order, and `ingest.py` and
    `rebuild.py` both look the TSVs up by srt_name. A guessed folder name
    means readers write where nothing will ever look, and the first sign of it
    is an episode that assembles with no text.
    """
    for entry in episodes.load():
        if entry["slug"] == slug:
            return entry["srt_name"]
    raise PipelineError("slug %r is not in inventory.json" % slug)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    args.slug = paths.check_name(args.slug, "slug")

    work = paths.work_dir(args.slug, WORK)
    tag = srt_name_of(args.slug)
    with open(paths.sheets_index(work), encoding="utf-8") as handle:
        sheets = json.load(handle)
    planned = prompt.batches_of(work)
    names = prompt.tsv_names(work, tag, len(planned))
    weights = dict(prompt.sheet_weights(work, sorted(sheets), sheets))
    print("# %s: %d sheet(s) pending in %d batch(es)"
          % (args.slug, len(pending_sheets(work)), len(planned)))
    for made, batch in enumerate(planned, 1):
        if args.limit and made > args.limit:
            break
        cues = []
        load = []
        for name in batch:
            cues += sheets[name]
            load.append(weights[name])
        cues = sorted(cues)
        print("\n=== batch %02d  (%d sheets, %d cues, ~%d tokens) ===" %
              (made, len(batch), len(cues), prompt.estimate(load)))
        print("DIR %s" % paths.sheets_dir(work))
        print("SHEETS %s" % " ".join(batch))
        print("CUES %d..%d" % (cues[0], cues[-1]))
        print("TSV %s" % os.path.join(paths.stage_path(OUT, tag),
                                      names[made - 1]))


if __name__ == "__main__":
    main()
