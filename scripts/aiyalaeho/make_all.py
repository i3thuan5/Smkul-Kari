#!/usr/bin/env python3
"""Turn every finished work dir into an SRT and refresh the work table.

    python3 -m scripts.aiyalaeho.make_all            # 規批
    python3 -m scripts.aiyalaeho.make_all 開會了_068_Amis_阿美

Safe to re-run at any point: an episode still being read is reported as
待處理 rather than assembled.

這爿無寫任何一張表——兩張 smkul 表是節目目錄，人維護ê輸入。某一集做
到佗一步，答案佇階段目錄。
"""
import json
import os
import sys

from scripts import datadirs
from scripts.aiyalaeho import episodes
from scripts.aiyalaeho import make_srt
from scripts.aiyalaeho import paths


def vision_complete(work):
    """True when every cue of this episode has been read.

    Compares the two sets of cue numbers rather than their sizes: a
    verified.json can carry rows for numbers that no longer exist, reach
    the total, and hide real cues nobody has read.

    An episode with no cues at all is complete. Three episodes here carry
    no subtitles (88, 90, 98) and cut to nothing; the news side's test
    demands at least one cue and would hold such an episode -- and with it
    the whole batch -- open forever.
    """
    cues = datadirs.cues_to_read(work)
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
    return wanted <= read


def make_one(entry):
    """Build one episode's SRT; return its status line."""
    if entry["abnormal"]:
        # No band, or no Formosan row: there is nothing to assemble, and
        # a 0-line SRT in 3-srt/ would claim a deliverable that is not
        # one. It is listed in smkul-字幕版型異常.csv with the reason.
        return "字幕版型異常（%s；列於 %s）" % (
            entry["備註"], os.path.basename(paths.ABNORMAL_STORE))
    work = paths.work_dir(entry["srt_name"])
    if not datadirs.cues_to_read(work):
        return "待處理（尚未切cue）"
    if not vision_complete(work):
        return "待處理（已切cue，尚未校讀完）"

    out = paths.stage_path(paths.SRT_DIR, entry["srt_name"], ".srt")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    qc = make_srt.run(work, out)
    if not qc["cues"]:
        return "交付：0 條 cue（這集無字幕）"
    return "交付：%d 行字幕（族語 %d、華語 %d）" % (
        qc["srt_lines"], qc["formosan_rows"], qc["han_rows"])


def main(argv=None):
    names = list(argv or [])
    entries = episodes.load()
    os.makedirs(paths.SRT_DIR, exist_ok=True)

    for entry in entries:
        if names and entry["srt_name"] not in names:
            continue
        status = make_one(entry)
        print("%-30s %s" % (entry["srt_name"], status))
    # 這爿無閣寫任何一張表矣：兩張 smkul 表是**節目目錄**，人維護ê
    # 輸入。某一集做到佗一步，答案佇階段目錄。
    publish_report(entries)
    return 0


def publish_report(entries):
    """List the abnormal episodes and mark the ones a measurement found.

    A reason taken from the file name is the broadcaster's own label and
    needs no second look. One that came from the band check or from
    somebody reading a contact sheet is this pipeline's own judgement, so
    it gets named here -- the batch does not stop to ask, it says so at
    the end.
    """
    from scripts.aiyalaeho import publish
    listed = []
    for entry in entries:
        if entry["abnormal"]:
            listed.append(entry)
    if not listed:
        return
    measured = set(publish.measured_reasons(entries))
    print("\n字幕版型異常 %d 集：" % len(listed))
    for entry in listed:
        mark = ("  ← 量測抑是人判ê，看一目"
                if entry["srt_name"] in measured else "")
        print("  %-30s %s%s" % (entry["srt_name"], entry["備註"], mark))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
