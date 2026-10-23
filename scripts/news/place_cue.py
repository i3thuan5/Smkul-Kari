#!/usr/bin/env python3
"""Put a cue where frame-stepping says one belongs, or move a cue's ends.

    python3 -m scripts.news.place_cue <work-dir stem> insert <start> <end> \\
        --text "畫面頂懸彼句"
    python3 -m scripts.news.place_cue <work-dir stem> bounds <cue> \\
        <start> <end>

WHY
---
`split_cue` divides a cue that exists. Some lines never got a cue at all:
2021-12-03 337 晚間 at 1178–1180 s shows two one-character captions, 山 then
海, over an aerial shot of breaking waves. The surf alone carries 314–504
ink per sample, a single character adds about 150, and consecutive masks
differ by 0.41–0.73 -- past the 0.35 change threshold every time -- so the
segmenter (and a re-cut with the same preset) sees one unstable blur. 山
has no cue; 海's cue starts 0.58 s late and runs into the next one.

The times here come from stepping native frames, the same as `split_cue`;
nothing is re-segmented. Both operations refuse to make cues overlap: if a
measured span runs into a neighbour, move that neighbour first with
`bounds`, so every change is one the caller chose.

The inserted cue has no strip (`images` is empty, as for split_cue's second
half) and is marked `placed`; later cues are renumbered without renaming
their strips, for the reasons in `split_cue`.
"""
import argparse
import glob
import json
import os
import sys

from scripts.errors import PipelineError
from scripts.news import episodes
from scripts.news import paths
from scripts.news import split_cue


def _mid(start, end):
    return round((start + end) / 2, 3)


def insert(cues, start, end):
    """(cues with a new cue over [start, end], its 1-based index)."""
    if not start < end:
        raise PipelineError("插入ê cue 起迄 %.3f–%.3f 毋著" % (start, end))
    index = len(cues) + 1
    for position, one in enumerate(cues):
        if one["start"] >= end:
            index = position + 1
            break
    before = cues[index - 2] if index > 1 else None
    after = cues[index - 1] if index <= len(cues) else None
    if (before and before["end"] > start) or (after and after["start"] < end):
        raise PipelineError(
            "%.3f–%.3f 硩著隔壁ê cue，先用 bounds 調彼條" % (start, end))
    new = {"start": start, "end": end, "frames": 0, "ink": 0,
           "sample_ts": _mid(start, end), "images": {}, "placed": True}
    out = []
    for one in cues[:index - 1]:
        out.append(dict(one))
    out.append(new)
    for one in cues[index - 1:]:
        out.append(dict(one))
    for number, one in enumerate(out, 1):
        one["index"] = number
    return out, index


def set_bounds(cues, index, start, end):
    """cues with cue `index` moved to [start, end]; neighbours untouched."""
    if index < 1 or index > len(cues):
        raise PipelineError("cue %d 佇 %d 條內底無" % (index, len(cues)))
    if not start < end:
        raise PipelineError("cue %d 起迄 %.3f–%.3f 毋著" % (index, start, end))
    before = cues[index - 2] if index > 1 else None
    after = cues[index] if index < len(cues) else None
    if (before and before["end"] > start) or (after and after["start"] < end):
        raise PipelineError(
            "cue %d 調做 %.3f–%.3f 會硩著隔壁，先調隔壁彼條"
            % (index, start, end))
    out = []
    for one in cues:
        out.append(dict(one))
    moved = out[index - 1]
    moved["start"] = start
    moved["end"] = end
    if not start <= moved.get("sample_ts", start) <= end:
        moved["sample_ts"] = _mid(start, end)
    return out


def shift_rows(rows, index):
    """[(cue, text)] with every cue at or after `index` moved up by one."""
    out = []
    for number, text in rows:
        out.append((number + 1 if number >= index else number, text))
    return out


def remap_rows(rows, index, text):
    """shift_rows plus the new row, in cue order."""
    out = shift_rows(rows, index)
    out.append((index, text))
    out.sort(key=lambda row: row[0])
    return out


def remap_sheets(sheets, index):
    """`sheets.json` after an insert: later cues shift, the new cue joins
    the sheet of the cue before it (the first sheet if it is cue 1), so
    `ingest` still finds every cue on some sheet."""
    home = None
    for name in sorted(sheets):
        if (index - 1) in sheets[name] or (index == 1 and 1 in sheets[name]):
            home = name
    out = {}
    for name in sheets:
        moved = []
        for number in sheets[name]:
            moved.append(number + 1 if number >= index else number)
        if name == home:
            moved.append(index)
        out[name] = sorted(moved)
    return out


# ------------------------------------------------------------------ I/O


def _book(stem):
    work = paths.work_dir(stem)
    path = paths.cues_to_read(work)
    if path is None:
        raise PipelineError("%s 無時間軸" % work)
    with open(path, encoding="utf-8") as handle:
        return work, path, json.load(handle)


def _save(path, book):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(book, handle, ensure_ascii=False, indent=2, sort_keys=True)


def _name_of(stem):
    for entry in episodes.load():
        if entry["slug"] == stem:
            return entry["srt_name"]
    raise PipelineError("inventory 內底揣無 %s" % stem)


def apply_insert(stem, start, end, text):
    """Insert across the timeline, sheets.json and the vision TSVs."""
    work, path, book = _book(stem)
    book["cues"], index = insert(book["cues"], start, end)
    book["placed"] = book.get("placed", []) + [
        {"op": "insert", "cue": index, "start": start, "end": end,
         "text": text}]
    _save(path, book)
    sheets_path = paths.sheets_index(work)
    if os.path.exists(sheets_path):
        with open(sheets_path, encoding="utf-8") as handle:
            sheets = json.load(handle)
        _save(sheets_path, remap_sheets(sheets, index))
    folder = split_cue.vision_folders(_name_of(stem))[0]
    # the new row goes in with its neighbour: the file holding the cue that
    # now comes after it (old number `index`), or the last one before it
    target = split_cue.holding(folder, index)
    for one in sorted(glob.glob(os.path.join(folder, "b*.tsv"))):
        rows = split_cue.read_tsv(one)
        if one == target:
            rows = remap_rows(rows, index, text)
        else:
            rows = shift_rows(rows, index)
        split_cue.write_tsv(one, rows)
    return index, len(book["cues"])


def apply_bounds(stem, index, start, end):
    """Move one cue's ends in the timeline; numbering does not change."""
    _work, path, book = _book(stem)
    book["cues"] = set_bounds(book["cues"], index, start, end)
    book["placed"] = book.get("placed", []) + [
        {"op": "bounds", "cue": index, "start": start, "end": end}]
    _save(path, book)
    return len(book["cues"])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("stem")
    sub = ap.add_subparsers(dest="op", required=True)
    one = sub.add_parser("insert")
    one.add_argument("start", type=float)
    one.add_argument("end", type=float)
    one.add_argument("--text", required=True)
    two = sub.add_parser("bounds")
    two.add_argument("cue", type=int)
    two.add_argument("start", type=float)
    two.add_argument("end", type=float)
    args = ap.parse_args(argv)
    if args.op == "insert":
        index, total = apply_insert(args.stem, args.start, args.end,
                                    args.text)
        print("%s：%.3f–%.3f 插做 cue %d，總數變 %d"
              % (args.stem, args.start, args.end, index, total))
    else:
        total = apply_bounds(args.stem, args.cue, args.start, args.end)
        print("%s：cue %d 調做 %.3f–%.3f（總數 %d）"
              % (args.stem, args.cue, args.start, args.end, total))
    return 0


if __name__ == "__main__":
    sys.exit(main())
