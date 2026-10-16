#!/usr/bin/env python3
"""族語新聞雙語字幕交件：Kari-SRT 的 2-csv-analysis、3-srt-paragraph → 交件資料夾、清單、抽查請求.

    python3 -m scripts.news.paragraph_export --export 2021-01 2021-02
    python3 -m scripts.news.paragraph_export --spot-sample 2021-01 2021-02
    python3 -m scripts.news.paragraph_export --spot-report

`--export` copies, under `--out` (default kithann/out/news/雙語字幕/):

    1-雙語字幕/<年-月>/<成果檔名>.srt   3-srt-paragraph 那份原樣
    2-平行語料/<年-月>/<成果檔名>.csv   2-csv-analysis 那份原樣
    3-雙語字幕清單.csv                  一集一列（不入 Kari-SRT）

The folder names are the ones the reviewers already have from the
第二期第一批 delivery. Nothing is made here: the SRT and the CSV come
from one `pairs_run` pass, and `rebuild --verify` holds both.

`--spot-sample` draws high-confidence groups for an Opus judge
(`scripts/mt/judge_prompt_paragraph.md`, the same request rows as
`pairs_tune`); the judge writes `reply-01.tsv` and `--spot-report`
checks its ids and counts the labels.
"""
import argparse
import collections
import csv
import glob
import os
import random
import shutil
import sys

from scripts.errors import PipelineError
from scripts.mt import load
from scripts.mt import overlap
from scripts.mt import tier
from scripts.mt import tuning
from scripts.news import episodes
from scripts.news import pairs_run
from scripts.news import pairs_tune
from scripts.news import paths
from scripts.srtlib import srt

DROPPED = "不採用"
OUT = os.path.join(paths.NEWS_OUT, "雙語字幕")
SPOT = os.path.join(paths.NEWS_OUT, "雙語字幕-抽查")
SPOT_SIZE = 48
SPOT_SEED = 20261016
SUMMARY_FIELDS = ["成果檔名", "播出日期", "族語別", "語言別代號", "雙語字幕條數",
                  "高信心", "中信心", "不採用", "雙語字幕時長（分）"]
SPOT_FIELDS = ["編號", "成果檔名", "組序", "開始時間", "結束時間"]


def _sec(stamp):
    return srt._parse_ts(stamp)


def summary(entry, rows):
    """One row of 3-雙語字幕清單.csv; minutes are of the CSV's (padded)
    time, the same the delivered SRT shows."""
    count = collections.Counter()
    seconds = 0.0
    for r in rows:
        count[r["信心層級"]] += 1
        if r["信心層級"] != DROPPED:
            seconds += _sec(r["結束時間"]) - _sec(r["開始時間"])
    return {"成果檔名": entry["成果檔名"], "播出日期": entry["播出日期"],
            "族語別": entry["族語別(中)"], "語言別代號": entry["語言別代號"],
            "雙語字幕條數": count["高信心"] + count["中信心"],
            "高信心": count["高信心"], "中信心": count["中信心"],
            "不採用": count[DROPPED],
            "雙語字幕時長（分）": "%.1f" % (seconds / 60.0)}


def _read(path):
    with open(path, encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def pair_files(months):
    found = []
    for month in months:
        found.extend(sorted(glob.glob(os.path.join(paths.PAIRS_DIR, month,
                                                   "*.csv"))))
    if not found:
        raise PipelineError("2-csv-analysis 沒有 %s 的集數" % "、".join(months))
    return found


def _catalogue():
    out = {}
    for entry in episodes.load():
        out[entry["srt_name"]] = entry
    return out


def _name_month(path):
    return (os.path.basename(path)[:-len(".csv")],
            os.path.basename(os.path.dirname(path)))


def export(months, out=OUT):
    """Copy both layers under `out`; returns the summary rows."""
    catalogue = _catalogue()
    rows_out = []
    for path in pair_files(months):
        name, month = _name_month(path)
        if name not in catalogue:
            raise PipelineError("%s 不在節目目錄 smkul.csv" % name)
        subtitles = pairs_run.srt_path(name)
        if not os.path.exists(subtitles):
            raise PipelineError("%s：3-srt-paragraph 沒有這一集，先跑 pairs_run"
                                % name)
        for source, target in (
                (subtitles, os.path.join(out, "1-雙語字幕", month,
                                         name + ".srt")),
                (path, os.path.join(out, "2-平行語料", month, name + ".csv"))):
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copyfile(source, target)
        rows_out.append(summary(catalogue[name], _read(path)))
    with open(os.path.join(out, "3-雙語字幕清單.csv"), "w", encoding="utf-8",
              newline="") as handle:
        writer = csv.DictWriter(handle, SUMMARY_FIELDS, lineterminator="\n")
        writer.writeheader()
        for r in rows_out:
            writer.writerow(r)
    return rows_out


def spot_pick(pool, n, seed=SPOT_SEED, skip=()):
    """[(成果檔名, 組序)]: n high-confidence groups, the same for a seed."""
    candidates = []
    for name in sorted(pool):
        for index, r in enumerate(pool[name]):
            if r["信心層級"] == "高信心" and (name, index) not in skip:
                candidates.append((name, index))
    return random.Random(seed).sample(candidates, min(n, len(candidates)))


def check_span(row, span, name, index, tolerance=0.001):
    """Refuse when the CSV row is not the re-paired group.

    `span` is the padded time -- the one the CSV holds; the true span
    would refuse every CSV made right.
    """
    start, end = span
    if (abs(_sec(row["開始時間"]) - start) > tolerance
            or abs(_sec(row["結束時間"]) - end) > tolerance):
        facts = (name, index, row["開始時間"], row["結束時間"], start, end)
        raise PipelineError(
            "%s 第 %d 組：CSV 是 %s–%s，重算的組是 %.3f–%.3f；先用 "
            "pairs_run 重產" % facts)


def _material(entry, lengths):
    """(groups, padded spans, segments, subtitles) as pairs_run pairs."""
    name = entry["srt_name"]
    with open(paths.stage_path(paths.SAPOLITA_SRT, name, ".srt"),
              encoding="utf-8") as handle:
        segments = load.whisper_segments(handle.read())
    subtitles = load.store_entries(
        paths.stage_path(paths.KARI_CUES, name, ".json"),
        paths.stage_path(paths.KARI_VISION, name), drop_leader=True)
    groups, _segs, _ents = overlap.max_overlap_groups(
        segments, subtitles, straddle_frac=tier.MERGE_FRACTION)
    spans = overlap.padded_spans(groups, segments,
                                 pairs_run.audio_length(name, lengths))
    return groups, spans, segments, subtitles


def write_spot(months, folder=SPOT, n=SPOT_SIZE, seed=SPOT_SEED):
    """sample.csv plus request-01-{a..d}.tsv; returns how many drawn."""
    catalogue = _catalogue()
    lengths = pairs_run.audio_lengths()
    pool = {}
    lines = {}
    skip = set()
    for path in pair_files(months):
        name, _month = _name_month(path)
        rows = _read(path)
        pool[name] = rows
        groups, spans, segments, subtitles = _material(catalogue[name],
                                                       lengths)
        if len(groups) != len(rows):
            facts = (name, len(rows), len(groups))
            raise PipelineError("%s：CSV %d 組、重算 %d 組；先用 pairs_run "
                                "重產" % facts)
        for index, r in enumerate(rows):
            if r["信心層級"] != "高信心":
                continue
            check_span(r, spans[index], name, index)
            group = groups[index]
            line = pairs_tune.request_row(0, group, segments, subtitles)
            if tuning.too_long(line):
                skip.add((name, index))
            lines[(name, index)] = (group, segments, subtitles)
    chosen = spot_pick(pool, n, seed, skip)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "sample.csv"), "w", encoding="utf-8",
              newline="") as handle:
        writer = csv.DictWriter(handle, SPOT_FIELDS, lineterminator="\n")
        writer.writeheader()
        number = 0
        for name, index in chosen:
            number += 1
            r = pool[name][index]
            writer.writerow({"編號": number, "成果檔名": name, "組序": index,
                             "開始時間": r["開始時間"],
                             "結束時間": r["結束時間"]})
    part = -(-len(chosen) // len(pairs_tune.PARTS))
    number = 0
    for offset, letter in enumerate(pairs_tune.PARTS):
        path = os.path.join(folder, "request-01-%s.tsv" % letter)
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(pairs_tune.HEADER + "\n")
            for key in chosen[offset * part:(offset + 1) * part]:
                number += 1
                group, segments, subtitles = lines[key]
                handle.write(pairs_tune.request_row(
                    number, group, segments, subtitles) + "\n")
    return len(chosen)


def spot_report(folder=SPOT):
    """Counter of the judge's labels, after checking the reply's ids."""
    with open(os.path.join(folder, "reply-01.tsv"), encoding="utf-8") as h:
        labels = tuning.ingest(pairs_tune.request_ids(folder, "01"),
                               h.read())
    return collections.Counter(labels.values())


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--export", nargs="+", metavar="年-月")
    ap.add_argument("--spot-sample", nargs="+", metavar="年-月")
    ap.add_argument("--spot-report", action="store_true")
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args(argv)
    if args.export:
        rows = export(args.export, args.out)
        total = collections.Counter()
        for r in rows:
            total["集"] += 1
            total["條"] += r["雙語字幕條數"]
        facts = (total["集"], total["條"], args.out)
        print("寫了 %d 集、%d 條雙語字幕 → %s" % facts)
    if args.spot_sample:
        print("抽了 %d 組 → %s" % (write_spot(args.spot_sample), SPOT))
    if args.spot_report:
        for label, count in sorted(spot_report().items()):
            print("%s\t%d" % (label, count))
    return 0


if __name__ == "__main__":
    sys.exit(main())
