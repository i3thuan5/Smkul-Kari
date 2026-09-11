#!/usr/bin/env python3
"""Check a batch of vision TSVs and import them into their work dir.

Two things are checked before anything is written, because both fail
silently otherwise:

  format   a blank cue is written as `12<TAB>han` when the trailing tab gets
           stripped, which the importer reads as a missing field
  mapping  every cue number must actually appear on a sheet the reader was
           given. A row for a cue outside that set means the reader drifted,
           and the text would land on the wrong subtitle -- far worse than a
           misread character, because nothing downstream looks wrong.
"""
import argparse
import glob
import json
import os

from scripts.news import episodes
from scripts.news import paths
from scripts.ocr import transcripts
from scripts.errors import PipelineError

WORK = paths.WORK

# gap_sheets kā 校讀用ê contact sheet 园佇 <slug>.work，
# 逐擺攏仝款；本來是 --suffix，毋過對來到今無人傳過別ê值。
WORK_SUFFIX = ".work"


def _cue_order(row):
    """Sort key: by cue number, keeping unnumbered rows at the end.

    An unnumbered row is a batch `_audit_row` will reject; it is kept and
    written back so that the rejection still names it.
    """
    index = row.split("\t")[0]
    if index.isdigit():
        return (0, int(index))
    return (1, 0)


def normalise(path):
    """Restore the blank third field, and put the rows in cue order.

    The sheets are packed widest-with-widest, so one of them carries cue
    703, 612, 699... and the reader writes its TSV in the order it saw
    them. `Kari-SRT/` is read by people, and numbers that jump about make
    it unreadable, so the order is restored here rather than asked for in
    the reading brief -- the machine is the reliable one.

    The sort is stable, which is what keeps 開會了's two lines of one cue
    (formosan above han) in the order the reader wrote them.
    """
    rows = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            parts = line.split("\t")
            while len(parts) < 3:
                parts.append("")
            rows.append("\t".join(parts[:3]))
    rows.sort(key=_cue_order)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(rows) + "\n")
    return rows


def _tsvdir_of(slug):
    """Default TSV dir: news/1-ocr/2-vision/<srt_name>, from the slug."""
    for entry in episodes.load():
        if entry["slug"] == slug:
            return paths.stage_path(paths.KARI_VISION,
                                    entry["srt_name"])
    raise PipelineError("slug %r not in inventory; pass a TSV dir "
                        "explicitly" % slug)


def _audit_row(path, row, on_sheets, seen, problems):
    """One TSV row: indexed, on a sheet somebody read, claimed once."""
    index = row.split("\t")[0]
    if not index.isdigit():
        problems.append("%s: bad index %r" % (path, index))
        return
    index = int(index)
    if index not in on_sheets:
        problems.append("%s: cue %d was not on any sheet given to a "
                        "reader" % (path, index))
    if index in seen and seen[index] != path:
        problems.append("cue %d appears in both %s and %s"
                        % (index, os.path.basename(seen[index]),
                           os.path.basename(path)))
    seen[index] = path


def _audit_rows(files, on_sheets):
    seen = {}
    problems = []
    for path in files:
        for row in normalise(path):
            _audit_row(path, row, on_sheets, seen, problems)
    return seen, problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("tsvdir", nargs="?", default="",
                    help="TSV dir; default news/1-ocr/2-vision/<srt_name> "
                         "looked up from the slug")
    args = ap.parse_args()

    slug = paths.check_name(args.slug, "slug")
    tsvdir = paths.check_under(args.tsvdir or _tsvdir_of(slug), "tsvdir")

    work = os.path.join(WORK, slug + WORK_SUFFIX)
    with open(os.path.join(work, "sheets.json"), encoding="utf-8") as handle:
        sheets = json.load(handle)
    on_sheets = set()
    for cues in sheets.values():
        on_sheets.update(cues)

    # `b*.tsv` ê 才是視覺辨識ê批。Store 內底 644 个 TSV 有 643 个
    # 按呢號名；賰彼一个（20210209_040 ê `sample.tsv`）是逐 72 條抽
    # 4 條ê抽查檔，內容對 `b*.tsv` 抄ê，ingest 伊加無半字，顛倒會
    # 予 `_audit_row` 掠做「仝一个 cue 出現佇兩个檔」規批擋落來。
    files = sorted(glob.glob(os.path.join(tsvdir, "b*.tsv")))
    seen, problems = _audit_rows(files, on_sheets)

    if problems:
        for line in problems[:20]:
            print("PROBLEM", line)
        raise PipelineError("%d problem(s); nothing imported" % len(problems))

    missing = sorted(on_sheets - set(seen))
    print("%d TSV file(s), %d cue(s) read, %d of %d gap cues covered"
          % (len(files), len(seen), len(seen), len(on_sheets)))
    if missing:
        print("still unread: %d (e.g. %s)" % (len(missing), missing[:10]))

    covered = total = 0
    for path in files:
        _rows, covered, total = transcripts.import_tsv(work, path)
    print("imported; transcripts now cover %d/%d cues" % (covered, total))


if __name__ == "__main__":
    main()
