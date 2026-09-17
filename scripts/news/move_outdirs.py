#!/usr/bin/env python3
"""One-off: reorganise kithann/out into corpus -> month -> episode.

    python3 -m scripts.news.move_outdirs --dry-run   # print the plan
    python3 -m scripts.news.move_outdirs             # move, then self-check

What moves, and only this (loose files in out/ stay where they are):

    out/mxf/<slug>.work          -> out/news/1-ocr/<年-月>/<slug>.work
    out/mxf-logs/<slug>.<x>.log  -> out/news/logs/<年-月>/
    out/mkv/<srt_name>.*         -> out/news/mkv/<年-月>/
    out/asrmt/<srt_name>/        -> out/news/2-asr/<年-月>/<srt_name>/
    out/stage*/<video>           -> out/news/stage*/<年-月>/  (month from
                                    the catalogue; unknown files stay put)

and inside every work dir, news and 開會了 alike (they share the engine's
stage names): strips/ -> 2-strips/, 2-refined/ -> 3-refined/, sheets/ and
sheets.json -> 4-sheets/, transcripts.json and verified.json (and their
.before-rescan copies) -> 5-transcripts/, with the strip paths recorded in
the timelines rewritten to match.

Nothing is overwritten: a destination that already exists is a problem,
reported and left alone. After moving, every planned source must be gone
and every destination present, or the run exits non-zero naming them.
Anything left behind because it could not be placed is named too.
"""
import argparse
import glob
import json
import os
import sys

from scripts import datadirs
from scripts.news import episodes
from scripts.news import paths
from scripts.errors import PipelineError

# old name inside a work dir -> new place, relative to the work dir
RESTAGE = [
    ("strips", datadirs.STRIPS_STAGE),
    ("2-refined", datadirs.REFINED_STAGE),
    ("sheets", datadirs.SHEETS_STAGE),
    ("sheets.json", os.path.join(datadirs.SHEETS_STAGE, "sheets.json")),
]
TRANSCRIPT_FILES = ("transcripts.json", "verified.json")


def move(src, dst):
    """The one place that moves anything -- tests swap it out."""
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    os.rename(src, dst)


def restage_moves(work):
    """[(src, dst)] inside one work dir; empty when already new-shaped."""
    out = []
    for old, new in RESTAGE:
        src = os.path.join(work, old)
        if os.path.lexists(src):
            out.append((src, os.path.join(work, new)))
    for name in sorted(os.listdir(work)) if os.path.isdir(work) else []:
        for base in TRANSCRIPT_FILES:
            if name == base or name.startswith(base + "."):
                out.append((os.path.join(work, name),
                            os.path.join(work, datadirs.TRANSCRIPTS_STAGE,
                                         name)))
    return out


def rewrite_strip_refs(work):
    """Point the timelines' strip paths at 2-strips/; return files changed."""
    changed = 0
    old = "strips" + os.sep
    for timeline in (datadirs.coarse_cues(work), datadirs.refined_cues(work)):
        if not os.path.exists(timeline):
            continue
        with open(timeline, encoding="utf-8") as handle:
            doc = json.load(handle)
        touched = False
        for cue in doc.get("cues", []):
            images = cue.get("images") or {}
            for line in images:
                if images[line].startswith(old):
                    images[line] = datadirs.strip_ref(
                        images[line][len(old):])
                    touched = True
        if touched:
            temporary = timeline + ".tmp"
            with open(temporary, "w", encoding="utf-8") as handle:
                json.dump(doc, handle, ensure_ascii=False, indent=2,
                          sort_keys=True)
            os.replace(temporary, timeline)
            changed += 1
    return changed


def video_months(catalogue):
    """Source file name -> broadcast month, off the catalogue."""
    months = {}
    for entry in catalogue:
        month = paths.month_of(entry["srt_name"])
        names = [entry.get("file") or ""]
        for one in (entry.get("原始影片檔案位置") or "").split(";"):
            names.append(os.path.basename(one.strip()))
        for name in names:
            if name:
                months[name] = month
    return months


def _month_of_slug(slug):
    try:
        return paths.month_of_slug(slug)
    except PipelineError:
        return None


def _month_of_name(name):
    try:
        return paths.month_of(name)
    except PipelineError:
        return None


def plan(out, catalogue):
    """(moves, left): moves are (src, dst); left are (path, why)."""
    news = os.path.join(out, "news")
    moves = []
    left = []

    for work in sorted(glob.glob(os.path.join(out, "mxf", "*.work"))):
        slug = os.path.basename(work)[:-len(".work")]
        month = _month_of_slug(slug)
        if month is None:
            left.append((work, "名稱看不出播出月份"))
            continue
        moves.append((work, os.path.join(news, "1-ocr", month,
                                         os.path.basename(work))))

    for log in sorted(glob.glob(os.path.join(out, "mxf-logs", "*"))):
        month = _month_of_slug(os.path.basename(log).split(".")[0])
        if month is None:
            left.append((log, "不是逐集 log（檔名開頭不是 slug）"))
            continue
        moves.append((log, os.path.join(news, "logs", month,
                                        os.path.basename(log))))

    for item in sorted(glob.glob(os.path.join(out, "mkv", "*"))):
        month = _month_of_name(os.path.basename(item).split(".")[0])
        if month is None:
            left.append((item, "檔名不是 srt_name"))
            continue
        moves.append((item, os.path.join(news, "mkv", month,
                                         os.path.basename(item))))

    for item in sorted(glob.glob(os.path.join(out, "asrmt", "*"))):
        month = _month_of_name(os.path.basename(item))
        if month is None:
            left.append((item, "名稱不是 srt_name"))
            continue
        moves.append((item, os.path.join(news, "2-asr", month,
                                         os.path.basename(item))))

    months = video_months(catalogue)
    for folder in sorted(glob.glob(os.path.join(out, "stage*"))):
        if not os.path.isdir(folder):
            continue
        kind = os.path.basename(folder)
        for item in sorted(glob.glob(os.path.join(folder, "*"))):
            month = months.get(os.path.basename(item))
            if month is None:
                left.append((item, "節目目錄對不到是哪一集"))
                continue
            moves.append((item, os.path.join(news, kind, month,
                                             os.path.basename(item))))
    return moves, left


def work_dirs_after(out, moves):
    """Every work dir whose inside may need restaging, after the moves."""
    found = []
    for _src, dst in moves:
        if dst.endswith(".work"):
            found.append(dst)
    for work in sorted(glob.glob(os.path.join(out, "news", "1-ocr", "*",
                                              "*.work"))):
        if work not in found:
            found.append(work)
    found.extend(sorted(glob.glob(os.path.join(out, "aiyalaeho",
                                               "*.work"))))
    return found


def _execute(moves, problems):
    done = []
    for src, dst in moves:
        if os.path.lexists(dst):
            problems.append("目的地已經有東西，沒搬：%s" % dst)
            continue
        move(src, dst)
        done.append((src, dst))
    return done


def self_check(done):
    """Names of planned moves that did not land."""
    problems = []
    for src, dst in done:
        if os.path.lexists(src):
            problems.append("舊位置還在：%s" % src)
        if not os.path.lexists(dst):
            problems.append("新位置沒有：%s" % dst)
    return problems


def main(argv=None, catalogue=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=os.path.join(paths.KITHANN, "out"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    if catalogue is None:
        catalogue = episodes.load()

    moves, left = plan(args.out, catalogue)
    for path, why in left:
        print("留在原地\t%s\t%s" % (path, why))
    if args.dry_run:
        for src, dst in moves:
            print("搬\t%s\t%s" % (src, dst))
        restage = 0
        for src, _dst in moves:
            if src.endswith(".work"):
                restage += len(restage_moves(src))
        for work in work_dirs_after(args.out, []):
            restage += len(restage_moves(work))
        print("（--dry-run）要搬 %d 項、work dir 內改名 %d 項、留在原地 %d 項"
              % (len(moves), restage, len(left)))
        return 0

    problems = []
    done = _execute(moves, problems)
    inner = []
    rewritten = 0
    for work in work_dirs_after(args.out, done):
        inner.extend(_execute(restage_moves(work), problems))
        rewritten += rewrite_strip_refs(work)
    problems.extend(self_check(done + inner))
    print("搬了 %d 項、work dir 內改名 %d 項、改寫時間軸 %d 份、留在原地 %d 項"
          % (len(done), len(inner), rewritten, len(left)))
    for line in problems:
        print("PROBLEM\t%s" % line)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
