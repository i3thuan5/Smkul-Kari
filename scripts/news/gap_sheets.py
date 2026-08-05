#!/usr/bin/env python3
"""Prepare an episode for a vision pass that only reads what is still unknown.

The 文稿-aligned cues are already exact (96% measured against hand-read
truth), so re-reading them would be paid work for no gain. This builds a
plan-B work dir whose contact sheets carry *only* the cues without script
text, which is about a quarter less to read across the corpus.

The work dir keeps the FULL cue list in cues.json on purpose:

  * `import` validates every TSV row against it, so a stray cue number is
    still refused rather than silently landing on the wrong subtitle
  * the SRT is assembled from it, so the 文稿 cues keep their timings

Only sheets.json is restricted to the gap, and that is what `pending` walks.
"""
import argparse
import json
import os

from scripts.news import align as aligner
from scripts.news import paths
from scripts.subs2srt import cli as subs2srt

CORPUS = paths.CORPUS
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


def prepare(slug, rtf):
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

    aligned = {}
    if rtf and os.path.isdir(rtf):
        records, _, _ = aligner.resolve(src, rtf)
        for rec in records:
            if rec["aligned"].strip():
                aligned[rec["index"]] = rec["aligned"].strip()

    # The full list is what import and the SRT are checked against...
    with open(os.path.join(dst, "cues.json"), "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False)

    # ...but the sheets only show the cues nobody has read yet.
    gap = []
    for cue in manifest["cues"]:
        if cue["index"] not in aligned:
            gap.append(cue)
    filtered = dict(manifest)
    filtered["cues"] = gap
    made = subs2srt.build_sheets(dst, filtered)

    line = manifest["lines"][0]["name"]
    transcripts = {}
    verified = {}
    for index, text in aligned.items():
        transcripts[str(index)] = {line: text}
        verified[str(index)] = {line: True}
    with open(os.path.join(dst, "transcripts.json"), "w",
              encoding="utf-8") as handle:
        json.dump(transcripts, handle, ensure_ascii=False, indent=1)
    with open(os.path.join(dst, "verified.json"), "w",
              encoding="utf-8") as handle:
        json.dump(verified, handle, ensure_ascii=False, indent=1)
    # Remember which cues came from the script rather than from a reader, so
    # the tracker can report the two sources separately.
    with open(os.path.join(dst, "from_rtf.json"), "w",
              encoding="utf-8") as handle:
        json.dump(sorted(aligned), handle)

    return len(manifest["cues"]), len(aligned), len(gap), made


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("slugs", nargs="*", help="work-dir slugs; default all")
    ap.add_argument("--no-rtf", action="store_true",
                    help="put every cue on the sheets, even where a 文稿 "
                         "exists. Measured on the February batch: the 文稿 "
                         "is not faithful enough to ship (7.7%% of its lines "
                         "differ from the picture, and the picture is right "
                         "every time), so cues it covers get read anyway -- "
                         "reading them once here is cheaper than reading "
                         "them twice.")
    args = ap.parse_args()

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
        if os.path.exists(os.path.join(dst, "from_rtf.json")) \
                or already_read(dst):
            print("skip %s (already prepared or read)" % slug)
            continue
        rtf = ""
        if entry["文稿位置"] and not args.no_rtf:
            rtf = os.path.join(CORPUS, entry["文稿位置"])
        cues, aligned, gap, made = prepare(slug, rtf)
        total_sheets += made
        print("%-44s cues=%4d 文稿=%4d 待讀=%4d sheets=%3d"
              % (entry["srt_name"], cues, aligned, gap, made))
    print("\ngap sheets to read: %d" % total_sheets)


if __name__ == "__main__":
    main()
