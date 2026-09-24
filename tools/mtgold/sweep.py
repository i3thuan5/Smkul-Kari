#!/usr/bin/env python3
"""The merge threshold scanned on 開會了's gold.

    python3 -m tools.mtgold.sweep     # → kithann/out/mt/調參/開會了掃描.csv

開會了 burns the Formosan line into the picture, so which subtitles a
recognised segment really covers can be read off the words
(`scripts.mt.goldalign`), with no help from the timeline being graded.
Each candidate threshold is scored on that truth.

It is a reference, printed beside the news judging (`pairs_tune.py`),
not the decision: a talk show's recognition is cut into 1～3 s pieces,
news into ~8 s ones. The segments are fused into ≤30 s chunks first to
look more like news, as in the explore phase.

The recognition comes from `sapolita_aiyalaeho.py` (kithann/out/mt/
aiyalaeho-sapolita/). An episode without it is listed, not fatal: 107
拉阿魯哇 came back empty twice.
"""
import csv
import glob
import os
import sys

from scripts.aiyalaeho import paths as aiya
from scripts.mt import evaluate
from scripts.mt import goldalign
from scripts.mt import load
from scripts.mt import overlap
from scripts.mt import textsim
from scripts.news import paths

THRESHOLDS = [None, 0.1, 0.2, 0.3, 0.4, 0.5]
USABLE_RATE = 0.5
CORRECT = 0.8
CHUNK_SECONDS = 30.0
CHUNK_GAP = 1.0
ASR_DIR = os.path.join(paths.KITHANN, "out", "mt", "aiyalaeho-sapolita")
OUT = os.path.join(paths.TUNING_WORK, "開會了掃描.csv")
FIELDS = ["門檻", "組數", "可用組數", "正確組數", "正確率", "詞召回"]


def label(threshold):
    if threshold is None:
        return "不合併"
    return "%d%%" % round(threshold * 100)


def merge_chunks(segments, max_len=CHUNK_SECONDS, max_gap=CHUNK_GAP):
    """Consecutive segments fused into chunks of at most `max_len`."""
    out = []
    for seg in segments:
        if (out and seg["end"] - out[-1]["start"] <= max_len
                and seg["start"] - out[-1]["end"] <= max_gap):
            last = out[-1]
            last["end"] = seg["end"]
            last["formosan"] = (last["formosan"] + " "
                                + seg["formosan"]).strip()
            last["han"] = (last["han"] + " " + seg["han"]).strip()
            continue
        out.append(dict(seg))
    for index, seg in enumerate(out):
        seg["index"] = index
    return out


def _score(segments, entries, threshold, truth, words):
    groups, _, _ = overlap.max_overlap_groups(segments, entries,
                                              straddle_frac=threshold)
    usable = 0
    correct = 0
    recovered = 0
    for group in groups:
        rates = []
        for i in group["segs"]:
            rates.append(truth[i]["match_rate"])
        if min(rates) < USABLE_RATE:
            continue
        usable += 1
        score = evaluate.group_score(group, truth, words)
        if score["precision"] >= CORRECT and score["recall"] >= CORRECT:
            correct += 1
            for i in group["segs"]:
                for _j, (matched, _total) in truth[i]["entries"].items():
                    recovered += matched
    return len(groups), usable, correct, recovered


def sweep(episodes):
    """(rows, missing): one row per threshold over all episodes given as
    (name, segments or None, entries)."""
    totals = {}
    for threshold in THRESHOLDS:
        totals[threshold] = [0, 0, 0, 0]
    gold_words = 0
    missing = []
    for name, segments, entries in episodes:
        if segments is None:
            missing.append(name)
            continue
        chunks = merge_chunks(segments)
        words = {}
        for entry in entries:
            words[entry["index"]] = len(textsim.formosan_words(
                entry["formosan"]))
        truth = {}
        for seg in chunks:
            truth[seg["index"]] = goldalign.gold_cues(seg, entries)
            for _j, (matched, _total) in truth[seg["index"]][
                    "entries"].items():
                gold_words += matched
        for threshold in THRESHOLDS:
            got = _score(chunks, entries, threshold, truth, words)
            for index in range(4):
                totals[threshold][index] += got[index]
    rows = []
    for threshold in THRESHOLDS:
        groups, usable, correct, recovered = totals[threshold]
        rows.append({
            "門檻": label(threshold), "組數": groups, "可用組數": usable,
            "正確組數": correct,
            "正確率": "%.3f" % (correct / usable if usable else 0.0),
            "詞召回": "%.3f" % (recovered / gold_words if gold_words
                             else 0.0),
        })
    return rows, missing


def _episodes():
    out = []
    for path in sorted(glob.glob(os.path.join(aiya.KARI_CUES, "*.json"))):
        name = os.path.basename(path)[:-len(".json")]
        entries = load.store_entries(path, os.path.join(aiya.KARI_VISION,
                                                        name))
        asr = os.path.join(ASR_DIR, name + ".srt")
        segments = None
        if os.path.exists(asr):
            with open(asr, encoding="utf-8") as handle:
                segments = load.whisper_segments(handle.read())
        out.append((name, segments, entries))
    return out


def main():
    rows, missing = sweep(_episodes())
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, FIELDS, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    for row in rows:
        print("  ".join("%s=%s" % (key, row[key]) for key in FIELDS))
    for name in missing:
        print("沒有 sapolita 辨識：%s" % name)
    print("→", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
