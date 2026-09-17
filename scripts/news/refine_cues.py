#!/usr/bin/env python3
"""Refine cue boundaries from the 0.2s coarse grid to the native frame rate.

    python3 -m scripts.news.refine_cues VIDEO CUES_JSON            # in place
    python3 -m scripts.news.refine_cues VIDEO CUES_JSON --dry-run  # report

The coarse pass judged one frame per 0.2s, so every boundary lies within
+/-0.2s of the true switch. The judging itself -- which frames are which
side, where the switch is -- lives in `scripts.ocr.refine` and reads every
window of the episode in one ffmpeg run at the source's own frame rate.
This file is the news side of it: which preset, the MAX_SHIFT acceptance
check, and writing the result.

Atomicity: an episode is validated in full -- every refined boundary within
MAX_SHIFT of its coarse value, starts before ends, no overlap -- before its
timeline is written, and the write itself goes through a temporary file.
Any violation, or the decoder failing partway, names the episode and
leaves nothing written. Boundaries kept at their coarse value are counted
by reason: no frames (file edge, short window) or unclear (the picture).

The manifest gains `"refined": true` and (via ffprobe, since the coarse
manifests never stored it) `"duration"`, which the SRT padding rule needs.
"""
import argparse
import json
import os
import subprocess
import sys

from scripts.news import paths
from scripts.ocr import band as detector
from scripts.ocr import cuelib
from scripts.ocr import decode
from scripts.ocr import refine
from scripts import lowpri
from scripts.errors import PipelineError

MAX_SHIFT = 0.2


def probe_duration(video):
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", video], capture_output=True, text=True)
    try:
        return float(proc.stdout.strip())
    except ValueError:
        raise PipelineError("cannot probe duration of %s" % video)


def _refine_boundaries(video, manifest, duration, preset=None,
                       threads=decode.DEFAULT_THREADS):
    """Refine every boundary; returns the new times and the tallies.

    The spec is built from two places on purpose. Thresholds and the
    measured band rows come from the manifest, because they are properties
    of this one episode and the timeline is the only place they exist. The
    sampling factor and the compare window come from the layout preset,
    because they are properties of the layout and the timeline deliberately
    does not carry them (ruled 2026-09-09).
    """
    cues = manifest["cues"]
    region = manifest["region"]
    spec = cuelib.MaskSpec.from_dict(manifest.get("mask", {}))
    if preset is not None:
        declared = cuelib.segment_spec(preset)
        spec.scale = declared.scale
        spec.compare_cols = declared.compare_cols
        spec.compare_rows = declared.compare_rows
    seg = manifest.get("segmenter", {})
    min_ink = cuelib.effective_min_ink(seg.get("min_ink", 120), spec, region)
    change = seg.get("change", 0.35)

    boundaries = refine.boundaries_of(cues)
    found = refine.refine_all(video, region, spec, min_ink, change,
                              boundaries, duration, threads)

    new_start = {}
    new_end = {}
    kept = {refine.NO_FRAMES: 0, refine.UNCLEAR: 0}
    shifts = []
    problems = []
    for (positions, kind, t0), (t, reason) in zip(boundaries, found):
        if t is None:
            kept[reason] += 1
            continue
        if abs(t - t0) > MAX_SHIFT + 1e-9:
            problems.append("cue %s %s: shift %.3fs exceeds %.1fs"
                            % (cues[positions[0]]["index"], kind,
                               t - t0, MAX_SHIFT))
            continue
        shifts.append(t - t0)
        if kind == "start":
            new_start[positions[0]] = t
        elif kind == "end":
            new_end[positions[0]] = t
        else:
            new_end[positions[0]] = t
            new_start[positions[1]] = t
    return new_start, new_end, kept, shifts, problems


def _check_result(result, cues, problems):
    """Atomicity gate: starts before ends, no overlap, or nothing moves."""
    for i, (start, end) in enumerate(result):
        if start >= end:
            problems.append("cue %s: start %.3f >= end %.3f"
                            % (cues[i]["index"], start, end))
        if i and result[i - 1][1] > start + 1e-9:
            problems.append("cue %s overlaps its predecessor"
                            % cues[i]["index"])


def refined_target(cues_path):
    """Where this episode's refined timeline belongs, given what we read.

    The **input's layout decides**, which is what lets the split land while
    older work dirs are still around. A timeline read out of `1-cues/` is
    the new shape, so the refinement goes beside it in `3-refined/` and the
    coarse one is never touched again. A flat `<work>/cues.json` is the
    pre-split shape, and its readers -- the migration has not swept them,
    and the 開會了 side names that path directly -- expect the refinement
    in that same file, so it keeps being rewritten in place. Guessing the
    other way round would leave those episodes silently delivering coarse
    0.2s boundaries with nothing reporting it.
    """
    folder = os.path.dirname(cues_path)
    if os.path.basename(folder) == paths.COARSE_STAGE:
        return paths.refined_cues(os.path.dirname(folder))
    return cues_path


def write_refined(cues_path, manifest):
    """Write the refined timeline where `refined_target` says; return it."""
    target = refined_target(cues_path)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    temporary = target + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2,
                  sort_keys=True)
    os.replace(temporary, target)
    return target


def refine_episode(video, cues_path, preset=None, dry_run=False,
                   threads=decode.DEFAULT_THREADS):
    with open(cues_path, encoding="utf-8") as handle:
        manifest = json.load(handle)
    cues = manifest["cues"]
    duration = probe_duration(video)
    episode = os.path.basename(cues_path)[:-5]
    if episode == "cues":
        # `<work>/1-cues/cues.json`: the work dir names the episode
        episode = os.path.basename(os.path.dirname(os.path.dirname(
            os.path.abspath(cues_path))))
        if episode.endswith(paths.WORK_EXT):
            episode = episode[:-len(paths.WORK_EXT)]

    try:
        new_start, new_end, kept, shifts, problems = _refine_boundaries(
            video, manifest, duration, preset, threads)
    except RuntimeError as exc:
        raise PipelineError("%s：精修讀影片失敗，時間軸無寫：%s"
                            % (episode, exc))
    refined = len(shifts)
    kept_total = kept[refine.NO_FRAMES] + kept[refine.UNCLEAR]

    result = []
    for i, cue in enumerate(cues):
        start = new_start.get(i, cue["start"])
        end = new_end.get(i, cue["end"])
        result.append((round(start, 3), round(end, 3)))
    _check_result(result, cues, problems)

    stats = {
        "episode": episode,
        "boundaries": kept_total + refined + len(problems),
        "refined": refined,
        "kept_coarse": kept_total,
        "kept_no_frames": kept[refine.NO_FRAMES],
        "kept_unclear": kept[refine.UNCLEAR],
        "max_shift": round(max(map(abs, shifts)), 3) if shifts else 0.0,
        "mean_shift": (round(sum(map(abs, shifts)) / len(shifts), 3)
                       if shifts else 0.0),
        "duration": round(duration, 3),
    }

    if problems:
        for line in problems:
            print("FAIL:", line)
        raise PipelineError("%d 个邊界超出容允範圍；cues.json 無改"
                            % len(problems))

    if not dry_run:
        for i, cue in enumerate(cues):
            cue["start"], cue["end"] = result[i]
        manifest["refined"] = True
        manifest["duration"] = round(duration, 3)
        write_refined(cues_path, manifest)
    return stats


def _preset_or_die(presets_path, name):
    """The named layout, or a refusal that says which flag is missing."""
    if not name:
        raise PipelineError(
            "愛用 --preset 講明這集是佗一款版型切ê（配 --presets 指定"
            "檔案）。精修若用佮切 cue 無仝ê判準，邊界會恬恬走精，"
            "報表頂懸看起來猶原正常")
    if not presets_path:
        raise PipelineError("--preset %r 需要 --presets 指定 presets.json"
                            % name)
    presets = detector.load_presets(presets_path)
    if name not in presets:
        raise PipelineError("presets.json 內底無 %r（有ê是：%s）"
                            % (name, ", ".join(sorted(presets))))
    return presets[name]


def main():
    lowpri.be_nice()   # 長時間ê重工，莫kā機器食牢去
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("video")
    ap.add_argument("cues", help="cues.json to refine in place")
    ap.add_argument("--presets", help="path to the caller's presets.json")
    ap.add_argument("--preset",
                    help="name the layout this episode was cut with; refining "
                         "has to judge the band the same way cutting did")
    ap.add_argument("--dry-run", action="store_true",
                    help="report the shifts, write nothing")
    ap.add_argument("--threads", type=int, default=decode.DEFAULT_THREADS,
                    help="ffmpeg decode threads (default %d)"
                         % decode.DEFAULT_THREADS)
    args = ap.parse_args()
    # 版型先驗，才免路徑ê錯誤khàm去真正ê問題。
    # 無版型就用佮切 cue 無仝ê判準，煞閣報一个整齊ê數字——恬恬走精
    # 是這條規矩beh擋ê物件，佮 region「呼叫端指定、袂當家己臆」仝款。
    preset = _preset_or_die(args.presets, args.preset)
    # cues.json 是就地改寫的，指錯目標就毀掉一集的時間軸
    args.video = paths.check_under(args.video, "video")
    args.cues = paths.check_under(args.cues, "cues")
    stats = refine_episode(args.video, args.cues, preset=preset,
                           dry_run=args.dry_run, threads=args.threads)
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    sys.exit(main())
