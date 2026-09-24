#!/usr/bin/env python3
"""段落表上帶外ê段，用伊家己ê區域重切，接轉去時間軸。

    python3 -m scripts.news.segment_recut WORK VIDEO

2024 年「島語時間」ê對白置中佇 y≈960–1050、「部落信箱」ê旁白佇
y≈890–970、詩句佇 y 600–760，攏毋佇字幕帶 y 722–848；照字幕帶切，
彼幾段ê cue 是照單字卡、花字、人名條切出來ê，對白攏無。2021 年 15 集
帶外專題（y≈950–1002）仝款。

所以段落表（`segments`）標出來ê帶外段，逐段用 `AREA_PRESETS` 彼个
preset 重切、精修，換掉彼段本底ê cue，**佇讀字進前**：猶無 TSV，重新
編號無代價。已經讀字ê集數拒絕，愛行 `rescan_band`（範圍外ê TSV 愛
徙號碼）。

時間軸記錄：頂層 `areas` 列這集用著ê區域（preset 名佮 region），用帶
外區域切ê cue 加 `area`；字幕帶切ê cue 無加欄位，所以無帶外段ê集數時
間軸逐 byte 無變。重切出來ê彼段也愛精修過才接——store 干焦收精修過ê
時間軸。
"""
import argparse
import glob
import json
import os
import shutil
import sys

from scripts import datadirs
from scripts.errors import PipelineError
from scripts.news import paths
from scripts.news import segments
from scripts.news import splice

AREA_PRESETS = {
    "島語時間": "titv-news-island",
    "部落信箱": "titv-news-mailbox",
    "單元片頭": "titv-news-montage",
    "帶外專題": "titv-news-offband",
}


def already_read(work):
    """這集敢已經有讀者讀過字？（有逐字稿內容，抑是有校讀紀錄）"""
    if os.path.exists(paths.verified_file(work)):
        return True
    target = paths.transcripts_file(work)
    if not os.path.exists(target):
        return False
    with open(target, encoding="utf-8") as handle:
        return bool(json.load(handle))


def _recut(video, start, duration, out, preset):
    """切一段，回粗切時間軸ê路徑。"""
    splice.recut(video, start, duration, out, presets=paths.ENGINE_PRESETS,
                 preset=preset, venv=paths.venv_py())
    return datadirs.coarse_cues(out)


def _refine(video, coarse, preset):
    """精修一段，回精修時間軸ê路徑。"""
    from scripts.news import refine_cues
    layout = refine_cues._preset_or_die(paths.ENGINE_PRESETS, preset)
    refine_cues.refine_episode(video, coarse, preset=layout)
    return refine_cues.refined_target(coarse)


def _presets():
    with open(paths.ENGINE_PRESETS, encoding="utf-8") as handle:
        return json.load(handle)


def run(work, video, recut=_recut, refine=_refine, presets=None):
    """重切這集ê帶外段；回重切幾段。無帶外段就無寫任何物件。"""
    timeline = paths.cues_to_read(work)
    if timeline is None:
        raise PipelineError("%s 無時間軸" % work)
    table = segments.read(paths.segments_file(work))
    targets = []
    for row in table:
        if row["類型"] in AREA_PRESETS:
            targets.append(row)
    if not targets:
        return 0
    if already_read(work):
        raise PipelineError(
            "%s 已經讀字矣，重切會重新編號、TSV 對著別條 cue——"
            "改用 rescan_band" % work)
    if presets is None:
        presets = _presets()
    with open(timeline, encoding="utf-8") as handle:
        book = json.load(handle)
    cues = book["cues"]
    areas = dict(book.get("areas", {}))
    for row in targets:
        kind = row["類型"]
        name = AREA_PRESETS[kind]
        lo, hi = float(row["起秒"]), float(row["迄秒"])
        fresh = os.path.join(paths.shots_dir(work), "recut-%06d" % int(lo))
        refined = refine(video, recut(video, lo, hi - lo, fresh, name), name)
        with open(refined, encoding="utf-8") as handle:
            stretch = json.load(handle)
        if not stretch.get("refined"):
            raise PipelineError("%s 第 %s–%s 秒重切了無精修，無接轉去"
                                % (work, row["起秒"], row["迄秒"]))
        new = []
        for item in stretch["cues"]:
            item = dict(item)
            item["area"] = kind
            new.append(item)
        _copy_strips(fresh, work)
        cues = splice.splice_time(cues, lo, hi, new)
        region = (presets.get(name) or {}).get("region")
        areas[kind] = {"preset": name, "region": region}
    book["cues"] = cues
    book["areas"] = areas
    with open(timeline, "w", encoding="utf-8") as handle:
        json.dump(book, handle, ensure_ascii=False, indent=2, sort_keys=True)
    return len(targets)


def _copy_strips(fresh, work):
    """重切彼段ê圖條（照開始時間命名）抄入 work dir ê `2-strips/`。"""
    target = paths.strips_dir(work)
    os.makedirs(target, exist_ok=True)
    for path in sorted(glob.glob(os.path.join(paths.strips_dir(fresh),
                                              "*.png"))):
        shutil.copy2(path, os.path.join(target, os.path.basename(path)))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("work")
    ap.add_argument("video")
    args = ap.parse_args(argv)
    done = run(args.work, args.video)
    print("%s：重切 %d 段帶外段落" % (args.work, done))
    return 0


if __name__ == "__main__":
    sys.exit(main())
