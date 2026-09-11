#!/usr/bin/env python3
"""Rebuild every delivered SRT from the store alone, and prove it.

    python3 -m scripts.aiyalaeho.rebuild --verify

The executable form of the store's core promise: this repo (the code) plus
`Kari-SRT/aiyalaeho/` (`1-ocr/1-cues/` + `1-ocr/2-vision/` +
`inventory.json`) suffice to rebuild every delivered SRT and `smkul.csv`
byte for byte -- offline, without a video, calling no model. If that
holds, everything under `kithann/` really is a cache that can be thrown
away.

How it stays byte-identical: it does not reimplement assembly. For each
episode it synthesises a work dir -- cues.json copied from the store, a
transcripts.json rebuilt from the vision TSVs -- and then runs the very
same `make_srt` that produced the deliverable, followed by the same
tracker code that produced the table.

Any missing input is reported by name and stops the run before anything
is compared. Nothing incomplete is ever passed off as a rebuilt
deliverable.
"""
import argparse
import glob
import json
import os
import shutil
import sys
import tempfile

from scripts import catalogue_checks as checks
from scripts import datadirs
from scripts.aiyalaeho import make_srt
from scripts.aiyalaeho import episodes
from scripts.aiyalaeho import paths
from scripts.aiyalaeho.langcheck import report
from scripts.errors import PipelineError


# `b*.tsv` ê 才是視覺辨識ê批——佮 ingest 彼爿仝一條規矩。別ê檔（抽查、
# 筆記）若予 glob 食著，sort 起來排佇後壁ê彼个會kā別人ê字蓋去。
BATCH_GLOB = "b*.tsv"


def _tsv_rows(path):
    rows = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.rstrip("\n")
            if line.strip():
                rows.append(line)
    return rows


def episode_transcripts(srt_name):
    """transcripts.json content, rebuilt from this episode's vision TSVs."""
    folder = paths.stage_path(paths.KARI_VISION, srt_name)
    resolved = {}
    if not os.path.isdir(folder):
        return resolved
    for path in sorted(glob.glob(os.path.join(folder, BATCH_GLOB))):
        for row in _tsv_rows(path):
            parts = row.split("\t")
            while len(parts) < 3:
                parts.append("")
            resolved.setdefault(parts[0], {})[parts[1]] = parts[2]
    return resolved


def _cue_count(srt_name):
    path = paths.stage_path(paths.KARI_CUES, srt_name, ".json")
    with open(path, encoding="utf-8") as handle:
        return len(json.load(handle)["cues"])


def check_inputs(entries):
    """Everything the rebuild needs but cannot find, by name."""
    problems = []
    for entry in entries:
        # A registered episode still being worked on has nothing to
        # rebuild yet, and says so in the inventory. Every other episode
        # is a claim that it was delivered, and that claim is what the
        # rest of this checks.
        if entry["pending"] or entry["abnormal"]:
            # Two ways an episode legitimately has nothing to rebuild: it
            # is still being worked on, or it never was a bilingual
            # deliverable. Both say so in the inventory, so an episode
            # carrying neither is a claim -- and that claim is what the
            # rest of this checks.
            continue
        name = entry["srt_name"]
        cues = paths.stage_path(paths.KARI_CUES, name, ".json")
        if not os.path.exists(cues):
            problems.append("揣無 1-cues/%s.json" % name)
            continue
        if _cue_count(name) and not episode_transcripts(name):
            # An episode with no cues has nothing to read, and three of
            # them carry no subtitles at all.
            problems.append("%s 無視覺逐字稿（2-vision/%s/）" % (name, name))
    return problems


def rebuild_one(entry, tmp):
    """Synthesise a work dir and run the real make_srt over it."""
    name = entry["srt_name"]
    work = os.path.join(tmp, name + ".work")
    os.makedirs(work, exist_ok=True)
    timeline = datadirs.coarse_cues(work)
    os.makedirs(os.path.dirname(timeline), exist_ok=True)
    shutil.copy2(paths.stage_path(paths.KARI_CUES, name, ".json"), timeline)
    with open(os.path.join(work, "transcripts.json"), "w",
              encoding="utf-8") as handle:
        json.dump(episode_transcripts(name), handle, ensure_ascii=False)
    out = os.path.join(tmp, name + ".srt")
    make_srt.run(work, out)
    with open(out, encoding="utf-8") as handle:
        return handle.read()


def rebuild_all(entries=None):
    """{"srt": {name: body}, "rows": [row…]} -- the whole store, rebuilt."""
    if entries is None:
        entries = episodes.load()
    problems = check_inputs(entries)
    if problems:
        for line in problems:
            print("MISSING:", line)
        raise PipelineError("%d 項輸入袂齊，無重建" % len(problems))

    tmp = tempfile.mkdtemp(prefix="aiya-rebuild-")
    try:
        bodies = {}
        for entry in entries:
            if entry["pending"] or entry["abnormal"]:
                continue
            bodies[entry["srt_name"]] = rebuild_one(entry, tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    marks, dist = _language_tables(bodies, entries)
    return {"srt": bodies, "entries": entries,
            "lang_marks": marks, "lang_dist": dist}


def _language_tables(bodies, entries):
    """兩張語言檢查 CSV，**食重建出來ê SRT**，毋是 store 家己彼份。

    食 store 彼份ê話，上游換版、下游無綴ê時陣驗袂出來——兩爿攏是
    舊ê，比起來當然仝。
    """
    found = []
    for entry in entries:
        name = entry["srt_name"]
        if name not in bodies:
            continue
        found.append(report.Episode(name, entry["集數"],
                                    entry["族語別(中)"], entry["族語別(英)"],
                                    entry["語言別"], entry["語言別代號"],
                                    bodies[name]))
    lexicons = report.lexicons_for(found)
    return (report.mark_rows(found, lexicons),
            report.dist_rows(found, lexicons))


def stage_names():
    """[(階段, {成果檔名…})…]，頂懸ê排頭前。

    本語料ê store 無月份彼層，所以掃法佮新聞無仝，比對ê規矩相仝
    （見 srt-data-store「下游階段的集數必為上游的子集」）。
    """
    found = []
    for stage, base, ext in (("1-cues", paths.KARI_CUES, ".json"),
                             ("2-vision", paths.KARI_VISION, ""),
                             ("3-srt", paths.SRT_DIR, ".srt")):
        names = set()
        for entry in sorted(glob.glob(os.path.join(base, "*" + ext))):
            name = os.path.basename(entry)
            if ext:
                if not name.endswith(ext):
                    continue
                name = name[:-len(ext)]
            names.add(name)
        found.append((stage, names))
    return found


def verify():
    """[name…]——對袂起來ê交付物，佮無過ê不變量。"""
    built = rebuild_all()
    mismatched = list(datadirs.stage_problems(stage_names()))
    for name in sorted(built["srt"]):
        # 交付品是「比對ê對象」，毋是重建ê輸入——所以無佇 check_inputs
        # 內底問，佇遮無彼支就是「對袂起來」，仝款愛報。
        path = paths.stage_path(paths.SRT_DIR, name, ".srt")
        if not os.path.exists(path):
            mismatched.append(name + ".srt")
            continue
        with open(path, encoding="utf-8") as handle:
            if handle.read() != built["srt"][name]:
                mismatched.append(name + ".srt")

    mismatched.extend(_table_problems(built))
    mismatched.extend(_language_problems(built))
    return mismatched


def _language_problems(built):
    """兩張語言檢查 CSV，重建了逐 byte 比。"""
    wanted = [(os.path.basename(paths.LANGCHECK_MARKS),
               paths.LANGCHECK_MARKS, report.MARK_HEADER,
               built["lang_marks"]),
              (os.path.basename(paths.LANGCHECK_DIST),
               paths.LANGCHECK_DIST, report.DIST_HEADER,
               built["lang_dist"])]
    problems = []
    tmp = tempfile.mkdtemp(prefix="aiya-lang-")
    try:
        for label, target, header, rows in wanted:
            if not os.path.exists(target):
                raise PipelineError("揣無 %s——有 %d 逝愛记佇遐"
                                    % (label, len(rows)))
            table = os.path.join(tmp, label)
            report.write_table(table, header, rows)
            with open(table, "rb") as handle:
                rebuilt = handle.read()
            with open(target, "rb") as handle:
                if handle.read() != rebuilt:
                    problems.append(label)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return problems


def _table_problems(built):
    """兩張節目目錄表ê不變量。

    這馬 in 是**輸入**毋是產出——內容人維護ê，逐 byte 重算比對無意義
    矣。換做不變量：表頭、成果檔名規格佮唯一性、佮識別欄互推、
    `語言別代號` 值域、族語別中英一對一、素材位置非空、列序，加
    「異常表逐逝ê `備註` 愛非空」——兩張表欄位完全相仝，彼是唯一ê
    自我宣告。
    """
    problems = list(episodes.header_problems())
    for path in (paths.TRACKER_STORE, paths.ABNORMAL_STORE):
        problems.extend(checks.row_problems(episodes.rows(path)))
    problems.extend(checks.orphan_problems(
        episodes.rows(paths.TRACKER_STORE)
        + episodes.rows(paths.ABNORMAL_STORE),
        stage_names()))
    return problems


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--verify", action="store_true",
                    help="逐 byte 比對重建ê結果佮交付ê")
    args = ap.parse_args(argv)

    if not args.verify:
        built = rebuild_all()
        print("重建 %d 集（無比對；欲比對加 --verify）" % len(built["srt"]))
        return 0

    mismatched = verify()
    if mismatched:
        for name in mismatched:
            print("DIFFERS:", name)
        raise PipelineError("%d 項佮交付ê無仝" % len(mismatched))
    print("OK：%d 集ê SRT ＋ 兩張語言檢查 CSV 對 Kari-SRT 重建，逐 byte "
          "相仝；兩張節目目錄表ê不變量嘛過矣"
          % len(rebuild_all()["srt"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
