#!/usr/bin/env python3
"""The aiyalaeho/smkul.csv progress table: its columns, and one row of it.

Three programs need this and must agree to the byte -- make_all builds a
row per episode as it assembles, publish writes the table into the store
once a batch is complete, and rebuild rebuilds it from the store alone and
compares -- so it lives on its own rather than in any of them.

Nine columns, and no column that would have nothing in it. The news table
carries 年度, 播出日期 and 播出時段; this programme's broadcast dates are
not recorded anywhere we can reach -- not in the catalogue, whose 46 rows
for it hold only 序列, 節目名稱, 集數 and 備註, and not in the files, which
were re-encoded and carry no original timestamp. It carries no 語音辨識模型
either, because the Formosan text here comes off the picture and no
recogniser is involved. An empty column that can never be filled is a
column that has to be explained every time somebody opens the file; if a
broadcast date list ever arrives, adding the column then is one change
here.
"""
import csv
import json
import os

from scripts.aiyalaeho import paths
from scripts.errors import PipelineError

FIELDS = ["節目名稱", "集數", "族語別(英)", "族語別(中)", "語言別",
          "語言代號", "影片檔案位置", "影片長度", "成果檔名"]

# The second table's columns: the nine above, then why this episode is not
# a bilingual deliverable. Every row has a value there, so it is not a
# column kept empty for the sake of having it -- and `smkul.csv` does not
# get one, where 38 of its rows would have nothing to put in it.
ABNORMAL_FIELDS = FIELDS + ["理由"]


def hms(duration):
    """Seconds as 時:分:秒, or "" for nothing."""
    if not duration:
        return ""
    whole = int(round(float(duration)))
    return "%02d:%02d:%02d" % (whole // 3600, whole % 3600 // 60, whole % 60)


def video_length(srt_name, cues_dir=None):
    """How long the video ran, as 時:分:秒, or "" with no timeline yet.

    Read from the stored timeline rather than written down anywhere:
    `rebuild --verify` recomputes this table from the store alone, and a
    hand-written value could never survive that comparison.
    """
    if cues_dir is None:
        cues_dir = paths.KARI_CUES
    path = paths.stage_path(cues_dir, srt_name, ".json")
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as handle:
        duration = json.load(handle).get("duration")
    return hms(duration)


def is_abnormal(entry):
    """True when this episode cannot be a bilingual deliverable.

    One field decides which of the two tables an episode lands in, and it
    says why in the same breath: 無字幕 / 僅華語字幕 off the file name,
    版型不符：… measured before cutting, 人工判定：… after somebody looked
    at a contact sheet. Empty or absent means the ordinary path.
    """
    return bool(entry.get("理由"))


def corpus_path(path):
    """The video path as the delivered table records it: relative to the
    corpus root, the same form the catalogue uses.

    An absolute path here would make the delivered table specific to one
    machine, and a rebuild on another would report a mismatch with no
    visible cause.
    """
    if path.startswith("/"):
        raise PipelineError(
            "inventory ê video 欄愛是相對 corpus 根ê路徑"
            "（ilrdf-corpus/…），毋是絕對路徑：%s" % path)
    return path


def is_pending(entry):
    """True while an episode is registered but not yet delivered."""
    return bool(entry.get("pending"))


def tracker_row(entry, cues_dir=None):
    """One smkul.csv row."""
    return {
        "節目名稱": entry["節目名稱"],
        "集數": entry["集數"],
        "族語別(英)": entry["族語別(英)"],
        "族語別(中)": entry["族語別(中)"],
        "語言別": entry["語言別"],
        "語言代號": entry["語言代號"],
        "影片檔案位置": corpus_path(entry["video"]),
        "影片長度": video_length(entry["srt_name"], cues_dir),
        "成果檔名": entry["srt_name"],
    }


def tracker_rows(entries, cues_dir=None, include_pending=False):
    """One row per episode the store claims to have delivered.

    Pending episodes get none in the delivered table: what their row would
    say is which step they are stuck at, and that lives in a work dir --
    which rebuild has no access to, so such a table could never be rebuilt
    byte-for-byte. The work copy passes `include_pending` and lists
    everybody, which is what it is for.

    Abnormal episodes get none either: they have no deliverable, and a row
    here would name an SRT that does not exist. They are listed in the
    second table instead, with the reason.
    """
    rows = []
    for entry in entries:
        if is_pending(entry) and not include_pending:
            continue
        if is_abnormal(entry):
            continue
        rows.append(tracker_row(entry, cues_dir))
    return rows


def abnormal_rows(entries, include_pending=False):
    """One row per episode that cannot be delivered, and why.

    The length comes from the inventory rather than a timeline: these
    episodes are never cut, so `1-cues/` holds nothing for them, and the
    offline rebuild may not open a video to find out. A tool writes it at
    registration; nobody types it.
    """
    rows = []
    for entry in entries:
        if not is_abnormal(entry):
            continue
        if is_pending(entry) and not include_pending:
            continue
        row = tracker_row(entry)
        row["影片長度"] = hms(entry.get("影片長度秒"))
        row["理由"] = entry["理由"]
        rows.append(row)
    return rows


def write_tracker(rows, path, fields=None):
    """Write the table. utf-8-sig and CRLF: Excel is the reader."""
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields or FIELDS)
        writer.writeheader()
        writer.writerows(rows)
