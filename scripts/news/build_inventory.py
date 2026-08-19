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

This scans a LOCAL FOLDER, which is how the February masters arrived. Every
batch since came over SFTP and was deleted as soon as its cues were cut, so
there is no folder left to scan and `add_episodes.py` registers those from
the file name instead. Both write the same inventory -- the store's -- so a
scan merges rather than replaces; see merge().
"""
import argparse
import csv
import json
import os
import re
import sys

from scripts.news import paths

ETH_EN = "族語別(英)"
ETH_ZH = "族語別(中)"

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
        row[ETH_EN],
        row[ETH_ZH],
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
        row[ETH_EN],
        row[ETH_ZH],
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
            date_key, slot, row[ETH_ZH])
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
            ETH_EN: row[ETH_EN],
            ETH_ZH: row[ETH_ZH],
            "文稿位置": transcript,
            "truncated": TRUNCATED.get(name, ""),
        })
    return entries, warnings


def merge(scanned, existing):
    """Fold a scan into the inventory without dropping anyone else's work.

    The inventory is the store's, and most of what is in it did not come from
    scanning a local folder -- `add_episodes` puts SFTP-fetched episodes there
    from the file name alone, because their videos are deleted the moment the
    cues are cut. Writing a scan over the top would delete every one of them,
    and the folder this scans (`CORPUS/2月`) does not even exist on machines
    that only ever used SFTP.

    So a scan may add episodes and may not remove any. An episode already
    present is left exactly as it is: it may carry `partial`, a corrected
    `文稿位置`, or a source recovered after being written off, none of which a
    fresh scan of the original masters knows about.
    """
    known = set()
    for entry in existing:
        known.add(entry["slug"])
    merged = list(existing)
    added = []
    for entry in scanned:
        if entry["slug"] in known:
            continue
        merged.append(entry)
        added.append(entry)
    return merged, added


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--replace", action="store_true",
                    help="discard the existing inventory and write only what "
                         "this scan found. Destructive: everything registered "
                         "by add_episodes is lost.")
    ap.add_argument("-n", "--dry-run", action="store_true")
    args = ap.parse_args(argv)

    scanned, warnings = build()
    existing = []
    if os.path.exists(paths.INVENTORY):
        with open(paths.INVENTORY, encoding="utf-8") as handle:
            existing = json.load(handle)

    if args.replace:
        entries, added = scanned, scanned
        dropped = len(existing) - len(scanned)
        if dropped > 0:
            print("WARNING: --replace drops %d episode(s) already in the "
                  "inventory" % dropped)
    else:
        entries, added = merge(scanned, existing)

    usable = 0
    for e in scanned:
        if not e["truncated"]:
            usable += 1
        flag = "SKIP" if e["truncated"] else "ok  "
        print("%s %-34s -> %s.srt  文稿=%s"
              % (flag, e["file"], e["srt_name"], e["文稿位置"] or "(無)"))
    print("\nscanned %d files, %d usable, %d incomplete; %d new to the "
          "inventory, which now holds %d"
          % (len(scanned), usable, len(scanned) - usable,
             len(added), len(entries)))
    for warning in warnings:
        print("WARN", warning)

    if args.dry_run:
        print("(dry run, nothing written)")
        return
    with open(paths.INVENTORY, "w", encoding="utf-8") as handle:
        json.dump(entries, handle, ensure_ascii=False, indent=2)
    print("wrote", paths.INVENTORY)


if __name__ == "__main__":
    sys.exit(main())
