#!/usr/bin/env python3
"""Rebuild every delivered SRT from Kari-SRT alone, and prove it.

    python3 -m scripts.news.rebuild --verify
    python3 -m scripts.news.rebuild -o /some/dir      # keep the output

This is the executable form of the srt-data-store spec's core guarantee:
main repo (code) + Kari-SRT (news/1-ocr/ 1-cues + 3-vision + 4-vision-rtf,
plus news/inventory.json) suffice to rebuild every delivered SRT and
smkul.csv byte-identical to the committed deliverables in
news/1-ocr/6-srt/ -- offline, no video, calling no model. If that
holds, everything under kithann/ really is a regenerable cache.

How it stays byte-identical: it does not reimplement assembly. For each
episode it synthesises a work dir (cues.json copied from Kari-SRT, a
transcripts.json rebuilt from the vision TSVs, vision-rtf winning where both
read a cue -- the order ingest applied them in) and then runs the very same
`scripts.news.make_srt` that built the deliverables, followed by the same
tracker-row code make_all uses for smkul.csv.

Any missing input -- an absent cues/<srt_name>.json, an episode with no
TSVs -- is reported by name and exits non-zero before anything is compared.
Nothing incomplete is ever passed off as a rebuilt deliverable.
"""
import argparse
import glob
import json
import os
import shutil
import sys
import tempfile

from scripts.news import make_srt
from scripts.news import paths
from scripts.news import tracker


def episode_transcripts(srt_name):
    """transcripts.json content, rebuilt from the episode's vision TSVs."""
    resolved = {}
    for source in (paths.KARI_VISION, paths.KARI_VISION_RTF):
        folder = os.path.join(source, srt_name)
        if not os.path.isdir(folder):
            continue
        for path in sorted(glob.glob(os.path.join(folder, "*.tsv"))):
            with open(path, encoding="utf-8") as handle:
                for line in handle:
                    line = line.rstrip("\n")
                    if not line.strip():
                        continue
                    parts = line.split("\t")
                    text = parts[2] if len(parts) > 2 else ""
                    resolved[parts[0]] = {"han": text}
    return resolved


def check_inputs(entries):
    problems = []
    for entry in entries:
        # Two ways an episode legitimately has nothing to rebuild: its source
        # was too incomplete to ever subtitle, or it is registered and still
        # being worked on. Both are declarations made in the inventory, so an
        # episode carrying neither is a claim that it was delivered -- and
        # that claim is what the rest of this function checks.
        if entry["truncated"] or tracker.is_pending(entry):
            continue
        name = entry["srt_name"]
        if not os.path.exists(os.path.join(paths.KARI_CUES, name + ".json")):
            problems.append("missing 1-cues/%s.json" % name)
        if not episode_transcripts(name):
            problems.append("no vision TSVs for %s" % name)
        if not os.path.exists(os.path.join(paths.SRT_DIR, name + ".srt")):
            problems.append("missing delivered 6-srt/%s.srt to compare against"
                            % name)
    return problems


def rebuild_one(entry, tmp):
    """Synthesise a work dir and run the real make_srt over it."""
    name = entry["srt_name"]
    work = os.path.join(tmp, name + ".work")
    os.makedirs(work, exist_ok=True)
    shutil.copy2(os.path.join(paths.KARI_CUES, name + ".json"),
                 os.path.join(work, "cues.json"))
    with open(os.path.join(work, "transcripts.json"), "w",
              encoding="utf-8") as handle:
        json.dump(episode_transcripts(name), handle, ensure_ascii=False)

    out = os.path.join(tmp, "srt", name + ".srt")
    qc = make_srt.run(work, out)
    return tracker.vision_status(qc["srt_lines"], qc["cues"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true",
                    help="byte-compare the rebuild against news/1-ocr/6-srt/")
    ap.add_argument("-o", "--out", default="",
                    help="rebuild into this directory instead of a tempdir")
    args = ap.parse_args()

    entries = json.load(open(paths.INVENTORY, encoding="utf-8"))
    problems = check_inputs(entries)
    if problems:
        for line in problems:
            print("MISSING:", line)
        raise SystemExit(1)

    tmp = args.out or tempfile.mkdtemp(prefix="rebuild-")
    os.makedirs(os.path.join(tmp, "srt"), exist_ok=True)

    def status_of(entry):
        if entry["truncated"]:
            status = tracker.skipped_status(entry["truncated"])
        else:
            status = rebuild_one(entry, tmp)
        print("%-46s %s" % (entry["srt_name"], status))
        return status

    for entry in entries:
        if tracker.is_pending(entry):
            print("%-46s %s" % (entry["srt_name"], "略過：本批尚未完成"))
    rows = tracker.tracker_rows(entries, status_of)
    tracker.write_tracker(rows, os.path.join(tmp, "srt", "smkul.csv"))

    if not args.verify:
        print("\nrebuilt into", tmp)
        return 0

    mismatched = []
    for entry in entries:
        if entry["truncated"] or tracker.is_pending(entry):
            continue
        name = entry["srt_name"] + ".srt"
        built = open(os.path.join(tmp, "srt", name), "rb").read()
        shipped = open(os.path.join(paths.SRT_DIR, name), "rb").read()
        if built != shipped:
            mismatched.append(name)
    built = open(os.path.join(tmp, "srt", "smkul.csv"), "rb").read()
    shipped = open(paths.TRACKER_STORE, "rb").read()
    if built != shipped:
        mismatched.append("smkul.csv")

    if not args.out:
        shutil.rmtree(tmp)
    if mismatched:
        for name in mismatched:
            print("DIFFERS:", name)
        raise SystemExit(1)
    built_count = 0
    for entry in entries:
        if not entry["truncated"] and not tracker.is_pending(entry):
            built_count += 1
    print("\nOK: %d SRTs + smkul.csv rebuilt byte-identical from Kari-SRT"
          % built_count)
    return 0


if __name__ == "__main__":
    sys.exit(main())
