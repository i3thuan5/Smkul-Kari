#!/usr/bin/env python3
"""Name an episode from the catalogue: which row a file is, and what to
call the work dir and the deliverable.

`news/smkul.csv` lists every episode with its 原始影片檔案位置, so a file that
appears there can be named the same way the February batch was
(年度_集數_播出日期_時段_族語別) and its SRT will sort and read
consistently with the rest. A file the catalogue does not know about still
gets processed -- it just falls back to its own stem.

**Matching is on the whole path**, normalised. It used to be on the file
name alone, taken from the whole cell -- and the cell can hold several
paths separated by semicolons, so `os.path.basename()` returned only the
last one and 78 file names corpus-wide could not be found at all. A miss
falls back to the file's own stem, which means no 集數, no 播出日期 and no
slug, and nothing says so.

Normalising is what lets the same file be named three ways: the catalogue
writes `ilrdf-corpus/族語新聞/…`, the server serves
`/docker/ilrdf-corpus/族語新聞/…`, and `fetch_sftp.sh` passes
`族語新聞/…`. A bare file name still resolves, but only while it is
unambiguous -- three files in the catalogue are claimed by two episodes
each, and the old index gave them to whichever row was read first.
"""
import csv
import os
import re
import sys

from scripts import catalogue_checks as checks
from scripts.news import paths
from scripts.news import sources
from scripts.errors import PipelineError

CATALOGUE = paths.TRACKER_STORE

ETH_EN = "族語別(英)"
ETH_ZH = "族語別(中)"

# What the catalogue's paths are relative to, and what the server prefixes
# them with. Stripped so that one file has one key however it was written.
CORPUS_ROOT = "ilrdf-corpus/"
SERVER_ROOT = "docker/"


def normalise(path):
    """One key per file, whichever of the three prefixes it arrived with."""
    path = path.strip().lstrip("/")
    for prefix in (SERVER_ROOT, CORPUS_ROOT):
        if path.startswith(prefix):
            path = path[len(prefix):]
    return path


class Catalogue(object):
    """The catalogue, indexed so that a file can be looked up by path.

    Two indexes: the whole normalised path, and the bare file name. The
    second is a convenience for call sites that only have a name, and it
    deliberately refuses ambiguous names rather than picking one.
    """

    def __init__(self, rows):
        self.rows = list(rows)
        self.by_path = {}
        self.by_name = {}
        claimed = {}
        for row in rows:
            for path in sources.candidates(row):
                key = normalise(path)
                self.by_path.setdefault(key, row)
                name = os.path.basename(key)
                claimed.setdefault(name, [])
                if row not in claimed[name]:
                    claimed[name].append(row)
        for name, owners in claimed.items():
            if len(owners) == 1:
                self.by_name[name] = owners[0]
            else:
                self.by_name[name] = None

    def row_for(self, path):
        """(row, problem) -- the catalogue row this file belongs to."""
        key = normalise(path)
        row = self.by_path.get(key)
        if row is not None:
            return row, ""
        name = os.path.basename(key)
        if name in self.by_name:
            row = self.by_name[name]
            if row is None:
                return None, ("%s 予兩集以上宣告，無法度對檔名判斷是佗一集"
                              % name)
            return row, ""
        return None, "%s 毋佇目錄內底" % name

    def get(self, path):
        """The row, or None -- for call sites that do not want the reason."""
        return self.row_for(path)[0]


def load(path=None):
    """Read the catalogue. A missing file is an empty index, not a crash."""
    rows = []
    source = path or CATALOGUE
    if os.path.exists(source):
        with open(source, encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                rows.append(row)
    return Catalogue(rows)


def _field(row, name):
    value = (row.get(name) or "").strip()
    if not value:
        raise PipelineError("目錄這逝欠 %s，無法度命名：%r" % (name, row))
    return value


def srt_name(row, episode):
    """SRT stem: 播出日期_集數_播出時段_族語別(英)_族語別(中).

    The year is not repeated as its own field because the broadcast date
    already carries it. The episode number is zero padded to three digits so
    the files sort in broadcast order; it is the day of the year, so it
    reaches 365.
    """
    return "_".join([
        _field(row, "播出日期").replace("-", ""),
        "%03d" % int(episode),
        _field(row, "節目名稱") and checks.slot_of(row["節目名稱"]),
        _field(row, ETH_EN),
        _field(row, ETH_ZH),
    ])


def slugify(row, episode):
    """Work-directory name.

    Deliberately separate from the SRT name: work dirs hold gigabytes of
    strips and contact sheets and are referenced by a long-running decode, so
    renaming them to follow a change in the delivered file name would orphan
    work already done.
    """
    return "_".join([
        _field(row, "年度"),
        "%03d" % int(episode),
        _field(row, "播出日期"),
        _field(row, "節目名稱") and checks.slot_of(row["節目名稱"]),
        _field(row, ETH_EN),
        _field(row, ETH_ZH),
    ])


def slug_for(row, fallback):
    try:
        episode = "%03d" % int(row["集數"])
    except (KeyError, ValueError):
        return fallback
    try:
        slot = checks.slot_of(row.get("節目名稱", ""))
    except PipelineError:
        return fallback
    parts = [row.get("年度", ""), episode, row.get("播出日期", ""),
             slot, row.get(ETH_EN, ""), row.get(ETH_ZH, "")]
    if not all(parts):
        return fallback
    return "_".join(parts)


def safe(name):
    """A stem that is fine as a directory name."""
    name = os.path.splitext(os.path.basename(name))[0]
    return re.sub(r"[\\/\s]+", "_", name).strip("_") or "unnamed"


def main():
    target = sys.argv[1]
    row, _ = load().row_for(target)
    fallback = safe(target)
    print(slug_for(row, fallback) if row else fallback)


if __name__ == "__main__":
    main()
