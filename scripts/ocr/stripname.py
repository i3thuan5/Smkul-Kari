#!/usr/bin/env python3
"""What a cue's strip file is called: its start time, not its position.

A strip used to be `%05d_han.png` on the cue's index, which reads as an
identifier and is not one. Cue numbers move: anything that splits a cue --
`safe_resplit` during the reread, `rescan_band`, `split_cue` -- renumbers
every cue after it, while the files on disk keep the names they were given
when they were cut. Measured across the whole store on 2026-08-31:
**46,665 of 75,290 cues (62%, in 48 episodes) have a strip whose filename
is not its cue number.** `strips/00844_han.png` is cue 951.

Both numbers are four digits over overlapping ranges, so the wrong one
looks right. The README's list of recoverable sentences recorded strip
numbers as cue numbers, and acting on them would have edited cues a
hundred rows away with nothing reporting an error.

A start time does not move when some other cue is split, and `t01874700`
does not read as an ordinal, so nobody reaches for it as one. 使用者裁定
2026-08-31.

`cues.json`'s `images` field stays the one place that maps a cue to its
picture -- that was true under either naming and is what every reader is
told to use.
"""
import os
import re

from scripts.errors import PipelineError

ORDINAL = re.compile(r"^\d{4,6}_[A-Za-z0-9]+\.png$")


def of(start, line):
    """`t<milliseconds>_<line>.png` for a cue starting at `start` seconds.

    Milliseconds, zero-padded to eight: a 48-minute programme reaches
    2,880,000, and the shortest cue the segmenter emits is 0.2 s, so
    collisions are not a thing that can happen.
    """
    if start < 0:
        raise PipelineError("起始時間袂使是負ê：%r" % start)
    return "t%08d_%s.png" % (round(start * 1000), line)


def is_ordinal(path):
    """Was this strip named the old way, off the cue's index?

    Both namings live side by side for as long as an unmigrated work dir
    does, and the two are told apart by shape alone -- which is the point
    of the change.
    """
    return bool(ORDINAL.match(os.path.basename(path)))
