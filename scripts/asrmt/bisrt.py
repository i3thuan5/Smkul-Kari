#!/usr/bin/env python3
"""Render the default deliverable: the two-line raw SRT.

Two files, never one overwriting the other: the review render carries
every translation the money was already spent on, six labelled lines per
entry; once the primary engine is decided the complete render collapses
to the two delivered lines. Both use the chain's display timestamps, so
they stay coaxial with the delivered subtitle SRT line for line.
"""
from scripts.srtlib import srt

ENGINES = ("ailabs", "claude")


def _two_lines(rows):
    blocks = []
    for row in rows:
        lines = ["族語：" + row["formosan"],
                 "華語：" + row["subtitle"]]
        blocks.append((row["srt_start"], row["srt_end"], "\n".join(lines)))
    return srt.render_srt(blocks)


def raw_body(entries):
    """The two-line comparison SRT, renderable straight after projection.

    Same format as the deliverable (族語：/華語：), always one entry per
    delivered-SRT entry -- the un-merged view the complete render is
    compared against.
    """
    return _two_lines(entries)


def write(path, body):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(body)
        if body and not body.endswith("\n"):
            handle.write("\n")
