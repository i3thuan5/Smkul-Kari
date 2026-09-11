#!/usr/bin/env python3
"""Print the reader's brief for one batch of one episode.

The criteria in here came out of the episodes themselves, and they kept
changing -- four times in one session. Hand-editing eighty lines per
dispatch is how a criterion quietly stops being sent: the batch that
misses it reads differently from its neighbours, and nothing says so.

    python3 scripts/news/reread_tools/prompt.py <srt_name> a
    python3 scripts/news/reread_tools/prompt.py <srt_name> b
    python3 scripts/news/reread_tools/prompt.py <srt_name> a2 101-120

The third form takes an explicit row range, for finishing a batch that
stopped part-way -- a session limit has cut one off three times, and the
rows already written are worth keeping. `safe_resplit` globs `read*.tsv`,
so the offcut goes in its own file and needs no merging.

Batches are cut evenly over `segments.tsv`; `a` is the first half. The
episode's own numbers (segment count, sheet range, work dir) are read off
disk, so a new criterion is added once, here, and every later batch gets
it.
"""
import glob
import os
import sys
from scripts.errors import PipelineError
from scripts.news import paths

PER_SHEET = 4

BRIEF = os.path.join(os.path.dirname(__file__), "brief.md")


def work_dir(name):
    """The `.work` directory holding this episode's transcripts."""
    bits = name.split("_")
    for d in sorted(glob.glob("kithann/out/mxf/*.work")):
        got = os.path.basename(d)[:-len(".work")].split("_")
        if got[1] == bits[1] and got[3] == bits[2]:
            return d
    raise PipelineError("揣無 work dir：%s" % name)


def sources(name):
    """The places a sentence has to be absent from to count as new."""
    month = paths.month_of(name)
    return ["  - `%s/%s/%s/b*.tsv`（第三欄）"
            % (os.path.relpath(paths.KARI_VISION, os.path.dirname(paths.KARI)),
               month, name),
            "  - `%s/transcripts.json`（數字 key ê `han` 欄）"
            % work_dir(name)]


def brief(name, tag, halves=2, span=None):
    """The whole reader brief for batch `tag` of `name`.

    `span` is an explicit `"lo-hi"` row range; without it the episode is
    cut into `halves` even batches at sheet boundaries.
    """
    d = os.path.join("kithann/out/reread", name)
    total = 0
    for _ in open(os.path.join(d, "segments.tsv"), encoding="utf-8"):
        total += 1
    if span:
        lo, hi = int(span.split("-")[0]), int(span.split("-")[1])
    else:
        which = "abcd".index(tag[0])
        sheets = -(-total // PER_SHEET)
        step = -(-sheets // halves) * PER_SHEET      # 切佇圖條ê邊界
        lo = which * step + 1
        hi = min(total, lo + step - 1)
    got = sources(name)
    videos = sorted(glob.glob("kithann/out/mkv/%s.mkv" % name))
    if not videos:
        raise PipelineError("揣無影片：%s" % name)
    with open(BRIEF, encoding="utf-8") as handle:
        text = handle.read()
    # `str.format` 袂使用：brief.md 內底有 `mask_{i+1}` 這款散文用ê
    # 大括號，伊會當做佔位符去掔 KeyError。逐个已知ê鍵家己換就好，
    # 其他ê大括號原封不動。
    bits = name.split("_")
    fill = {"name": name, "tag": tag,
            "stem": bits[1] + bits[2],
            "total": total, "lo": lo, "hi": hi,
            "count": hi - lo + 1, "per": PER_SHEET, "video": videos[0],
            "sheet_lo": "%03d" % ((lo - 1) // PER_SHEET + 1),
            "sheet_hi": "%03d" % (-(-hi // PER_SHEET)),
            "sources": "\n".join(got),
            "sources_count": "三" if len(got) > 2 else "兩"}
    for key, value in fill.items():
        text = text.replace("{%s}" % key, str(value))
    return text


if __name__ == "__main__":
    got = sys.argv[3] if len(sys.argv) > 3 else None
    if got and "-" in got:
        print(brief(sys.argv[1], sys.argv[2], span=got))
    else:
        print(brief(sys.argv[1], sys.argv[2], int(got) if got else 2))
