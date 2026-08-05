#!/usr/bin/env python3
"""Copy an episode's process data into Kari-SRT, the canonical store.

    python3 -m scripts.news.publish            # every finished episode
    python3 -m scripts.news.publish --check    # report, write nothing

`make_all.py` writes the deliverable SRTs straight into Kari-SRT/srt/, and
the vision TSVs are written there by the readers themselves. What is left is
the per-episode data that `rebuild.py` needs to put an SRT back together
without touching a video: `cues/<srt_name>.json`, `from_rtf/<srt_name>.json`,
and the inventory it walks. `migrate_kari.py` did this once for the February
batch as part of a one-off move; this does it for every batch after.

Only episodes whose vision pass is finished are published. A half-read
episode has no SRT yet, so shipping its cues would put an input in the store
for a deliverable that is not there -- exactly the inconsistency
`rebuild --verify` exists to catch.
"""
import argparse
import json
import os
import shutil
import sys

from scripts.news import make_all
from scripts.news import paths

WORK = paths.WORK


def publishable(entry):
    """(source work dir, reason it cannot be published)."""
    if entry["truncated"]:
        return "", "略過（%s）" % entry["truncated"]
    # The .B.work dir is the one make_all assembled the SRT from, so it is
    # the one whose cues.json the store must hold.
    work = os.path.join(WORK, entry["slug"] + ".B.work")
    if not os.path.exists(os.path.join(work, "cues.json")):
        return "", "尚未切cue"
    if not make_all.vision_complete(work):
        return "", "視覺辨識尚未讀完"
    return work, ""


def publish_one(entry, work):
    """Copy this episode's inputs into the store; return what was written."""
    written = []
    for name, folder in (("cues.json", paths.KARI_CUES),
                         ("from_rtf.json", paths.KARI_FROM_RTF)):
        source = os.path.join(work, name)
        if not os.path.exists(source):
            continue
        os.makedirs(folder, exist_ok=True)
        shutil.copy2(source, os.path.join(folder, entry["srt_name"] + ".json"))
        written.append(os.path.basename(folder))
    return written


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="report what would be published, write nothing")
    args = ap.parse_args()

    with open(paths.INVENTORY, encoding="utf-8") as handle:
        entries = json.load(handle)

    done = 0
    for entry in entries:
        work, reason = publishable(entry)
        if reason:
            print("skip  %-46s %s" % (entry["srt_name"], reason))
            continue
        if args.check:
            print("ready %s" % entry["srt_name"])
        else:
            written = publish_one(entry, work)
            print("write %-46s %s" % (entry["srt_name"], ", ".join(written)))
        done += 1

    if args.check:
        print("\n%d of %d episode(s) ready to publish (nothing written)"
              % (done, len(entries)))
        return 0

    shutil.copy2(paths.INVENTORY, os.path.join(paths.KARI, "inventory.json"))
    print("\npublished %d of %d episode(s), plus inventory.json"
          % (done, len(entries)))
    print("next: python3 -m scripts.news.rebuild --verify")
    return 0


if __name__ == "__main__":
    sys.exit(main())
