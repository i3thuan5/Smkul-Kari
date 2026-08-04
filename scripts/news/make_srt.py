#!/usr/bin/env python3
"""Assemble one episode's cues and text into an SRT.

Text for a cue is taken from the best source available:

  文稿   the episode's own news script, located by aligning the recogniser's
         output against it. Exact wording, including the characters tesseract
         gets wrong -- 苧麻 where it read 芋麻, 救災 where it read 名及.
  ocr    tesseract, which on Chinese over moving footage is poor. Kept so the
         cue is not silently dropped, never presented as checked.

Both the merged SRT and a 文稿-only variant are written. The second is the one
fit to feed a corpus: every line in it is script-backed, so it is smaller but
not corrupted. Which is the same trade the skill makes when it refuses to
export unverified rows as training data.
"""
import argparse
import json
import os

from scripts.news import align as aligner
from scripts.subs2srt import cli as subs2srt
from scripts.subs2srt import cuelib


def load_ocr(work):
    path = os.path.join(work, "transcripts.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def build(work, rtf, min_coverage, min_compactness):
    """One record per cue: timing, OCR text, and 文稿 text where found."""
    with open(os.path.join(work, "cues.json"), encoding="utf-8") as handle:
        manifest = json.load(handle)
    cues = manifest["cues"]

    if rtf and os.path.isdir(rtf):
        records, refsize, filled = aligner.resolve(
            work, rtf, min_coverage, min_compactness)
        return manifest, records, refsize, filled

    ocr = load_ocr(work)
    records = []
    for cue in cues:
        got = ocr.get(str(cue["index"]))
        text = got.get("han", "") if isinstance(got, dict) else ""
        records.append({
            "index": cue["index"], "start": cue["start"], "end": cue["end"],
            "ocr": text or "", "aligned": "", "source": "",
            "coverage": 0.0, "compactness": 0.0,
        })
    return manifest, records, 0, 0


def drop_leader(records):
    """Discard the slate at the head of a broadcast master.

    These tapes open with bars and a slate before the programme starts, and
    the slate carries white text inside the subtitle band, so the segmenter
    opens a cue on the very first sampled frame and holds it for ten to
    fifteen seconds. Tesseract then reads it as `x2同。` or `5人還玉六計`,
    which lands as subtitle #1 of the episode.

    Nothing legitimate looks like this: the leader always precedes the
    programme, so a cue opening on frame zero cannot be dialogue. Measured
    across all 22 episodes the earliest genuine line starts at 5.8 seconds
    and the usual opening is 14 to 17 seconds, which the two vision-read
    episodes confirm -- they mark exactly this stretch blank.
    """
    for rec in records:
        if rec["start"] > 0.5:
            break
        rec["ocr"] = ""
        rec["aligned"] = ""
    return records


def entries_from(records, use):
    out = []
    for rec in records:
        if use == "rtf":
            text = rec["aligned"]
        else:
            text = rec["aligned"] or rec["ocr"]
        text = (text or "").strip()
        if not text:
            continue
        out.append((rec["start"], rec["end"], text))
    return out


def write_srt(path, entries, merge_gap=1.0, min_gap=0.04):
    entries = subs2srt.merge_repeats(entries, merge_gap)
    entries = subs2srt.apply_gap_rules(entries, min_gap)
    body = cuelib.render_srt(entries)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(body)
        if body and not body.endswith("\n"):
            handle.write("\n")
    return body.count("-->")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work")
    ap.add_argument("-o", "--out", required=True, help="merged SRT path")
    ap.add_argument("--rtf", default="")
    ap.add_argument("--rtf-out", default="", help="文稿-only SRT path")
    ap.add_argument("--min-coverage", type=float, default=0.5)
    ap.add_argument("--min-compactness", type=float, default=0.55)
    args = ap.parse_args()

    manifest, records, refsize, filled = build(
        args.work, args.rtf, args.min_coverage, args.min_compactness)
    records = drop_leader(records)

    with_text = 0
    aligned = 0
    for rec in records:
        if (rec["aligned"] or rec["ocr"]).strip():
            with_text += 1
        if rec["aligned"].strip():
            aligned += 1

    merged = write_srt(args.out, entries_from(records, "best"))
    rtf_lines = 0
    if args.rtf_out:
        rtf_lines = write_srt(args.rtf_out,
                              entries_from(records, "rtf"))

    aligned_pct = 0.0
    if with_text:
        aligned_pct = round(100.0 * aligned / with_text, 1)
    qc = {
        "cues": len(records),
        "cues_with_text": with_text,
        "cues_aligned": aligned,
        "aligned_pct": aligned_pct,
        "interpolated": filled,
        "rtf_chars": refsize,
        "srt_lines": merged,
        "rtf_srt_lines": rtf_lines,
    }
    with open(os.path.splitext(args.out)[0] + ".qc.json", "w",
              encoding="utf-8") as handle:
        json.dump(qc, handle, ensure_ascii=False, indent=2)
    print(json.dumps(qc, ensure_ascii=False))


if __name__ == "__main__":
    main()
