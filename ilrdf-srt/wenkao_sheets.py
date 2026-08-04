#!/usr/bin/env python3
"""Build contact sheets for the cues whose text came from the 文稿.

Those cues were deliberately left out of the first vision pass -- the script
already supplied their wording, so re-reading them would have been paid work
for no gain. Reading them now turns a 24-row spot check into a full
cue-by-cue comparison of script against picture.

This writes a THIRD work dir (`.C.work`) rather than touching `.B.work`,
because .B.work holds the finished vision pass plus the 文稿 text, and both
are needed to diff against. Nothing here overwrites either.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = "/workspaces/Corpus-Cleanup/.claude/skills/video-subtitle-srt/scripts"
sys.path.insert(0, HERE)
sys.path.insert(0, SKILL)

import subs2srt                                          # noqa: E402

WORK = "/workspaces/Corpus-Cleanup/kithann/out/mxf"


def prepare(slug):
    src = os.path.join(WORK, slug + ".work")
    plan_b = os.path.join(WORK, slug + ".B.work")
    dst = os.path.join(WORK, slug + ".C.work")

    marker = os.path.join(plan_b, "from_wenkao.json")
    if not os.path.exists(marker):
        return 0, 0
    with open(marker, encoding="utf-8") as handle:
        wanted = set(json.load(handle))
    if not wanted:
        return 0, 0

    os.makedirs(dst, exist_ok=True)
    link = os.path.join(dst, "strips")
    if not os.path.islink(link):
        os.symlink(os.path.join("..", slug + ".work", "strips"), link)

    with open(os.path.join(src, "cues.json"), encoding="utf-8") as handle:
        manifest = json.load(handle)
    # Full list again, so `import` still validates every cue number.
    with open(os.path.join(dst, "cues.json"), "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False)

    subset = []
    for cue in manifest["cues"]:
        if cue["index"] in wanted:
            subset.append(cue)
    filtered = dict(manifest)
    filtered["cues"] = subset
    made = subs2srt.build_sheets(dst, filtered)

    for name in ("transcripts.json", "verified.json"):
        path = os.path.join(dst, name)
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({}, handle)
    return len(subset), made


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("slugs", nargs="*")
    args = ap.parse_args()
    entries = json.load(open(os.path.join(HERE, "inventory.json"),
                             encoding="utf-8"))
    total_cues = total_sheets = 0
    for entry in entries:
        if entry["truncated"]:
            continue
        slug = entry["slug"]
        if args.slugs and slug not in args.slugs:
            continue
        dst = os.path.join(WORK, slug + ".C.work")
        if os.path.exists(os.path.join(dst, "sheets.json")):
            print("skip %s (already prepared)" % entry["srt_name"])
            continue
        cues, made = prepare(slug)
        if not cues:
            continue
        total_cues += cues
        total_sheets += made
        print("%-42s %4d cues -> %3d sheets" % (entry["srt_name"], cues, made))
    print("\n%d cues, %d sheets to read" % (total_cues, total_sheets))


if __name__ == "__main__":
    main()
