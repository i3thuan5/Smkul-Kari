#!/usr/bin/env python3
"""Turn every finished work dir into an SRT and record progress in smkul.csv.

Safe to re-run at any point: episodes still decoding are simply reported as
待處理, so the tracker can be refreshed while the long pass is running.
"""
import csv
import json
import os
import subprocess
import sys

from scripts.news import paths

CORPUS = paths.CORPUS
WORK = paths.WORK
SRT_DIR = paths.SRT_DIR
# 文稿-only variants are a regenerable working product, not a deliverable,
# so they stay in the kithann workspace rather than Kari-SRT.
RTF_DIR = os.path.join(paths.ROOT, "kithann", "out", "rtf-only")
PY = paths.VENV_PY

FIELDS = ["節目名稱", "年度", "集數", "播出日期", "播出時段",
          "族語別(英)", "族語別(中)", "影片檔案位置", "文稿位置", "字幕srt狀態"]


def relative(path):
    """Paths in the tracker are relative to the corpus root, as in the
    catalogue this corpus already ships."""
    if path.startswith(CORPUS + "/"):
        return "ilrdf-corpus/" + path[len(CORPUS) + 1:]
    return path


def vision_complete(work):
    """True when every contact sheet of a plan-B dir has been read.

    A part-finished vision pass is normal -- it is designed to be resumable --
    but only a finished one may replace the 文稿/tesseract output wholesale,
    so this insists on every cue being marked verified rather than merely on
    the directory existing.
    """
    cues = os.path.join(work, "cues.json")
    verified = os.path.join(work, "verified.json")
    if not (os.path.exists(cues) and os.path.exists(verified)):
        return False
    with open(cues, encoding="utf-8") as handle:
        total = len(json.load(handle)["cues"])
    with open(verified, encoding="utf-8") as handle:
        marked = json.load(handle)
    done = 0
    for value in marked.values():
        if value:
            done += 1
    return total > 0 and done >= total


def make_one(entry):
    """Build both SRTs for one episode; return its status line."""
    slug = entry["slug"]
    work = os.path.join(WORK, slug + ".work")
    if not os.path.exists(os.path.join(work, "cues.json")):
        return "待處理（尚未切cue）"
    if not os.path.exists(os.path.join(work, "transcripts.json")):
        return "待處理（已切cue，尚未辨識）"

    # A finished vision pass supersedes everything else: its text was read off
    # the contact sheets rather than recognised, so it needs no 文稿 to correct
    # it and must not be diluted by tesseract's version.
    vision = os.path.join(WORK, slug + ".B.work")
    if vision_complete(vision):
        out = os.path.join(SRT_DIR, entry["srt_name"] + ".srt")
        proc = subprocess.run(
            [PY, "-m", "scripts.news.make_srt", vision, "-o", out],
            capture_output=True, text=True, cwd=paths.ROOT)
        if proc.returncode != 0:
            lines = proc.stderr.strip().splitlines() or ["?"]
            return "錯誤：%s" % lines[-1][:80]
        qc = json.loads(proc.stdout.strip().splitlines()[-1])
        return ("已產生 %d 行；Claude 視覺辨識，%d 個 cue 全數校讀"
                % (qc["srt_lines"], qc["cues"]))

    rtf = ""
    if entry["文稿位置"]:
        rtf = os.path.join(CORPUS, entry["文稿位置"])

    name = entry["srt_name"]
    out = os.path.join(SRT_DIR, name + ".srt")
    wout = os.path.join(RTF_DIR, name + ".srt") if rtf else ""
    cmd = [PY, "-m", "scripts.news.make_srt", work, "-o", out]
    if rtf:
        cmd += ["--rtf", rtf, "--rtf-out", wout]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=paths.ROOT)
    if proc.returncode != 0:
        return "錯誤：%s" % (proc.stderr.strip().splitlines() or ["?"])[-1][:80]

    qc = json.loads(proc.stdout.strip().splitlines()[-1])
    if not rtf:
        return ("已產生 %d 行；無文稿可校對，全為 tesseract 辨識（品質低，"
                "建議以視覺辨識重讀）" % qc["srt_lines"])
    return ("已產生 %d 行；文稿對齊 %d 行（%.0f%%），其餘為 tesseract 辨識"
            % (qc["srt_lines"], qc["cues_aligned"], qc["aligned_pct"]))


def tracker_row(entry, status):
    """One smkul.csv row. rebuild.py reuses this so that a rebuilt tracker
    is byte-comparable with the delivered one."""
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
        "族語別(英)": entry["族語別(英)"],
        "族語別(中)": entry["族語別(中)"],
        "影片檔案位置": relative(entry["video"]),
        "文稿位置": script,
        "字幕srt狀態": status,
    }


def write_tracker(rows, path):
    with open(path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main():
    entries = json.load(open(paths.INVENTORY,
                             encoding="utf-8"))
    os.makedirs(SRT_DIR, exist_ok=True)
    os.makedirs(RTF_DIR, exist_ok=True)

    rows = []
    for entry in entries:
        if entry["truncated"]:
            status = "略過：" + entry["truncated"]
        else:
            status = make_one(entry)
        rows.append(tracker_row(entry, status))
        print("%-46s %s" % (entry["srt_name"], status))

    path = os.path.join(SRT_DIR, "smkul.csv")
    write_tracker(rows, path)
    print("\nwrote", path)


if __name__ == "__main__":
    sys.exit(main())
