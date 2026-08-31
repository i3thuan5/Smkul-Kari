#!/usr/bin/env python3
"""Which cues the contact sheet never really looked at.

    python3 -m scripts.news.blind_cues              # every delivered episode
    python3 -m scripts.news.blind_cues <srt_name>  # one episode, cue by cue
    python3 -m scripts.news.blind_cues <srt_name> --floor 2.0

WHY
---
A contact-sheet strip is `cuelib.Cue.composite()`: the per-pixel median of
the frames the segmenter kept for that cue. Three things in that path hide
subtitle text, and all three show up the same way in `cues.json`.

  `MAX_SAMPLES = 24` at 5 fps   a cue is sampled for at most 4.8 s; a 30 s
                                cue's last 25 s never reached the strip
  fewer than 3 samples          `composite()` falls back to one frame, so
                                the strip is a single instant -- and that
                                instant often lands on the *previous* line,
                                which is how a strip ends up showing a
                                neighbouring cue's sentence
  three or more samples         the median erases a line that was only on
                                screen for part of the cue

`frames` counts the sampled frames the segmenter judged to still be showing
the same text (`Segmenter._extend_current`, mask distance under `change`).
So `frames * 0.2` is how much of the cue was actually looked at, while
`end - start` is what it claims to cover. The difference is unseen, and it
is the difference -- not `frames` alone, not duration alone -- that flags
the trouble: 20210222_053 cue 861 has `frames=17`, which looks generous
until you notice it covers 3.4 s of a 6.08 s cue.

Measured on 20210222_053_午間_Atayal_泰雅, whose four rewritten cues were:

    cue  85  frames=8   saw 1.6 s of 3.50 s
    cue 201  frames=2   saw 0.4 s of 5.00 s
    cue 295  frames=2   saw 0.4 s of 3.30 s
    cue 573  frames=3   saw 0.6 s of 4.54 s

Across the 59 delivered episodes this flags 8.3% of cues and 4.5 hours of
video. Two episodes audited against the master turned up a correction per
four or five flagged cues, so the list is worth working through rather than
re-reading whole episodes.

WHAT COUNTS AS A MISSING LINE
-----------------------------
A flagged cue goes wrong two ways: a line no cue carries (append it), or a
cell holding a *neighbour's* sentence because the single-frame fallback
landed there (replace it). Either way the test before editing is the same --
is this line already carried somewhere? -- and it must be asked as **whole
cell equality**, not substring:

    awk -F'\t' '$3=="老人家"' *.tsv        # right
    grep -F "老人家" *.tsv                  # wrong: blocks the edit because
                                            # "老人家就會跟我們講說" contains it

Those are two different lines, on screen at two different times. Substring
matching silently drops exactly the short standalone lines (老人家, 對,
然後) that the median is most likely to have washed out in the first place.

The same cell content appearing elsewhere is not a reason to skip either --
a sentence said twice in a programme needs a cue each time. What the rule
guards against is concatenating text into a string that was never on screen
at once, which is only worth risking when the line would otherwise be lost.

And it guards only APPENDS. A cell holding a neighbour's sentence is wrong
whatever the neighbours say, so "already carried" must never block the fix:
one line stays on screen across several cues, and the store spells that out
by repeating the text in each of them -- measured at 12,351 consecutive
identical pairs across all 60 read episodes, so it is the house form, not an
accident. 20210220_051 cue 527 read 你要分擔 (526's line) where the screen
showed 你要分工; the fix pairs it with 528, which is what a line spanning two
cues is supposed to look like.

This only says where to look. What the text actually is still comes from
the video.
"""
import argparse
import glob
import json
import os
import sys

from scripts.news import paths
from scripts.errors import PipelineError

# `cuelib` samples the band at 5 fps, so one kept frame is a fifth of a
# second of coverage.
FRAME_DT = 0.2

# Below this, the unseen stretch is too short to hold a subtitle line worth
# chasing -- a line has to stay up long enough to read. Measured: the
# shortest genuinely hidden line found so far ran 0.6 s, and the shortest
# whole hidden sentence 1.2 s.
FLOOR = 1.0

# A cue this long is worth a second look whatever `frames` says. The
# segmenter's other failure is the mirror of the jam: a *static* bright
# background (a white document, snow) floods the mask, the subtitle is under
# 7% of it, and a sentence change moves too little for either gate to notice.
# `_extend_current` then succeeds on every frame, so `frames` looks healthy
# and the unseen figure stays small -- 20210220_051 cue 125 holds six
# sentences with frames=64 and only 1.04s unseen. Duration is the only
# handle on that one. Measured: 2,125 cues clear `LONG` that `FLOOR` misses,
# 17,664 seconds, more than the jam type's 16,036.
LONG = 6.0

# What `batches.py --size` is called with everywhere in this pipeline.
BATCH_SIZE = 96


def unseen(cue):
    """Seconds of this cue that never reached the contact sheet."""
    span = cue["end"] - cue["start"]
    looked = cue.get("frames", 0) * FRAME_DT
    return max(0.0, span - looked)


def risky(cues, floor=FLOOR, long=LONG):
    """The cues worth re-reading off the video, worst first.

    Each is the original dict plus `unseen` and `why` -- "unseen" for the
    jam, "long" for the static-bright case that only duration catches. Pass
    `long=None` to ask the unseen question alone.
    """
    out = []
    for cue in cues:
        gap = unseen(cue)
        span = cue["end"] - cue["start"]
        if gap >= floor:
            why = "unseen"
        elif long is not None and span >= long:
            why = "long"
        else:
            continue
        copy = dict(cue)
        copy["unseen"] = gap
        copy["why"] = why
        out.append(copy)
    out.sort(key=lambda c: -c["unseen"])
    return out


def summary(cues, floor=FLOOR, long=LONG):
    """How much of one episode needs a second look."""
    flagged = risky(cues, floor, long)
    total = 0.0
    longs = 0
    for cue in flagged:
        total += cue["unseen"]
        if cue["why"] == "long":
            longs += 1
    share = 0.0
    if cues:
        share = 100.0 * len(flagged) / len(cues)
    return {"cues": len(cues), "risky": len(flagged), "long": longs,
            "unseen": total, "share": share}


def batch_of(index, size=BATCH_SIZE):
    """Which `b??.tsv` holds this cue, so a correction can be applied."""
    return "b%02d" % ((int(index) - 1) // size + 1)


def load(srt_name):
    """The delivered cue timeline for one episode."""
    path = os.path.join(paths.KARI, "news", "1-ocr", "1-cues",
                        paths.month_of(srt_name), srt_name + ".json")
    if not os.path.exists(path):
        raise PipelineError("揣無時間軸：%s" % path)
    with open(path, encoding="utf-8") as handle:
        doc = json.load(handle)
    return doc if isinstance(doc, list) else doc.get("cues", doc)


def delivered():
    """Every episode with a cue timeline in the store, in name order."""
    root = os.path.join(paths.KARI, "news", "1-ocr", "1-cues")
    out = []
    for path in sorted(glob.glob(os.path.join(root, "*", "*.json"))):
        out.append(os.path.basename(path)[:-len(".json")])
    return out


def _one(srt_name, floor, long):
    cues = load(srt_name)
    for cue in risky(cues, floor, long):
        print("%s\t%s\t%d\t%.2f\t%.2f\t%.2f\t%s"
              % (srt_name, batch_of(cue["index"]), cue["index"],
                 cue["start"], cue["end"], cue["unseen"], cue["why"]))


def _all(floor, long):
    rows = []
    for name in delivered():
        rows.append((name, summary(load(name), floor, long)))
    rows.sort(key=lambda r: -r[1]["share"])
    print("%-42s %6s %6s %6s %6s %9s"
          % ("集數", "cue", "待查", "傷長", "占比", "未見秒"))
    for name, got in rows:
        print("%-42s %6d %6d %6d %5.1f%% %9.0f"
              % (name[:42], got["cues"], got["risky"], got["long"],
                 got["share"], got["unseen"]))
    cues = 0
    flagged = 0
    total = 0.0
    for _, got in rows:
        cues += got["cues"]
        flagged += got["risky"]
        total += got["unseen"]
    share = 100.0 * flagged / cues if cues else 0.0
    print()
    print("合計 %d 集 %d cue，待查 %d 條（%.1f%%），未見 %.0f 秒 ＝ %.1f 點鐘"
          % (len(rows), cues, flagged, share, total, total / 3600))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("srt_name", nargs="?", default=None,
                    help="干焦這一集（省略就是全部ê總表）")
    ap.add_argument("--floor", type=float, default=FLOOR,
                    help="偌濟秒無看著才算待查（預設 %.1f）" % FLOOR)
    ap.add_argument("--long", type=float, default=LONG,
                    help="偌長ê cue 無論按怎攏愛閣看（預設 %.1f，0 ＝ 莫）"
                         % LONG)
    args = ap.parse_args(argv)
    long = args.long or None
    if args.srt_name:
        _one(paths.check_srt_name(args.srt_name), args.floor, long)
    else:
        _all(args.floor, long)
    return 0


if __name__ == "__main__":
    sys.exit(main())
