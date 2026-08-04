#!/usr/bin/env python3
"""Name a work directory for a video, preferring the catalogue's metadata.

`ilrdf-corpus.csv` lists every episode with its 影片檔案位置, so a file that
appears there can be named the same way the February batch was
(年度_集數_播出日期_播出時段_族語別) and its SRT will sort and read
consistently with the rest. A file the catalogue does not know about still
gets processed -- it just falls back to its own stem.

Matching is on the file name alone, not the full path: the catalogue writes
`ilrdf-corpus/族語新聞/110.1-110.10/1月/…` while the server serves
`/docker/ilrdf-corpus/族語新聞/…`, and month folders differ in spelling
between the two (`2月` vs `2月原始mxf檔`).
"""
import csv
import os
import re
import sys

from scripts.news import paths

CATALOGUE = paths.CATALOGUE


def load():
    """file name -> catalogue row."""
    index = {}
    if not os.path.exists(CATALOGUE):
        return index
    with open(CATALOGUE, encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            path = (row.get("影片檔案位置") or "").strip()
            if path:
                index.setdefault(os.path.basename(path), row)
    return index


def slug_for(row, fallback):
    try:
        episode = "%03d" % int(row["集數"])
    except (KeyError, ValueError):
        return fallback
    parts = [row.get("年度", ""), episode, row.get("播出日期", ""),
             row.get("播出時段", ""), row.get("族語別(英)", ""),
             row.get("族語別(中)", "")]
    if not all(parts):
        return fallback
    return "_".join(parts)


def safe(name):
    """A stem that is fine as a directory name."""
    name = os.path.splitext(os.path.basename(name))[0]
    return re.sub(r"[\\/\s]+", "_", name).strip("_") or "unnamed"


def main():
    target = sys.argv[1]
    name = os.path.basename(target)
    row = load().get(name)
    fallback = safe(name)
    print(slug_for(row, fallback) if row else fallback)


if __name__ == "__main__":
    main()
