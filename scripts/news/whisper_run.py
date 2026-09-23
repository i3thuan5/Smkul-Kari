#!/usr/bin/env python3
"""Every episode through sapolita (whisper 族語辨識): audio -> raw SRT.

    python3 -m scripts.news.whisper_run [<成果檔名>...] [--server URL]
                                        [--limit N]

Per episode: take the audio (`scripts.news.audio`, shared with kaldi),
決定送 sapolita 的語別碼（`scripts/news/新聞語言別代號.csv`），辨識
（`scripts.asrmt.sapolita`），把伺服器回傳的文字**原樣**存做 SRT，寫
一列辨識紀錄，刪暫存音檔。一次只送一集——伺服器不可平行。

沒有名字時做整批，跳過已經做完的集（SRT 佮辨識紀錄兩者都在才算做
完）；帶名字時只做那幾集，即使已經做完也重做（讓使用者能挑出特定
集數重跑）。
"""
import argparse
import csv
import datetime
import glob
import os
import re
import sys

from scripts.asrmt import sapolita
from scripts.news import audio
from scripts.news import episodes
from scripts.news import paths
from scripts.srtlib import srt as srtlib
from scripts import languages
from scripts import lowpri
from scripts.errors import PipelineError

DEFAULT_SERVER = "https://ai-labs.ilrdf.org.tw/sapolita/"

LOG_FIELDS = [
    "成果檔名", "語言別代號", "主播名", "伺服器", "辨識日期",
    "音長秒", "段數"]

# 開場自我介紹只出現在片頭幾條；15 是抽聽階段量到族語新聞開場最長
# 也不過 4 條字幕就報完名字，留一截餘裕。
ANCHOR_WINDOW = 15
ANCHOR_RE = re.compile(r"我是(.+)")

UNKNOWN_ANCHOR = "不明"


# ------------------------------------------------------------- 語別碼


def _read_varieties(path=None):
    path = path or paths.NEWS_VARIETIES
    table = {}
    with open(path, encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            table[row["族語別(中)"]] = row["語言別代號"]
    return table


def code_for(entry, variety_path=None):
    """這集送 sapolita 的語別碼，查 `新聞語言別代號.csv`。

    鍵是節目目錄的 `族語別(中)`，不是既有的 `語言別代號`——後者對
    多語別的族只記到族語別（`ami`），而賽德克（`trv`）跟太魯閣
    （`trv-x-truku`）前綴相同，用前綴查會混淆兩族。
    """
    name = entry["srt_name"]
    family = entry["族語別(中)"]
    table = _read_varieties(variety_path)
    if family not in table:
        raise PipelineError(
            "%s：新聞語言別代號.csv 無 %r 這族，袂使送出" % (name, family))
    code = table[family]
    try:
        languages.language_of(code)
    except PipelineError:
        raise PipelineError(
            "%s：新聞語言別代號.csv 的代號 %r（%s）查無族語別／語言別"
            "代號對照表，袂使送出" % (name, code, family))
    return code


# --------------------------------------------------------------- SRT


def write_srt(srt_name, text, srt_dir=None):
    """存伺服器回傳的文字，逐 byte 原樣：不重排、不加留白、不補換行。"""
    path = paths.stage_path(srt_dir or paths.SAPOLITA_SRT, srt_name, ".srt")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(text.encode("utf-8"))
    return path


def srt_stats(text):
    """(音長秒, 段數)，對回傳文字唯讀解析——存檔本身不經過這條路。"""
    entries = srtlib.parse_srt(text)
    if not entries:
        return 0.0, 0
    duration = 0.0
    for _start, end, _text in entries:
        duration = max(duration, end)
    return duration, len(entries)


# ------------------------------------------------------------- 主播名


def anchor_name(srt_name, vision_dir=None):
    """這集 OCR 字幕開頭「我是…」後面的文字；查無就「不明」。"""
    folder = paths.stage_path(vision_dir or paths.KARI_VISION, srt_name)
    if not os.path.isdir(folder):
        return UNKNOWN_ANCHOR
    lines = []
    for path in sorted(glob.glob(os.path.join(folder, "b*.tsv"))):
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                parts = line.rstrip("\n").split("\t")
                if len(parts) >= 3 and parts[0].isdigit():
                    lines.append((int(parts[0]), parts[2]))
    lines.sort()
    for _index, text in lines[:ANCHOR_WINDOW]:
        match = ANCHOR_RE.search(text)
        if match:
            return match.group(1).strip()
    return UNKNOWN_ANCHOR


# --------------------------------------------------------------- 紀錄


def _read_log(path=None):
    path = path or paths.SAPOLITA_LOG
    rows = {}
    if not os.path.exists(path):
        return rows
    with open(path, encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            rows[row["成果檔名"]] = row
    return rows


def _write_log(rows, path=None):
    path = path or paths.SAPOLITA_LOG
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, LOG_FIELDS, lineterminator="\n")
        writer.writeheader()
        for name in sorted(rows):
            writer.writerow(rows[name])


def record_row(srt_name, code, anchor, server, when, duration, segments,
               log_path=None):
    """寫（抑是覆寫）辨識紀錄的一列；列序照成果檔名排序。"""
    rows = _read_log(log_path)
    rows[srt_name] = {
        "成果檔名": srt_name, "語言別代號": code, "主播名": anchor,
        "伺服器": server, "辨識日期": when,
        "音長秒": "%.3f" % duration, "段數": str(segments),
    }
    _write_log(rows, log_path)


def is_done(srt_name, srt_dir=None, log_path=None):
    """SRT 佮紀錄列**兩者都在**才算做完——只有一邊是中途被打斷。"""
    path = paths.stage_path(srt_dir or paths.SAPOLITA_SRT, srt_name, ".srt")
    if not os.path.exists(path):
        return False
    return srt_name in _read_log(log_path)


def todo(entries, srt_dir=None, log_path=None):
    out = []
    for entry in entries:
        if not is_done(entry["srt_name"], srt_dir, log_path):
            out.append(entry)
    return out


# --------------------------------------------------------------- 逐集


def _now_cst():
    tz = datetime.timezone(datetime.timedelta(hours=8))
    return datetime.datetime.now(tz).strftime("%Y-%m-%d %H:%M")


def _audio_tmp_path(srt_name, work_dir=None):
    return paths.stage_path(work_dir or paths.WHISPER_WORK, srt_name,
                            ".mp3")


def run_episode(entry, server, recognize=None, audio_get=None,
                vision_dir=None, variety_path=None, srt_dir=None,
                log_path=None, work_dir=None, now=None):
    """一集：取音檔 → 查語別碼 → 辨識 → 原樣存 SRT → 寫紀錄 → 刪暫存。

    失敗（伺服器出錯、語別碼查無）時 SHALL NOT 留下 SRT 或紀錄列；
    暫存音檔不論成敗都清掉。
    """
    recognize = recognize or sapolita.recognize
    audio_get = audio_get or audio.get_audio
    now = now or _now_cst
    name = entry["srt_name"]
    code = code_for(entry, variety_path)
    mp3 = _audio_tmp_path(name, work_dir)
    os.makedirs(os.path.dirname(mp3), exist_ok=True)
    try:
        audio_get(entry, mp3)
        text = recognize(server, mp3, code)
        write_srt(name, text, srt_dir)
        anchor = anchor_name(name, vision_dir)
        duration, segments = srt_stats(text)
        record_row(
            name, code, anchor, server, now(), duration, segments,
            log_path)
    finally:
        if os.path.exists(mp3):
            os.remove(mp3)


def run_batch(entries, server, **kwargs):
    """依序（一次一集）跑完這批；一集失敗記下、繼續下一集。"""
    done = []
    failed = []
    for entry in entries:
        name = entry["srt_name"]
        print("==", name, flush=True)
        try:
            run_episode(entry, server, **kwargs)
            done.append(name)
        except PipelineError as error:
            failed.append((name, str(error)))
            print("FAILED:", name, "--", error, flush=True)
    return done, failed


def main(argv=None):
    lowpri.be_nice()   # 長時間ê重工，莫kā機器食牢去
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("names", nargs="*",
                    help="干焦做這幾集（無名字就整批、跳過做過ê）")
    ap.add_argument("--server", default=DEFAULT_SERVER)
    ap.add_argument("--limit", type=int, default=0,
                    help="stop after N episodes (0 = all)")
    args = ap.parse_args(argv)

    entries = episodes.load()
    if args.names:
        wanted = set(args.names)
        queue = []
        for entry in entries:
            if entry["srt_name"] in wanted:
                queue.append(entry)
    else:
        queue = todo(entries)
    if args.limit:
        queue = queue[:args.limit]

    done, failed = run_batch(queue, args.server)

    print("\n完成 %d 集" % len(done))
    for name, why in failed:
        print("失敗：%s（%s）" % (name, why))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
