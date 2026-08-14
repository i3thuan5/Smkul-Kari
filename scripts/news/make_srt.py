#!/usr/bin/env python3
"""Assemble one episode's cues and checked text into an SRT.

The text comes from the episode's transcripts, which are what a human read
off the contact sheets. Nothing else supplies text.

Two other sources were tried and dropped, both measured:

  tesseract  26% of lines right on this material, whole-line
             (`去年底桃園復興巴陵的一場大火` came back as
             `同/和)[人圖復興叫陜病一易大六`)
  文稿       the episode's own news script, located by aligning a
             recogniser's output against it. Of 4,344 cues it supplied,
             336 (7.7%) disagreed with the picture and the picture was
             right every time -- 58% because the script does not record
             where the subtitler broke a narration paragraph, 40% because
             the subtitler corrected the script as they typed. No amount
             of alignment recovers either. Removed; see git history and
             `Kari-SRT/report/rtf-vs-vision.*` for the comparison.
"""
import argparse
import json
import os

from scripts.subs2srt import assemble
from scripts.subs2srt import cuelib


def load_transcripts(work):
    path = os.path.join(work, "transcripts.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def build(work):
    """One record per cue: its timing and its text."""
    with open(os.path.join(work, "cues.json"), encoding="utf-8") as handle:
        manifest = json.load(handle)

    texts = load_transcripts(work)
    records = []
    for cue in manifest["cues"]:
        got = texts.get(str(cue["index"]))
        text = got.get("han", "") if isinstance(got, dict) else ""
        records.append({
            "index": cue["index"],
            "start": cue["start"],
            "end": cue["end"],
            "text": text or "",
        })
    return manifest, records


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
        rec["text"] = ""
    return records


def entries_from(records):
    out = []
    for rec in records:
        text = (rec["text"] or "").strip()
        if not text:
            continue
        out.append((rec["start"], rec["end"], text))
    return out


def write_srt(path, entries, merge_gap=1.0, min_gap=0.04, duration=None):
    entries = assemble.merge_repeats(entries, merge_gap)
    entries = assemble.apply_gap_rules(entries, min_gap)
    # Padding is last on purpose: it may leave pairs touching at a gap's
    # midpoint, which apply_gap_rules would pull apart again.
    entries = assemble.pad_edges(entries, duration=duration)
    body = cuelib.render_srt(entries)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(body)
        if body and not body.endswith("\n"):
            handle.write("\n")
    return body.count("-->")


def run(work, out):
    """Write one episode's SRT; return the QC counts as a dict.

    This is the callable form, and it is what make_all and rebuild use. They
    used to spawn this module as a subprocess and parse the last line of its
    stdout as JSON -- a contract nothing declared and nothing checked, which
    an extra print() at the end would have broken silently.
    """
    manifest, records = build(work)
    records = drop_leader(records)

    with_text = 0
    for rec in records:
        if rec["text"].strip():
            with_text += 1

    duration = manifest.get("duration")
    return {
        "cues": len(records),
        "cues_with_text": with_text,
        "srt_lines": write_srt(out, entries_from(records),
                               duration=duration),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("work")
    ap.add_argument("-o", "--out", required=True, help="SRT path")
    args = ap.parse_args(argv)

    qc = run(args.work, args.out)
    with open(os.path.splitext(args.out)[0] + ".qc.json", "w",
              encoding="utf-8") as handle:
        json.dump(qc, handle, ensure_ascii=False, indent=2)
    print(json.dumps(qc, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    main()
