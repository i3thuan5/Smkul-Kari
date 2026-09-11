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
揀袂出來ê集數逐擺攏報，等人判好才做。
"""
import argparse
import collections
import os
import sys

from scripts.news import episodes
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


def plan(month, entries, limit=0):
    """這个月這批是啥：會使做ê集數，佮揀袂出來ê。

    **唯讀。** 節目目錄頭一工就涵蓋全部集數，所以無「登記」這个動作
    矣——這支干焦是講出這个月有佗幾集、逐集配佗一支來源。跑進前跑
    了後 Kari-SRT 一个 byte 攏無變。

    `limit` 是「這改先做幾集」，予人會使一集一集做。揀袂出來ê集數
    逐擺攏報，才袂等到 limit 拄好行到彼跡才現形。
    """
    rows = []
    for entry in entries:
        if entry["播出日期"].startswith(month):
            rows.append(entry)
    if not rows:
        raise PipelineError("節目目錄內底無 %s 這个月的集數" % month)

    picked = sources.resolve(rows)
    planned = []
    skipped = []
    for row, (video, problem) in zip(rows, picked):
        if problem is sources.NO_SOURCE:
            continue
        if not video:
            skipped.append((label_of(row), problem))
            continue
        planned.append(dict(row, video=video))
    if limit:
        planned = planned[:limit]
    return Report(month, rows, planned, skipped, 0)


def already_cut(entry, work=None, store=None):
    """Is this episode's timeline finished -- cut **and** refined?

    Both halves, because refine is the last step that opens the video. An
    episode cut but not refined still needs it, and calling that finished
    strands the episode: it drops off the fetch list and keeps its 0.2s
    boundaries forever. That is not hypothetical -- 2021_006 was cut at
    03:31, its refine was killed seconds later, and the todo list went from
    59 to 58 with nothing reporting anything. 使用者裁定 2026-08-31: such an
    episode is re-cut from scratch rather than given a refine-only path,
    because the case is rare.

    Two places are asked, for different reasons:

    - the **work dirs** on this disk, where a batch in progress keeps its
      timeline;
    - the **store**, `1-cues/<月份>/<srt_name>.json`, the delivered
      timeline's one canonical copy. `kithann/` is gitignored and a rebuilt
      devcontainer wipes it -- that has happened twice. Asking only the work
      dirs, every delivered episode would then look uncut, get fetched and
      **re-cut**: every cue renumbered underneath an SRT that was already
      shipped, with nothing anywhere reporting an error.

    The arguments are injectable so the rule can be exercised without a disk.
    """
    folder = paths.work_dir(entry["slug"], work)
    if paths.cues_to_read(folder):
        return paths.is_refined(folder)
    base = paths.KARI_CUES if store is None else store
    shipped = paths.stage_path(base, entry["srt_name"], ".json")
    return (os.path.exists(shipped)
            and paths.timeline_is_refined(shipped))


def todo(month, entries, already_cut=already_cut):
    """[(slug, corpus-relative path)] for this month's episodes needing video.

    The fetch list comes from here rather than from listing a remote folder,
    which is the practical half of "a folder is not a month": one month's
    episodes can sit in two folders, so no single listing holds them all, and
    a listing cannot say which episode a file is anyway.

    One rule: **an episode is fetched when it is registered and has no cues
    yet.** Cutting is the last step that needs the video -- the vision pass
    reads `strips/` and `sheets/`, and the SRT is assembled from `cues.json`
    -- so a timeline that already exists means the download would be pure
    waste. Two earlier rules collapsed into this one on 使用者裁定
    2026-08-31:

    - pending used to mean "fetch unconditionally", which re-downloaded
      2.7 GB for two episodes whose cues had been cut weeks before, only to
      verify the band and delete them again;
    - delivered episodes with no video left on this disk used to be fetched
      too, to have native frames ready for a reread. Rereads fetch their own
      video when they actually run (download, work,
      delete), so a month's fetch has no reason to stock up for them.

    Which leaves nothing on this list that is already cut, so nothing here
    can ever ask for a second cut of an episode -- the failure that would
    renumber every cue under a delivered SRT.

    Paths come back corpus-root-relative, the form the server takes under its
    own root and the form `resolve_slug` normalises to.
    """
    out = []
    for entry in entries:
        if not entry["播出日期"].startswith(month):
            continue
        if not entry.get("pending"):
            continue
        if already_cut(entry):
            continue
        out.append((entry["slug"], resolve_slug.normalise(entry["video"])))
    return out


def print_report(report):
    for entry in report.added:
        print("plan  %-46s %s" % (entry["srt_name"], entry["video"]))
    for label, reason in report.skipped:
        print("SKIP  %-46s %s" % (label, reason))
    print("\n%s：會使做 %d 集，揀袂出來 %d 集（無寫任何檔）"
          % (report.month, len(report.added), len(report.skipped)))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("month", help="播出月份，親像 2021-01")
    ap.add_argument("--todo", action="store_true",
                    help="干焦印出愛抓的清單（slug<TAB>路徑），予 shell 食")
    ap.add_argument("--limit", type=int, default=0,
                    help="一改干焦登記 N 集（0＝規个月）")
    args = ap.parse_args(argv)

    if args.todo:
        for slug, video in todo(args.month, episodes.load()):
            print("%s\t%s" % (slug, video))
        return 0

    report = plan(args.month, episodes.load(), limit=args.limit)
    print_report(report)
    if report.added:
        print("next: bash scripts/news/fetch_sftp.sh %s" % args.month)
    return 0


if __name__ == "__main__":
    sys.exit(main())
