#!/usr/bin/env python3
"""Rename a work dir's strips from cue ordinals to cue start times.

    python3 -m scripts.news.migrate_strips --check      # report, write none
    python3 -m scripts.news.migrate_strips <stem> ...   # these work dirs
    python3 -m scripts.news.migrate_strips              # every news work dir

Why the naming changed at all is in `scripts/ocr/stripname.py`: cue numbers
move when anything splits a cue, filenames do not, and 46,665 of 75,290
cues (62%, across 48 episodes) already carry a strip whose filename is some
older cue's number. 使用者裁定 2026-08-31 -- rename them all, old episodes
included.

TWO THINGS THIS HAS TO GET RIGHT
--------------------------------
**Go by the file, not by the cue.** Several cues can share one strip: a
reread that split one cue into four leaves all four halves pointing at the
original picture -- 20210201_032_午間_Atayal_泰雅 cues 108-111 all name
`strips/00103_han.png`. Computing a new name per cue would demand four
different names for one file. So each file gets exactly one new name, taken
from the earliest cue that references it, and every reference is rewritten
to match.

**Nothing can collide.** Ordinal names and time names live in disjoint
shapes, so no rename can land on a file that is still wanted -- unlike
`rescan_band`'s within-ordinal shuffle, where 400 moving to 402 would
clobber the 402 still on disk. The one collision that *is* possible --
two different files wanting the same time -- is checked before anything
moves, and raises rather than overwriting.

`kithann/out/aiyalaeho/` is left alone: that corpus is mid-run in another
session, and `cues.json` written by two processes at once goes wrong
silently.
"""
import argparse
import glob
import json
import os
import sys

from scripts.errors import PipelineError
from scripts.news import paths
from scripts.ocr import stripname


def plan(cues):
    """{old relative path: new relative path} for the strips that move.

    Keyed by file, valued by the start time of the earliest cue naming it.
    """
    first = {}
    for cue in cues:
        for _line, rel in (cue.get("images") or {}).items():
            if not stripname.is_ordinal(rel):
                continue
            if rel not in first or cue["start"] < first[rel]:
                first[rel] = cue["start"]
    moves = {}
    taken = {}
    for rel in sorted(first):
        line = os.path.basename(rel).split("_", 1)[1].rsplit(".", 1)[0]
        new = os.path.join(os.path.dirname(rel),
                           stripname.of(first[rel], line))
        if new in taken:
            raise PipelineError(
                "新名撞號：%s 佮 %s 攏欲換做 %s" % (taken[new], rel, new))
        taken[new] = rel
        moves[rel] = new
    return moves


def rewrite(cues, moves):
    """`cues` with every `images` value put through `moves`."""
    out = []
    for cue in cues:
        one = dict(cue)
        images = {}
        for line, rel in (cue.get("images") or {}).items():
            images[line] = moves.get(rel, rel)
        one["images"] = images
        out.append(one)
    return out


def already_done(exists, work, old, new):
    """Has this rename happened already, through a shared strips dir?

    `gap_sheets` symlinks `<slug>.B.work/strips` at `<slug>.work/strips`,
    so the two work dirs share one set of files. Migrating `.B.work`
    renames them through the symlink but only updates its own cues.json;
    when `.work`'s turn comes, its old names are gone -- not lost, moved.

    New name present and old one absent means done. Neither present is a
    real loss and has to say so.
    """
    return (exists(os.path.join(work, new))
            and not exists(os.path.join(work, old)))


def migrate(work, dry_run=False):
    """Rename one work dir's strips and update its cues.json."""
    book_path = os.path.join(work, "cues.json")
    with open(book_path, encoding="utf-8") as handle:
        book = json.load(handle)
    moves = plan(book["cues"])
    if not moves:
        return 0, 0
    todo = {}
    missing = []
    for old, new in moves.items():
        if already_done(os.path.exists, work, old, new):
            continue
        if not os.path.exists(os.path.join(work, old)):
            missing.append(old)
        todo[old] = new
    if missing:
        raise PipelineError("%d 支欲改名ê檔案兩爿攏無，比論 %s"
                            % (len(missing), missing[0]))
    if dry_run:
        return len(moves), 0
    moved = 0
    for old, new in todo.items():
        os.rename(os.path.join(work, old), os.path.join(work, new))
        moved += 1
    book["cues"] = rewrite(book["cues"], moves)
    with open(book_path, "w", encoding="utf-8") as handle:
        json.dump(book, handle, ensure_ascii=False, indent=2)
    return len(moves), moved


SUFFIXES = (".B.work", ".work")


def is_work_dir(name):
    """Both kinds count.

    `ocr-cli cues` writes `<slug>.work` and `gap_sheets` derives
    `<slug>.B.work` from it; `fetch_sftp.sh` sometimes cuts straight into
    `.B.work`. The first pass of this migration only looked at `.B.work`
    and left 1,149 strips behind in 20210106_006_午間_Cou_鄒, freshly
    fetched and not yet made into sheets.
    """
    for suffix in SUFFIXES:
        if name.endswith(suffix):
            return True
    return False


def stem_of(name):
    """The work-dir name with either suffix removed."""
    for suffix in SUFFIXES:
        if name.endswith(suffix):
            return name[:-len(suffix)]
    return name


def work_dirs(stems=None):
    """The news work dirs to touch. Never `kithann/out/aiyalaeho/`."""
    out = []
    for path in sorted(glob.glob(os.path.join(paths.WORK, "*.work"))):
        name = os.path.basename(path)
        if not is_work_dir(name):
            continue
        if stems and stem_of(name) not in stems:
            continue
        if os.path.exists(os.path.join(path, "cues.json")):
            out.append(path)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("stems", nargs="*")
    ap.add_argument("--check", action="store_true",
                    help="report what would move, write nothing")
    args = ap.parse_args(argv)

    total = done = 0
    for work in work_dirs(set(args.stems) if args.stems else None):
        planned, moved = migrate(work, dry_run=args.check)
        if planned:
            print("%-52s %d 張" % (stem_of(os.path.basename(work)), planned))
        total += planned
        done += moved
    if args.check:
        print("\n（試跑）欲改名 %d 張" % total)
    else:
        print("\n改名 %d 張，更新 %d 集ê cues.json" % (done, len(work_dirs())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
