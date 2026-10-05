#!/usr/bin/env python3
"""段落表上帶外ê段，用伊家己ê區域重切，接轉去時間軸。

    python3 -m scripts.news.segment_recut WORK VIDEO

2024 年「島語時間」ê對白置中佇 y≈960–1050、「部落信箱」ê旁白佇
y≈890–970、詩句佇 y 600–760，攏毋佇字幕帶 y 722–848；照字幕帶切，
彼幾段ê cue 是照單字卡、花字、人名條切出來ê，對白攏無。2021 年 15 集
帶外專題（y≈950–1002）仝款。2021 年「文化小辭典」子母畫面ê字幕沉到
y≈803–885，嘛愛重切（`SUNKEN`，干焦 2021 年）。

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
# 2021 年「文化小辭典」ê字幕沉到 y≈803–885，字幕帶切袂著；2022 起轉去
# 帶內。分界看播出年，毋是 preset（2021-11 佮 2022-01 仝款 titv-news-848）。
SUNKEN = {"文化小辭典": ("titv-news-dict-2021", "2022")}
# 沉落去ê字幕高低逐集無仝（20211101_305 晚間 y 815–870、20211124_328
# 晚間 780–825），重切進前佇遮量字佇佗幾列。下緣停佇 900：粉紅框下跤
# 「文化小辭典」ê白字標題對 905 起，逐格攏佇，會予人當做字幕。
PROBE_TOP, PROBE_BOTTOM = 740, 900
PROBE_COLS = (600, 1740)
PROBE_FRAMES = 15
PAD = 10


def already_read(work):
    """這集敢已經有讀者讀過字？（有逐字稿內容，抑是有校讀紀錄）"""
    if os.path.exists(paths.verified_file(work)):
        return True
    target = paths.transcripts_file(work)
    if not os.path.exists(target):
        return False
    with open(target, encoding="utf-8") as handle:
        return bool(json.load(handle))


def _year(work):
    """Work dir 名 `2021_305_2021-11-01_…` ê播出年；看袂出來回空。"""
    parts = os.path.basename(work.rstrip(os.sep)).split("_")
    if len(parts) > 2 and parts[2][:4].isdigit():
        return parts[2][:4]
    return ""


def _preset_for(kind, year):
    """這類段落愛用佗一个 preset 重切；免重切回空。"""
    if kind in AREA_PRESETS:
        return AREA_PRESETS[kind]
    if kind in SUNKEN:
        name, until = SUNKEN[kind]
        if year and year < until:
            return name
    return ""


def text_rows(frames, white=200, dark=80, reach=4, min_share=0.02):
    """幾格仝一區ê畫面 → 字幕佔ê列（頭, 尾+1）；看無穩定ê字回 None。

    字是白字烏框，所以算「白點、邊仔 reach 點內有烏點」：日頭照ê樹葉
    嘛白，毋過無烏框（20211124_328 晚間，干焦算白點規條帶攏超過）。
    逐列取中位數：背景會變，字ê位置無變，中位數干焦留字。取上濟彼段
    連紲ê列。
    """
    import numpy as np
    profiles = []
    for frame in frames:
        rgb = np.asarray(frame)
        bright = rgb.min(axis=2) > white
        shade = rgb.max(axis=2) < dark
        near = np.zeros_like(shade)
        for step in range(-reach, reach + 1):
            near |= np.roll(shade, step, axis=0)
            near |= np.roll(shade, step, axis=1)
        profiles.append((bright & near).mean(axis=1))
    if not profiles:
        return None
    median = np.median(np.stack(profiles), axis=0)
    best, best_mass = None, 0.0
    start = None
    for index in range(len(median) + 1):
        inside = index < len(median) and median[index] > min_share
        if inside and start is None:
            start = index
        elif not inside and start is not None:
            mass = float(median[start:index].sum())
            if mass > best_mass:
                best, best_mass = (start, index), mass
            start = None
    return best


def _probe(video, lo, hi):
    """彼段內底平均抽幾格，干焦留量字幕高低彼條帶。"""
    import subprocess
    import numpy as np
    x0, x1 = PROBE_COLS
    w, h = x1 - x0, PROBE_BOTTOM - PROBE_TOP
    frames = []
    for index in range(PROBE_FRAMES):
        at = lo + (hi - lo) * (index + 0.5) / PROBE_FRAMES
        done = subprocess.run(
            ["ffmpeg", "-nostdin", "-v", "error", "-ss", "%.3f" % at,
             "-i", video, "-frames:v", "1",
             "-vf", "crop=%d:%d:%d:%d" % (w, h, x0, PROBE_TOP),
             "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
            stdin=subprocess.DEVNULL, capture_output=True)
        if len(done.stdout) == w * h * 3:
            frames.append(np.frombuffer(done.stdout, np.uint8)
                          .reshape(h, w, 3))
    return frames


def _fitted(work, name, rows, lo, presets):
    """量著ê列 → 這段專用ê preset 檔；回檔名佮 region。"""
    layout = json.loads(json.dumps(presets[name]))
    top = PROBE_TOP + rows[0] - PAD
    height = rows[1] - rows[0] + 2 * PAD
    layout["region"][1] = top
    layout["region"][3] = height
    layout["lines"][0]["h"] = height
    layout["mask"]["compare_rows"] = [PAD - 2, height - PAD + 2]
    target = os.path.join(paths.shots_dir(work),
                          "recut-presets-%06d.json" % int(lo))
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8") as handle:
        json.dump({name: layout}, handle, ensure_ascii=False, indent=2,
                  sort_keys=True)
    return target, layout["region"]


def _recut(video, start, duration, out, preset, presets=None):
    """切一段，回粗切時間軸ê路徑。"""
    splice.recut(video, start, duration, out,
                 presets=presets or paths.ENGINE_PRESETS,
                 preset=preset, venv=paths.venv_py())
    return datadirs.coarse_cues(out)


def _refine(video, coarse, preset, presets=None):
    """精修一段，回精修時間軸ê路徑。"""
    from scripts.news import refine_cues
    layout = refine_cues._preset_or_die(presets or paths.ENGINE_PRESETS,
                                        preset)
    refine_cues.refine_episode(video, coarse, preset=layout)
    return refine_cues.refined_target(coarse)


def _presets():
    with open(paths.ENGINE_PRESETS, encoding="utf-8") as handle:
        return json.load(handle)


def run(work, video, recut=_recut, refine=_refine, presets=None,
        probe=None):
    """重切這集ê帶外段；回重切幾段。無帶外段就無寫任何物件。"""
    timeline = paths.cues_to_read(work)
    if timeline is None:
        raise PipelineError("%s 無時間軸" % work)
    table = segments.read(paths.segments_file(work))
    year = _year(work)
    targets = []
    for row in table:
        if _preset_for(row["類型"], year):
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
        name = _preset_for(kind, year)
        lo, hi = float(row["起秒"]), float(row["迄秒"])
        fresh = os.path.join(paths.shots_dir(work), "recut-%06d" % int(lo))
        region = (presets.get(name) or {}).get("region")
        rows = None
        if probe is not None and kind in SUNKEN:
            rows = text_rows(probe(video, lo, hi))
        if rows:
            fitted, region = _fitted(work, name, rows, lo, presets)
            refined = refine(video, recut(video, lo, hi - lo, fresh, name,
                                          presets=fitted),
                             name, presets=fitted)
        else:
            refined = refine(video, recut(video, lo, hi - lo, fresh, name),
                             name)
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
    done = run(args.work, args.video, probe=_probe)
    print("%s：重切 %d 段帶外段落" % (args.work, done))
    return 0


if __name__ == "__main__":
    sys.exit(main())
