#!/usr/bin/env python3
"""Do the two sides agree about time?

The speech side projects its words onto the picture side's timeline, so
`2-asr/3-srt-raw/<name>.srt` and `1-ocr/3-srt/<name>.srt` are meant to
carry the same entries at the same timestamps. Nothing checked it:
`rebuild --verify` rebuilds the picture side and never opens the speech
side, so 47 delivered episodes drifted apart and stayed that way for two
months.

Two rules, deliberately not symmetrical (使用者裁定 2026-09-03):

  both sides delivered   the (index, start, end) sequences must match.
                         A mismatch is an error to fix -- two files
                         claiming different timings for one episode is a
                         contradiction, and nothing downstream can say
                         which is right. The fix is cheap: reproject and
                         re-render off `2-entries`, no recognition again.
  only the picture side   fine, and not even a warning. The speech side
                         runs at its own pace and `smkul.csv` already
                         reports how far it has got; making "not done
                         yet" an error keeps the check red for weeks,
                         and a permanently red check is one nobody reads.

Timestamps only. The 族語 line comes from the recogniser and is not
supposed to match the subtitle, so comparing text would be red for every
episode ever.
"""
import os

from scripts.srtlib import srt


def _spine(path):
    """(index, start, end) for each entry, which is what has to agree."""
    with open(path, encoding="utf-8") as handle:
        entries = srt.parse_srt(handle.read())
    out = []
    for index, (start, end, _text) in enumerate(entries, 1):
        out.append((index, round(start, 3), round(end, 3)))
    return out


def compare(picture, speech):
    """None when the two agree (or the speech side has not been made)."""
    if not os.path.exists(speech):
        return None
    if not os.path.exists(picture):
        return None
    left = _spine(picture)
    right = _spine(speech)
    if left == right:
        return None
    for a, b in zip(left, right):
        if a != b:
            return ("條目 %d：影像側 %.3f–%.3f、語音側 %.3f–%.3f"
                    % (a[0], a[1], a[2], b[1], b[2]))
    return "條目數無仝：影像側 %d 條、語音側 %d 條" % (len(left), len(right))


def problems(episodes):
    """`[(name, picture, speech)]` -> one line per episode that differs."""
    out = []
    for name, picture, speech in episodes:
        said = compare(picture, speech)
        if said:
            out.append("%s %s" % (name, said))
    return out
