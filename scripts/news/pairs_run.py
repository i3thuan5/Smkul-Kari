#!/usr/bin/env python3
"""族華平行語料：sapolita 段落配華語字幕 → 2-平行語料/<年-月>/<成果檔名>.csv

    python3 -m scripts.news.pairs_run                  # 範圍內整批
    python3 -m scripts.news.pairs_run <成果檔名>...     # 只做這幾集
    python3 -m scripts.news.pairs_run --recalibrate    # 先重算校正基準

範圍是 2021-01～10、兩側（`1-ocr/3-srt/` 與 `2-asr-whisper/
1-srt-sapolita/`）都有的集數；只有一側的列出來、不算錯。

每一集是 store 輸入加辭典的純函式，所以重跑逐 byte 相同，`rebuild
--verify` 用同一個 `episode_csv` 重產比對。校正基準只在 `--recalibrate`
時重算——平時重算的話，每加一批，舊集數的分層就跟著變。

不呼叫任何模型：裁判只用在調合併門檻（`pairs_tune.py`）。
"""
import argparse
import os
import sys

from scripts.lexicon import vocab
from scripts.mt import calibration
from scripts.mt import features
from scripts.mt import load
from scripts.mt import overlap
from scripts.mt import pairs
from scripts.mt import tier
from scripts.news import episodes
from scripts.news import lexicon_fetch
from scripts.news import paths

FIRST_MONTH = "2021-01"
LAST_MONTH = "2021-10"


def in_scope(srt_name):
    return FIRST_MONTH <= paths.month_of(srt_name) <= LAST_MONTH


def plan(entries):
    """(todo, skipped): entries with both sides, and (name, why) for the
    ones that have only one. Episodes with neither are not started."""
    todo = []
    skipped = []
    for entry in entries:
        name = entry["srt_name"]
        if not in_scope(name):
            continue
        ocr = os.path.exists(paths.stage_path(paths.SRT_DIR, name, ".srt"))
        asr = os.path.exists(paths.stage_path(paths.SAPOLITA_SRT, name,
                                              ".srt"))
        if ocr and asr:
            todo.append(entry)
        elif ocr:
            skipped.append((name, "缺 sapolita 辨識"))
        elif asr:
            skipped.append((name, "缺交付字幕"))
    return todo, skipped


def _fold(code):
    def fold(word):
        return vocab.fold(word, code)
    return fold


def measured(entry, lexicons, merge=None):
    """(groups, segments, entries, features per group) for one episode."""
    name = entry["srt_name"]
    tribe = entry["族語別(中)"]
    with open(paths.stage_path(paths.SAPOLITA_SRT, name, ".srt"),
              encoding="utf-8") as handle:
        segments = load.whisper_segments(handle.read())
    subtitles = load.store_entries(
        paths.stage_path(paths.KARI_CUES, name, ".json"),
        paths.stage_path(paths.KARI_VISION, name), drop_leader=True)
    if merge is None:
        merge = tier.MERGE_FRACTION
    groups, _lone_segments, _lone_entries = overlap.max_overlap_groups(
        segments, subtitles, straddle_frac=merge)
    feats = []
    for group in groups:
        feats.append(features.group_features(
            group, segments, subtitles, lexicons[tribe],
            fold=_fold(entry["語言別代號"]), lexicons=lexicons, tribe=tribe))
    return groups, segments, subtitles, feats


def opening_samples(entry, lexicons):
    """What calibration.baseline reads from one episode."""
    groups, segments, subtitles, feats = measured(entry, lexicons)
    out = []
    for group, feat in zip(groups, feats):
        start, _end = overlap.span(group, segments, subtitles)
        out.append({"tribe": entry["族語別(中)"], "start": start,
                    "asr_words": feat["asr_words"],
                    "lexicon_rate": feat["lexicon_rate"]})
    return out


def episode_csv(entry, lexicons, table):
    """The delivered CSV text of one episode."""
    name = entry["srt_name"]
    tribe = entry["族語別(中)"]
    baseline = calibration.rate_of(table, tribe, name)
    groups, segments, subtitles, feats = measured(entry, lexicons)
    head = {"族語別": tribe, "語言別代號": entry["語言別代號"],
            "成果檔名": name}
    rows = []
    for group, feat in zip(groups, feats):
        level, reason = tier.classify(
            hallucinated=feat["hallucinated"],
            other_language=feat["foreign"], rate=feat["lexicon_rate"],
            chrf=feat["chrf"], words=feat["asr_words"], baseline=baseline)
        rows.append(pairs.row(head, group, segments, subtitles, feat, level,
                              reason))
    return pairs.render(rows)


def output_path(srt_name):
    return paths.stage_path(paths.PAIRS_DIR, srt_name, ".csv")


def write_calibration(todo, lexicons):
    samples = []
    for entry in todo:
        samples.extend(opening_samples(entry, lexicons))
    calibration.write(calibration.baseline(samples),
                      paths.PAIRS_CALIBRATION)


def run(names=None, recalibrate=False, lexicons=None):
    """([written paths], [(name, why) skipped])."""
    todo, skipped = plan(episodes.load())
    if lexicons is None:
        lexicons = lexicon_fetch.lexicons()
    if recalibrate:
        write_calibration(todo, lexicons)
    table = calibration.read(paths.PAIRS_CALIBRATION)
    wanted = set(names or [])
    written = []
    for entry in todo:
        if wanted and entry["srt_name"] not in wanted:
            continue
        target = output_path(entry["srt_name"])
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8", newline="") as handle:
            handle.write(episode_csv(entry, lexicons, table))
        written.append(target)
    return written, skipped


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("names", nargs="*", help="干焦做這幾集")
    ap.add_argument("--recalibrate", action="store_true",
                    help="先用範圍內全部集數重算校正基準")
    args = ap.parse_args(argv)
    written, skipped = run(args.names, recalibrate=args.recalibrate)
    print("寫了 %d 集" % len(written))
    for name, why in skipped:
        print("跳過：%s（%s）" % (name, why))
    return 0


if __name__ == "__main__":
    sys.exit(main())
