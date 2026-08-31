#!/usr/bin/env python3
"""Assemble one episode's cues and checked text into a two-row SRT.

Both rows come off the picture: this programme burns the Formosan line
above the Chinese one, so what the vision pass read is the whole
deliverable -- there is no recogniser in this corpus and nothing else
supplies text.

Every entry carries both labels:

    12
    00:14:02,300 --> 00:14:08,160
    族語：Matini san i ma'araway namo a kamok honi i
    華語：剛剛你們所看見的節目

A row the picture does not carry is written as its label and nothing
else. Dropping the line instead would make "this row has no subtitle"
and "a row went missing" look the same in the delivered file, and the
two are not the same thing: 083 carries no Formosan row at all, and in
every episode the passages where somebody speaks Chinese carry only the
lower row.

Timing comes from `scripts.srtlib.assemble`, the same chain the news
side uses, so the 0.5s edge padding and the midpoint rule are one
implementation rather than two that have to agree.
"""
import argparse
import json
import os

from scripts.aiyalaeho import paths
from scripts.srtlib import assemble
from scripts.srtlib import srt

# The rows, in the order they appear on screen and in the file, each with
# the label the delivered SRT carries. Same wording as the speech side's
# raw SRT, so somebody reading both does not have to learn two formats.
LABELS = (("formosan", "族語："), ("han", "華語："))


def load_transcripts(work):
    path = os.path.join(work, "transcripts.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def build(work):
    """One record per cue: its timing and each row's text."""
    with open(os.path.join(work, "cues.json"), encoding="utf-8") as handle:
        manifest = json.load(handle)

    texts = load_transcripts(work)
    records = []
    for cue in manifest["cues"]:
        got = texts.get(str(cue["index"]))
        if not isinstance(got, dict):
            got = {}
        record = {"index": cue["index"], "start": cue["start"],
                  "end": cue["end"], "read": bool(got)}
        for name, _label in LABELS:
            record[name] = (got.get(name) or "").strip()
        records.append(record)
    return manifest, records


def entry_text(record):
    """The two labelled rows, or "" when the cue carries no subtitle.

    A cue nobody read yields nothing at all -- an unread cue is not the
    same as a cue read as blank, and only the second one is a statement
    about the picture.
    """
    if not record["read"]:
        return ""
    carried = False
    for name, _label in LABELS:
        if record[name]:
            carried = True
    if not carried:
        return ""
    rows = []
    for name, label in LABELS:
        rows.append(label + record[name])
    return "\n".join(rows)


def entries_from(records):
    out = []
    for record in records:
        text = entry_text(record)
        if text:
            out.append((record["start"], record["end"], text))
    return out


def write_srt(path, entries, merge_gap=1.0, min_gap=0.04, duration=None):
    # Merging compares the whole two-row text, so two cues fuse only when
    # both rows agree -- the Formosan row often runs on under a changing
    # Chinese one, and those are different subtitles.
    rows = assemble.chain_with_spans(entries, merge_gap, min_gap,
                                     duration=duration)
    rendered = []
    for row in rows:
        rendered.append((row["srt_start"], row["srt_end"], row["text"]))
    body = srt.render_srt(rendered)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(body)
        if body and not body.endswith("\n"):
            handle.write("\n")
    return body.count("-->")


def run(work, out):
    """Write one episode's SRT; return the QC counts as a dict."""
    manifest, records = build(work)

    with_text = 0
    per_row = {}
    for name, _label in LABELS:
        per_row[name] = 0
    for record in records:
        if entry_text(record):
            with_text += 1
        for name, _label in LABELS:
            if record[name]:
                per_row[name] += 1

    qc = {
        "cues": len(records),
        "cues_with_text": with_text,
        "srt_lines": write_srt(out, entries_from(records),
                               duration=manifest.get("duration")),
    }
    for name, _label in LABELS:
        qc[name + "_rows"] = per_row[name]
    return qc


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("work")
    ap.add_argument("-o", "--out", required=True, help="SRT path")
    args = ap.parse_args(argv)
    work = paths.check_under(args.work, "work")
    out = paths.check_under(args.out, "-o/--out")

    qc = run(work, out)
    with open(os.path.splitext(out)[0] + ".qc.json", "w",
              encoding="utf-8") as handle:
        json.dump(qc, handle, ensure_ascii=False, indent=2)
    print(json.dumps(qc, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    main()
