#!/usr/bin/env python3
"""調合併門檻：抽新聞樣本給 Claude 裁判、收回覆、出比例表。

    python3 -m scripts.news.pairs_tune --sample          # 抽樣、寫請求檔
    python3 -m scripts.news.pairs_tune --ingest 03       # 收第 03 批回覆
    python3 -m scripts.news.pairs_tune --report          # 各格比例與選值

The method is in `scripts.mt.tuning`. Everything lands in
kithann/out/mt/調參/ (`paths.TUNING_WORK`): the deliverables do not
depend on it, so none of it enters Kari-SRT; the chosen value and the
table go into 2-平行語料/README.md by hand.

Each batch is four request files of 50 rows (`request-NN-{a,b,c,d}.tsv`)
because a 200-row file is past what the Read tool takes in one go; the
judge (an Opus subagent reading `scripts/mt/judge_prompt_paragraph.md`)
answers with one `reply-NN.tsv`. `--ingest` checks the ids and copies an
accepted reply into `accepted/`; only those are reported.
"""
import argparse
import csv
import glob
import os
import random
import shutil
import sys

from scripts.asrmt import judge
from scripts.mt import load
from scripts.mt import textsim
from scripts.mt import tuning
from scripts.news import episodes
from scripts.news import pairs_run
from scripts.news import paths

PER_BUCKET = 97
SEED = 20260924
PARTS = "abcd"
HEADER = ("編號\t族語ASR結果\t華語OCR字幕\t族語ASR結果翻譯華語-sapolita"
          "\t前一組的華語字幕\t後一組的華語字幕")
SAMPLE_FIELDS = ["編號", "版本", "成果檔名", "邊界", "格", "較少邊比例",
                 "族語詞數"]
PROMPT = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "mt", "judge_prompt_paragraph.md")


def _flat(text):
    return text.replace("\t", " ").replace("\n", " ").strip()


def _side(texts):
    return "｜".join(_flat(t) for t in texts if t.strip())


def request_row(number, group, segments, entries):
    """One TSV line of the judge's request for a group."""
    formosan = " ".join(segments[i]["formosan"] for i in group["segs"])
    mt = []
    canned = 0
    for i in group["segs"]:
        mt.append(segments[i]["han"])
        if judge.is_gloss(segments[i]["han"]):
            canned += 1
    mt_text = _side(mt)
    if canned:
        mt_text += "　（有 %d 段疑似罐頭譯文）" % canned
    subtitles = []
    for j in group["entries"]:
        subtitles.append(entries[j]["han"])
    first = min(group["entries"])
    last = max(group["entries"])
    before = entries[first - 1]["han"] if first > 0 else ""
    after = entries[last + 1]["han"] if last + 1 < len(entries) else ""
    return "\t".join([str(number), _flat(formosan), _side(subtitles),
                      mt_text, _flat(before), _flat(after)])


def _words(group, segments):
    text = " ".join(segments[i]["formosan"] for i in group["segs"])
    return len(textsim.formosan_words(text))


def _episode_material(entry):
    name = entry["srt_name"]
    with open(paths.stage_path(paths.SAPOLITA_SRT, name, ".srt"),
              encoding="utf-8") as handle:
        segments = load.whisper_segments(handle.read())
    subtitles = load.store_entries(
        paths.stage_path(paths.KARI_CUES, name, ".json"),
        paths.stage_path(paths.KARI_VISION, name), drop_leader=True)
    return segments, subtitles


def pool():
    """Every straddled location in scope whose rows fit the Read tool."""
    todo, _skipped = pairs_run.plan(episodes.load())
    found = []
    for entry in todo:
        segments, subtitles = _episode_material(entry)
        for loc in tuning.locations(segments, subtitles):
            fits = True
            for group in tuning.versions(loc):
                if group is None:
                    continue
                if tuning.too_long(request_row(0, group, segments,
                                               subtitles)):
                    fits = False
            if fits:
                found.append({"key": (entry["srt_name"], loc["boundary"]),
                              "bucket": loc["bucket"],
                              "share": loc["share"], "entry": entry})
    return found


def write_sample(folder, per_bucket=PER_BUCKET, seed=SEED):
    """Draw the sample and write sample.csv plus the request files."""
    chosen, short = tuning.sample(pool(), per_bucket, seed)
    os.makedirs(folder, exist_ok=True)
    material = {}
    items = []
    rows = {}
    number = 0
    for pick in chosen:
        name, boundary = pick["key"]
        if name not in material:
            material[name] = _episode_material(pick["entry"])
        segments, subtitles = material[name]
        loc = None
        for candidate in tuning.locations(segments, subtitles):
            if candidate["boundary"] == boundary:
                loc = candidate
        for kind, group in zip("GAB", tuning.versions(loc)):
            if group is None:
                continue
            number += 1
            items.append({"id": number, "kind": kind})
            rows[number] = {
                "編號": number, "版本": kind, "成果檔名": name,
                "邊界": boundary, "格": pick["bucket"],
                "較少邊比例": "%.3f" % pick["share"],
                "族語詞數": _words(group, segments),
                "line": request_row(number, group, segments, subtitles)}
    random.Random(seed).shuffle(items)
    with open(os.path.join(folder, "sample.csv"), "w", encoding="utf-8",
              newline="") as handle:
        writer = csv.DictWriter(handle, SAMPLE_FIELDS, lineterminator="\n",
                                extrasaction="ignore")
        writer.writeheader()
        for key in sorted(rows):
            writer.writerow(rows[key])
    for index, batch in enumerate(tuning.batches(items), 1):
        for letter, part in zip(PARTS, batch):
            path = os.path.join(folder, "request-%02d-%s.tsv"
                                % (index, letter))
            with open(path, "w", encoding="utf-8", newline="") as handle:
                handle.write(HEADER + "\n")
                for item in part:
                    handle.write(rows[item["id"]]["line"] + "\n")
    return len(chosen), short


def request_ids(folder, number):
    ids = []
    for path in sorted(glob.glob(os.path.join(
            folder, "request-%s-*.tsv" % number))):
        with open(path, encoding="utf-8") as handle:
            for line in list(handle)[1:]:
                if line.strip():
                    ids.append(int(line.split("\t")[0]))
    return ids


def accept(folder, number):
    """Check reply-NN against its requests; copy it to accepted/."""
    reply = os.path.join(folder, "reply-%s.tsv" % number)
    with open(reply, encoding="utf-8") as handle:
        text = handle.read()
    tuning.ingest(request_ids(folder, number), text)
    target = os.path.join(folder, "accepted", "reply-%s.tsv" % number)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    shutil.copyfile(reply, target)
    return target


def _labels(folder):
    found = {}
    for path in sorted(glob.glob(os.path.join(folder, "accepted",
                                              "reply-*.tsv"))):
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                parts = line.rstrip("\n").split("\t")
                if len(parts) >= 2 and parts[0].strip().isdigit():
                    found[int(parts[0])] = parts[1].strip()
    return found


def report(folder):
    """([row per bucket], chosen threshold or None)."""
    labels = _labels(folder)
    places = {}
    with open(os.path.join(folder, "sample.csv"), encoding="utf-8",
              newline="") as handle:
        for row in csv.DictReader(handle):
            key = (row["成果檔名"], int(row["邊界"]))
            place = places.setdefault(key, {"bucket": int(row["格"])})
            place[row["版本"]] = (int(row["編號"]), int(row["族語詞數"]))
    tally = {}
    for bucket in range(tuning.BUCKETS):
        tally[bucket] = {tuning.MERGE_BETTER: 0, tuning.SPLIT_BETTER: 0,
                         tuning.SAME: 0, "未收齊": 0}
    for place in places.values():
        judged = {}
        complete = True
        for kind in "GAB":
            if kind not in place:
                judged[kind] = None
                continue
            number, words = place[kind]
            if number not in labels:
                complete = False
                break
            judged[kind] = (labels[number], words)
        if not complete:
            tally[place["bucket"]]["未收齊"] += 1
            continue
        tally[place["bucket"]][tuning.outcome(
            judged["G"], judged["A"], judged["B"])] += 1
    rows = []
    verdicts = {}
    for bucket in range(tuning.BUCKETS):
        counts = tally[bucket]
        better = counts[tuning.MERGE_BETTER]
        worse = counts[tuning.SPLIT_BETTER]
        low, high = tuning.wilson(better, better + worse)
        verdicts[bucket] = tuning.verdict(better, worse)
        rows.append({
            "格": "%d–%d%%" % (bucket * 10, bucket * 10 + 10),
            tuning.MERGE_BETTER: better, tuning.SPLIT_BETTER: worse,
            tuning.SAME: counts[tuning.SAME], "未收齊": counts["未收齊"],
            "區間下": "%.3f" % low, "區間上": "%.3f" % high,
            "判定": verdicts[bucket]})
    return rows, tuning.choose(verdicts)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sample", action="store_true")
    ap.add_argument("--ingest", metavar="NN")
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args(argv)
    folder = paths.TUNING_WORK
    if args.sample:
        count, short = write_sample(folder)
        print("抽了 %d 處；不足 %d 處的格：%s"
              % (count, PER_BUCKET, short or "無"))
        print("判準：%s" % PROMPT)
    if args.ingest:
        print("收下：%s" % accept(folder, args.ingest))
    if args.report:
        rows, chosen = report(folder)
        fields = ["格", tuning.MERGE_BETTER, tuning.SPLIT_BETTER, tuning.SAME,
                  "未收齊", "區間下", "區間上", "判定"]
        with open(os.path.join(folder, "結果.csv"), "w", encoding="utf-8",
                  newline="") as handle:
            writer = csv.DictWriter(handle, fields, lineterminator="\n")
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
        for row in rows:
            print("  ".join("%s=%s" % (k, row[k]) for k in fields))
        if chosen is None:
            print("選定的合併門檻：不合併")
        else:
            print("選定的合併門檻：%d%%" % round(chosen * 100))
    return 0


if __name__ == "__main__":
    sys.exit(main())
