#!/usr/bin/env python3
"""Write the delivered SRT's name into the catalogue, as a generated column.

    python3 -m scripts.news.name_catalogue           # fill the column
    python3 -m scripts.news.name_catalogue --check   # verify, write nothing

`srt_name` is what everyone -- the store, `smkul.csv`, and the outside
bodies this corpus is shared with -- calls an episode, but the catalogue
did not carry it: a person holding one catalogue row had no way to say
which SRT it becomes. So the column is here for them to read.

It is **generated, never hand-maintained**. The name is derived from five
columns already in the row (`resolve_slug.srt_name`), so a stored copy is a
second source of truth that can drift: correct a typo in `族語別(中)` and
the two disagree with nothing to say which wins. `--check` is the answer to
that -- it recomputes every cell and reports the ones that no longer match,
so a hand edit is caught instead of quietly becoming the new name.

Rows the catalogue cannot name get an empty cell rather than a guess. Today
that is the 46 《開會了》 rows, which carry neither 年度 nor 播出日期.

The file is CRLF with a BOM because the people reading it open it in Excel;
`rewrite()` preserves both, so filling the column shows up as one added
field per line and not as a whole-file diff.
"""
import argparse
import csv
import os
import sys

from scripts.news import paths
from scripts.news import resolve_slug
from scripts.errors import PipelineError

COLUMN = "srt_name"

# What the catalogue is on disk. Excel is the reader on the other end.
ENCODING = "utf-8-sig"
NEWLINE = "\r\n"


def name_of(row):
    """This row's SRT name, or "" when the catalogue cannot name it.

    Empty is a real answer, not a failure: `resolve_slug.srt_name` raises
    when a naming field is blank, and a catalogue that lists a programme
    with no broadcast date should say so rather than invent a name.
    """
    try:
        return resolve_slug.srt_name(row, row["集數"])
    except (PipelineError, KeyError, TypeError, ValueError):
        return ""


def fieldnames(existing):
    """Column order with `srt_name` first, everything else as it was.

    First because it is the identifier -- whoever opens the file should see
    it without scrolling past twelve columns of paths.
    """
    out = [COLUMN]
    for name in existing:
        if name != COLUMN:
            out.append(name)
    return out


def named(rows, existing):
    """(rows with the column filled, the new column order).

    The input rows are copied, not mutated: callers hold catalogue rows
    that other code is still reading.
    """
    out = []
    for row in rows:
        copy = dict(row)
        copy[COLUMN] = name_of(row)
        out.append(copy)
    return out, fieldnames(existing)


def check(rows):
    """[(line, stored, wanted)] -- cells that disagree with the算法.

    `line` is the line number in the file, counting the header as 1, so
    that the report points at something a person can open and look at.
    """
    bad = []
    for index, row in enumerate(rows):
        wanted = name_of(row)
        stored = row.get(COLUMN)
        if stored is None or stored.strip() != wanted:
            bad.append((index + 2, stored, wanted))
    return bad


def read(path=None):
    """(rows, column order) as the file has them."""
    source = path or paths.CATALOGUE
    if not os.path.exists(source):
        raise PipelineError("揣無目錄：%s" % source)
    with open(source, encoding=ENCODING, newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        head = list(reader.fieldnames or [])
    return rows, head


def write(path, rows, head):
    with open(path, "w", encoding=ENCODING, newline="") as handle:
        writer = csv.DictWriter(handle, head, lineterminator=NEWLINE)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def rewrite(path=None):
    """Fill the column in place; return how many rows got a name."""
    target = path or paths.CATALOGUE
    rows, head = read(target)
    rows, head = named(rows, head)
    write(target, rows, head)
    got = 0
    for row in rows:
        if row[COLUMN]:
            got += 1
    return got


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("catalogue", nargs="?", default=None,
                        help="目錄 CSV（省略就用 paths.CATALOGUE）")
    parser.add_argument("--check", action="store_true",
                        help="干焦核對，無寫入；無合就 exit 1")
    args = parser.parse_args()
    target = args.catalogue or paths.CATALOGUE

    if args.check:
        rows, head = read(target)
        if COLUMN not in head:
            print("%s 猶未有 %s 這欄" % (target, COLUMN))
            return 1
        bad = check(rows)
        for line, stored, wanted in bad:
            print("第%d逝 %r 應該是 %r" % (line, stored, wanted))
        print("%s：%d 逝，無合 %d 逝" % (target, len(rows), len(bad)))
        return 1 if bad else 0

    rows, _ = read(target)
    got = rewrite(target)
    print("%s：%d 逝，命著名 %d 逝，留空 %d 逝"
          % (target, len(rows), got, len(rows) - got))
    return 0


if __name__ == "__main__":
    sys.exit(main())
