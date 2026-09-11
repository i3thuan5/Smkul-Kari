#!/usr/bin/env python3
"""節目目錄讀出來ê逐集條目——兩張 smkul 表是正本。

本底這爿是 `paths.load_inventory()` 讀 `aiyalaeho/inventory.json`。彼
44 筆對兩張表逐欄對會起來、零處無仝，所以彼份檔提掉。

兩張表欄位完全相仝，分別干焦佇「這一逝佇佗一个檔」：`備註` 非空ê彼
張是字幕版型異常集（走袂了雙列雙語流程ê）。`理由` 彼欄併入 `備註`，
所以 `is_abnormal` 這馬是問「這逝對佗一張表來ê」。

無矣ê兩个鍵：`影片長度秒`（長度欄整个提掉，需要ê時對時間軸讀）、
`pending`（改問階段目錄）。
"""
import csv
import glob
import os

from scripts import catalogue_checks as checks
from scripts.aiyalaeho import paths


def _delivered():
    """`3-srt/` 內底實在有ê成果檔名。"""
    names = set()
    for path in glob.glob(os.path.join(paths.SRT_DIR, "*.srt")):
        names.add(os.path.basename(path)[:-len(".srt")])
    return names


def entry_of(row, abnormal, delivered):
    entry = dict(row)
    entry["srt_name"] = row["成果檔名"]
    entry["file"] = os.path.basename(row["原始影片檔案位置"].strip())
    entry["video"] = row["原始影片檔案位置"]
    entry["abnormal"] = abnormal
    entry["pending"] = row["成果檔名"] not in delivered
    return entry


def rows(path):
    with open(path, encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def load(table=None, abnormal_table=None, srt_dir=None):
    """兩張表合起來ê逐集條目，照 `成果檔名` 排。"""
    delivered = _delivered() if srt_dir is None else set(srt_dir)
    found = []
    for path, abnormal in ((table or paths.TRACKER_STORE, False),
                           (abnormal_table or paths.ABNORMAL_STORE, True)):
        for row in rows(path):
            found.append(entry_of(row, abnormal, delivered))
    found.sort(key=lambda one: one["srt_name"])
    return found


def header_problems(table=None, abnormal_table=None):
    """兩張表ê表頭愛相仝，而且異常表逐逝ê `備註` 愛非空。

    欄位完全相仝了後，`備註` 非空是彼張表**唯一**ê自我宣告——無ê話
    有人kā一逝徙毋著檔，對欄位看袂出來。
    """
    problems = []
    for path in (table or paths.TRACKER_STORE,
                 abnormal_table or paths.ABNORMAL_STORE):
        with open(path, encoding="utf-8-sig") as handle:
            names = csv.DictReader(handle).fieldnames or []
        problems.extend(checks.header_problems(names, checks.EPISODE_KEYS))
    for row in rows(abnormal_table or paths.ABNORMAL_STORE):
        if not (row.get("備註") or "").strip():
            problems.append("字幕版型異常表：%s 無備註，看袂出伊按怎袂使"
                            "做雙語交付" % row.get("成果檔名"))
    return problems
