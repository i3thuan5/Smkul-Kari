#!/usr/bin/env python3
"""Register SFTP-fetched episodes in the store's inventory, as pending.

`build_inventory.py` scans a local folder of .mxf masters, which is how the
February batch arrived. Everything since comes over SFTP one file at a time
and is deleted the moment its cues are cut, so by the time the inventory
matters there is no folder left to scan. This names those episodes from the
catalogue instead, using the file name alone -- exactly the way
`resolve_slug.py` names their work dirs -- and appends them.

    python3 -m scripts.news.add_episodes \\
        '族語新聞/110.1-110.10/7月/21NL004_38晚間族語新聞.mp4' ...

Paths are given relative to the corpus root, the same form `fetch_sftp.sh`
takes, and are recorded that way: the video is gone from this machine, so an
absolute local path would name a file that does not exist.

Episodes already in the inventory are left untouched, so it is safe to
re-run over a folder that was only partly fetched. The one exception is an
episode the inventory records as a truncated upload: two of the February
masters were short and were skipped, and both have a complete .mp4 on the
server, so a fresh source for one of those replaces the dead entry rather
than being refused as a duplicate.

Everything written here is marked `pending`. The inventory lives in the
store, and the store's guarantee is that it can rebuild every episode it
names -- which is not yet true of one that has only just been fetched.
`publish` clears the flag once the whole batch is finished, and until then
`rebuild --verify` skips those episodes and stays green.
"""
import argparse
import json
import os
import sys

from scripts.news import build_inventory
from scripts.news import paths
from scripts.news import resolve_slug

# The catalogue writes 文稿 paths from the repo root; the inventory has always
# written them from the corpus root, and make_all re-prefixes them for the
# tracker. Strip the one to get the other rather than inventing a third form.
SCRIPT_PREFIX = "kithann/tongan/"


def transcript_of(row):
    """The episode's 文稿 folder, relative to the corpus root."""
    value = (row.get("文稿位置") or "").strip()
    if not value:
        return ""
    if value.startswith(SCRIPT_PREFIX):
        return value[len(SCRIPT_PREFIX):]
    return value


def entry_for(remote_path, catalogue):
    """One inventory entry, or a reason it cannot be made."""
    name = os.path.basename(remote_path)
    row = catalogue.get(name)
    if row is None:
        return None, "%s is not in the catalogue" % name
    try:
        episode = int(row["集數"])
    except (KeyError, ValueError):
        return None, "%s has no usable 集數 in the catalogue" % name
    return {
        "file": name,
        "video": "ilrdf-corpus/" + remote_path.lstrip("/"),
        "slug": build_inventory.slugify(row, episode),
        "srt_name": build_inventory.srt_name(row, episode),
        "節目名稱": row["節目名稱"],
        "年度": row["年度"],
        "集數": row["集數"],
        "播出日期": row["播出日期"],
        "播出時段": row["播出時段"],
        "族語別(英)": row["族語別(英)"],
        "族語別(中)": row["族語別(中)"],
        "文稿位置": transcript_of(row),
        "truncated": "",
        # Registered, not delivered. Everything downstream needs this episode
        # named before anyone can start on it, but the inventory lives in the
        # store and the store's claim is that it can rebuild whatever it
        # names -- and there is nothing to rebuild from yet. `publish` clears
        # the flag once the whole batch is finished.
        "pending": True,
    }, ""


def add(remote_paths):
    """Merge entries for the given videos into the inventory.

    Returns the full entry list plus what happened to each video, so the
    caller can report it and decide whether to write.
    """
    catalogue = resolve_slug.load()
    with open(paths.INVENTORY, encoding="utf-8") as handle:
        entries = json.load(handle)
    known = {}
    for position, entry in enumerate(entries):
        known[entry["slug"]] = position

    added = []
    replaced = []
    skipped = []
    errors = []
    for remote in remote_paths:
        entry, problem = entry_for(remote, catalogue)
        if problem:
            errors.append(problem)
            continue
        position = known.get(entry["slug"])
        if position is not None:
            if not entries[position]["truncated"]:
                skipped.append(entry["srt_name"])
                continue
            # A complete source for an episode that was written off as a
            # short upload. Keep its place in the running order.
            entries[position] = entry
            replaced.append(entry)
            continue
        known[entry["slug"]] = len(entries)
        entries.append(entry)
        added.append(entry)
    return entries, added, replaced, skipped, errors


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("videos", nargs="+",
                    help="video paths relative to the corpus root")
    ap.add_argument("-n", "--dry-run", action="store_true")
    args = ap.parse_args()

    entries, added, replaced, skipped, errors = add(args.videos)
    for line in errors:
        print("ERROR", line)
    for name in skipped:
        print("skip  %s (already in inventory)" % name)
    for verb, group in (("add", added), ("redo", replaced)):
        for entry in group:
            print("%-5s %-46s 文稿=%s"
                  % (verb, entry["srt_name"], entry["文稿位置"] or "(無)"))
    if errors:
        return 1
    if args.dry_run:
        print("\n%d to add, %d to replace (dry run)"
              % (len(added), len(replaced)))
        return 0
    if added or replaced:
        with open(paths.INVENTORY, "w", encoding="utf-8") as handle:
            json.dump(entries, handle, ensure_ascii=False, indent=2)
    print("\n%d added, %d replaced, %d already there; inventory now holds "
          "%d episode(s)"
          % (len(added), len(replaced), len(skipped), len(entries)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
