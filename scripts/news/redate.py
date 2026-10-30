#!/usr/bin/env python3
"""目錄那一集ê播出日期、集數標毋著：改目錄那一列，store 內底仝一集ê檔綴咧改名。

    python3 -m scripts.news.redate <成果檔名> <播出日期> <集數> --reason "…"

2026-10-29：`20240930_274_晚間_Amis_阿美` 用ê是 `20241001S2000.mkv`，OCR
內容（台9線崇德土石流、山陀兒颱風來襲）佮檔名攏是 10-01，毋是 09-30。
成果檔名內底有日期佮集數，目錄一改名就換，store 逐階段ê檔若無綴咧改，
就變孤兒檔，`rebuild --verify` 會擋。

佮 `relabel`（語別標毋著）相反：內容猶是仝一集、語言毋曾改，所以 whisper
辨識結果、平行語料、kaldi 各階段**攏是對ê，逐階段全部改名，一个都毋刪**。
跨月（09 → 10）ê時，月份資料夾嘛換。

逐个目標攏先檢查無存在才開始搬，一个衝突就規个停，毋會搬一半。
"""
import argparse
import datetime
import os
import re
import sys

from scripts import catalogue_checks as checks
from scripts.errors import PipelineError
from scripts.news import name_catalogue
from scripts.news import paths
from scripts.news import relabel

DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# 有成果檔名ê逐列紀錄表（store 內底ê相對路徑）。
LOGS = ("1-ocr/片頭辨識.csv", "2-asr-whisper/1-srt-sapolita/辨識紀錄.csv",
        "1-ocr/訂正紀錄.csv")


def redate_row(row, date, episode, reason):
    """目錄一列換做 `date` 第 `episode` 集：年度、集數、播出日期、節目名稱、成果檔名、備註。"""
    if not DATE.match(date or ""):
        raise PipelineError("播出日期愛寫 YYYY-MM-DD：%r" % date)
    try:
        datetime.date.fromisoformat(date)
    except ValueError:
        raise PipelineError("無這个日期：%r" % date)
    out = dict(row)
    out["年度"] = date[:4]
    out["集數"] = str(int(episode))
    out["播出日期"] = date
    # 跨過改名生效日（2024-08-01）ê時節目名稱嘛愛換，無就會予日期對照
    # 檢查擋落來。
    out["節目名稱"] = checks.programme_for(
        checks.slot_of(row["節目名稱"]), date)
    out["成果檔名"] = checks.srt_name_of(out)
    note = "播出日期本底標 %s（第 %s 集），改 %s（第 %s 集）：%s" % (
        row["播出日期"], int(row["集數"]), date, int(episode), reason)
    out["備註"] = (row.get("備註") or "").strip()
    out["備註"] = (out["備註"] + "；" + note) if out["備註"] else note
    return out


def _rename_rows(path, old, new):
    """紀錄表內底 `old` 那列改 `new`；原本就照名排好ê，改了嘛照名排。"""
    if not os.path.exists(path):
        return False
    rows, head = relabel._read(path)
    names = []
    for row in rows:
        names.append(row.get("成果檔名", ""))
    was_sorted = names == sorted(names)
    found = False
    for row in rows:
        if row.get("成果檔名") == old:
            row["成果檔名"] = new
            found = True
    if not found:
        return False
    if was_sorted:
        rows.sort(key=lambda row: row["成果檔名"])
    relabel._write(path, rows, head)
    return True


def move_store(old, new, store=None):
    """store 內 `old` 這集ê檔逐階段改名 `new`（月份資料夾跟咧換）。"""
    store = store or paths.NEWS_STORE
    if old == new:
        raise PipelineError("新舊成果檔名仝款：%s" % old)
    moves = []
    for rel, ext in relabel.RENAME + relabel.REMOVE:
        source = relabel._stage(store, rel, old, ext)
        if os.path.exists(source):
            target = relabel._stage(store, rel, new, ext)
            if os.path.exists(target):
                raise PipelineError("%s 已經有 %s，無搬任何物件" % (rel, new))
            moves.append((source, target))
    for source, target in moves:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        os.rename(source, target)
        folder = os.path.dirname(source)
        if not os.listdir(folder):
            os.rmdir(folder)
    renamed = []
    for _source, target in moves:
        renamed.append(target)
    for rel in LOGS:
        if _rename_rows(os.path.join(store, rel), old, new):
            renamed.append(os.path.join(store, rel) + "（" + new + " 那列）")
    return relabel.Report(renamed, [])


def redate(name, date, episode, reason, catalogue=None, store=None):
    """改目錄（照成果檔名重排）、搬 store；回 (新成果檔名, Report)。"""
    target = catalogue or paths.TRACKER_STORE
    rows, head = name_catalogue.read(target)
    found = None
    for index, row in enumerate(rows):
        if row["成果檔名"] == name:
            found = index
    if found is None:
        raise PipelineError("目錄內底無 %s" % name)
    new_row = redate_row(rows[found], date, episode, reason)
    new = new_row["成果檔名"]
    for row in rows:
        if row["成果檔名"] == new and new != name:
            raise PipelineError("目錄已經有 %s，無改任何物件" % new)
    report = move_store(name, new, store=store)
    rows[found] = new_row
    rows.sort(key=lambda row: row["成果檔名"])
    name_catalogue.write(target, rows, head)
    return new, report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("name", help="目前ê成果檔名")
    ap.add_argument("date", help="正確ê播出日期 YYYY-MM-DD")
    ap.add_argument("episode", type=int, help="正確ê集數")
    ap.add_argument("--reason", required=True, help="寫入備註ê依據")
    args = ap.parse_args(argv)
    new, report = redate(args.name, args.date, args.episode, args.reason)
    print("%s → %s" % (args.name, new))
    for path in report.renamed:
        print("改名  %s" % path)
    print("next: rebuild --verify、name_catalogue --check")
    return 0


if __name__ == "__main__":
    sys.exit(main())
