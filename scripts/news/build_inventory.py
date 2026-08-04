#!/usr/bin/env python3
"""Map each .mxf in the corpus to its catalogue row and name its SRT.

The filename carries the episode number and the time slot, and the episode
number is the day of the year, so episode + slot is enough to look the
episode up in ilrdf-corpus.csv. Two things in the filenames are unreliable
and are deliberately not trusted:

  * the two-digit year prefix -- five February 2021 files are stamped `20`
  * the NL code -- `21NL004_37午間` carries the 晚間 code but is 午間

Both were settled by reading the language badge burned into the bottom left
of the picture and checking it against the catalogue; all 24 files agree.
The slot therefore comes from the Chinese word in the filename, not from the
NL code, and the year comes from the catalogue.
"""
import csv
import json
import os
import re

from scripts.news import paths

CORPUS = paths.CORPUS
VIDEO_DIR = os.path.join(CORPUS, "2月")
CATALOGUE = paths.CATALOGUE

# Files whose byte count is far below the constant 6.30 MB/s of a complete
# master, i.e. the upload stopped early. Measured, not guessed.
TRUNCATED = {
    "21NL003_41午間族語新聞.mxf": "上傳不完整（2.83 MB/s，約為完整檔 45%，尾端解碼毀損）",
    "21NL004_37晚間族語新聞.mxf": "上傳不完整（3.44 MB/s，約為完整檔 55%，尾端解碼毀損）",
}

SLOT_RE = re.compile(r"_(\d+)(午間|晚間|晨間)")


def load_catalogue():
    """Index the catalogue by (年度, 集數, 播出時段)."""
    index = {}
    with open(CATALOGUE, encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            key = (row["年度"], row["集數"], row["播出時段"])
            index[key] = row
    return index


def find_transcript(date_key, slot, language):
    """Locate the 文稿 folder for an episode, if it was delivered.

    Folder names look like `1100201 1100原視新聞泰雅` -- a ROC date followed
    by loosely formatted text. The broadcast time must be looked for *after*
    the date, because the date itself starts with `1100` and would otherwise
    match every 午間 episode.

    The folder also names the language, usually abbreviated (`噶` for 噶瑪蘭,
    `拉阿` for 拉阿魯哇), so it is used only to confirm the date+time hit
    rather than to find it.
    """
    root = os.path.join(CORPUS, "110年2月_族語新聞文稿")
    if not os.path.isdir(root):
        return "", ""
    times = {"晨間": ("0800",), "午間": ("1100",), "晚間": ("1800", "2000")}
    hits = []
    for name in sorted(os.listdir(root)):
        if not name.startswith(date_key):
            continue
        tail = name[len(date_key):]
        for stamp in times.get(slot, ()):
            if stamp in tail:
                hits.append(name)
                break
    if not hits:
        return "", ""
    if len(hits) > 1:
        return "", "多個文稿符合 %s %s: %s" % (date_key, slot, hits)

    name = hits[0]
    warning = ""
    for size in (3, 2, 1):
        if language[:size] in name:
            break
    else:
        warning = "文稿資料夾語言與目錄不符: %r 應為 %s" % (name, language)
    return os.path.join("110年2月_族語新聞文稿", name), warning


def srt_name(row, episode):
    """SRT stem: 播出日期_集數_播出時段_族語別(英)_族語別(中).

    The year is not repeated as its own field because the broadcast date
    already carries it. The episode number is zero padded to three digits so
    the files sort in broadcast order; it is the day of the year, so it
    reaches 365.
    """
    return "_".join([
        row["播出日期"].replace("-", ""),
        "%03d" % int(episode),
        row["播出時段"],
        row["族語別(英)"],
        row["族語別(中)"],
    ])


def slugify(row, episode):
    """Work-directory name.

    Deliberately separate from the SRT name: work dirs hold gigabytes of
    strips and contact sheets and are referenced by a long-running decode, so
    renaming them to follow a change in the delivered file name would orphan
    work already done.
    """
    return "_".join([
        row["年度"],
        "%03d" % int(episode),
        row["播出日期"],
        row["播出時段"],
        row["族語別(英)"],
        row["族語別(中)"],
    ])


def build():
    index = load_catalogue()
    entries = []
    warnings = []
    for name in sorted(os.listdir(VIDEO_DIR)):
        if not name.endswith(".mxf"):
            continue
        match = SLOT_RE.search(name)
        if not match:
            raise SystemExit("cannot parse episode/slot from %r" % name)
        episode, slot = match.group(1), match.group(2)
        row = index.get(("2021", episode, slot))
        if row is None:
            raise SystemExit("no catalogue row for 集%s %s" % (episode, slot))

        date_key = "110%02d%02d" % tuple(
            int(p) for p in row["播出日期"].split("-")[1:])
        transcript, warning = find_transcript(
            date_key, slot, row["族語別(中)"])
        if warning:
            warnings.append(warning)
        entries.append({
            "file": name,
            "video": os.path.join(VIDEO_DIR, name),
            "slug": slugify(row, episode),
            "srt_name": srt_name(row, episode),
            "節目名稱": row["節目名稱"],
            "年度": row["年度"],
            "集數": episode,
            "播出日期": row["播出日期"],
            "播出時段": slot,
            "族語別(英)": row["族語別(英)"],
            "族語別(中)": row["族語別(中)"],
            "文稿位置": transcript,
            "truncated": TRUNCATED.get(name, ""),
        })
    return entries, warnings


if __name__ == "__main__":
    entries, warnings = build()
    out = paths.INVENTORY
    with open(out, "w", encoding="utf-8") as handle:
        json.dump(entries, handle, ensure_ascii=False, indent=2)
    usable = 0
    for e in entries:
        if not e["truncated"]:
            usable += 1
        flag = "SKIP" if e["truncated"] else "ok  "
        print("%s %-34s -> %s.srt  文稿=%s"
              % (flag, e["file"], e["srt_name"], e["文稿位置"] or "(無)"))
    print("\n%d files, %d usable, %d incomplete"
          % (len(entries), usable, len(entries) - usable))
    for warning in warnings:
        print("WARN", warning)
    print("wrote", out)
