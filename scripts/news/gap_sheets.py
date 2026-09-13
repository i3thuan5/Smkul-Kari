#!/usr/bin/env python3
"""Prepare an episode's contact sheets for the vision pass.

Every cue goes on a sheet. There was once a filter here: cues the episode's
文稿 could supply were left off, on the grounds that re-reading them was paid
work for no gain. Measuring it settled the question the other way -- of 4,344
cues the script supplied, 336 disagreed with the picture and the picture was
right every time -- so those cues had to be read anyway, and building two
rounds of contact sheets to read the same strips twice cost more than reading
them once. The 文稿 path is gone; see git history and
`Kari-SRT/report/rtf-vs-vision.*` for the comparison it produced.

It builds the sheets inside the episode's own work dir (`<slug>.work`),
beside the strips they are cut from.
"""
import argparse
import json
import os

from scripts.news import episodes
from scripts.news import paths
from scripts.ocr import sheets
from scripts import lowpri
from scripts.errors import PipelineError

WORK = paths.WORK


# Both tools here rebuild sheets for news work dirs only -- 開會了 has its
# own pipeline and `scripts/aiyalaeho/README.md` lists gap_sheets among the
# four news tools it does without. So the layout is read straight off the
# news presets, with no flag for the caller to remember and get wrong; the
# sheets a rebuild produces then match the ones `cues --sheets` produced.
NEWS_PRESET = "titv-news"


def news_sheet_layout(preset_name=NEWS_PRESET):
    """(row_slots, compare_cols, right_anchor) declared by the news layout."""
    with open(paths.ENGINE_PRESETS, encoding="utf-8") as handle:
        presets = json.load(handle)
    preset = presets.get(preset_name) or {}
    mask = preset.get("mask", {}) or {}
    return (preset.get("sheet", {}).get("row_slots"),
            mask.get("compare_cols"),
            mask.get("right_anchor"))


def already_read(dst):
    """True if somebody has already transcribed cues into this work dir.

    Preparing writes a fresh transcripts.json and verified.json, so running it
    over a finished vision pass would throw that reading away. The reading is
    the expensive part of the whole pipeline -- guard it.
    """
    path = os.path.join(dst, "verified.json")
    if not os.path.exists(path):
        return False
    with open(path, encoding="utf-8") as handle:
        return bool(json.load(handle))


def prepare(slug):
    """Build this episode's sheets in its own work dir.

    This used to build a second dir beside it (`<slug>.B.work`) with a copy
    of the timeline and a symlink to the strips. The copy is gone with the
    second dir: the sheets are built from whichever stage `cues_to_read`
    picks, and writing that manifest back would overwrite the coarse file,
    which is meant to be written once and never touched again.
    """
    paths.check_name(slug, "slug")
    work = paths.work_dir(slug, WORK)
    if already_read(work):
        raise PipelineError(
            "%s already holds verified transcripts; refusing to "
            "overwrite" % work)
    os.makedirs(work, exist_ok=True)

    with open(paths.cues_to_read(work), encoding="utf-8") as handle:
        manifest = json.load(handle)

    slots, cols, anchor = news_sheet_layout()
    made = sheets.build_sheets(work, manifest, row_slots=slots,
                               compare_cols=cols, right_anchor=anchor)

    for name in ("transcripts.json", "verified.json"):
        with open(os.path.join(work, name), "w", encoding="utf-8") as handle:
            json.dump({}, handle, ensure_ascii=False, indent=2,
                      sort_keys=True)

    return len(manifest["cues"]), made


def main(argv=None):
    lowpri.be_nice()   # 長時間ê重工，莫kā機器食牢去
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("slugs", nargs="*", help="work-dir slugs; default all")
    args = ap.parse_args(argv)

    entries = episodes.load()
    total_sheets = 0
    for entry in entries:
        slug = entry["slug"]
        if args.slugs and slug not in args.slugs:
            continue
        work = paths.work_dir(slug, WORK)
        if not paths.cues_to_read(work):
            print("skip %s (not decoded)" % slug)
            continue
        if os.path.exists(os.path.join(work, "sheets.json")) \
                or already_read(work):
            print("skip %s (already prepared or read)" % slug)
            continue
        cues, made = prepare(slug)
        total_sheets += made
        print("%-44s cues=%4d sheets=%3d" % (entry["srt_name"], cues, made))
    print("\nsheets to read: %d" % total_sheets)
    return 0


if __name__ == "__main__":
    main()
