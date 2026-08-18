#!/usr/bin/env python3
"""Copy an episode's process data into Kari-SRT, the canonical store.

    python3 -m scripts.news.publish            # every finished episode
    python3 -m scripts.news.publish --check    # report, write nothing

`make_all.py` writes the deliverable SRTs straight into news/1-ocr/6-srt/, and
the vision TSVs are written there by the readers themselves. What is left is
the per-episode data that `rebuild.py` needs to put an SRT back together
without touching a video: `cues/<srt_name>.json`, `from_rtf/<srt_name>.json`,
and the inventory it walks. `migrate_kari.py` did this once for the February
batch as part of a one-off move; this does it for every batch after.

This is also where the store smkul.csv is written. make_all keeps a work
copy
in kithann/out/ that it can refresh as often as it likes; only the version
written here is a deliverable. The reason is that a mid-batch row says which
step an episode is stuck at, and that lives in the work dir -- which rebuild
does not have, so it could never rebuild such a table byte-for-byte.

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
from scripts.news import tracker

WORK = paths.WORK


def publishable(entry):
    """(source work dir, reason it cannot be published).

    A reason is only a failure when the episode is pending -- see gate(). An
    already-delivered episode whose work dir has been cleared away is simply
    nothing to do: its inputs are in the store, which is exactly why the work
    dir was safe to delete.
    """
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


def gate(entries):
    """Pending episodes that are not finished, i.e. why we cannot publish.

    Publishing is a whole-batch step, not a per-episode one: it clears the
    pending flags and writes the tracker, and both of those are claims about
    the batch as a whole. Half of them would leave the store saying it holds
    deliverables it does not -- the very inconsistency `rebuild --verify`
    exists to find.
    """
    blocked = []
    for entry in entries:
        if not tracker.is_pending(entry):
            continue
        _work, reason = publishable(entry)
        if reason:
            blocked.append((entry["srt_name"], reason))
    return blocked


def publish_one(entry, work):
    """Copy this episode's inputs into the store; return what was written."""
    written = []
    for name, folder in (("cues.json", paths.KARI_CUES),
                         ("from_rtf.json", paths.KARI_FROM_RTF)):
        source = os.path.join(work, name)
        if not os.path.exists(source):
            # from_rtf.json is a historical index: which cues the 文稿 once
            # supplied, back when it supplied any. Episodes prepared since
            # that path was removed have none, and the store keeps the old
            # ones as the key to the rtf-vs-vision comparison report.
            continue
        os.makedirs(folder, exist_ok=True)
        shutil.copy2(source, os.path.join(folder, entry["srt_name"] + ".json"))
        written.append(os.path.basename(folder))
    return written


def delivered_status(entry):
    """The tracker status for an episode that is already in the store.

    Read back off the store rather than carried over from make_all, and
    without re-running the assembly: `rebuild` counts the same lines out of
    the same file, so a row built here is the row it will rebuild.
    """
    if entry["truncated"]:
        return tracker.skipped_status(entry["truncated"])
    name = entry["srt_name"]
    with open(os.path.join(paths.SRT_DIR, name + ".srt"),
              encoding="utf-8") as handle:
        srt_lines = handle.read().count("-->")
    return tracker.vision_status(srt_lines)


def write_deliverable_tracker(entries):
    rows = tracker.tracker_rows(entries, delivered_status)
    path = paths.TRACKER_STORE
    tracker.write_tracker(rows, path)
    return path


def clear_pending(entries):
    """Drop the pending flags: every one of them is now delivered."""
    cleared = 0
    for entry in entries:
        if tracker.is_pending(entry):
            del entry["pending"]
            cleared += 1
    with open(paths.INVENTORY, "w", encoding="utf-8") as handle:
        json.dump(entries, handle, ensure_ascii=False, indent=2)
    return cleared


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="report what would be published, write nothing")
    args = ap.parse_args(argv)

    with open(paths.INVENTORY, encoding="utf-8") as handle:
        entries = json.load(handle)

    # Decide everything before writing anything: publishing is all-or-nothing.
    blocked = gate(entries)
    ready = []
    for entry in entries:
        work, reason = publishable(entry)
        if reason:
            print("skip  %-46s %s" % (entry["srt_name"], reason))
            continue
        ready.append((entry, work))
        if args.check:
            print("ready %s" % entry["srt_name"])

    if blocked:
        print("\n%d pending episode(s) not finished; nothing written:"
              % len(blocked))
        for name, reason in blocked[:10]:
            print("  %-46s %s" % (name, reason))
        return 1

    if args.check:
        print("\n%d of %d episode(s) ready to publish (nothing written)"
              % (len(ready), len(entries)))
        return 0

    for entry, work in ready:
        written = publish_one(entry, work)
        print("write %-46s %s" % (entry["srt_name"], ", ".join(written)))

    # There is no inventory to copy: it lives in the store already, and
    # add_episodes writes it there directly. This used to overwrite the
    # store's copy with a second one kept in the main repo, which is how the
    # two could disagree about which episodes exist. What is written back is
    # the same file with the pending flags gone.
    cleared = clear_pending(entries)
    path = write_deliverable_tracker(entries)
    print("\npublished %d of %d episode(s); %d no longer pending; wrote %s"
          % (len(ready), len(entries), cleared, os.path.basename(path)))
    print("next: python3 -m scripts.news.rebuild --verify")
    return 0


if __name__ == "__main__":
    sys.exit(main())
