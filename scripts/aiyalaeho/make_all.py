#!/usr/bin/env python3
"""Turn every finished work dir into an SRT and refresh the work table.

    python3 -m scripts.aiyalaeho.make_all            # 規批
    python3 -m scripts.aiyalaeho.make_all 開會了_068_Amis_阿美

Safe to re-run at any point: an episode still being read is reported as
待處理 rather than assembled, so the table can be refreshed while a long
vision pass is running.

The table written here is the work copy. The delivered one is written by
`publish`, once a whole batch is finished -- a mid-batch row says which
step an episode is stuck at, and that state lives in a work dir, which the
offline rebuild does not have.
"""
import json
import os
import sys

from scripts.aiyalaeho import make_srt
from scripts.aiyalaeho import paths
from scripts.aiyalaeho import tracker


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
    cues = os.path.join(work, "cues.json")
    verified = os.path.join(work, "verified.json")
    if not (os.path.exists(cues) and os.path.exists(verified)):
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
    work = paths.work_dir(entry["srt_name"])
    if not os.path.exists(os.path.join(work, "cues.json")):
        return "待處理（尚未切cue）"
    if not vision_complete(work):
        return "待處理（已切cue，尚未校讀完）"

    out = paths.stage_path(paths.SRT_DIR, entry["srt_name"], ".srt")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    qc = make_srt.run(work, out)
    with open(os.path.splitext(out)[0] + ".qc.json", "w",
              encoding="utf-8") as handle:
        json.dump(qc, handle, ensure_ascii=False, indent=2)
    if not qc["cues"]:
        return "交付：0 條 cue（這集無字幕）"
    return "交付：%d 行字幕（族語 %d、華語 %d）" % (
        qc["srt_lines"], qc["formosan_rows"], qc["han_rows"])


def main(argv=None):
    names = list(argv or [])
    entries = paths.load_inventory()
    os.makedirs(paths.SRT_DIR, exist_ok=True)

    for entry in entries:
        if names and entry["srt_name"] not in names:
            continue
        status = make_one(entry)
        print("%-30s %s" % (entry["srt_name"], status))
    # Every episode gets a row in the work copy, pending ones included --
    # that is what it is for: seeing how far the batch has got.
    rows = tracker.tracker_rows(entries, include_pending=True)
    tracker.write_tracker(rows, paths.TRACKER_CACHE)
    print("\nwrote", paths.TRACKER_CACHE)
    print("（store ê smkul.csv 是 publish 寫ê，規批做煞才寫）")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
