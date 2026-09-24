#!/usr/bin/env python3
"""目錄語別標毋著：改目錄那一列，store 內底仝一集ê檔綴咧改名抑刪掉。

    python3 -m scripts.news.relabel <成果檔名> <族語別(中)> --reason "…"

片頭辨識（`opening ingest`）讀著ê語別牌佮目錄無仝，查過確定是目錄標
毋著，就用這支改。目錄一改，成果檔名就換（族語別佇名內底），store 內底
逐階段ê檔若無綴咧改，就變孤兒檔，`rebuild --verify` 會擋。

- 佮語別無關ê：時間軸（1-cues）、讀者逐字稿（2-vision）、交付 SRT
  （3-srt）、段落表（0-segments）、片頭辨識那一列 → **改名**，內容無動。
- 用毋著ê語言做出來ê：whisper SRT 佮辨識紀錄那一列、平行語料、kaldi
  各階段 → **刪掉**，印出愛重跑ê指令。改名留咧，就是用排灣語辨識卑南語
  ê結果頂替正確ê。

逐个目標攏先檢查無存在才開始搬，一个衝突就規个停，毋會搬一半。
"""
import argparse
import collections
import csv
import os
import shutil
import sys

from scripts import catalogue_checks as checks
from scripts import languages
from scripts.errors import PipelineError
from scripts.news import name_catalogue
from scripts.news import paths

Report = collections.namedtuple("Report", "renamed removed")

# (store 內ê相對目錄, 副檔名)；副檔名空字串是逐集一个資料夾。
RENAME = (("1-ocr/1-cues", ".json"), ("1-ocr/2-vision", ""),
          ("1-ocr/3-srt", ".srt"), ("1-ocr/0-segments", ".csv"))
REMOVE = (("2-asr-whisper/1-srt-sapolita", ".srt"),
          ("2-asr-whisper/2-平行語料", ".csv"),
          ("2-asr-kaldi/1-words", ".json"), ("2-asr-kaldi/2-srt-raw", ".srt"),
          ("2-asr-kaldi/3-srt-ai", ".srt"),
          ("2-asr-kaldi/4-srt-quality", ".srt"))


def relabel_row(row, chinese, reason):
    """目錄一列換做 `chinese` 這族：族語別、代號、成果檔名、備註。"""
    english = languages.english_for(chinese)
    out = dict(row)
    old = row["族語別(中)"]
    out["族語別(英)"] = english
    out["族語別(中)"] = chinese
    out["語言別"] = ""
    out["語言別代號"] = languages.code_for(chinese, "")
    out["成果檔名"] = checks.srt_name_of(out)
    note = "族語別本底標 %s，改 %s：%s" % (old, chinese, reason)
    out["備註"] = (row.get("備註") or "").strip()
    out["備註"] = (out["備註"] + "；" + note) if out["備註"] else note
    return out


def _stage(store, rel, name, ext):
    return os.path.join(store, rel, paths.month_of(name), name + ext)


def move_store(old, new, chinese, store=None):
    """store 內 `old` 這集ê檔：佮語別無關ê改名 `new`，其他ê刪掉。"""
    store = store or paths.NEWS_STORE
    moves = []
    for rel, ext in RENAME:
        source = _stage(store, rel, old, ext)
        if os.path.exists(source):
            target = _stage(store, rel, new, ext)
            if os.path.exists(target):
                raise PipelineError("%s 已經有 %s，無搬任何物件" % (rel, new))
            moves.append((source, target))
    for source, target in moves:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        os.rename(source, target)
    removed = []
    for rel, ext in REMOVE:
        path = _stage(store, rel, old, ext)
        if os.path.isdir(path):
            shutil.rmtree(path)
            removed.append(path)
        elif os.path.exists(path):
            os.remove(path)
            removed.append(path)
    log = os.path.join(store, "2-asr-whisper/1-srt-sapolita/辨識紀錄.csv")
    if _drop_row(log, old):
        removed.append(log + "（" + old + " 那列）")
    _rename_opening(os.path.join(store, "1-ocr/片頭辨識.csv"), old, new,
                    chinese)
    renamed = []
    for _source, target in moves:
        renamed.append(target)
    return Report(renamed, removed)


def _read(path):
    with open(path, encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader), list(reader.fieldnames or [])


def _write(path, rows, head):
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, head, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _drop_row(path, name):
    if not os.path.exists(path):
        return False
    rows, head = _read(path)
    kept = []
    for row in rows:
        if row["成果檔名"] != name:
            kept.append(row)
    if len(kept) == len(rows):
        return False
    _write(path, kept, head)
    return True


def _rename_opening(path, old, new, chinese):
    if not os.path.exists(path):
        return
    rows, head = _read(path)
    for row in rows:
        if row["成果檔名"] == old:
            row["成果檔名"] = new
            if row["畫面語別牌"] == chinese:
                row["與目錄相符"] = "是"
    rows.sort(key=lambda row: row["成果檔名"])
    _write(path, rows, head)


def relabel(name, chinese, reason, catalogue=None):
    """改目錄（照成果檔名重排）、搬 store；回 (新成果檔名, Report)。"""
    target = catalogue or paths.TRACKER_STORE
    rows, head = name_catalogue.read(target)
    found = None
    for index, row in enumerate(rows):
        if row["成果檔名"] == name:
            found = index
    if found is None:
        raise PipelineError("目錄內底無 %s" % name)
    new_row = relabel_row(rows[found], chinese, reason)
    new = new_row["成果檔名"]
    report = move_store(name, new, chinese)
    rows[found] = new_row
    rows.sort(key=lambda row: row["成果檔名"])
    name_catalogue.write(target, rows, head)
    return new, report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("name", help="目前ê成果檔名")
    ap.add_argument("language", help="正確ê族語別（中文）")
    ap.add_argument("--reason", required=True, help="寫入備註ê依據")
    args = ap.parse_args(argv)
    new, report = relabel(args.name, args.language, args.reason)
    print("%s → %s" % (args.name, new))
    for path in report.renamed:
        print("改名  %s" % path)
    for path in report.removed:
        print("刪掉  %s" % path)
    print("next: whisper 重跑 `python3 -m scripts.news.whisper_run %s`，"
          "平行語料重做，然後 rebuild --verify、name_catalogue --check" % new)
    return 0


if __name__ == "__main__":
    sys.exit(main())
