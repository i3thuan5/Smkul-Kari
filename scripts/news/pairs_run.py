#!/usr/bin/env python3
"""族華平行語料：sapolita 段落配華語字幕 → 2-csv-analysis/<年-月>/<成果檔名>.csv，
同一輪寫出 3-srt-paragraph/<年-月>/<成果檔名>.srt

    python3 -m scripts.news.pairs_run                  # 整批
    python3 -m scripts.news.pairs_run <成果檔名>...     # 只做這幾集
    python3 -m scripts.news.pairs_run --recalibrate    # 先補校正基準缺的列

做兩側（`1-ocr/3-srt/` 與 `2-asr-whisper/1-srt-sapolita/`）都有的
集數，不限月份；只有一側的列出來、不算錯。

每一集是 store 輸入加辭典的純函式，所以重跑逐 byte 相同，`rebuild
--verify` 用同一個 `episode_files` 重產比對。校正基準只在
`--recalibrate` 時補缺的列，既有的列不動——平時重算的話，每加一批，
舊集數的分層就跟著變。要重算既有的列，先刪表。

辭典：官方 16 族辭典；語言別代號在 `lexicon_fetch.SUPPLEMENTS` 的集
（萬山），本族辭典換成官方該族辭典與 E樂園 該語言別詞表的聯集，校正
基準也另成一列。範圍內沒有這類集時不讀 E樂園。

兩種時間：配對、補洞、校正基準的前 90 秒、特徵都用真實的語音邊界
（`overlap.span`）；只有 CSV 的開始、結束時間是延伸 0.5 秒後的
（`overlap.padded_spans`，鄰居是整集全部語音段），SRT 照抄 CSV。
延伸要夾在音長以內，音長取 `1-srt-sapolita/辨識紀錄.csv`。

不呼叫任何模型：裁判只用在調合併門檻（`pairs_tune.py`）。
"""
import argparse
import csv
import os
import sys

from scripts import languages
from scripts.lexicon import vocab
from scripts.mt import calibration
from scripts.mt import features
from scripts.mt import load
from scripts.mt import overlap
from scripts.mt import pairs
from scripts.mt import paragraph_srt
from scripts.mt import tier
from scripts.news import episodes
from scripts.errors import PipelineError
from scripts.news import lexicon_fetch
from scripts.news import paths


def _sides(srt_name):
    ocr = os.path.exists(paths.stage_path(paths.SRT_DIR, srt_name, ".srt"))
    asr = os.path.exists(paths.stage_path(paths.SAPOLITA_SRT, srt_name,
                                          ".srt"))
    return ocr, asr


def ready(srt_name):
    """Both sides are in: the episode's pairs can be (re)made."""
    ocr, asr = _sides(srt_name)
    return ocr and asr


def plan(entries):
    """(todo, skipped): entries with both sides, and (name, why) for the
    ones that have only one. Episodes with neither are not started."""
    todo = []
    skipped = []
    for entry in entries:
        name = entry["srt_name"]
        ocr, asr = _sides(name)
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


def supplement_codes(entries):
    """The supplemented 語言別代號 these episodes use."""
    found = set()
    for entry in entries:
        if entry["語言別代號"] in lexicon_fetch.SUPPLEMENTS:
            found.add(entry["語言別代號"])
    return found


def dictionaries(entries, lexicons=None, supplements=None):
    """(official lexicons, supplements) for these episodes; E樂園 is read
    only when one of them uses a supplemented variety."""
    if lexicons is None:
        lexicons = lexicon_fetch.lexicons()
    if supplements is None:
        codes = supplement_codes(entries)
        supplements = {}
        if codes:
            supplements = lexicon_fetch.supplements(codes)
    return lexicons, supplements


def episode_lexicons(entry, lexicons, supplements):
    """The 16 tribes as this episode reads them: for a supplemented
    variety, its tribe is the official dictionary plus the variety's
    words -- a union, so the 霧台 speakers in a 萬山 bulletin still count."""
    code = entry["語言別代號"]
    if code not in lexicon_fetch.SUPPLEMENTS:
        return lexicons
    tribe = entry["族語別(中)"]
    out = dict(lexicons)
    out[tribe] = set(lexicons[tribe]) | set(supplements[code])
    return out


def calibration_code(entry):
    """Which baseline row the episode counts towards and reads."""
    code = entry["語言別代號"]
    if code in lexicon_fetch.SUPPLEMENTS:
        return code
    return languages.code_for(entry["族語別(中)"], "")


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
        # the true start: padded, 90.0-90.5 s openings would creep in
        start, _end = overlap.span(group, segments)
        out.append({"tribe": entry["族語別(中)"],
                    "code": calibration_code(entry), "start": start,
                    "asr_words": feat["asr_words"],
                    "lexicon_rate": feat["lexicon_rate"]})
    return out


def audio_lengths(path=None):
    """{成果檔名: 音長秒 text} from the sapolita recognition log."""
    path = path or paths.SAPOLITA_LOG
    out = {}
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            out[row["成果檔名"]] = row.get("音長秒", "")
    return out


def audio_length(name, lengths):
    """The episode's audio length; refuse rather than leave it unclamped."""
    value = (lengths.get(name) or "").strip()
    if not value:
        raise PipelineError("%s：辨識紀錄.csv 沒有音長秒，延伸後的時間夾不了"
                            "音長" % name)
    return float(value)


def episode_files(entry, lexicons, table, lengths):
    """(CSV text, SRT text) of one episode, from one pairing."""
    name = entry["srt_name"]
    tribe = entry["族語別(中)"]
    baseline = calibration.rate_of(table, tribe, entry["語言別代號"], name)
    duration = audio_length(name, lengths)
    groups, segments, subtitles, feats = measured(entry, lexicons)
    try:
        spans = overlap.padded_spans(groups, segments, duration)
    except PipelineError as error:
        raise PipelineError("%s：%s" % (name, error))
    head = {"族語別": tribe, "語言別代號": entry["語言別代號"],
            "成果檔名": name}
    rows = []
    for group, feat, padded in zip(groups, feats, spans):
        level, reason = tier.classify(
            hallucinated=feat["hallucinated"],
            other_language=feat["foreign"], rate=feat["lexicon_rate"],
            chrf=feat["chrf"], words=feat["asr_words"], baseline=baseline)
        rows.append(pairs.row(head, group, segments, subtitles, feat, level,
                              reason, padded))
    return pairs.render(rows), paragraph_srt.render(rows)


def output_path(srt_name):
    return paths.stage_path(paths.PAIRS_DIR, srt_name, ".csv")


def srt_path(srt_name):
    return paths.stage_path(paths.PARAGRAPH_SRT, srt_name, ".srt")


def refuse_legacy_dir():
    """Two copies of the layer must not live side by side."""
    if os.path.exists(paths.LEGACY_PAIRS_DIR):
        raise PipelineError(
            "舊目錄 %s 還在：平行語料已改名 2-csv-analysis，先把舊目錄搬走或"
            "刪掉（可能是平行 session 用舊程式寫的）" % paths.LEGACY_PAIRS_DIR)


def write_calibration(todo, lexicons, supplements):
    """Fill the rows the table lacks; the rows it has stay as they are."""
    samples = []
    for entry in todo:
        samples.extend(opening_samples(
            entry, episode_lexicons(entry, lexicons, supplements)))
    old = {}
    if os.path.exists(paths.PAIRS_CALIBRATION):
        old = calibration.read(paths.PAIRS_CALIBRATION)
    calibration.write(
        calibration.fill_missing(old, calibration.baseline(samples)),
        paths.PAIRS_CALIBRATION)


def run(names=None, recalibrate=False, lexicons=None, supplements=None):
    """([written CSV paths], [(name, why) skipped])."""
    refuse_legacy_dir()
    todo, skipped = plan(episodes.load())
    lexicons, supplements = dictionaries(todo, lexicons, supplements)
    if recalibrate:
        write_calibration(todo, lexicons, supplements)
    table = calibration.read(paths.PAIRS_CALIBRATION)
    lengths = audio_lengths()
    wanted = set(names or [])
    written = []
    for entry in todo:
        name = entry["srt_name"]
        if wanted and name not in wanted:
            continue
        csv_text, srt_text = episode_files(
            entry, episode_lexicons(entry, lexicons, supplements), table,
            lengths)
        for target, text in ((output_path(name), csv_text),
                             (srt_path(name), srt_text)):
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "w", encoding="utf-8", newline="") as handle:
                handle.write(text)
        written.append(output_path(name))
    return written, skipped


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("names", nargs="*", help="干焦做這幾集")
    ap.add_argument("--recalibrate", action="store_true",
                    help="先補校正基準表缺的列（既有的列不動）")
    args = ap.parse_args(argv)
    written, skipped = run(args.names, recalibrate=args.recalibrate)
    print("寫了 %d 集" % len(written))
    for name, why in skipped:
        print("跳過：%s（%s）" % (name, why))
    return 0


if __name__ == "__main__":
    sys.exit(main())
