#!/usr/bin/env python3
"""How good is a cut? Three numbers, off the store, without the video.

    python3 -m tools.cuescore.score TIMELINE VISION_DIR [--cut OTHER]

TIMELINE is a `cues.json` (the store's `1-cues/<srt_name>.json` will do) and
VISION_DIR holds that episode's `b*.tsv`. Nothing here decodes a frame, so
scoring a month costs seconds.

WHY THIS EXISTS
---------------
Every knob on the segmenter trades one kind of loss for another, and two of
the three losses are invisible in the delivered SRT. Raising the change
threshold to cut repeats was measured to swallow real sentences at roughly
the same rate it saved reading; narrowing the compare window cut repeats by
44-69% AND cut swallowed sentences, which is only knowable if both are
counted at once. `rebuild --verify` cannot see any of it: it rebuilds SRTs
from stored timelines and never looks at a mask.

    repeated   adjacent cues that touch and carry the same text -- one
               sentence cut into pieces, each piece read again by Claude
               Vision. 24.9% of the whole store when this was written.
    swallowed  a place where the delivered text changes, but one cue of the
               cut being scored spans straight through it. That subtitle is
               lost.
    dropped    a delivered cue with text that no cue of the scored cut
               covers at all. Also lost.

`repeated` needs only the timeline and the TSVs. `swallowed` and `dropped`
compare some other cut against the delivered one, so they need `--cut`.
"""
import argparse
import json
import os
import sys


def read_texts(vision_dir):
    """{cue index: text} with a corpus's rows joined into one string.

    Both rows together are the text: 開會了 puts Formosan above Chinese, and
    two cues whose Chinese matches while the Formosan differs are two
    different subtitles.
    """
    rows = {}
    for name in sorted(os.listdir(vision_dir)):
        if not name.endswith(".tsv"):
            continue
        path = os.path.join(vision_dir, name)
        for line in open(path, encoding="utf-8"):
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 2 or not parts[0].strip().isdigit():
                continue
            text = parts[2].strip() if len(parts) > 2 else ""
            rows.setdefault(int(parts[0]), {})[parts[1].strip()] = text
    joined = {}
    for index, per_line in rows.items():
        parts = []
        for name in sorted(per_line):
            parts.append(per_line[name])
        joined[index] = "|".join(parts).strip("|")
    return joined


def load_cues(path):
    with open(path, encoding="utf-8") as handle:
        doc = json.load(handle)
    return doc["cues"] if isinstance(doc, dict) else doc


def text_at(truth, texts, moment, slack=0.05):
    """What the delivered timeline says was on screen at `moment`.

    A cut being scored has its own numbering -- re-cutting renumbers
    everything -- so its cues cannot be looked up by index. Time is the only
    thing the two cuts share.
    """
    for cue in truth:
        if cue["start"] - slack <= moment <= cue["end"] + slack:
            return texts.get(cue["index"], "")
    return ""


def count_repeated(cues, texts, truth=None, touching=0.02):
    """Adjacent touching cues carrying the same non-empty text.

    With `truth` given, `cues` is some other cut and its text is looked up
    by time instead of by index.
    """
    total = 0
    for i in range(len(cues) - 1):
        first, second = cues[i], cues[i + 1]
        if abs(second["start"] - first["end"]) >= touching:
            continue
        if truth is None:
            a = texts.get(first["index"], "")
            b = texts.get(second["index"], "")
        else:
            a = text_at(truth, texts, (first["start"] + first["end"]) / 2.0)
            b = text_at(truth, texts,
                        (second["start"] + second["end"]) / 2.0)
        if a and b and a == b:
            total += 1
    return total


def _text_changes(cues, texts, touching=0.02):
    """Times where the delivered text changes from one cue to the next."""
    out = []
    for i in range(len(cues) - 1):
        first, second = cues[i], cues[i + 1]
        a = texts.get(first["index"], "")
        b = texts.get(second["index"], "")
        if a and b and abs(second["start"] - first["end"]) < touching \
                and a != b:
            out.append(first["end"])
    return out


def count_swallowed(truth, texts, cut, slack=0.25):
    """Text changes that one cue of `cut` runs straight through."""
    total = 0
    for moment in _text_changes(truth, texts):
        for cue in cut:
            if cue["start"] < moment - slack and cue["end"] > moment + slack:
                total += 1
                break
    return total


def count_dropped(truth, texts, cut, slack=0.1):
    """Delivered cues with text that no cue of `cut` covers."""
    total = 0
    for cue in truth:
        if not texts.get(cue["index"], ""):
            continue
        middle = (cue["start"] + cue["end"]) / 2.0
        covered = False
        for other in cut:
            if other["start"] - slack <= middle <= other["end"] + slack:
                covered = True
                break
        if not covered:
            total += 1
    return total


def score(timeline, vision_dir, cut=None):
    """The three numbers, plus what they were counted out of."""
    truth = load_cues(timeline)
    texts = read_texts(vision_dir)
    scored = truth if cut is None else cut
    with_text = 0
    for cue in truth:
        if texts.get(cue["index"], ""):
            with_text += 1
    return {
        "cues": len(scored),
        "delivered_cues": len(truth),
        "with_text": with_text,
        "changes": len(_text_changes(truth, texts)),
        "repeated": count_repeated(scored, texts,
                                   None if cut is None else truth),
        "swallowed": count_swallowed(truth, texts, scored),
        "dropped": count_dropped(truth, texts, scored),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("timeline", help="cues.json to score")
    ap.add_argument("vision", help="directory of b*.tsv for that episode")
    ap.add_argument("--cut", help="another cues.json to score against the "
                                  "delivered timeline")
    args = ap.parse_args()
    cut = load_cues(args.cut) if args.cut else None
    print(json.dumps(score(args.timeline, args.vision, cut),
                     ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    sys.exit(main())
