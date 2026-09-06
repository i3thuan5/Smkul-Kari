#!/usr/bin/env python3
"""Rewrite the store's JSON so a person can read it. Once.

    python3 -m scripts.news.redump_store            # 看伊beh改佗幾份
    python3 -m scripts.news.redump_store --write    # 真正改

`Kari-SRT/` is the deliverable, and every file in it should open and read
(使用者裁定 2026-09-04). Most of it already does -- SRT and CSV are text
by nature -- but the JSON was written compact and ASCII-escaped, which
makes it unreadable in two separate ways: one line means a diff of a
one-value change shows the whole file, and `\\uXXXX` means the Chinese
and Formosan text is not there to be read at all.

So: indent 2, sorted keys, characters as themselves. JSONL caches
(mt-cache, quality-cache) are the exception -- one record per line is
what makes them appendable -- so they get sorted keys and readable
characters but stay one line each, and keep their record order.

**Formatting only.** What each file *says* is unchanged, which is what
makes this safe to run over the store: `rebuild --verify` derives the
delivered SRTs from these inputs and compares them byte for byte, so it
would catch a sweep that lost or reordered a value. It reads content,
not layout, so a reformatted input rebuilds the same SRT.

Idempotent: a file already in the target shape is left alone, so an
interrupted sweep just carries on.
"""
import argparse
import json
import os
import sys

from scripts.news import paths


def _dump(doc):
    return json.dumps(doc, ensure_ascii=False, indent=2,
                      sort_keys=True) + "\n"


def redump_json(path):
    """Rewrite one JSON file in the readable shape; did it change?"""
    with open(path, encoding="utf-8") as handle:
        before = handle.read()
    after = _dump(json.loads(before))
    if after == before:
        return False
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(after)
    return True


def _jsonl_text(before):
    """One record per line, keys sorted, characters as themselves."""
    out = []
    for line in before.splitlines():
        if not line.strip():
            continue
        out.append(json.dumps(json.loads(line), ensure_ascii=False,
                              sort_keys=True) + "\n")
    return "".join(out)


def redump_jsonl(path):
    """Same for a one-record-per-line cache; did it change?

    Record order is kept. The cache is content-addressed so order does
    not carry meaning -- but reordering it would put the whole file in
    the diff, and then nobody can see what was actually appended.
    """
    with open(path, encoding="utf-8") as handle:
        before = handle.read()
    after = _jsonl_text(before)
    if after == before:
        return False
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(after)
    return True


def _files(root):
    """Every .json and .jsonl under `root`, in a stable order."""
    found = []
    for folder, _dirs, names in os.walk(root):
        for name in sorted(names):
            if name.endswith(".json") or name.endswith(".jsonl"):
                found.append(os.path.join(folder, name))
    found.sort()
    return found


def _would_change(path):
    """Is this file already in the target shape?"""
    with open(path, encoding="utf-8") as handle:
        before = handle.read()
    if path.endswith(".jsonl"):
        after = _jsonl_text(before)
    else:
        after = _dump(json.loads(before))
    return after != before


def sweep(roots, write=False):
    """Return (paths that need rewriting, count already tidy).

    Without `write` nothing is touched -- the list is the plan.
    """
    changed = []
    tidy = 0
    for root in roots:
        if not os.path.isdir(root):
            continue
        for path in _files(root):
            if not _would_change(path):
                tidy += 1
                continue
            changed.append(path)
            if write:
                if path.endswith(".jsonl"):
                    redump_jsonl(path)
                else:
                    redump_json(path)
    return changed, tidy


def store_roots():
    """The store folders this sweep covers: the whole news corpus.

    Everything, not a chosen few: the rule is about the store, and a
    file left out is a file that reads differently from its neighbours
    for no reason anyone can see later.
    """
    return [paths.NEWS_STORE]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--write", action="store_true",
                    help="真正改（無這个就干焦報伊beh改佗幾份）")
    ap.add_argument("--root", action="append", default=None,
                    help="欲掃ê資料夾（會使講幾若擺；預設是店面）")
    args = ap.parse_args(argv)

    roots = args.root or store_roots()
    changed, tidy = sweep(roots, write=args.write)
    for path in changed:
        print(os.path.relpath(path, paths.ROOT))
    if args.write:
        print("\n改 %d 份，本底就好勢ê %d 份" % (len(changed), tidy))
    else:
        print("\n%d 份愛改、%d 份本底就好勢；加 --write 才真正改"
              % (len(changed), tidy))
    return 0


if __name__ == "__main__":
    sys.exit(main())
