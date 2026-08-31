#!/usr/bin/env python3
"""Cut one cue in two at a measured time, and carry everything else along.

    python3 -m scripts.news.split_cue <work-dir stem> <cue> <seconds> \\
        --first "頭前彼句" --second "後壁彼句"

WHY
---
Six sentences were found on screen that the store does not hold, and all six
failed the same way: the cue boundary landed in the middle of two sentences
and the segmenter could not see the change -- a weather graphic too bright
for the mask, or two lines swapping while the background held still. One cue
carries two sentences, and the reader could only write one of them down.

The times came from measurement, not from re-running the segmenter: each
split point is known to about 0.03 s, from stepping native frames across the
cue. So this does not re-cut anything; it divides a span that is already
right.

THE `images` FIELD IS LEFT ALONE, ON PURPOSE
--------------------------------------------
Splitting renumbers every cue after it, and the obvious next move -- rename
the strips to match -- is the one to avoid. Strip filenames are already
*not* cue numbers across most of this corpus: `safe_resplit` renumbered
during the reread without renaming, so 46,665 of 75,290 cues (62%, in 48
episodes) have a strip whose filename is some older number.
`strips/00844_han.png` is cue 951.

Renaming would make that true again for one episode while leaving it false
everywhere else, and renaming is the step most likely to go wrong: cue 400
moving to 402 clobbers the 402 still on disk unless the order is right.
Keeping each cue's own `images` value means the mapping stays correct
without moving a single file, and `images` is what every reader is told to
trust.

The new second half has no strip yet -- an empty `images` says so, rather
than pointing at the first half's picture and quietly being wrong.
"""
import argparse
import glob
import json
import os
import sys

from scripts.errors import PipelineError
from scripts.news import paths


def split(cues, index, at):
    """`cues` with cue `index` divided at `at` seconds, renumbered 1..N.

    Every other cue keeps its times and its `images`; see the module note
    on why the strips are not renamed.
    """
    if index < 1 or index > len(cues):
        raise PipelineError("cue %d 佇 %d 條內底無" % (index, len(cues)))
    one = cues[index - 1]
    if not one["start"] < at < one["end"]:
        raise PipelineError(
            "切點 %.3f 無佇 cue %d（%.3f–%.3f）內底"
            % (at, index, one["start"], one["end"]))
    head = dict(one)
    head["end"] = at
    tail = dict(one)
    tail["start"] = at
    tail["images"] = {}
    out = []
    for cue in cues[:index - 1]:
        out.append(dict(cue))
    out.append(head)
    out.append(tail)
    for cue in cues[index:]:
        out.append(dict(cue))
    for number, cue in enumerate(out, 1):
        cue["index"] = number
    return out


def remap_rows(rows, index, first, second):
    """[(cue, text)] with `index` replaced by two rows and the rest shifted."""
    out = []
    for cue, text in rows:
        if cue < index:
            out.append((cue, text))
        elif cue > index:
            out.append((cue + 1, text))
    out.append((index, first))
    out.append((index + 1, second))
    out.sort(key=lambda row: row[0])
    return out


def remap_sheets(sheets, index):
    """`sheets.json` with cue `index` split: later cues shift, the new
    half joins the sheet its first half is already on.

    `ingest` uses this file to answer "was this cue ever put in front of a
    reader", and refuses an episode carrying one that was not. That guard
    is right -- it is what stops a cue nobody looked at being invented --
    so the file has to move with the numbering rather than the guard being
    loosened. The second half belongs on the same sheet as the first: the
    two sentences were in one cell on screen, and that cell is what the
    reader saw.
    """
    out = {}
    for name in sheets:
        cues = []
        for cue in sheets[name]:
            if cue < index:
                cues.append(cue)
            elif cue == index:
                cues.append(cue)
                cues.append(cue + 1)
            else:
                cues.append(cue + 1)
        out[name] = sorted(cues)
    return out


# ------------------------------------------------------------------ I/O


def read_tsv(path):
    rows = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 3 and parts[0].isdigit():
                rows.append((int(parts[0]), parts[2]))
    return rows


def write_tsv(path, rows):
    with open(path, "w", encoding="utf-8") as handle:
        for cue, text in rows:
            handle.write("%d\than\t%s\n" % (cue, text))


def holding(folder, index):
    """The TSV that carries cue `index`, or the last one before it.

    The two halves have to land in one file, and it has to be the file the
    range belongs to -- writing them anywhere else makes `ingest` report a
    cue in two files and refuse the whole episode.
    """
    best = None
    for path in sorted(glob.glob(os.path.join(folder, "b*.tsv"))):
        rows = read_tsv(path)
        if not rows:
            continue
        low = min(cue for cue, _ in rows)
        high = max(cue for cue, _ in rows)
        if low <= index <= high:
            return path
        if high < index:
            best = path
    if best is None:
        raise PipelineError("揣無會使囥 cue %d ê TSV" % index)
    return best


def vision_folders(name):
    """Both places a cue's text can live, in the order `rebuild` reads them.

    `rebuild` merges `3-vision` and `4-vision-rtf`, the rtf side winning.
    Renumbering only the first leaves the second off by one -- and
    **`ingest` does not notice**, because it only walks `3-vision`. It was
    `rebuild --verify` that caught it: of the four episodes split on
    2026-08-31, exactly the two with rtf files came out wrong.
    """
    out = []
    for root in (paths.KARI_VISION, paths.KARI_VISION_RTF):
        out.append(os.path.join(root, paths.month_of(name), name))
    return out


def apply(stem, index, at, first, second):
    """Do the split across cues.json and the episode's vision TSVs."""
    work = os.path.join(paths.WORK, stem + ".B.work")
    path = os.path.join(work, "cues.json")
    with open(path, encoding="utf-8") as handle:
        book = json.load(handle)
    book["cues"] = split(book["cues"], index, at)
    book["split"] = book.get("split", []) + [
        {"cue": index, "at": at, "first": first, "second": second}]
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(book, handle, ensure_ascii=False, indent=2)

    sheets_path = os.path.join(work, "sheets.json")
    if os.path.exists(sheets_path):
        with open(sheets_path, encoding="utf-8") as handle:
            sheets = json.load(handle)
        with open(sheets_path, "w", encoding="utf-8") as handle:
            json.dump(remap_sheets(sheets, index), handle,
                      ensure_ascii=False)

    name = None
    for entry in paths.load_inventory():
        if entry["slug"] == stem:
            name = entry["srt_name"]
    if name is None:
        raise PipelineError("inventory 內底揣無 %s" % stem)
    folders = vision_folders(name)
    # The two halves are written into `3-vision` only: that is where a
    # reader's own words go. `4-vision-rtf` is renumbered but never gains
    # a row -- it is a record of what the 文稿 once supplied, and nothing
    # new belongs in it.
    target = holding(folders[0], index)
    for folder in folders:
        for one in sorted(glob.glob(os.path.join(folder, "b*.tsv"))):
            rows = read_tsv(one)
            if one == target:
                rows = remap_rows(rows, index, first, second)
            else:
                moved = []
                for cue, text in rows:
                    moved.append((cue + 1 if cue > index else cue, text))
                rows = moved
            write_tsv(one, rows)
    return len(book["cues"])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("stem")
    ap.add_argument("cue", type=int)
    ap.add_argument("at", type=float)
    ap.add_argument("--first", required=True)
    ap.add_argument("--second", required=True)
    args = ap.parse_args(argv)
    total = apply(args.stem, args.cue, args.at, args.first, args.second)
    print("%s：cue %d 對 %.3f 秒剖開，總數變 %d"
          % (args.stem, args.cue, args.at, total))
    return 0


if __name__ == "__main__":
    sys.exit(main())
