#!/usr/bin/env python3
"""The two sides of one episode, read the way alignment needs them.

Speech side: sapolita's SRT, one VAD segment per entry, two labelled
rows (「族語：」 the recognised text, 「華語：」 the service's own MT).
The boundaries are real speech boundaries -- the store keeps them
without the 0.5 s padding (see 2-asr-whisper/README).

Picture side: the store's timeline (`1-cues/`) plus the vision TSVs
(`2-vision/`), run through the very assembly chain the delivered SRTs
use, so an entry here is exactly one delivered SRT entry -- but carrying
its **true** window. The padded SRT window is display-only and would
make every subtitle appear to overlap its neighbours' segments.
"""
import glob
import json
import os

from scripts.srtlib import assemble
from scripts.srtlib import srt as srtlib

LABELS = (("formosan", "族語："), ("han", "華語："))
BATCH_GLOB = "b*.tsv"


def _rows_of(text):
    out = {}
    for line in text.split("\n"):
        for key, label in LABELS:
            if line.startswith(label):
                out[key] = line[len(label):].strip()
    return out


def whisper_segments(text):
    """sapolita SRT text -> [{index, start, end, formosan, han}]."""
    out = []
    for start, end, body in srtlib.parse_srt(text):
        rows = _rows_of(body)
        out.append({"index": len(out), "start": start, "end": end,
                    "formosan": rows.get("formosan", ""),
                    "han": rows.get("han", "")})
    return out


def _transcripts(vision_dir):
    """{cue index (str): {row: text}} from the batch TSVs."""
    found = {}
    for path in sorted(glob.glob(os.path.join(vision_dir, BATCH_GLOB))):
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                line = line.rstrip("\n")
                if not line.strip():
                    continue
                parts = line.split("\t")
                while len(parts) < 3:
                    parts.append("")
                found.setdefault(parts[0], {})[parts[1]] = parts[2]
    return found


def _record_text(record):
    """The assembly key: every carried row, labelled, one per line.

    Same shape as the delivered two-row SRT, so two cues fuse only when
    every row agrees -- the Formosan row often runs on under a changing
    Chinese one, and those are different subtitles.
    """
    carried = False
    for key, _label in LABELS:
        if record[key]:
            carried = True
    if not carried:
        return ""
    lines = []
    for key, label in LABELS:
        lines.append(label + record[key])
    return "\n".join(lines)


def store_entries(cues_path, vision_dir, drop_leader=False):
    """One dict per delivered SRT entry, with its true window.

    Keys: index (0-based position), cues (the timeline indexes fused
    into it), true_start/true_end, srt_start/srt_end, formosan, han.
    `drop_leader` blanks a cue opening at t=0 (the broadcast slate the
    news assembly discards, see news/make_srt.drop_leader).
    """
    with open(cues_path, encoding="utf-8") as handle:
        manifest = json.load(handle)
    texts = _transcripts(vision_dir)

    records = []
    for cue in manifest["cues"]:
        got = texts.get(str(cue["index"])) or {}
        record = {"cue": cue["index"], "start": cue["start"],
                  "end": cue["end"]}
        for key, _label in LABELS:
            record[key] = (got.get(key) or "").strip()
        if drop_leader and cue["start"] <= 0.5:
            for key, _label in LABELS:
                record[key] = ""
        records.append(record)

    entries = []
    per_entry_cues = []
    for record in records:
        text = _record_text(record)
        if not text:
            continue
        entries.append((record["start"], record["end"], text))
        per_entry_cues.append(record["cue"])

    rows = assemble.chain_with_spans(entries, duration=manifest.get(
        "duration"))
    # chain_with_spans fuses same-text neighbours; recover which cues
    # went into each fused row by replaying the same rule on the ids.
    out = []
    position = 0
    for row in rows:
        fused = []
        while position < len(entries):
            start, end, text = entries[position]
            if fused and not (text == row["text"]
                              and start <= row["true_end"] + 1e-9):
                break
            if not fused and text != row["text"]:
                break
            fused.append(per_entry_cues[position])
            position += 1
            if end >= row["true_end"] - 1e-9:
                break
        parsed = _rows_of(row["text"])
        out.append({
            "index": len(out), "cues": fused,
            "true_start": row["true_start"], "true_end": row["true_end"],
            "srt_start": row["srt_start"], "srt_end": row["srt_end"],
            "formosan": parsed.get("formosan", ""),
            "han": parsed.get("han", ""),
        })
    return out
