#!/usr/bin/env python3
"""The smkul.csv progress table: its columns, and how one row is built.

Three programs need this and must agree to the byte, so it lives on its own
rather than in any of them:

    make_all   builds a row per episode as it assembles the SRTs
    publish    writes the table into Kari-SRT once a batch is complete
    rebuild    rebuilds the table from Kari-SRT alone and compares it

`rebuild --verify` compares its output against the delivered table byte for
byte, so anything that changes what a row says has to change it here -- a
second copy of this logic at any call site would drift and only show up as a
mismatch nobody can explain.
"""
import csv
import os

from scripts.news import paths

CORPUS = paths.CORPUS

ETH_EN = "族語別(英)"
ETH_ZH = "族語別(中)"

FIELDS = ["節目名稱", "年度", "集數", "播出日期", "播出時段",
          ETH_EN, ETH_ZH, "影片檔案位置", "文稿位置",
          "字幕srt狀態", "語音辨識模型"]

# The speech-side cell names the recogniser, not a revision: delivery stops
# at 3-srt-raw, so that file existing is what says the audio was recognised.
# The align extension above it (4-srt-ai, 6-srt-complete) was a pilot whose
# semantic merge did not work out and is not produced for later episodes, so
# it no longer counts as a higher version of the same thing.
#
# Derived from the store rather than hand-written: a written value could not
# survive `rebuild --verify`, which recomputes this table from the store
# alone -- file existence is the only input both sides share.
ASR_SRT = ("3-srt-raw", ".srt")
ASR_MODEL = "Kaldi"


def asr_model(srt_name, asr_dir=None):
    """Which recogniser produced this episode's speech side, if any."""
    if asr_dir is None:
        asr_dir = paths.ASR_DIR
    folder, ext = ASR_SRT
    if os.path.exists(os.path.join(asr_dir, folder, srt_name + ext)):
        return ASR_MODEL
    return ""


def relative(path):
    """Paths in the tracker are relative to the corpus root, as in the
    catalogue this corpus already ships."""
    if path.startswith(CORPUS + "/"):
        return "ilrdf-corpus/" + path[len(CORPUS) + 1:]
    return path


# The only two statuses that ever reach the delivered table. Everything else
# make_all can say ("待處理…", "錯誤…") describes a work dir, which is exactly
# what rebuild has no access to -- so those never leave the working copy.
# Both are written from three places; the wording has to match to the byte or
# `rebuild --verify` reports a mismatch with no visible cause.


def vision_status(srt_lines):
    """A delivered episode: read off the contact sheets, every cue checked."""
    return "Claude Vision OCR 已產生 %d 行字幕" % srt_lines


def skipped_status(reason):
    """An episode whose source was too incomplete to subtitle at all."""
    return "略過：" + reason


def tracker_row(entry, status, asr_dir=None):
    """One smkul.csv row."""
    # An episode whose only surviving source is short still gets subtitled --
    # a partial transcript beats none -- but the tracker has to say so, or the
    # SRT reads as a complete episode that simply stops. The note is attached
    # here rather than where the SRT is built so that make_all and rebuild
    # cannot drift apart on it.
    if entry.get("partial"):
        status = "%s；來源不完整：%s" % (status, entry["partial"])
    script = ""
    if entry["文稿位置"]:
        script = "ilrdf-corpus/" + entry["文稿位置"]
    return {
        "節目名稱": entry["節目名稱"],
        "年度": entry["年度"],
        "集數": entry["集數"],
        "播出日期": entry["播出日期"],
        "播出時段": entry["播出時段"],
        ETH_EN: entry[ETH_EN],
        ETH_ZH: entry[ETH_ZH],
        "影片檔案位置": relative(entry["video"]),
        "文稿位置": script,
        "字幕srt狀態": status,
        "語音辨識模型": asr_model(entry["srt_name"], asr_dir),
    }


def is_pending(entry):
    """True while an episode is registered but not yet delivered.

    The inventory has to name an episode before the batching, the reader
    hand-off or the import can look its naming up. `pending` is what lets it
    do that without the store claiming a deliverable that is not there.
    """
    return bool(entry.get("pending"))


def tracker_rows(entries, status_of):
    """One row per episode the store claims to have delivered.

    Pending episodes get none. Their status would say which step they are
    stuck at, and that lives in a work dir -- which rebuild has no access to,
    so a table holding such a row could never be rebuilt byte-for-byte again.
    """
    rows = []
    for entry in entries:
        if is_pending(entry):
            continue
        rows.append(tracker_row(entry, status_of(entry)))
    return rows


def write_tracker(rows, path):
    with open(path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
