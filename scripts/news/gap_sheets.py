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

The work dir this builds is `<slug>.B.work`, beside the `<slug>.work` that
`cues` produced. It carries its own cues.json and sheets.json but symlinks
the strips, which are gigabytes of PNG.
"""
import argparse
import json
import os

from scripts.news import paths
from scripts.subs2srt import sheets

WORK = paths.WORK


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
    src = os.path.join(WORK, slug + ".work")
    dst = os.path.join(WORK, slug + ".B.work")
    if already_read(dst):
        raise SystemExit("%s already holds verified transcripts; refusing to "
                         "overwrite" % dst)
    os.makedirs(dst, exist_ok=True)

    with open(os.path.join(src, "cues.json"), encoding="utf-8") as handle:
        manifest = json.load(handle)

    # Point at the original strips rather than copying gigabytes of PNG.
    link = os.path.join(dst, "strips")
    if not os.path.islink(link):
        os.symlink(os.path.join("..", slug + ".work", "strips"), link)

    with open(os.path.join(dst, "cues.json"), "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False)
    made = sheets.build_sheets(dst, manifest)

    for name in ("transcripts.json", "verified.json"):
        with open(os.path.join(dst, name), "w", encoding="utf-8") as handle:
            json.dump({}, handle, ensure_ascii=False, indent=1)

    return len(manifest["cues"]), made


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("slugs", nargs="*", help="work-dir slugs; default all")
    args = ap.parse_args(argv)

    entries = json.load(open(paths.INVENTORY, encoding="utf-8"))
    total_sheets = 0
    for entry in entries:
        if entry["truncated"]:
            continue
        slug = entry["slug"]
        if args.slugs and slug not in args.slugs:
            continue
        if not os.path.exists(os.path.join(WORK, slug + ".work", "cues.json")):
            print("skip %s (not decoded)" % slug)
            continue
        dst = os.path.join(WORK, slug + ".B.work")
        if os.path.exists(os.path.join(dst, "sheets.json")) \
                or already_read(dst):
            print("skip %s (already prepared or read)" % slug)
            continue
        cues, made = prepare(slug)
        total_sheets += made
        print("%-44s cues=%4d sheets=%3d" % (entry["srt_name"], cues, made))
    print("\nsheets to read: %d" % total_sheets)
    return 0


if __name__ == "__main__":
    main()
