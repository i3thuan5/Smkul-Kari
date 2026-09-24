#!/usr/bin/env python3
"""開會了 through sapolita, for the gold that `sweep.py` grades against.

    python3 -m tools.mtgold.sapolita_aiyalaeho [成果檔名...]

開會了 is not a corpus of this line -- it only supplies the truth -- so
the recognition lands in kithann/out/mt/aiyalaeho-sapolita/, never in
Kari-SRT. One episode at a time (the server is not parallel); episodes
already done are skipped. The 語別碼 is the catalogue's own when the
server knows it, else the news table's per-tribe default (the catalogue
only records 族語級 for most episodes).

Done once on 2026-09-23: 38 of the 39 bilingual episodes; 107 拉阿魯哇
came back with empty text twice.
"""
import csv
import datetime
import os
import sys

from scripts.aiyalaeho import paths as aiya
from scripts.asrmt import sapolita
from scripts.news import audio
from scripts.news import paths
from scripts.news.whisper_run import DEFAULT_SERVER, srt_stats
from tools.mtgold.sweep import ASR_DIR

LOG = os.path.join(ASR_DIR, "辨識紀錄.csv")
LOG_FIELDS = ["成果檔名", "送出語言別代號", "目錄語言別代號", "伺服器",
              "辨識日期", "音長秒", "段數"]


def _fallback_codes():
    table = {}
    with open(paths.NEWS_VARIETIES, encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            table[row["族語別(中)"]] = row["語言別代號"]
    return table


def episodes():
    fallback = _fallback_codes()
    out = []
    with open(aiya.TRACKER_STORE, encoding="utf-8-sig",
              newline="") as handle:
        for row in csv.DictReader(handle):
            code = row["語言別代號"]
            if code not in sapolita.GROUP_OF_CODE:
                code = fallback[row["族語別(中)"]]
            video = os.path.join(aiya.SOURCE,
                                 os.path.basename(row["原始影片檔案位置"]))
            out.append({"srt_name": row["成果檔名"], "code": code,
                        "catalogue_code": row["語言別代號"],
                        "video": video})
    return out


def _now():
    tz = datetime.timezone(datetime.timedelta(hours=8))
    return datetime.datetime.now(tz).strftime("%Y-%m-%d %H:%M")


def _log(row):
    exists = os.path.exists(LOG)
    with open(LOG, "a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, LOG_FIELDS, lineterminator="\n")
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def run(entry):
    name = entry["srt_name"]
    target = os.path.join(ASR_DIR, name + ".srt")
    if os.path.exists(target):
        return "已有"
    if not os.path.exists(entry["video"]):
        return "沒有影片"
    mp3 = os.path.join(ASR_DIR, "tmp", name + ".mp3")
    os.makedirs(os.path.dirname(mp3), exist_ok=True)
    try:
        audio.extract_audio(entry["video"], mp3)
        text = sapolita.recognize(DEFAULT_SERVER, mp3, entry["code"])
        with open(target, "wb") as handle:
            handle.write(text.encode("utf-8"))
        duration, segments = srt_stats(text)
        _log({"成果檔名": name, "送出語言別代號": entry["code"],
              "目錄語言別代號": entry["catalogue_code"],
              "伺服器": DEFAULT_SERVER, "辨識日期": _now(),
              "音長秒": "%.3f" % duration, "段數": str(segments)})
        return "完成 %d 段" % segments
    finally:
        if os.path.exists(mp3):
            os.remove(mp3)


def main(argv=None):
    wanted = set(argv if argv is not None else sys.argv[1:])
    os.makedirs(ASR_DIR, exist_ok=True)
    failed = 0
    for entry in episodes():
        if wanted and entry["srt_name"] not in wanted:
            continue
        try:
            print(entry["srt_name"], run(entry), flush=True)
        except Exception as error:
            failed += 1
            print("失敗：%s（%s）" % (entry["srt_name"], error), flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
