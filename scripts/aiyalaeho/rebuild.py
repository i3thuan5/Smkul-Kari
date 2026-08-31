#!/usr/bin/env python3
"""Rebuild every delivered SRT from the store alone, and prove it.

    python3 -m scripts.aiyalaeho.rebuild --verify

The executable form of the store's core promise: this repo (the code) plus
`Kari-SRT/aiyalaeho/` (`1-ocr/1-cues/` + `1-ocr/2-vision/` +
`inventory.json`) suffice to rebuild every delivered SRT and `smkul.csv`
byte for byte -- offline, without a video, calling no model. If that
holds, everything under `kithann/` really is a cache that can be thrown
away.

How it stays byte-identical: it does not reimplement assembly. For each
episode it synthesises a work dir -- cues.json copied from the store, a
transcripts.json rebuilt from the vision TSVs -- and then runs the very
same `make_srt` that produced the deliverable, followed by the same
tracker code that produced the table.

Any missing input is reported by name and stops the run before anything
is compared. Nothing incomplete is ever passed off as a rebuilt
deliverable.
"""
import argparse
import glob
import json
import os
import shutil
import sys
import tempfile

from scripts.aiyalaeho import make_srt
from scripts.aiyalaeho import paths
from scripts.aiyalaeho import tracker
from scripts.errors import PipelineError

SMKUL = "smkul.csv"

# `b*.tsv` ê 才是視覺辨識ê批——佮 ingest 彼爿仝一條規矩。別ê檔（抽查、
# 筆記）若予 glob 食著，sort 起來排佇後壁ê彼个會kā別人ê字蓋去。
BATCH_GLOB = "b*.tsv"


def _tsv_rows(path):
    rows = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.rstrip("\n")
            if line.strip():
                rows.append(line)
    return rows


def episode_transcripts(srt_name):
    """transcripts.json content, rebuilt from this episode's vision TSVs."""
    folder = paths.stage_path(paths.KARI_VISION, srt_name)
    resolved = {}
    if not os.path.isdir(folder):
        return resolved
    for path in sorted(glob.glob(os.path.join(folder, BATCH_GLOB))):
        for row in _tsv_rows(path):
            parts = row.split("\t")
            while len(parts) < 3:
                parts.append("")
            resolved.setdefault(parts[0], {})[parts[1]] = parts[2]
    return resolved


def _cue_count(srt_name):
    path = paths.stage_path(paths.KARI_CUES, srt_name, ".json")
    with open(path, encoding="utf-8") as handle:
        return len(json.load(handle)["cues"])


def check_inputs(entries):
    """Everything the rebuild needs but cannot find, by name."""
    problems = []
    for entry in entries:
        # A registered episode still being worked on has nothing to
        # rebuild yet, and says so in the inventory. Every other episode
        # is a claim that it was delivered, and that claim is what the
        # rest of this checks.
        if tracker.is_pending(entry):
            continue
        name = entry["srt_name"]
        cues = paths.stage_path(paths.KARI_CUES, name, ".json")
        if not os.path.exists(cues):
            problems.append("揣無 1-cues/%s.json" % name)
            continue
        if _cue_count(name) and not episode_transcripts(name):
            # An episode with no cues has nothing to read, and three of
            # them carry no subtitles at all.
            problems.append("%s 無視覺逐字稿（2-vision/%s/）" % (name, name))
    return problems


def rebuild_one(entry, tmp):
    """Synthesise a work dir and run the real make_srt over it."""
    name = entry["srt_name"]
    work = os.path.join(tmp, name + ".work")
    os.makedirs(work, exist_ok=True)
    shutil.copy2(paths.stage_path(paths.KARI_CUES, name, ".json"),
                 os.path.join(work, "cues.json"))
    with open(os.path.join(work, "transcripts.json"), "w",
              encoding="utf-8") as handle:
        json.dump(episode_transcripts(name), handle, ensure_ascii=False)
    out = os.path.join(tmp, name + ".srt")
    make_srt.run(work, out)
    with open(out, encoding="utf-8") as handle:
        return handle.read()


def rebuild_all():
    """{"srt": {name: body}, "rows": [row…]} -- the whole store, rebuilt."""
    entries = paths.load_inventory()
    problems = check_inputs(entries)
    if problems:
        for line in problems:
            print("MISSING:", line)
        raise PipelineError("%d 項輸入袂齊，無重建" % len(problems))

    tmp = tempfile.mkdtemp(prefix="aiya-rebuild-")
    try:
        bodies = {}
        for entry in entries:
            if tracker.is_pending(entry):
                continue
            bodies[entry["srt_name"]] = rebuild_one(entry, tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return {"srt": bodies, "rows": tracker.tracker_rows(entries)}


def verify():
    """[name…] of deliverables whose bytes differ from the rebuild."""
    built = rebuild_all()
    mismatched = []
    for name in sorted(built["srt"]):
        # 交付品是「比對ê對象」，毋是重建ê輸入——所以無佇 check_inputs
        # 內底問，佇遮無彼支就是「對袂起來」，仝款愛報。
        path = paths.stage_path(paths.SRT_DIR, name, ".srt")
        if not os.path.exists(path):
            mismatched.append(name + ".srt")
            continue
        with open(path, encoding="utf-8") as handle:
            if handle.read() != built["srt"][name]:
                mismatched.append(name + ".srt")

    tmp = tempfile.mkdtemp(prefix="aiya-table-")
    try:
        table = os.path.join(tmp, SMKUL)
        tracker.write_tracker(built["rows"], table)
        with open(table, "rb") as handle:
            rebuilt = handle.read()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    with open(paths.TRACKER_STORE, "rb") as handle:
        if handle.read() != rebuilt:
            mismatched.append(SMKUL)
    return mismatched


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--verify", action="store_true",
                    help="逐 byte 比對重建ê結果佮交付ê")
    args = ap.parse_args(argv)

    if not args.verify:
        built = rebuild_all()
        print("重建 %d 集（無比對；欲比對加 --verify）" % len(built["srt"]))
        return 0

    mismatched = verify()
    if mismatched:
        for name in mismatched:
            print("DIFFERS:", name)
        raise PipelineError("%d 項佮交付ê無仝" % len(mismatched))
    entries = paths.load_inventory()
    print("OK：%d 集ê SRT ＋ smkul.csv 對 Kari-SRT 重建，逐 byte 相仝"
          % len(tracker.tracker_rows(entries)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
