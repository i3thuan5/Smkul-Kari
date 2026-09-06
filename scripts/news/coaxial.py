#!/usr/bin/env python3
"""Can the store rebuild the speech side, byte for byte?

The speech side's deliverables are all derived: `2-srt-raw` is the word
stream projected onto the picture side's timeline, `3-srt-ai` adds a
translation out of the shared cache, `4-srt-quality` adds a grade out of
the judgment cache. Every one of them can be produced again from things
that are in the store -- so the check is to produce it again and compare
the bytes, which is exactly what `rebuild --verify` has always done to
the picture side.

That catches three ways of going wrong, where comparing timestamps
caught only the last: a delivered file edited by hand; the code changed
without the file being regenerated (or the other way round); and an
input re-versioned without the files below it following. Coaxiality
comes out of it for free -- a rebuilt Formosan line was projected onto
the picture side's own timeline, so it cannot disagree about time.

Two rules, deliberately not symmetrical (使用者裁定 2026-09-03):

  a stage with no file    fine, and not even a warning. The speech side
                          runs at its own pace and `smkul.csv` already
                          reports how far it has got; making "not done
                          yet" an error keeps the check red for weeks,
                          and a permanently red check is one nobody
                          reads.
  a file that cannot      an error. It means the file did not come out
  be rebuilt              of the store -- a translation or a judgment
                          was written straight into the deliverable, or
                          a cache entry has since been removed.

The rebuilders are passed in rather than imported, so this module stays
a comparison and the callers own the pipeline. `scripts.news.rebuild`
assembles the list.
"""
import os

from scripts.news import paths
from scripts.srtlib import srt
from scripts.errors import PipelineError


def _entries(text):
    """(start, end, text) per entry, or None when it will not parse."""
    try:
        return srt.parse_srt(text)
    except Exception:
        return None


def difference(stored, rebuilt):
    """None when the two are identical, else what a person should look at.

    Named by entry, not by byte offset: the fix is always to re-render
    one episode, and the entry number is what points at the cause.
    """
    if stored == rebuilt:
        return None
    left = _entries(stored)
    right = _entries(rebuilt)
    if left is None or right is None:
        return "檔案讀袂出來（毋是好勢ê SRT）"
    if len(left) != len(right):
        return ("條目數無仝：交付 %d 條、重建 %d 條"
                % (len(left), len(right)))
    for index, (a, b) in enumerate(zip(left, right), 1):
        if a == b:
            continue
        if (a[0], a[1]) != (b[0], b[1]):
            return ("條目 %d 時間無仝：交付 %.3f–%.3f、重建 %.3f–%.3f"
                    % (index, a[0], a[1], b[0], b[1]))
        return "條目 %d 文字無仝：交付 %r、重建 %r" % (index, a[2], b[2])
    return "逐條攏仝，毋過 byte 無仝（留白抑是逝尾ê問題）"


def problems(names, stages):
    """One line per (episode, stage) whose stored file is not rebuildable.

    `stages` is [(label, base folder, suffix, rebuild(srt_name) -> text)].
    A stage with no file for an episode is skipped in silence.
    """
    out = []
    for name in names:
        for label, base, suffix, rebuild in stages:
            path = paths.stage_path(base, name, suffix)
            if not os.path.exists(path):
                continue
            try:
                rebuilt = rebuild(name)
            except PipelineError as error:
                out.append("%s %s：重建袂出來——%s" % (name, label, error))
                continue
            with open(path, encoding="utf-8") as handle:
                stored = handle.read()
            said = difference(stored, rebuilt)
            if said:
                out.append("%s %s：%s" % (name, label, said))
    return out
