#!/usr/bin/env python3
"""Renders for the align side: the review SRT and the merged deliverable.

Everything here depends on translations or detection verdicts, which the
default pipeline (ending at 3-srt-raw) never runs -- these renders are
invoked only when the align extension is asked for by name.
"""
from scripts.asrmt import bisrt
from scripts.srtlib import srt

ENGINES = ("ailabs", "claude")


def review_body(entries, classes=None):
    """The review SRT: six labelled lines, plus the detector's verdict
    when `classes` (index -> class string) is supplied -- so ok and
    mismatch are visible right in the player."""
    if classes is None:
        classes = {}
    blocks = []
    for row in entries:
        lines = ["族語ASR結果：" + row["formosan"]]
        for engine in ENGINES:
            lines.append("華語OCR字幕翻譯成族語-%s：%s"
                         % (engine, row["formosan_from_zh"].get(engine, "")))
        lines.append("華語OCR字幕：" + row["subtitle"])
        for engine in ENGINES:
            lines.append("族語ASR結果翻譯華語-%s：%s"
                         % (engine, row["zh"].get(engine, "")))
        verdict = classes.get(row["index"])
        if verdict:
            lines.append("偵測：" + verdict)
        blocks.append((row["srt_start"], row["srt_end"], "\n".join(lines)))
    return srt.render_srt(blocks)


def _merge_group(group):
    formosan = []
    subtitle = []
    for row in group:
        if row["formosan"]:
            formosan.append(row["formosan"])
        subtitle.append(row["subtitle"])
    return {"formosan": " ".join(formosan), "subtitle": "".join(subtitle),
            "srt_start": group[0]["srt_start"],
            "srt_end": group[-1]["srt_end"]}


def complete_body(entries, verdicts=None, block_of=None):
    """The deliverable: source material only, selectively sentence-merged.

    Rules (使用者裁定): an entry the detector classed `ok` stays on its
    own; a sentence block containing any other verdict is merged into
    one entry -- Chinese = the block's subtitle lines concatenated in
    order, Formosan = the block's recognised words in time order. Never
    reordered, never rewritten, no machine translation anywhere.
    """
    if verdicts is None or block_of is None:
        return bisrt._two_lines(entries)
    rows = []
    position = 0
    while position < len(entries):
        block = block_of.get(entries[position]["index"])
        group = [entries[position]]
        position += 1
        while position < len(entries) and \
                block_of.get(entries[position]["index"]) == block:
            group.append(entries[position])
            position += 1
        all_ok = True
        for row in group:
            if verdicts.get(row["index"]) != "ok":
                all_ok = False
        if all_ok or len(group) == 1:
            rows.extend(group)
        else:
            rows.append(_merge_group(group))
    return bisrt._two_lines(rows)
