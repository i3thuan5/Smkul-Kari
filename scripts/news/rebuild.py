#!/usr/bin/env python3
"""Rebuild every delivered SRT from Kari-SRT alone, and prove it.

    python3 -m scripts.news.rebuild --verify

This is the executable form of the srt-data-store spec's core guarantee:
main repo (code) + Kari-SRT (news/1-ocr/ 1-cues + 2-vision, plus
news/inventory.json) suffice to rebuild every delivered SRT and
smkul.csv byte-identical to the committed deliverables in
news/1-ocr/3-srt/ -- offline, no video, calling no model. If that
holds, everything under kithann/ really is a regenerable cache.

How it stays byte-identical: it does not reimplement assembly. For each
episode it synthesises a work dir (the timeline copied from Kari-SRT, a
transcripts.json rebuilt from the vision TSVs) and then runs the very same
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

from scripts.news import coaxial
from scripts.news import make_srt
from scripts.news import paths
from scripts.news import tracker
from scripts.errors import PipelineError

SMKUL = "smkul.csv"


def _tsv_lines(path):
    rows = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.rstrip("\n")
            if line.strip():
                rows.append(line)
    return rows


def episode_transcripts(srt_name):
    """transcripts.json content, rebuilt from the episode's vision TSVs."""
    resolved = {}
    folder = paths.stage_path(paths.KARI_VISION, srt_name)
    if os.path.isdir(folder):
        # `b*.tsv` ê 才是視覺辨識ê批（644 个內底 643 个按呢號名）。
        # 賰彼一个 `sample.tsv` sort 起來排佇後壁，會kā彼幾條蓋過
        # 去；舊編號ê時內容拄好仝款所以看袂出來，重新編號了後就
        # 指著別條 cue。`ingest` 彼爿仝款愛限做 `b*.tsv`。
        for path in sorted(glob.glob(os.path.join(folder, "b*.tsv"))):
            for line in _tsv_lines(path):
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
        if not os.path.exists(paths.stage_path(paths.KARI_CUES, name,
                                               ".json")):
            problems.append("missing 1-cues/%s.json" % name)
        if not episode_transcripts(name):
            problems.append("no vision TSVs for %s" % name)
        if not os.path.exists(paths.stage_path(paths.SRT_DIR, name,
                                               ".srt")):
            problems.append("missing delivered 3-srt/%s.srt to compare against"
                            % name)
    return problems


def rebuild_one(entry, tmp):
    """Synthesise a work dir and run the real make_srt over it."""
    name = entry["srt_name"]
    work = os.path.join(tmp, name + ".work")
    os.makedirs(work, exist_ok=True)
    timeline = paths.coarse_cues(work)
    os.makedirs(os.path.dirname(timeline), exist_ok=True)
    shutil.copy2(paths.stage_path(paths.KARI_CUES, name, ".json"), timeline)
    with open(os.path.join(work, "transcripts.json"), "w",
              encoding="utf-8") as handle:
        json.dump(episode_transcripts(name), handle, ensure_ascii=False,
                  indent=2, sort_keys=True)

    out = os.path.join(tmp, "srt", name + ".srt")
    qc = make_srt.run(work, out)
    return tracker.vision_status(qc["srt_lines"])


def _mismatches(tmp, entries):
    """Deliverables whose rebuilt bytes differ from the shipped ones."""
    mismatched = []
    for entry in entries:
        if entry["truncated"] or tracker.is_pending(entry):
            continue
        name = entry["srt_name"] + ".srt"
        built = open(os.path.join(tmp, "srt", name), "rb").read()
        shipped = open(paths.stage_path(paths.SRT_DIR, entry["srt_name"],
                                        ".srt"), "rb").read()
        if built != shipped:
            mismatched.append(name)
    built = open(os.path.join(tmp, "srt", SMKUL), "rb").read()
    shipped = open(paths.TRACKER_STORE, "rb").read()
    if built != shipped:
        mismatched.append(SMKUL)
    return mismatched


def speech_stages():
    """The speech-side deliverables, each with how to rebuild it.

    Imported here rather than at the top because `asrmt_run` reads this
    module (it rebuilds an episode's transcripts the same way): at
    module level the two would import each other while half-built.
    A stage is listed as soon as something can produce it -- what makes
    a stage checkable is a rebuilder, not whether any episode has got
    that far yet.
    """
    from scripts.news import asrmt_run
    return [("2-srt-raw", paths.ASR_RAW, ".srt", asrmt_run.raw_body_of),
            ("3-srt-ai", paths.ASR_AI, ".srt", asrmt_run.ai_body_of)]


def speech_problems(entries):
    """Speech-side deliverables the store cannot rebuild byte for byte.

    Only files that exist: the speech side is its own line and "not made
    yet" is not a defect. See `scripts.news.coaxial`.
    """
    names = []
    for entry in entries:
        if entry["truncated"] or tracker.is_pending(entry):
            continue
        names.append(entry["srt_name"])
    return coaxial.problems(names, speech_stages())


def _delivered_count(entries):
    count = 0
    for entry in entries:
        if not entry["truncated"] and not tracker.is_pending(entry):
            count += 1
    return count


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true",
                    help="byte-compare the rebuild against news/1-ocr/3-srt/")
    args = ap.parse_args()

    entries = paths.load_inventory()
    problems = check_inputs(entries)
    if problems:
        for line in problems:
            print("MISSING:", line)
        raise PipelineError("%d 項輸入袂齊，無重建" % len(problems))

    tmp = tempfile.mkdtemp(prefix="rebuild-")
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
    tracker.write_tracker(rows, os.path.join(tmp, "srt", SMKUL))

    if not args.verify:
        print("\nrebuilt into", tmp)
        return

    drifted = speech_problems(entries)
    if drifted:
        for line in drifted:
            print("REBUILD DIFFERS:", line)
        raise PipelineError(
            "%d 份語音側交付對 store 重建袂出來——重投影閣 render 一擺"
            "（`asrmt_run <集名> --step raw`）；若是講快取內底無彼條，"
            "彼份檔毋是對 store 產出來ê，愛查" % len(drifted))

    mismatched = _mismatches(tmp, entries)
    if mismatched:
        # 留咧予人 diff：這時陣正是需要看輸出ê時陣，刣掉就無通比
        for name in mismatched:
            print("DIFFERS:", name)
        print("\n重建ê結果留佇", tmp)
        raise PipelineError("%d 項佮交付ê無仝" % len(mismatched))
    shutil.rmtree(tmp)
    print("\nOK: %d SRTs + smkul.csv rebuilt byte-identical from Kari-SRT"
          % _delivered_count(entries))


if __name__ == "__main__":
    sys.exit(main())
