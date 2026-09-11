#!/usr/bin/env python3
"""一擺性：kā節目目錄佮交付表合做一張。

    python3 openspec/changes/unify-episode-tables/migrations/\
convert_catalogues.py          # 看伊beh寫啥
    python3 …/convert_catalogues.py --write     # 真正寫

吃：`Kari-SRT/ilrdf-corpus.csv`（1029 逝）、`news/inventory.json`（備註
內底ê「來源不完整」）、《開會了》既有ê兩張表。
出：`news/smkul.csv`（11 欄）、`aiyalaeho/smkul.csv`（9 欄）、
`aiyalaeho/smkul-字幕版型異常.csv`（9 欄）。

跑一擺就無路用矣，留佇 change 目錄做紀錄，無入 `scripts/`。
"""
import argparse
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, ROOT)

from scripts import catalogue_checks as checks      # noqa: E402
from scripts import languages                       # noqa: E402

KARI = os.path.join(ROOT, "Kari-SRT")
NEWS_FIELDS = list(checks.head(checks.NEWS_KEYS)) + [
    "原始影片檔案位置", "備註"]
AIYA_FIELDS = list(checks.head(checks.EPISODE_KEYS)) + [
    "原始影片檔案位置", "備註"]


def _read(path, encoding="utf-8-sig"):
    with open(path, encoding=encoding) as handle:
        return list(csv.DictReader(handle))


def _variety_in(paths_cell, language):
    """影片檔名內底敢有這族ê變體字樣？無就回空字串。

    983 逝內底干焦 1 逝有（`魯凱語-霧台20210101S1100.mp4`）。查有就填，
    查無留空——「語言別 空」是常態，代號空才是錯。
    """
    table = languages.VARIETIES.get(language) or {}
    for cell in paths_cell.split(";"):
        stem = os.path.basename(cell.strip())
        for variety in sorted(table, key=len, reverse=True):
            if variety in stem:
                return variety
    return ""


def _notes(catalogue_note, partial):
    """備註：目錄本底彼欄，加頂懸ê「來源不完整」。

    `字幕srt狀態` 尾溜彼段來源判斷推袂出來——彼是人量ê，無收起來就無去。
    """
    parts = []
    for one in (catalogue_note, partial):
        if (one or "").strip():
            parts.append(one.strip())
    return "；".join(parts)


def news_rows():
    cat = _read(os.path.join(KARI, "ilrdf-corpus.csv"))
    with open(os.path.join(KARI, "news", "inventory.json"),
              encoding="utf-8") as handle:
        inventory = json.load(handle)
    partial = {}
    for entry in inventory:
        note = entry.get("partial") or entry.get("truncated") or ""
        if note:
            partial[entry["srt_name"]] = "來源不完整：" + note

    rows = []
    for one in cat:
        if one["節目名稱"] == checks.AIYALAEHO:
            continue
        if one["有無影片"] != "是" or not one["影片檔案位置"].strip():
            continue
        language = one["族語別(中)"]
        variety = _variety_in(one["影片檔案位置"], language)
        row = {
            "節目名稱": one["節目名稱"],
            "年度": one["年度"],
            "集數": one["集數"],
            "播出日期": one["播出日期"],
            "族語別(英)": one["族語別(英)"],
            "族語別(中)": language,
            "語言別": variety,
            "語言別代號": languages.code_for(language, variety),
            "原始影片檔案位置": one["影片檔案位置"].strip(),
        }
        row["成果檔名"] = checks.srt_name_of(row)
        row["備註"] = _notes(one["備註"], partial.get(row["成果檔名"], ""))
        rows.append(row)
    rows.sort(key=lambda one: one["成果檔名"])
    return rows


def _aiya_row(one, note):
    language = one["族語別(中)"]
    variety = one["語言別"]
    row = {
        "節目名稱": one["節目名稱"],
        "集數": one["集數"],
        "族語別(英)": one["族語別(英)"],
        "族語別(中)": language,
        "語言別": variety,
        "語言別代號": languages.code_for(language, variety),
        "原始影片檔案位置": one["影片檔案位置"].strip(),
        "備註": note,
    }
    row["成果檔名"] = checks.srt_name_of(row)
    return row


def aiyalaeho_rows():
    """(正常表, 字幕版型異常表)。`理由` 併入 `備註`。"""
    normal = []
    for one in _read(os.path.join(KARI, "aiyalaeho", "smkul.csv")):
        normal.append(_aiya_row(one, ""))
    abnormal = []
    for one in _read(os.path.join(KARI, "aiyalaeho",
                                  "smkul-字幕版型異常.csv")):
        reason = (one.get("理由") or "").strip()
        if not reason:
            raise SystemExit("異常表有一逝無理由：%s" % one.get("成果檔名"))
        abnormal.append(_aiya_row(one, reason))
    normal.sort(key=lambda one: one["成果檔名"])
    abnormal.sort(key=lambda one: one["成果檔名"])
    return normal, abnormal


def write(path, fields, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args(argv)

    news = news_rows()
    normal, abnormal = aiyalaeho_rows()
    plan = [
        (os.path.join(KARI, "news", "smkul.csv"), NEWS_FIELDS, news),
        (os.path.join(KARI, "aiyalaeho", "smkul.csv"), AIYA_FIELDS, normal),
        (os.path.join(KARI, "aiyalaeho", "smkul-字幕版型異常.csv"),
         AIYA_FIELDS, abnormal),
    ]

    problems = []
    for _path, _fields, rows in plan:
        source = "原始影片檔案位置"
        problems.extend(checks.row_problems(rows, source_column=source))
    if problems:
        for line in problems[:20]:
            print("PROBLEM:", line)
        raise SystemExit("%d 條不變量無過，無寫" % len(problems))

    for path, fields, rows in plan:
        print("%-52s %4d 逝 %2d 欄"
              % (os.path.relpath(path, ROOT), len(rows), len(fields)))
        if args.write:
            write(path, fields, rows)
    print("寫矣" if args.write else "（無寫；欲寫加 --write）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
