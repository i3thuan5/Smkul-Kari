#!/usr/bin/env python3
"""節目目錄讀出來ê逐集條目——`news/smkul.csv` 是正本。

本底這爿是 `paths.load_inventory()` 讀 `news/inventory.json`。彼份檔ê
逐一欄攏對節目目錄推導會出來，驗過零例外（133 筆）：

    slug     = 年度_集數3碼_播出日期_播出時段_族英_族中   133/133
    file     = basename(原始影片檔案位置)                133/133
    pending  ≡ `3-srt/<成果檔名>.srt` 佇無                133/133

所以彼份檔提掉，改對節目目錄讀。**條目ê形狀無變**——十八支程式ê
`entry["slug"]`、`entry["srt_name"]` 攏原封不動，只有「對佗位讀」這
一件代誌改去；這款時陣 `rebuild --verify` 是半失效ê，改愈少愈好揣
是佗一步歹去。

無矣ê三个鍵：`truncated`（無影片ê集數這馬根本無入表）、`partial`
（收入 `備註`）、`文稿位置`（文稿路線裁掉矣）。
"""
import csv
import glob
import os

from scripts import catalogue_checks as checks
from scripts.news import paths


def _delivered():
    """`3-srt/` 內底實在有ê成果檔名。"""
    names = set()
    for path in glob.glob(os.path.join(paths.SRT_DIR, "*", "*.srt")):
        names.add(os.path.basename(path)[:-len(".srt")])
    return names


def slug_of(row):
    """Work dir ê名：`<年度>_<集數3碼>_<播出日期>_<時段>_<族英>_<族中>`。

    佮 `成果檔名` 無仝形——彼是交付用ê（日期八碼、無年度），這是工作
    區用ê。集數愛補三碼：`2021_32_…` 排起來佮 `2021_032_…` 無仝位，
    而且揣無彼跡。
    """
    return "%s_%03d_%s_%s_%s_%s" % (
        row["年度"], int(row["集數"]), row["播出日期"],
        checks.slot_of(row["節目名稱"]), row["族語別(英)"], row["族語別(中)"])


def file_of(row):
    """來源檔家己ê檔名，報表頂懸寫ê彼个。

    `原始影片檔案位置` 是**候選清單**（122 逝用分號黏幾若條），所以
    袂使規格直接 basename——愛先剖分號才提頭一條。揀佗一條是
    `sources.py` ê代誌，遮干焦講出伊ê名。
    """
    first = row["原始影片檔案位置"].split(";")[0].strip()
    return os.path.basename(first)


def entry_of(row, delivered):
    entry = dict(row)
    entry["srt_name"] = row["成果檔名"]
    entry["slug"] = slug_of(row)
    entry["file"] = file_of(row)
    entry["video"] = row["原始影片檔案位置"]
    entry["播出時段"] = checks.slot_of(row["節目名稱"])
    entry["pending"] = row["成果檔名"] not in delivered
    return entry


def rows(path=None):
    """節目目錄ê逐一逝，原樣。"""
    with open(path or paths.TRACKER_STORE, encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def load(path=None, srt_dir=None):
    """逐集條目，照 `成果檔名` 排。

    `pending` 是問檔案系統ê——某一集做到佗一步，答案佇階段目錄，毋是
    佇任何一欄宣告。
    """
    delivered = _delivered() if srt_dir is None else set(srt_dir)
    found = []
    for row in rows(path):
        found.append(entry_of(row, delivered))
    return found
