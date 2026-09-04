#!/usr/bin/env python3
"""Move a finished batch into the store and stand behind it.

    python3 -m scripts.aiyalaeho.publish            # 規批定版
    python3 -m scripts.aiyalaeho.publish --check    # 報告，一字都無寫

`make_all` writes the delivered SRTs straight into 3-srt/, and the vision
TSVs are written into 2-vision/ by the readers themselves. What is left is
the per-episode input the offline rebuild needs to put an SRT back
together without a video -- `1-cues/<srt_name>.json` -- plus the delivered
progress table and the clearing of the pending flags.

All or nothing: while any registered episode is still unread, nothing is
written at all. Half a batch would leave the store claiming deliverables
it does not have, which is the inconsistency `rebuild --verify` exists to
find.
"""
import argparse
import json
import os
import shutil
import sys

from scripts import datadirs
from scripts.aiyalaeho import make_all
from scripts.aiyalaeho import paths
from scripts.aiyalaeho import tracker


def publishable(entry):
    """(source work dir, reason it cannot be published).

    A reason only stops the batch when the episode is pending -- an
    already-delivered episode whose work dir has been cleared away is
    nothing to do, which is exactly why the work dir was safe to delete.
    """
    work = paths.work_dir(entry["srt_name"])
    if not datadirs.cues_to_read(work):
        return "", "尚未切cue"
    if not make_all.vision_complete(work):
        return "", "視覺辨識尚未讀完"
    if not os.path.exists(paths.stage_path(paths.SRT_DIR,
                                           entry["srt_name"], ".srt")):
        return "", "猶未組裝（先走 make_all）"
    return work, ""


def gate(entries):
    """Registered episodes that are not finished -- why we cannot publish."""
    blocked = []
    for entry in entries:
        if not tracker.is_pending(entry):
            continue
        _work, reason = publishable(entry)
        if reason:
            blocked.append((entry["srt_name"], reason))
    return blocked


def publish_one(entry, work):
    """Copy this episode's timeline into the store."""
    target = paths.stage_path(paths.KARI_CUES, entry["srt_name"], ".json")
    os.makedirs(os.path.dirname(target), exist_ok=True)
    shutil.copy2(datadirs.cues_to_read(work), target)
    return target


def clear_pending(entries, published):
    """Drop the pending flag from the episodes actually written."""
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
                    help="報告欲定版啥，一字都無寫")
    args = ap.parse_args(argv)

    entries = paths.load_inventory()

    # Decide everything before writing anything.
    blocked = gate(entries)
    ready = []
    for entry in entries:
        work, reason = publishable(entry)
        if reason:
            print("skip  %-30s %s" % (entry["srt_name"], reason))
            continue
        ready.append((entry, work))
        if args.check:
            print("ready %s" % entry["srt_name"])

    if blocked:
        print("\n%d 集猶未做煞，一字都無寫：" % len(blocked))
        for name, reason in blocked[:10]:
            print("  %-30s %s" % (name, reason))
        return 1

    if args.check:
        print("\n%d／%d 集會使定版（試跑，無寫入）"
              % (len(ready), len(entries)))
        return 0

    published = set()
    for entry, work in ready:
        publish_one(entry, work)
        published.add(entry["srt_name"])
        print("write %s" % entry["srt_name"])

    cleared = clear_pending(entries, published)
    rows = tracker.tracker_rows(entries)
    tracker.write_tracker(rows, paths.TRACKER_STORE)
    print("\n定版 %d／%d 集；%d 集清掉 pending；寫 %s"
          % (len(ready), len(entries), cleared,
             os.path.basename(paths.TRACKER_STORE)))
    print("next: python3 -m scripts.aiyalaeho.rebuild --verify")
    return 0


if __name__ == "__main__":
    sys.exit(main())
