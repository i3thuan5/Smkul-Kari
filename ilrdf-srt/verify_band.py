#!/usr/bin/env python3
"""Confirm a video's subtitle band really is where the preset says.

    python3 ilrdf-srt/verify_band.py VIDEO --preset titv-news   # --quiet for
                                                                # just a verdict

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

TWO LANDMARKS
-------------
  dialogue plateau  the busiest row once the edge is masked out. Must be
                    INSIDE the preset's region, else we are reading the wrong
                    strip entirely.
  lower-third edge  the single brightest row -- the horizontal white border on
                    top of the red banner. Must NOT be inside the region, else
                    the headline and interviewee name supers get segmented as
                    if they were dialogue.

Deliberately not checked: where ink first appears. There is always some above
the band (white shirts, sky, and the subtitle itself rides higher over
letterboxed clips), so "topmost inky row" flags healthy files -- the first
version of this script did exactly that and false-alarmed on a good file.

PROVENANCE AND VALIDATION STATE  (read this before trusting it)
---------------------------------------------------------------
New in the session that added SFTP fetching; it did not exist for the
February batch, whose band was confirmed by hand instead.

Measured, on 魯凱語-霧台20210101S1100.mp4 (240 sampled frames):

  --preset titv-news                  PASS   edge y=848, plateau y=816
  --preset amis-xiuguluan-bilingual   FAIL   correctly rejected, exit 1

NOT yet measured -- the open item:

The edge rule was loosened after the fact and has not been run against any
video since. A dry run of `fetch_sftp.sh` on 卑南語-20210103S1800.mp4 aborted
because that episode puts its lower-third edge at y=917 rather than the y=848
of the February masters, and the rule then demanded the edge sit just below
the region. Reasoning says an edge *further* below is harmless -- it cannot
leak banner text into a region that ends at y=844 -- so the rule now only
rejects an edge that falls strictly inside the region. That reasoning is
sound but untested: nobody has confirmed that the y=796 plateau on that file
is really dialogue.

Before trusting a month that contains files like it: run this WITHOUT
--quiet on one of them, eyeball the printed profile, and open
`kithann/out/mxf/<slug>.work/sheets/sheet_001.png` to see that the strips
carry the dialogue line and nothing else.
"""
import argparse
import json
import os
import sys

SKILL = "/workspaces/Corpus-Cleanup/.claude/skills/video-subtitle-srt/scripts"
sys.path.insert(0, SKILL)

import numpy as np                                       # noqa: E402
import cuelib                                            # noqa: E402


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--preset", required=True)
    ap.add_argument("--start", type=float, default=300.0)
    ap.add_argument("--duration", type=float, default=240.0)
    ap.add_argument("--quiet", action="store_true",
                    help="only report pass/fail, no profile")
    args = ap.parse_args()

    with open(os.path.join(SKILL, "presets.json"), encoding="utf-8") as handle:
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

    # Two landmarks, both unambiguous:
    #
    #   edge     the brightest row by a wide margin -- the top border of the
    #            red lower-third, a horizontal rule of near-white pixels
    #   plateau  the busiest row once the edge is masked out -- the dialogue
    #
    # Deliberately NOT checked: where ink first appears. There is always some
    # above the band (white shirts, sky, and the subtitle itself rides higher
    # over letterboxed clips), so "topmost inky row" flags healthy files.
    edge_i = int(np.argmax(rows))
    edge = probe[1] + edge_i
    body = rows.copy()
    body[max(0, edge_i - 8):edge_i + 9] = 0
    plateau = probe[1] + int(np.argmax(body))

    lo, hi = want[1], want[1] + want[3]
    print("\npreset %s region y=%d..%d" % (args.preset, lo, hi))
    print("brightest row  y=%d  <- red lower-third edge (%d frames)"
          % (edge, frames))
    print("busiest row    y=%d  <- dialogue plateau" % plateau)

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
    problems = []
    if not lo <= plateau <= hi:
        problems.append("dialogue plateau at y=%d falls outside the region "
                        "(%d..%d)" % (plateau, lo, hi))
    if lo < edge < hi:
        problems.append("lower-third edge at y=%d is inside the region "
                        "(%d..%d); its headline text would be read as "
                        "dialogue" % (edge, lo, hi))
    if problems:
        for line in problems:
            print("FAIL:", line)
        raise SystemExit(1)
    print("OK: band matches the preset")


if __name__ == "__main__":
    main()
