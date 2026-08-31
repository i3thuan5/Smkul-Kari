#!/usr/bin/env python3
"""Plan one broadcast month: which episodes, and which file each one is.

    python3 -m scripts.news.plan_month 2021-01
    python3 -m scripts.news.plan_month 2021-01 -n     # report, write nothing

A batch is a **broadcast month**, not a source folder. The two are not the
same thing: six broadcast months are spread across two folders each, and
`110.1-110.10/7月/` holds 140 files of which 66 are February's programmes.
Working a folder therefore does not produce a month -- it produces some of
that month plus some of another.

Registration happens here, before anything is downloaded. Everything
downstream (`batches`, `ingest`, `make_all`) looks an episode's naming up in
the inventory, and by the time they run the video is gone -- `fetch_sftp.sh`
deletes it the moment the cues are cut, so there is nothing left to scan.
The entries are written `pending`, which is what lets the store name an
episode it cannot yet rebuild; `publish` clears the flag when the batch is
done.

Episodes the rules cannot decide are skipped and listed, not guessed at --
see `sources.py`. Skipped episodes are not written to the inventory, so the
batch can still be published without one of them holding it open forever;
once a person has decided, `add_episodes.py` takes the chosen path.
"""
import argparse
import collections
import json
import sys

from scripts.news import add_episodes
from scripts.news import paths
from scripts.news import resolve_slug
from scripts.news import sources
from scripts.errors import PipelineError

Report = collections.namedtuple(
    "Report", "month entries added skipped no_source")


def month_rows(rows, month):
    """The catalogue rows broadcast in this month, in catalogue order."""
    out = []
    for row in rows:
        if (row.get("播出日期") or "").startswith(month):
            out.append(row)
    return out


def label_of(row):
    """How an episode is named in the skip report."""
    return "%s %s %s" % (row.get("播出日期", "?"), row.get("播出時段", "?"),
                         row.get("族語別(中)", "?"))


def merge(planned, existing):
    """Fold a plan into the inventory without dropping anyone else's work.

    The inventory is the store's, and most of what is in it did not come from
    this month's plan -- `add_episodes` puts episodes there one at a time,
    from the file name alone, because their videos are deleted the moment the
    cues are cut.

    So a plan may add episodes and may not remove any. An episode already
    present is left exactly as it is: it may carry `partial`, a corrected
    `文稿位置`, or a source recovered after being written off, none of which
    a fresh plan knows about.
    """
    known = set()
    for entry in existing:
        known.add(entry["slug"])
    merged = list(existing)
    added = []
    for entry in planned:
        if entry["slug"] in known:
            continue
        known.add(entry["slug"])
        merged.append(entry)
        added.append(entry)
    return merged, added


def plan(month, catalogue, inventory=None, limit=0):
    """What this month's batch is: entries to register, and what was skipped.

    Nothing is written; `write()` does that, so `--dry-run` and the real run
    take exactly the same path up to the last step.

    `limit` caps how many episodes are *registered*, not how many are
    considered: an episode the rules could not decide is reported every
    time, so it surfaces on the first run rather than whenever the limit
    happens to reach it. Registering one at a time is what makes "one
    episode per batch" work -- `publish` refuses to write while any pending
    episode is unfinished, so the way to publish per episode is to have
    only ever registered one.
    """
    rows = month_rows(catalogue.rows, month)
    if not rows:
        raise PipelineError("目錄內底無 %s 這个月的集數" % month)

    picked = sources.resolve(rows)
    planned = []
    skipped = []
    no_source = 0
    for row, (video, problem) in zip(rows, picked):
        if problem is sources.NO_SOURCE:
            no_source += 1
            continue
        if not video:
            skipped.append((label_of(row), problem))
            continue
        entry, trouble = add_episodes.entry_for_row(row, video)
        if trouble:
            skipped.append((label_of(row), trouble))
            continue
        planned.append(entry)

    existing = paths.load_inventory(inventory)
    entries, added = merge(planned, existing)
    if limit and len(added) > limit:
        # Drop the surplus from both the merged list and the report: they
        # were never registered, so a later run picks them up unchanged.
        dropped = added[limit:]
        added = added[:limit]
        kept = []
        for entry in entries:
            if entry not in dropped:
                kept.append(entry)
        entries = kept
    return Report(month, entries, added, skipped, no_source)


def todo(month, entries):
    """[(slug, corpus-relative path)] for this month's unfetched episodes.

    The fetch list comes from here rather than from listing a remote folder,
    which is the practical half of "a folder is not a month": one month's
    episodes can sit in two folders, so no single listing holds them all, and
    a listing cannot say which episode a file is anyway.

    Paths come back corpus-root-relative, the form the server takes under its
    own root and the form `resolve_slug` normalises to.
    """
    out = []
    for entry in entries:
        if not entry.get("pending"):
            continue
        if not entry["播出日期"].startswith(month):
            continue
        out.append((entry["slug"], resolve_slug.normalise(entry["video"])))
    return out


def write(report, inventory=None):
    """Register the plan's episodes in the inventory."""
    path = inventory or paths.INVENTORY
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(report.entries, handle, ensure_ascii=False, indent=2)
    return path


def print_report(report, wrote):
    for entry in report.added:
        print("plan  %-46s %s" % (entry["srt_name"], entry["video"]))
    for label, reason in report.skipped:
        print("SKIP  %-46s %s" % (label, reason))
    print("\n%s：登記 %d 集%s，跳過 %d 集"
          % (report.month, len(report.added),
             "" if wrote else "（試跑，無寫入）", len(report.skipped)))
    if report.no_source:
        print("另有 %d 集目錄標示無影片，無法度處理。" % report.no_source)
    if report.skipped:
        print("跳過的集數判好了後，用 add_episodes.py 指定路徑補做。")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("month", help="播出月份，親像 2021-01")
    ap.add_argument("-n", "--dry-run", action="store_true",
                    help="報告欲做啥，毋寫入 inventory")
    ap.add_argument("--todo", action="store_true",
                    help="干焦印出愛抓的清單（slug<TAB>路徑），予 shell 食")
    ap.add_argument("--limit", type=int, default=0,
                    help="一改干焦登記 N 集（0＝規个月）")
    args = ap.parse_args(argv)

    if args.todo:
        for slug, video in todo(args.month, paths.load_inventory()):
            print("%s\t%s" % (slug, video))
        return 0

    report = plan(args.month, resolve_slug.load(), limit=args.limit)
    if not args.dry_run:
        write(report)
    print_report(report, not args.dry_run)
    if not args.dry_run and report.added:
        print("next: bash scripts/news/fetch_sftp.sh %s" % args.month)
    return 0


if __name__ == "__main__":
    sys.exit(main())
