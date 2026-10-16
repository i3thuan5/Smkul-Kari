#!/usr/bin/env python3
"""One episode's CSV rows as the 3-srt-paragraph SRT (a string).

The high- and mid-confidence groups, one cue each, numbered in order,
two labelled lines with the CSV's text. The time is the CSV's, copied:
it is already padded with every VAD segment of the episode as a
neighbour (`overlap.padded_spans`). Padding again from the kept rows
alone would let a cue reach into a dropped group or a lonely segment,
so this module never sees segments or the audio length at all.

An episode with no kept group is an empty file, so it reads as made.
"""
from scripts.srtlib import srt

DROPPED = "不採用"


def render(rows):
    """SRT text for the kept rows; "" when none is kept."""
    entries = []
    for r in rows:
        if r["信心層級"] == DROPPED:
            continue
        entries.append((srt._parse_ts(r["開始時間"]),
                        srt._parse_ts(r["結束時間"]),
                        "族語：%s\n華語：%s" % (r["族語"], r["華語"])))
    text = srt.render_srt(entries)
    return text + "\n" if text else ""
