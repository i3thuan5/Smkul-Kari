"""Blank runs in each episode's vision TSVs, and which of them hide a
subtitle printed outside the band.

A subtitle stretch printed outside `REGION` reaches the reader as a blank
strip, so it lands in the store as a run of empty text. Ordinary gaps --
an establishing shot, a graphic card -- do the same, and **length does not
tell them apart**: 006 (2021-01-06) hides 12 cues of subtitle printed
ABOVE the band, while the longest blank run in that same episode is the
13-cue plaque-unveiling shot, which is fine. A run-length threshold picked
off the 054-059 batch (94-147 cues) misses the 12 and would have to reach
below the 13 to catch it.

So length only sorts. What decides is the evidence the reader described:
the strip's **top edge cuts through ink**. The region starts at y=722; a
subtitle painted above it leaves only the bottom slice of its glyphs in
the strip, hard against row 0. A subtitle sitting properly in the band
clears that boundary, and picture -- a white shirt, snow -- is not ink at
all, because `cuelib.text_mask` wants a black outline around the white.

Ink alone is not enough, and neither is how concentrated it is. A
vegetable garden's galvanised pipes put 0.309 of their strip's ink
against the top edge, against 0.320 for the real thing -- no threshold on
those two numbers separates them. The **shape** does: a line of type
leaves many narrow marks, one per stroke, where a pipe leaves a few wide
ones and a transition sting leaves two or three specks. So the evidence
is three numbers, and `edge_marks` carries the measurement.

What is left is still a review list, not a gate. Text above the band is
real in more ways than one:

  dialogue outside the band   006 cues 167-178, mid-programme. The one
                              that has to be fixed.
  a caption above the band    056晚 cues 312-316: a place-name super, its
                              bottom half legible in the strip. 058晨
                              cues 76-79 is a headline card the same way.
  the closing sequence        the trailer card and credit roll, in every
                              episode measured, always past 2,800 s.

All three are genuinely text the reader never saw; only the first is a
defect. Nothing in a strip separates them, and the clock separates the
third at a glance, so the list prints it and a person spends a few
seconds an entry.

One thing does still get through the shape test: **woven trim**. The
patterned band on a 族服 sleeve is a row of narrow bright marks, which
is the definition the test uses, and 002晨 cue 1 -- a studio shot, no
text anywhere -- clears it with 11 marks of width 3. Studio openings are
where that shows up, which is another reason the clock earns its column.

The strips live in the work dir (`kithann/out/mxf/<slug>.B.work/strips/`),
which is regenerable and not always still there. An episode whose work dir
is gone reports "no strips to measure" rather than "nothing to see": those
are different answers and the caller is told which one it got.
"""
import argparse
import glob
import json
import os
import sys

import numpy as np
from PIL import Image

from scripts.news import paths
from scripts.ocr import cuelib

# How deep the strip's top edge reaches. A glyph the region's upper
# boundary cut through leaves ink on the first row or two; a subtitle in
# its proper place clears the boundary by far more than this.
EDGE_ROWS = 3

# Ink pixels in those rows before a run is worth a human's time, and how
# much of the strip's whole ink has to sit there. Both are calibrated
# numbers, not guesses -- the sample they were measured on is recorded in
# scripts/news/README.md, and 換素材愛重校.
EDGE_INK = 60
EDGE_SHARE = 0.11

# And the shape of it: a line of type leaves a row of narrow marks, one
# per stroke. Measured, the three real cases leave 16, 26 and 29 marks of
# median width 4-5; the false ones leave 14 of median width 21 (galvanised
# pipes), 6, and 2. See `edge_marks`.
EDGE_MARKS = 10
MARK_WIDTH = 12


def blanks(name):
    """(cue, text) for the episode, in cue order."""
    month = paths.month_of(name)
    folder = os.path.join(paths.KARI_VISION, month, name)
    rows = {}
    for path in sorted(glob.glob(folder + "/b*.tsv")):
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                parts = line.rstrip("\n").split("\t")
                if len(parts) >= 3 and parts[0].isdigit():
                    rows[int(parts[0])] = parts[2].strip()
    return rows


def runs_of_blank(rows):
    """Contiguous stretches of empty text: list of (first, last)."""
    spans = []
    start = None
    last = None
    for cue in sorted(rows):
        # Strip here as well as on the way in: a reader who leaves one
        # space in the third column would otherwise read as text, and
        # this runs over stores written before that was tidied up.
        if not rows[cue].strip():
            if start is None:
                start = cue
            last = cue
        elif start is not None:
            spans.append((start, last))
            start = None
    if start is not None:
        spans.append((start, last))
    return spans


def strip_rgb(path):
    """One contact-sheet strip as an RGB array."""
    with Image.open(path) as image:
        return np.asarray(image.convert("RGB"))


def cut_evidence(rgb, spec, rows=EDGE_ROWS):
    """Ink against the strip's top edge, and ink in the whole strip.

    Measured with the pipeline's own ink definition rather than a
    brightness threshold: `text_mask` wants white *inside a dark outline*,
    which is what keeps a white shirt or a field of snow out of it.
    Cropping to the top rows would move the outline's dark pixels out of
    reach of the dilation, so the mask is taken over the whole strip and
    only then sliced.

    Both numbers are needed because the first one on its own flags the
    wrong things. A full-screen graphic card -- dark lettering on a pale
    field -- is white beside dark everywhere, so it puts more ink against
    the top edge than a real cut-off subtitle does. What separates them is
    **where the ink sits**: a subtitle printed above the band leaves its
    ink in the top rows and picture below, while a card's ink runs the
    whole depth. Measured on 006: the two real cases score 0.320 and
    0.099 of their strip's ink in the top three rows, every card and every
    benign gap 0.029 or less.
    """
    return measure(cuelib.text_mask(rgb, spec), rows)[:2]


def measure(mask, rows=EDGE_ROWS):
    """All four numbers off one mask: `(edge, total, marks, width)`.

    The mask is the expensive part -- an episode is 1,200-odd strips of
    1920x122 -- so everything that reads it reads it once.
    """
    lit = mask[:rows].any(axis=0)
    widths = []
    run = 0
    for on in lit:
        if on:
            run += 1
        elif run:
            widths.append(run)
            run = 0
    if run:
        widths.append(run)
    return (int(mask[:rows].sum()), int(mask.sum()), len(widths),
            int(np.median(widths)) if widths else 0)


def edge_ink(rgb, spec, rows=EDGE_ROWS):
    """Just the top-edge half of `cut_evidence`."""
    return cut_evidence(rgb, spec, rows)[0]


def edge_marks(rgb, spec, rows=EDGE_ROWS):
    """`(how many separate marks along the top edge, their median width)`.

    How much ink and how concentrated it is cannot tell a cut-off line
    from a bright thin object: a vegetable garden's galvanised pipes score
    0.309 of their strip's ink at the edge, against 0.320 for the real
    thing, so no threshold on those two numbers separates them.

    The shape does. The bottom slice of a line of type is **many narrow
    marks in a row** -- one per stroke -- while a pipe is a few wide ones
    and a transition sting is two or three specks. Measured: the three
    real cases leave 16, 26 and 29 marks of median width 4-5; the three
    false ones leave 14 marks of median width 21 (the pipes), 6 marks and
    2 marks. Counting marks is what the spec asks for in the first place
    -- the evidence is a glyph cut in half, not ink.
    """
    return measure(cuelib.text_mask(rgb, spec), rows)[2:]


def evidence_of(work, rows=EDGE_ROWS):
    """`(edge, total, marks, width)` per cue, off this work dir's strips.

    `cues.json`'s `images` field is the one place that maps a cue to its
    picture: strip filenames are start times, not cue numbers, and 62% of
    the store's cues have a strip whose number is not theirs. An episode
    with two subtitle lines reports the line with the most edge ink.
    """
    path = paths.cues_to_read(work)
    if not path:
        return {}
    with open(path, encoding="utf-8") as handle:
        book = json.load(handle)
    spec = cuelib.MaskSpec.from_dict(book.get("mask") or {})
    out = {}
    for cue in book.get("cues", []):
        for name in sorted(cue.get("images") or {}):
            image = os.path.join(work, cue["images"][name])
            if not os.path.exists(image):
                continue
            got = measure(cuelib.text_mask(strip_rgb(image), spec), rows)
            if got[0] > out.get(cue["index"], (0,))[0]:
                out[cue["index"]] = got
    return out


def flagged_runs(spans, evidence, floor=EDGE_INK, share=EDGE_SHARE,
                 marks=EDGE_MARKS, mark_width=MARK_WIDTH):
    """Blank runs whose strips carry a cut-off line, best evidence first.

    Three gates, all from the same measurement: enough ink against the top
    edge to be more than noise, enough of the strip's ink concentrated
    there to be more than a graphic card, and the ink shaped like a row of
    type rather than a bright object -- many narrow marks, not a few wide
    ones. The third gate is what the first two cannot do; see `edge_marks`
    for the measurement that says so.

    A run is judged by its best cue, not by how long it is: one cue of
    truncated glyph is a subtitle nobody read. Length rides along so the
    reader knows how much programme is behind each entry, and it breaks
    ties, but it never puts a run on the list nor keeps it off.
    """
    out = []
    for first, last in spans:
        # 揀「三爿門檻攏過」ê內底上強彼條，毋是規段上懸ê比值：一條
        # 雜訊ê比值會使足懸（1 點墨khǹg佇 2 點內底 ＝ 0.5）閣過袂了
        # 絕對門檻，予伊代表規段，真ê彼條就綴伊落勾。
        best = None
        for cue in range(first, last + 1):
            got = evidence.get(cue)
            if not got:
                continue
            edge, total, count, width = got
            if edge < floor or not total or edge / total < share:
                continue
            if count < marks or width > mark_width:
                continue
            if best is None or edge / total > best[0] / best[1]:
                best = got
        if best is not None:
            out.append({"first": first, "last": last,
                        "cues": last - first + 1, "ink": best[0],
                        "share": best[0] / best[1], "marks": best[2],
                        "width": best[3]})
    out.sort(key=lambda run: (-run["share"], -run["ink"], -run["cues"]))
    return out


def work_of(srt_name):
    """The work dir holding this episode's strips, or None if it is gone."""
    for entry in paths.load_inventory():
        if entry.get("srt_name") != srt_name:
            continue
        for folder in paths.work_dirs(entry["slug"]):
            if os.path.isdir(os.path.join(folder, "strips")):
                return folder
    return None


def review(srt_name, floor=EDGE_INK, share=EDGE_SHARE, rows=EDGE_ROWS):
    """Blank runs in this episode that a human should look at again.

    None when the work dir is gone: the strips are the evidence, and
    "cannot tell" is not the same answer as "nothing to see".
    """
    work = work_of(srt_name)
    if work is None:
        return None
    spans = runs_of_blank(blanks(srt_name))
    return flagged_runs(spans, evidence_of(work, rows), floor, share)


def when(name, first, last):
    """Seconds covered by cues `first`..`last`, off the store's cues.json."""
    path = paths.stage_path(paths.KARI_CUES, name, ".json")
    if not os.path.exists(path):
        return None
    cues = json.load(open(path, encoding="utf-8"))["cues"]
    if last > len(cues):
        return None
    return cues[first - 1]["start"], cues[last - 1]["end"]


def cue_times(work):
    """`{cue: (start, end)}` off a work dir's own timeline.

    The review list needs the clock more than anything else it prints:
    text above the band at 2,840 s is the closing trailer card, text above
    the band mid-programme is dialogue nobody read, and the measurement
    cannot tell those apart -- only the reader can, and only if told when.
    An episode still being worked on has no timeline in the store yet, so
    asking the store alone leaves exactly the batch under review with a
    dash in that column.
    """
    path = paths.cues_to_read(work)
    if not path:
        return {}
    with open(path, encoding="utf-8") as handle:
        book = json.load(handle)
    out = {}
    for cue in book.get("cues", []):
        out[cue["index"]] = (cue["start"], cue["end"])
    return out


def _table():
    """Every episode's blank runs by length -- the shortlist, not a verdict."""
    out = []
    for folder in sorted(glob.glob(paths.KARI_VISION + "/*/*")):
        name = os.path.basename(folder)
        rows = blanks(name)
        if not rows:
            continue
        spans = runs_of_blank(rows)
        longest = 0
        where = None
        for first, last in spans:
            if last - first + 1 > longest:
                longest = last - first + 1
                where = (first, last)
        total = 0
        for first, last in spans:
            if last - first + 1 >= 20:
                total += last - first + 1
        out.append((total, longest, name, where, len(rows)))
    out.sort(reverse=True)
    print("空白≥20連\t上長連\t集\t上長彼段(cue)\t時間\t總 cue")
    for total, longest, name, where, size in out:
        if total == 0:
            continue
        span = when(name, where[0], where[1]) if where else None
        stamp = "%.0f–%.0fs" % span if span else "-"
        print("%d\t%d\t%s\t%d–%d\t%s\t%d"
              % (total, longest, name, where[0], where[1], stamp, size))


def _review(srt_name, floor, share):
    """One episode's runs that carry cut-off ink, worst evidence first."""
    work = work_of(srt_name)
    if work is None:
        print("%s：work dir 無矣，無圖條通量" % srt_name)
        return 0
    runs = review(srt_name, floor, share)
    if not runs:
        print("%s：無揣著帶外字幕ê證據" % srt_name)
        return 0
    times = cue_times(work)
    print("段(cue)\t條數\t頂逝墨\t占規條\t痕\t闊\t時間")
    for run in runs:
        span = when(srt_name, run["first"], run["last"])
        if span is None and run["first"] in times and run["last"] in times:
            span = (times[run["first"]][0], times[run["last"]][1])
        stamp = "%.0f–%.0fs" % span if span else "-"
        print("%d–%d\t%d\t%d\t%.3f\t%d\t%d\t%s"
              % (run["first"], run["last"], run["cues"], run["ink"],
                 run["share"], run["marks"], run["width"], stamp))
    print()
    print("節目尾（≳2800 秒）ê片尾卡、預告卡ê字嘛印佇帶頂懸，掠著是"
          "正常ê，毋是漏勾ê對白——看時間就分會出來。")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("srt_name", nargs="?", default=None,
                    help="干焦這一集，掠帶外字幕（省略就是全部ê長度總表）")
    ap.add_argument("--floor", type=float, default=EDGE_INK,
                    help="頂逝愛偌濟墨才算證據（預設 %d）" % EDGE_INK)
    ap.add_argument("--share", type=float, default=EDGE_SHARE,
                    help="彼寡墨愛佔規條偌濟（預設 %.2f）" % EDGE_SHARE)
    args = ap.parse_args(argv)
    if args.srt_name:
        return _review(paths.check_srt_name(args.srt_name), args.floor,
                       args.share)
    _table()
    return 0


if __name__ == "__main__":
    sys.exit(main())
