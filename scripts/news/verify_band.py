#!/usr/bin/env python3
"""Confirm a video's subtitle band really is where the preset says.

    python3 -m scripts.news.verify_band VIDEO --preset titv-news   # --quiet
                                                                   # for just
                                                                   # a verdict

WHY THIS EXISTS
---------------
`subs2srt detect` is not usable here on its own: on this material it ranks the
weather graphic and the station lower-third above the dialogue line, so a run
driven by it would segment confidently on the wrong strip of pixels and never
report an error. Cutting a whole month against the wrong band costs hours and
looks completely normal until somebody opens a contact sheet.

So this does not detect anything. It *measures* the ink profile over a few
minutes of video and checks it against the band the preset already claims,
failing loudly on a mismatch. `fetch_sftp.sh` runs it once per folder before
committing to a batch.

TWO LANDMARKS, TOLD APART BY SHAPE
----------------------------------
A line of subtitle is a *broad* feature: fifty-odd rows of similar ink, the
height of the glyph bodies. A graphic's border is a *thin* one: two or three
near-white rows with ordinary picture either side. Reading the profile by
height alone confuses them, and did, twice -- so each landmark is found by
the shape that defines it.

  dialogue plateau  the busiest row of the profile after smoothing over a
                    glyph's height, which levels thin rules and leaves broad
                    ones standing. Must be INSIDE the preset's region, else we
                    are reading the wrong strip entirely.
  lower-third edge  the row standing highest above its own local baseline --
                    what the smoothing threw away. It counts as a border only
                    at SPIKE times that baseline; below it there is no graphic
                    in view, only the densest row of the subtitle itself.
                    Where there is one, it must NOT be inside the region, else
                    the headline and interviewee name supers get segmented as
                    if they were dialogue.

The spike is measured against its own neighbourhood rather than against the
dialogue, which keeps it readable when the graphic is on screen for only part
of the sampled window: both terms of the ratio shrink together, where a
fraction-of-the-dialogue reading would simply collapse.

Deliberately not checked: where ink first appears. There is always some above
the band (white shirts, sky, and the subtitle itself rides higher over
letterboxed clips), so "topmost inky row" flags healthy files -- the first
version of this script did exactly that and false-alarmed on a good file.

PROVENANCE AND VALIDATION STATE  (read this before trusting it)
---------------------------------------------------------------
New in the session that added SFTP fetching; it did not exist for the
February batch, whose band was confirmed by hand instead.

Measured, 240 sampled frames from t=300s. `spike` is the tallest row over its
own local baseline; a real border is a multiple of it, a subtitle row is not:

  file                         preset      plateau  spike        verdict
  魯凱語-霧台20210101S1100.mp4  titv-news   y=814    y=849  3.12  PASS
  魯凱語-霧台20210101S1100.mp4  amis-…      y=848    y=836  1.01  FAIL, right:
      the plateau falls outside that preset's 876..1014, which is what
      catches a preset applied to the wrong material
  21NL003_41午間族語新聞.mp4     titv-news   y=807    y=835  1.23  PASS
      no lower third on screen at all, only a language badge below the
      region; y=835 is the bottom stroke of the glyphs
  21NL004_37晚間族語新聞.mp4     titv-news   y=800    y=919  4.50  PASS
      the full news layout: two borders below the region, at y=846 and
      y=919, and the dialogue inside it

3.12 and 4.50 against 1.23 and 1.01 is the gap SPIKE splits.

Both of the PASSes above were failures before the shape reading went in, and
both would have made a whole folder unfetchable:

  41午  its brightest row is the glyphs' own bottom stroke, which is inside
        the region by construction, so it was refused as a border in the band
  37晚  its busiest single row is a border 3 px BELOW the region, so the
        plateau was reported at y=847 and called outside

An edge below the region is fine and does happen: the February masters put
one at y=848, four pixels under, and a January 卑南 episode at y=917. Only an
edge landing within lo..hi is rejected.

This is a measurement, not a proof. On the first file of any new folder, run
WITHOUT --quiet, eyeball the printed profile, and open
`kithann/out/mxf/<slug>.work/sheets/sheet_001.png` to see that the strips
carry the dialogue line and nothing else.
"""
import argparse
import json

import numpy as np

from scripts.news import paths
from scripts.ocr import cuelib

# Rows to average over when separating broad features from thin ones: about
# the height of a subtitle glyph, so a line of text survives and a two-pixel
# rule does not.
SMOOTH = 24

# How far a row must stand above its own local baseline before it is read as a
# graphic's border rather than as part of the subtitle. Measured: 3.12 and
# 4.50 for real borders, 1.23 and 1.01 for the densest row of a subtitle.
SPIKE = 2.0


def profile(path, region, spec, start, duration, fps=1.0):
    rows = np.zeros(region[3], dtype=np.int64)
    frames = 0
    for _, rgb in cuelib.stream_region(path, region, fps=fps,
                                       start=start, duration=duration):
        rows += cuelib.text_mask(rgb, spec).sum(axis=1)
        frames += 1
    if not frames:
        raise SystemExit("no frames decoded from %s" % path)
    return rows / float(frames), frames


def landmarks(rows):
    """(edge index or None, plateau index, spike ratio).

    Split the profile into what survives smoothing over a glyph's height and
    what that smoothing throws away. The first is where the text is; the
    second is where the thin bright rules are, if any. Judging both by height
    instead confuses a graphic's border with the densest row of a subtitle,
    which is what made this refuse two perfectly good layouts.
    """
    broad = np.convolve(rows, np.ones(SMOOTH) / SMOOTH, mode="same")
    plateau = int(np.argmax(broad))
    thin = rows - broad
    edge = int(np.argmax(thin))
    baseline = broad[edge]
    if baseline <= 0:
        return None, plateau, 0.0
    # Against its own baseline, not against the dialogue: a border on screen
    # for only part of the window shrinks both terms together, so the ratio
    # degrades gently instead of collapsing.
    ratio = float(thin[edge]) / float(baseline)
    if ratio < SPIKE:
        return None, plateau, ratio
    return edge, plateau, ratio


def judge(edge, plateau, lo, hi):
    """The two rules that must hold before a batch may be cut.

    The dialogue plateau must sit inside the preset's region, and a
    lower-third edge (when one is on screen at all) must not: an edge any
    distance BELOW the region is fine -- the February masters put it 4px
    under (y=848), a January 卑南 episode 73px under (y=917), both safe.
    """
    problems = []
    if not lo <= plateau <= hi:
        problems.append("dialogue plateau at y=%d falls outside the region "
                        "(%d..%d)" % (plateau, lo, hi))
    if edge is not None and lo < edge < hi:
        problems.append("lower-third edge at y=%d is inside the region "
                        "(%d..%d); its headline text would be read as "
                        "dialogue" % (edge, lo, hi))
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--preset", required=True)
    ap.add_argument("--start", type=float, default=300.0)
    ap.add_argument("--duration", type=float, default=240.0)
    ap.add_argument("--quiet", action="store_true",
                    help="only report pass/fail, no profile")
    args = ap.parse_args()

    with open(paths.ENGINE_PRESETS, encoding="utf-8") as handle:
        presets = json.load(handle)
    if args.preset not in presets:
        raise SystemExit("no preset %r" % args.preset)
    preset = presets[args.preset]
    want = preset["region"]
    spec = cuelib.MaskSpec.from_dict(preset.get("mask", {}))

    # Look well above and below the expected band so a shifted layout shows up
    # as a plateau outside it rather than as a plateau that merely looks odd.
    probe = cuelib.normalize_region((0, want[1] - 40, want[2], want[3] + 120))
    rows, frames = profile(args.video, probe, spec, args.start, args.duration)

    if not args.quiet:
        for i in range(0, probe[3], 4):
            value = rows[i:i + 4].mean()
            print("y=%4d %7.1f %s" % (probe[1] + i, value,
                                      "#" * int(min(60, value / 5))))

    # Two landmarks, each found by its shape (see the module docstring):
    # a broad plateau is text, a thin spike is a graphic's border, and not
    # every layout has a border in view at all.
    #
    # Deliberately NOT checked: where ink first appears. There is always some
    # above the band (white shirts, sky, and the subtitle itself rides higher
    # over letterboxed clips), so "topmost inky row" flags healthy files.
    edge_i, plateau_i, ratio = landmarks(rows)
    edge = None if edge_i is None else probe[1] + edge_i
    plateau = probe[1] + plateau_i

    lo, hi = want[1], want[1] + want[3]
    print("\npreset %s region y=%d..%d  (%d frames)"
          % (args.preset, lo, hi, frames))
    print("broad plateau  y=%d  <- dialogue" % plateau)
    if edge is None:
        print("no thin rule   (tallest spike only %.2fx its baseline, under "
              "%.2f) <- no lower third on screen" % (ratio, SPIKE))
    else:
        print("thin rule      y=%d  <- lower-third edge, %.2fx its baseline"
              % (edge, ratio))

    # What actually has to hold:
    #
    #   the dialogue must be inside the region, or we are reading the wrong
    #   strip of pixels entirely; and
    #   the lower-third's edge must not be inside it, or its headline and
    #   name supers get segmented as if they were dialogue.
    #
    # An edge comfortably *below* the region is fine, and does happen: the
    # February masters put it at y=848, four pixels under the region, while a
    # January 卑南 episode puts it at y=917. Both are safe; only an edge that
    # lands within lo..hi is not.
    problems = judge(edge, plateau, lo, hi)
    if problems:
        for line in problems:
            print("FAIL:", line)
        raise SystemExit(1)
    print("OK: band matches the preset")


if __name__ == "__main__":
    main()
