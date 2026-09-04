#!/usr/bin/env python3
"""Move old work dirs onto the staged cue layout, once.

    python3 -m scripts.news.migrate_workdirs            # 看伊beh按怎做
    python3 -m scripts.news.migrate_workdirs --write    # 真正徙

Work dirs cut before the split have a flat `<work>/cues.json`; the ones
cut since have `1-cues/cues.json` and, after refining, `2-refined/`.
`cues_to_read` reads all three, which is what let the two layouts live
side by side while a long cutting batch was in flight. This is the sweep
that ends the transition, so that fallback can go.

**Which stage a flat file belongs in is what it says about itself.** A
timeline carrying `refined` has been through the 25fps boundary pass and
belongs in `2-refined/`; one without it is coarse and belongs in
`1-cues/`. Getting that backwards would be quiet and expensive: the
episode would read as un-refined and something would try to refine it
again off a video that was deleted the moment its cues were cut.

Idempotent, because a sweep over a hundred-odd work dirs gets
interrupted: a dir that is already staged is left alone, and a flat file
sitting beside a staged one is **not** moved over it -- the staged one is
the newer truth.

Only this corpus's work dirs (`scripts.news.paths.WORK`). 《開會了》 keeps
its own work area and its own readers, which still name the flat path
directly, so nothing here goes near it.
"""
import argparse
import json
import os
import shutil
import sys

from scripts.news import paths
from scripts.ocr import stripname


def target_for(flat):
    """Which stage this flat timeline belongs in, by what it declares."""
    work = os.path.dirname(flat)
    if paths.timeline_is_refined(flat):
        return paths.refined_cues(work)
    return paths.coarse_cues(work)


def migrate(work):
    """Move this work dir's flat timeline into its stage; did it move?"""
    flat = os.path.join(work, "cues.json")
    if not os.path.exists(flat):
        return False
    target = target_for(flat)
    if os.path.exists(target):
        # Already staged, and the staged one is the newer truth. Leaving
        # the flat file where it is keeps the evidence for a person to
        # look at rather than silently picking a winner.
        return False
    os.makedirs(os.path.dirname(target), exist_ok=True)
    shutil.move(flat, target)
    return True


def migrate_sheets(work):
    """Rename this work dir's contact sheets by start time; did any move?

    `sheet_003.png` is a position in a batch, and positions move: split a
    cue, rebuild the sheets, and sheet three covers a different piece of
    programme than it did. Strips had the same problem and were measured
    at 46,665 of 75,290 files carrying a number that was not their cue's.

    `sheets.json` is the map under either naming, so nothing that reads
    it is affected -- the name is for the person looking at the file. The
    map's keys are the file names, though, so they are rewritten here in
    the same pass; renaming one without the other breaks the map.

    A sheet whose first cue the timeline no longer has is left alone with
    its old name, because the only honest new name would be a guess.
    """
    index = os.path.join(work, "sheets.json")
    folder = os.path.join(work, "sheets")
    timeline = paths.cues_to_read(work)
    if not (os.path.exists(index) and os.path.isdir(folder) and timeline):
        return False
    with open(index, encoding="utf-8") as handle:
        mapping = json.load(handle)
    with open(timeline, encoding="utf-8") as handle:
        starts = {}
        for cue in json.load(handle).get("cues", []):
            starts[cue["index"]] = cue["start"]

    renamed = {}
    moved = False
    for name, cues in mapping.items():
        if not stripname.is_ordinal_sheet(name) or not cues:
            renamed[name] = cues
            continue
        first = cues[0]
        if first not in starts:
            renamed[name] = cues
            continue
        new = stripname.sheet_of(starts[first])
        old_path = os.path.join(folder, name)
        new_path = os.path.join(folder, new)
        if os.path.exists(old_path) and not os.path.exists(new_path):
            os.rename(old_path, new_path)
            moved = True
        renamed[new] = cues
    if moved:
        with open(index, "w", encoding="utf-8") as handle:
            json.dump(renamed, handle, ensure_ascii=False)
    return moved


def sweep(root, sheets=False):
    """Migrate every work dir under `root`; return (moved, skipped).

    `sheets` also renames the contact sheets. Off by default so the cue
    sweep -- which has already run everywhere -- stays exactly what it
    was, and the sheet pass can be asked for separately.
    """
    moved = 0
    skipped = 0
    for name in sorted(os.listdir(root)):
        work = os.path.join(root, name)
        if not os.path.isdir(work):
            continue
        did = migrate(work)
        if sheets and migrate_sheets(work):
            did = True
        if did:
            moved += 1
        else:
            skipped += 1
    return moved, skipped


def _plan(root):
    """What a sweep would do, without doing it."""
    plans = []
    for name in sorted(os.listdir(root)):
        work = os.path.join(root, name)
        flat = os.path.join(work, "cues.json")
        if not os.path.isdir(work) or not os.path.exists(flat):
            continue
        target = target_for(flat)
        if os.path.exists(target):
            plans.append((name, "已經有新版面矣，無徙"))
        else:
            plans.append((name, os.path.relpath(target, work)))
    return plans


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sheets", action="store_true",
                    help="順紲kā contact sheet 改做時間命名")
    ap.add_argument("--write", action="store_true",
                    help="真正徙（無這个就干焦報伊beh按怎做）")
    ap.add_argument("--root", default=paths.WORK,
                    help="欲掃ê work 資料夾（預設 %s）" % paths.WORK)
    args = ap.parse_args(argv)

    if not args.write:
        plans = _plan(args.root)
        for name, where in plans:
            print("%-52s → %s" % (name[:52], where))
        print("\n%d 个 work dir 有平版面ê時間軸；加 --write 才真正徙"
              % len(plans))
        return 0

    before = len(_plan(args.root))
    moved, skipped = sweep(args.root, sheets=args.sheets)
    print("徙 %d 个，無動 %d 个（掃進前算著 %d 个愛徙）"
          % (moved, skipped, before))
    left = len(_plan(args.root))
    if left:
        print("猶賰 %d 个平版面ê——彼寡是新版面遮已經有檔ê，愛人看" % left)
    return 0


if __name__ == "__main__":
    sys.exit(main())
