#!/usr/bin/env python3
"""Turn every finished work dir into an SRT and record progress in smkul.csv.

Safe to re-run at any point: episodes still decoding are simply reported as
待處理, so a person can see how far the long pass has got.
"""
import json
import os
import sys

from scripts.news import make_srt
from scripts.news import episodes
from scripts.news import paths

WORK = paths.WORK
SRT_DIR = paths.SRT_DIR


def vision_complete(work):
    """True when every cue of a plan-B dir has actually been read.

    A part-finished vision pass is normal -- it is designed to be resumable --
    but only a finished one may replace the 文稿/tesseract output wholesale,
    so this insists on every cue being marked verified rather than merely on
    the directory existing.

    It compares the two sets of cue numbers rather than their sizes. Counting
    is not checking: rebuilding the contact sheets renumbers the cues, so a
    verified.json can carry rows for numbers that no longer exist, reach the
    total, and hide real cues that nobody has read. The episode would then be
    assembled and published with subtitles simply missing from it.
    """
    cues = paths.cues_to_read(work)
    verified = os.path.join(work, "verified.json")
    if not (cues and os.path.exists(verified)):
        return False
    with open(cues, encoding="utf-8") as handle:
        wanted = set()
        for cue in json.load(handle)["cues"]:
            wanted.add(str(cue["index"]))
    with open(verified, encoding="utf-8") as handle:
        marked = json.load(handle)
    read = set()
    for index in marked:
        if marked[index]:
            read.add(str(index))
    return bool(wanted) and wanted <= read


def make_one(entry):
    """Build one episode's SRT; return its status line."""
    slug = entry["slug"]
    # "Has it been cut?" -- see paths.has_cues, which `fetch_sftp.sh`
    # asks the same question of.
    vision = paths.work_dir(slug, WORK)
    if not paths.has_cues(slug, WORK):
        return "待處理（尚未切cue）"

    # The vision pass is where the text comes from: read off the contact
    # sheets by a human, cue by cue. An episode is only assembled once every
    # one of its cues has been read -- a half-read pass is a normal state
    # (the pass is designed to be resumable) but not a deliverable one.
    if not vision_complete(vision):
        return "待處理（已切cue，尚未校讀完）"

    out = paths.stage_path(SRT_DIR, entry["srt_name"], ".srt")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    qc = make_srt.run(vision, out)
    return "Claude Vision OCR 已產生 %d 行字幕" % qc["srt_lines"]


def main():
    entries = episodes.load()
    os.makedirs(SRT_DIR, exist_ok=True)

    # 這爿無閣寫任何一張表矣。`smkul.csv` 是**節目目錄**——人維護ê輸入，
    # 毋是這條流程ê產出；某一集做到佗一步，答案佇階段目錄，用
    # `/news-stage-count` 數就有。組ê結果印出來，予人看這輪做著啥。
    done = 0
    for entry in entries:
        status = make_one(entry)
        if status.startswith("Claude Vision"):
            done += 1
        print("%-46s %s" % (entry["srt_name"], status))
    print("\n組好 %d 集；交付ê SRT 直接寫入 %s" % (done, SRT_DIR))


if __name__ == "__main__":
    sys.exit(main())
