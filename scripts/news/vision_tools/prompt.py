#!/usr/bin/env python3
"""Print the reader's brief for one batch of a first-pass vision read.

Same reason as `reread_tools/prompt.py`: the criteria keep changing, and
hand-editing the brief per batch is how one quietly stops being sent. A
February batch is ~45 batches, so the drift would be invisible.

    python3 scripts/news/vision_tools/prompt.py <slug> <batch-no> [--size N]

Batches are cut off `sheets.json`, the same order `scripts.news.batches`
uses, so the TSV name and the cue range agree with what `ingest` expects.
"""
import json
import os
import sys
from scripts.errors import PipelineError
from scripts.news import paths

SIZE = 4
MIN_TAIL = 2
BRIEF = os.path.join(os.path.dirname(__file__), "brief.md")
# `or`, not a `get` default: an exported-but-empty CLAUDE_SCRATCH counts
# as set, and `os.path.join("", name)` then hands the reader a
# relative path that lands wherever it happens to be standing.
SCRATCH = os.environ.get("CLAUDE_SCRATCH") or "/tmp/vision-scratch"


def episode(slug):
    """srt_name for a slug, off the inventory."""
    with open(os.path.join(paths.KARI, "news", "inventory.json"),
              encoding="utf-8") as handle:
        inv = json.load(handle)
    items = inv["episodes"] if isinstance(inv, dict) and "episodes" in inv \
        else inv
    for entry in (items.values() if isinstance(items, dict) else items):
        if entry["slug"] == slug:
            return entry["srt_name"]
    raise PipelineError("inventory 內底揣無 slug：%s" % slug)


def plan(total, size=SIZE, min_tail=MIN_TAIL):
    """Where to cut `total` sheets into batches: a list of (lo, hi).

    Cut at `size`, except that a tail shorter than `min_tail` is folded
    into the batch before it. Each agent carries a fixed cost -- reading
    the brief, checking the frame-extraction pipeline, building masks --
    that does not shrink with the batch (~19k tokens), so folding a tiny
    tail in makes one batch bigger, which is the cheaper direction.

    `scripts.news.batches` calls this rather than cutting its own way:
    it hands out the TSV names that the briefs are written against, and
    when the two disagreed a short tail got its own b03 here and was
    folded into b02 there, so the same cues were read twice under two
    names and `ingest` refused the whole episode.
    """
    if size < 1:
        # `lo += size` never advances, so the loop below spins forever with
        # no output -- the tool looks hung rather than wrong. Caught by
        # passing `--size -1` through `batches`, where argparse takes a
        # negative int happily and `size or SIZE` lets it through truthy.
        raise PipelineError("一批愛至少 1 張，提著 %r" % size)
    spans = []
    lo = 0
    while lo < total:
        spans.append((lo, min(total, lo + size)))
        lo += size
    if len(spans) > 1 and spans[-1][1] - spans[-1][0] < min_tail:
        last = spans.pop()
        spans[-1] = (spans[-1][0], last[1])
    return spans or [(0, 0)]


def workdir(slug):
    """Where `ocr-cli cues` left the sheets for `slug`."""
    return os.path.join("kithann/out/mxf", slug + ".work")


def sheets_holding(order, sheets, lo, hi):
    """The sheet names whose cues overlap [lo, hi], and every cue on them.

    A cue range almost never lands on sheet boundaries, and a half sheet is
    no use to a reader: the numbers are printed on the image, so they can
    only report what is in front of them. So the span is widened to whole
    sheets and the brief asks for every cue on them -- reading a few extra
    already-read cues is cheap, and a row missing from the TSV is not.
    """
    names = []
    cues = []
    for name in order:
        on = sheets[name]
        if max(on) < lo or min(on) > hi:
            continue
        names.append(name)
        cues += on
    if not names:
        raise PipelineError("cue %d–%d 無佇任何一張圖條頂懸" % (lo, hi))
    return names, sorted(cues)


def brief_range(slug, lo, hi, tsv=None):
    """The reader brief for one cue range rather than one numbered batch.

    What `rescan_band` leaves behind: a stretch of fresh cues in the middle
    of an episode whose other batches are already read. There is no batch
    number to ask for -- the range is what identifies the work.

    The edge sheets almost always carry cues from *outside* the range, and
    those are already in another TSV. Writing them again makes `ingest`
    refuse the whole episode ("cue 444 appears in both b02.tsv and
    b05.tsv"). 058晚 b05's reader caught that unaided -- luck, not a
    guard -- so the brief now says the range out loud whenever the sheets
    hold more than was asked for.
    """
    def pick(order, sheets):
        return sheets_holding(order, sheets, lo, hi)

    return _brief(slug, pick, tsv or "b99.tsv", asked=(lo, hi))


def brief(slug, which, size=SIZE, tsv=None):
    """The whole reader brief for batch `which` (1-based) of `slug`."""
    def pick(order, sheets):
        spans = plan(len(order), size)
        if which < 1 or which > len(spans):
            raise PipelineError("批 %d 超出範圍（總共 %d 張、%d 批）"
                                % (which, len(order), len(spans)))
        lo, hi = spans[which - 1]
        cues = []
        for key in order[lo:hi]:
            cues += sheets[key]
        return order[lo:hi], cues

    return _brief(slug, pick, tsv or "b%02d.tsv" % which)


def _brief(slug, pick, tsvname, asked=None):
    """Shared body: `pick(order, sheets)` chooses the sheets and their cues."""
    name = episode(slug)
    work = workdir(slug)
    with open(os.path.join(work, "sheets.json"), encoding="utf-8") as handle:
        sheets = json.load(handle)
    order = sorted(sheets)
    names, cues = pick(order, sheets)
    with open(BRIEF, encoding="utf-8") as handle:
        text = handle.read()
    extra = ""
    if asked and (min(cues) < asked[0] or max(cues) > asked[1]):
        wanted = []
        for cue in cues:
            if asked[0] <= cue <= asked[1]:
                wanted.append(cue)
        extra = ("\n\n**干焦寫 cue %d..%d**（%d 逝）。頭一張佮尾一張圖條"
                 "頂懸有範圍以外ê cue，彼幾條別个 TSV 已經讀過矣——"
                 "閣寫一擺，`ingest` 會講「cue X 佇兩个檔攏有」，"
                 "規集擋落來。"
                 % (asked[0], asked[1], len(wanted)))
        cues = wanted
    # Scratchpad is shared across every agent running at once, so a
    # checkpoint named only for its batch (`b02/part_073.tsv`) gets
    # overwritten by another episode's agent writing the same name over
    # the same cue range -- and it looks completely normal. 057晚 b02
    # lost most of its checkpoints that way.
    scratch = os.path.join(SCRATCH, "%s-%s" % (name, tsvname[:-4]))
    # 「逐張幾條」愛算ê，莫寫死：重切了後ê圖條逐張 3 條，尾張閣較少。
    # 059晚 b09 ê提示寫「逐張 4 條」，讀者去看 `sheets.json` 才無算毋著。
    counts = set()
    for one in names:
        counts.add(len(sheets[one]))
    if len(counts) == 1:
        per = "逐張 %d 條 cue" % counts.pop()
    else:
        per = "上濟 %d 條 cue，尾張較少" % max(counts)
    fill = {"name": name, "work": work, "sheets": len(names), "per": per,
            "scratch": scratch,
            "lo": names[0].split("_")[1].split(".")[0],
            "hi": names[-1].split("_")[1].split(".")[0],
            "clo": min(cues), "chi": max(cues), "cues": len(cues),
            "tsvname": tsvname,
            "video": "kithann/out/mkv/%s.mkv" % name,
            "tsv": os.path.join(paths.KARI_VISION,
                                paths.month_of(name), name, tsvname)}
    for key, value in fill.items():
        text = text.replace("{%s}" % key, str(value))
    if extra:
        text = text.replace("一逝都莫少。", "一逝都莫少。" + extra, 1)
    return text


if __name__ == "__main__":
    # 重切了後ê提示：批次號碼無意義矣，講 cue 範圍。
    #     prompt.py <slug> --cues 292-444 --name b05.tsv
    if "--cues" in sys.argv:
        span = sys.argv[sys.argv.index("--cues") + 1]
        first, last = span.split("-")
        pick_tsv = None
        if "--name" in sys.argv:
            pick_tsv = sys.argv[sys.argv.index("--name") + 1]
        print(brief_range(sys.argv[1], int(first), int(last), pick_tsv))
        sys.exit(0)
    got = SIZE
    if "--size" in sys.argv:
        got = int(sys.argv[sys.argv.index("--size") + 1])
    tsv = None
    if "--name" in sys.argv:
        tsv = sys.argv[sys.argv.index("--name") + 1]
    print(brief(sys.argv[1], int(sys.argv[2]), got, tsv))
