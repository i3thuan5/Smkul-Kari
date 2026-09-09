#!/usr/bin/env python3
"""Copy an episode's process data into Kari-SRT, the canonical store.

    python3 -m scripts.news.publish            # every finished episode
    python3 -m scripts.news.publish --check    # report, write nothing

`make_all.py` writes the deliverable SRTs straight into news/1-ocr/3-srt/, and
the vision TSVs are written there by the readers themselves. What is left is
the per-episode data that `rebuild.py` needs to put an SRT back together
without touching a video: `cues/<srt_name>.json` and the inventory it
walks. A one-off migration script did this once for
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

The unit of that judgement is **one episode**, not a batch. It was the whole
inventory once, then a broadcast month (2026-08-31), and is now per-episode
(2026-09-09) -- because each of the two narrowings found the same thing: the
wider unit was holding finished work hostage to unrelated work. January had
58 episodes not yet cut, and that kept 006午 -- cut, refined, read and
verified -- out of the store, while the only copy of its timeline sat in a
work dir whose master had already been deleted.

Per-episode stays self-consistent because no episode vouches for another:
`publishable` already demands that this episode was cut, refined and fully
read; `smkul.csv` lists only the non-pending ones; and `rebuild --verify`
walks only the non-pending ones. Publishing one moves that one from pending
to delivered and puts its own inputs in the store. Nothing is claimed about
the rest.
"""
import argparse
import json
import os
import sys

from scripts.news import make_all
from scripts.news import paths
from scripts.news import redump_store
from scripts.news import tracker
from scripts.errors import PipelineError

WORK = paths.WORK


def publishable(entry):
    """(source work dir, reason it cannot be published).

    A reason only holds back this one episode. An already-delivered episode
    whose work dir has been cleared away is simply nothing to do: its inputs
    are in the store, which is exactly why the work dir was safe to delete.
    """
    if entry["truncated"]:
        return "", "略過（%s）" % entry["truncated"]
    # The .B.work dir is the one make_all assembled the SRT from, so it is
    # the one whose cues.json the store must hold.
    work = os.path.join(WORK, entry["slug"] + ".B.work")
    # Asked through the helper, so every layout the timeline can arrive in
    # counts. Spelling `<work>/cues.json` out here reads a staged work dir
    # as uncut, and the batch is then held back for the wrong reason.
    if paths.cues_to_read(work) is None:
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
    """Pending episodes in `month` that are not finished -- why each waits.

    This is a **query**, not the gate. `main` no longer consults it before
    writing: an unfinished episode holds back only itself (see the module
    docstring). What it is still good for is answering "what is this batch
    waiting on", which is what a person wants when a month is dragging.

    Scope is a **broadcast month**, the same unit `plan_month.py` and
    `fetch_sftp.sh` work in; passing no month walks the whole inventory.
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


def refined_timeline(entry, work):
    """This episode's timeline, or say which of the two things is wrong.

    The store only takes refined timelines. Every delivered timestamp is
    derived from this one file, and the two grades differ by an order of
    magnitude -- 0.2s against 0.05s -- so once both are in `1-cues/`
    nothing tells them apart. Gating here is what lets that folder state
    outright that everything in it has been refined.

    The two refusals are worded apart because the fixes are: a coarse
    timeline wants `refine_cues`, a missing one wants the episode cut.
    """
    source = paths.cues_to_read(work)
    if source is None:
        raise PipelineError("%s：%s 內底揣無時間軸，袂使定版"
                            % (entry["srt_name"], work))
    if not paths.timeline_is_refined(source):
        raise PipelineError(
            "%s：時間軸猶未精修（%s），袂使入 store——先走 refine_cues"
            % (entry["srt_name"], source))
    return source


def publish_one(entry, work, cues_dir=None):
    """Copy this episode's inputs into the store; return what was written.

    Cues used to share a loop with `from_rtf.json` whose "missing? carry
    on" arm was written for that file, which legitimately is absent for
    most episodes. A timeline is never optional, and sharing that arm is
    what made a missing one silent.

    Read and re-dumped rather than `shutil.copy2`-ed, because the store's
    JSON has to be readable by a person (see CLAUDE.md) and the work dir's
    copy is not: its keys are in insertion order. Copying it verbatim
    overwrote the store's sorted layout, so one publish rewrote 74 already
    delivered files whose content had not changed at all -- and the next
    re-dump of the store would flip them straight back. Same fix the
    aiyalaeho side already carries.
    """
    folder = paths.KARI_CUES if cues_dir is None else cues_dir
    source = refined_timeline(entry, work)
    target = paths.stage_path(folder, entry["srt_name"], ".json")
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(source, encoding="utf-8") as handle:
        manifest = json.load(handle)
    with open(target, "w", encoding="utf-8") as handle:
        handle.write(redump_store.dump(manifest))
    return [os.path.basename(folder)]


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
    whole-inventory; now that one episode can go out while its neighbours
    are still being read, clearing them all would mark unread episodes
    delivered -- the store would claim deliverables that are not there.
    """
    cleared = 0
    for entry in entries:
        if entry["srt_name"] not in published:
            continue
        if tracker.is_pending(entry):
            del entry["pending"]
            cleared += 1
    with open(paths.INVENTORY, "w", encoding="utf-8") as handle:
        json.dump(entries, handle, ensure_ascii=False, indent=2,
                  sort_keys=True)
    return cleared


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="report what would be published, write nothing")
    args = ap.parse_args(argv)

    entries = paths.load_inventory()

    # Decide everything before writing anything. The unit is one episode:
    # each is judged by `publishable` alone, and an unfinished one holds
    # back only itself. Nothing here vouches for anything else -- see the
    # module docstring for why that keeps the store self-consistent.
    ready = []
    for entry in entries:
        work, reason = publishable(entry)
        if reason:
            print("skip  %-46s %s" % (entry["srt_name"], reason))
            continue
        ready.append((entry, work))
        if args.check:
            print("ready %s" % entry["srt_name"])

    # An empty `ready` is not a failure. It means either that everything
    # is already delivered, or that no episode of this batch has finished
    # yet -- and the `skip` line above already named the step each one is
    # stuck at. Returning non-zero here made batch scripts read "not my
    # turn yet" as "something broke".
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
