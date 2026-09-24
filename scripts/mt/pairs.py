#!/usr/bin/env python3
"""One episode's groups as the delivered CSV (a string; the caller writes).

Column order is the user's (2026-09-24), with the drop reason last.
Times are SRT stamps of the group's true span (earliest to latest of
its segments and subtitles, no 0.5 s padding). The Formosan text is
sapolita's verbatim, the Chinese the subtitles' verbatim, each joined
by one space. Every group is a row, dropped ones included, so a reader
can see why something is missing; an episode with no groups is still a
file, header only, or it would look not yet produced.
"""
import csv
import io

from scripts.mt import overlap
from scripts.srtlib import srt

FIELDS = ["族語別", "語言別代號", "成果檔名", "開始時間", "結束時間", "族語",
          "華語", "信心層級", "辭典命中率", "chrF", "最像的族語別", "語音段數",
          "字幕條數", "不採用原因"]


def row(episode, group, segments, entries, feats, level, reason):
    """One CSV row (dict) for a group."""
    start, end = overlap.span(group, segments, entries)
    formosan = []
    for i in group["segs"]:
        text = segments[i]["formosan"].strip()
        if text:
            formosan.append(text)
    han = []
    for j in group["entries"]:
        text = entries[j]["han"].strip()
        if text:
            han.append(text)
    return {
        "族語別": episode["族語別"], "語言別代號": episode["語言別代號"],
        "成果檔名": episode["成果檔名"],
        "開始時間": srt.srt_timestamp(start),
        "結束時間": srt.srt_timestamp(end),
        "族語": " ".join(formosan), "華語": " ".join(han),
        "信心層級": level,
        "辭典命中率": "%.3f" % feats["lexicon_rate"],
        "chrF": "%.3f" % feats["chrf"],
        "最像的族語別": feats.get("best_tribe", ""),
        "語音段數": str(len(group["segs"])),
        "字幕條數": str(len(group["entries"])),
        "不採用原因": reason,
    }


def render(rows):
    """UTF-8-ready text: header plus rows, LF, quoted where needed."""
    out = io.StringIO()
    writer = csv.DictWriter(out, FIELDS, lineterminator="\n")
    writer.writeheader()
    for item in rows:
        writer.writerow(item)
    return out.getvalue()
