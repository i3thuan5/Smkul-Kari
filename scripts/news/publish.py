#!/usr/bin/env python3
"""Copy an episode's process data into Kari-SRT, the canonical store.

    python3 -m scripts.news.publish            # every finished episode
    python3 -m scripts.news.publish --check    # report, write nothing

`make_all.py` writes the deliverable SRTs straight into news/1-ocr/6-srt/, and
the vision TSVs are written there by the readers themselves. What is left is
the per-episode data that `rebuild.py` needs to put an SRT back together
without touching a video: `cues/<srt_name>.json`, `from_rtf/<srt_name>.json`,
and the inventory it walks. A one-off migration script did this once for
the February batch; this does it for every batch after.

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


def months_of(entries):
    """Every broadcast month the inventory holds, in order."""
    seen = set()
    for entry in entries:
        seen.add(paths.month_of(entry["srt_name"]))
    return sorted(seen)


def gate(entries, month=None):
    """Pending episodes in `month` that are not finished -- why it is held.

    Publishing is a whole-*batch* step, not a per-episode one: it clears the
    pending flags and writes the tracker, and both are claims about the
    batch. Half of them would leave the store saying it holds deliverables
    it does not -- the inconsistency `rebuild --verify` exists to find.

    A batch is a **broadcast month**, the same unit `plan_month.py` and
    `fetch_sftp.sh` work in. This used to walk the whole inventory instead,
    which meant registering January held February back even though the two
    months share nothing; 使用者裁定 2026-08-31 that they must not. Passing
    no month keeps the old whole-inventory behaviour for callers that want
    a single verdict.
    """
    blocked = []
    for entry in entries:
        if month is not None and paths.month_of(entry["srt_name"]) != month:
            continue
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
        target = paths.stage_path(folder, entry["srt_name"], ".json")
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(source, target)
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
    with open(paths.stage_path(paths.SRT_DIR, name, ".srt"),
              encoding="utf-8") as handle:
        srt_lines = handle.read().count("-->")
    return tracker.vision_status(srt_lines)


def write_deliverable_tracker(entries):
    rows = tracker.tracker_rows(entries, delivered_status)
    path = paths.TRACKER_STORE
    tracker.write_tracker(rows, path)
    return path


def clear_pending(entries, published):
    """Drop the pending flag from the episodes actually written this run.

    `published` is the set of srt_names that were. It used to clear every
    pending flag in the inventory, which was right while publishing was
    whole-inventory; now that a month can go out while another is still
    being read, clearing them all would mark the unpublished month
    delivered -- the store would claim a deliverable that is not there.
    """
    cleared = 0
    for entry in entries:
        if entry["srt_name"] not in published:
            continue
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

    entries = paths.load_inventory()

    # Decide everything before writing anything: publishing is
    # all-or-nothing *within a broadcast month*. A month that is still
    # being read holds only itself back now, not the finished ones.
    held = {}
    for month in months_of(entries):
        blocked = gate(entries, month)
        if blocked:
            held[month] = blocked

    ready = []
    for entry in entries:
        month = paths.month_of(entry["srt_name"])
        if month in held:
            continue
        work, reason = publishable(entry)
        if reason:
            print("skip  %-46s %s" % (entry["srt_name"], reason))
            continue
        ready.append((entry, work))
        if args.check:
            print("ready %s" % entry["srt_name"])

    for month in sorted(held):
        print("\nhold  %s：%d 集猶未讀完，這個月無寫"
              % (month, len(held[month])))
        for name, reason in held[month][:10]:
            print("  %-46s %s" % (name, reason))

    # Empty `ready` on its own is not a failure: an inventory that is
    # wholly delivered has nothing to copy, and the tracker still gets
    # written. It is a failure only when work was held and none went out.
    if held and not ready:
        print("\n無一个月份好勢，啥物都無寫")
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
    published = set()
    for entry, _work in ready:
        published.add(entry["srt_name"])
    cleared = clear_pending(entries, published)
    path = write_deliverable_tracker(entries)
    print("\npublished %d of %d episode(s); %d no longer pending; wrote %s"
          % (len(ready), len(entries), cleared, os.path.basename(path)))
    print("next: python3 -m scripts.news.rebuild --verify")
    return 0


if __name__ == "__main__":
    sys.exit(main())
