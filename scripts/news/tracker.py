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
import json
import os

from scripts.news import paths
from scripts.errors import PipelineError

ETH_EN = "族語別(英)"
ETH_ZH = "族語別(中)"

# Read left to right: which episode this is, where its material lives,
# how far it has got. Every column is derived from the store -- nothing
# here is typed in, because `rebuild --verify` recomputes the whole table
# and compares it byte for byte.
#
# `播出時段` is not a column: it is inside `成果檔名`, and dropping it
# without adding that one would leave the identity columns ambiguous --
# 74 rows carry only 33 distinct broadcast dates, 31 of them shared by
# two or three episodes. `文稿位置` is gone with the 文稿 route itself.
# 使用者裁定 2026-09-03.
FIELDS = ["年度", "集數", "播出日期", "節目名稱", ETH_EN, ETH_ZH,
          "影片檔案位置", "影片長度", "成果檔名", "cues",
          "字幕srt狀態", "語音辨識模型"]

# What the `cues` column says about the delivered timeline. Publish only
# takes refined ones into the store, so the delivered table reads the
# same all the way down; the working copy is where 粗切 shows up, on the
# episodes that are cut but not yet refined.
CUES_REFINED = "已精修"
CUES_COARSE = "粗切"

# The speech-side cell names the recogniser, not a revision: 2-srt-raw is
# the recognised deliverable, so that file existing is what says the audio
# was recognised. The stages above it (3-srt-ai, 4-srt-quality) are analysis
# renders -- a machine translation and a correspondence grade -- and neither
# changes which recogniser produced the Formosan text, which is the one
# thing a reader of this column can act on.
#
# Derived from the store rather than hand-written: a written value could not
# survive `rebuild --verify`, which recomputes this table from the store
# alone -- file existence is the only input both sides share.
ASR_SRT = ("2-srt-raw", ".srt")
ASR_MODEL = "Kaldi"


def asr_model(srt_name, asr_dir=None):
    """Which recogniser produced this episode's speech side, if any."""
    if asr_dir is None:
        asr_dir = paths.ASR_DIR
    folder, ext = ASR_SRT
    if os.path.exists(paths.stage_path(os.path.join(asr_dir, folder),
                                       srt_name, ext)):
        return ASR_MODEL
    return ""


def cue_grade(srt_name, cues_dir=None):
    """Is this episode's delivered timeline refined, or still coarse?

    Read off the store's own file, never written by hand: any recompute
    has to give the same answer or the table stops being rebuildable.

    In the delivered table this reads 已精修 all the way down, because
    publish refuses a coarse timeline. That is the point of having it --
    it is where that guarantee shows. The working copy is the one where
    粗切 appears, on episodes cut but not yet refined.
    """
    if cues_dir is None:
        cues_dir = paths.KARI_CUES
    path = paths.stage_path(cues_dir, srt_name, ".json")
    if not os.path.exists(path):
        return ""
    return CUES_REFINED if paths.timeline_is_refined(path) else CUES_COARSE


def video_length(srt_name, cues_dir=None):
    """How long the video ran, as 時:分:秒, or "" if it has no timeline yet.

    Recorded, never judged. The programme has more than one normal length --
    48-minute editions, 24-minute ones in the Lunar New Year week, and
    episodes in between, all with the same cue density -- so a threshold on
    length mislabels normal episodes. A reader of the table can see the
    number and decide for themselves.

    Read from the stored timeline rather than written down anywhere, for the
    same reason as the speech-side column: `rebuild --verify` recomputes this
    table from the store alone, and a hand-written value could never survive
    that comparison.
    """
    if cues_dir is None:
        cues_dir = paths.KARI_CUES
    path = paths.stage_path(cues_dir, srt_name, ".json")
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as handle:
        duration = json.load(handle).get("duration")
    if not duration:
        return ""
    whole = int(round(float(duration)))
    return "%02d:%02d:%02d" % (whole // 3600, whole % 3600 // 60, whole % 60)


def corpus_path(path):
    """The video path as the delivered table records it: relative to the
    corpus root, the same form the shipped catalogue uses.

    The inventory already stores it that way -- `add_episodes` writes it,
    and the February batch was migrated to match -- so this only guards
    the invariant. An absolute path here would make the delivered table
    specific to one machine, and `rebuild --verify` on another would
    report a mismatch with no visible cause.
    """
    if path.startswith("/"):
        raise PipelineError(
            "inventory 的 video 欄愛是相對 corpus 根的路徑"
            "（ilrdf-corpus/…），毋是絕對路徑：%s" % path)
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


def tracker_row(entry, status, asr_dir=None, cues_dir=None):
    """One smkul.csv row."""
    # An episode whose only surviving source is short still gets subtitled --
    # a partial transcript beats none -- but the tracker has to say so, or the
    # SRT reads as a complete episode that simply stops. The note is attached
    # here rather than where the SRT is built so that make_all and rebuild
    # cannot drift apart on it.
    if entry.get("partial"):
        status = "%s；來源不完整：%s" % (status, entry["partial"])
    return {
        "年度": entry["年度"],
        "集數": entry["集數"],
        "播出日期": entry["播出日期"],
        "節目名稱": entry["節目名稱"],
        ETH_EN: entry[ETH_EN],
        ETH_ZH: entry[ETH_ZH],
        "影片檔案位置": corpus_path(entry["video"]),
        "影片長度": video_length(entry["srt_name"], cues_dir),
        "成果檔名": entry["srt_name"],
        "cues": cue_grade(entry["srt_name"], cues_dir),
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
