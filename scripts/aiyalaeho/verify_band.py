#!/usr/bin/env python3
"""Confirm an episode really carries this programme's two-row band.

    python3 -m scripts.aiyalaeho.verify_band VIDEO          # 量了印出來
    python3 -m scripts.aiyalaeho.verify_band VIDEO --quiet   # 干焦結論

WHY THIS EXISTS
---------------
Cutting an episode against the wrong strip of pixels costs hours and looks
completely normal until somebody opens a contact sheet. The news side has
the same guard, but nothing of its judgement transfers: it looks for a
dialogue plateau and the red lower-third's top edge, and this programme
has neither. It paints two rows of text on an opaque yellow-to-red band
across the foot of the frame, and that band is what gets measured here.

WHAT IS MEASURED, AND WHY THAT
------------------------------
Two things, both over a sampled window in the middle of the episode:

  the band   per row, the share of pixels that are band-coloured
             (saturated, and red >= green >= blue). The band is opaque and
             full width, so a row it covers scores far higher than a row
             above it does. Measured as the ratio of the region's lower
             rows to the rows just above the region: 2.0 to 22 where the
             band is up, 0.8 to 1.0 where there is none (88 with no
             subtitles at all, and a news episode fed in on purpose). The
             low end of that range is 081, whose studio above the band is
             warm enough to lift the denominator; its two rows sit
             squarely in their slots all the same. The threshold sits at
             1.5, between 081 and the highest negative.

  the rows    the text mask's ink per row, but only over the rows the band
             covers. This is the part that took a wrong turn first: 083
             carries one Chinese row and a shorter band, and the bright
             studio picture ABOVE its band read as a 48-row block of ink
             that no slot could hold. Picture is not subtitle, and the
             band is what tells them apart.

WHAT THE VERDICT MEANS
----------------------
  ok         every text row found sits inside the slot the preset
             declares for it, one row per slot. This is the only thing
             that returns ok, and the band's colour does not gate it.
             Cut it.
  no-band    no band in the sampled window, and no text-row-shaped ink
             either. Three episodes are like this -- 88, 90 and 98 are
             marked 無字幕 and carry none -- so this is not a failure:
             cutting yields no cues and the episode is delivered with an
             empty SRT. Reported all the same, because it is also what a
             wrong file would look like if it happened to be featureless.
  mismatch   either the band is there and a text row falls outside its
             slot, or there is no band but there IS structured ink where
             the rows should be. A news episode measured here lands in the
             second: two blocks of ink from the red lower-third and its
             name supers, and no band. Do not cut; look at it.
"""
import argparse
import json
import os
import sys

import numpy as np

from scripts.aiyalaeho import paths
from scripts.ocr import cuelib
from scripts.errors import PipelineError

# Where to sample: past the opening titles, long enough that a stretch
# with nobody talking does not decide it.
START = 300.0
DURATION = 240.0
FPS = 1.0

# --- 帶ê判準（量過ê） --------------------------------------------------
# 一粒像素敢若是彼條帶：有飽和、閣是黃到紅這爿ê色。
BAND_SATURATION = 60
BAND_BRIGHT = 120
# 一逝敢是帶：規逝有這个比例以上ê帶色像素。
BAND_ROW = 0.5
# 區內下沿 / 區外頂懸ê比。**這馬是報告用ê，無咧做判定。**
#
# 本底伊是閘門，門檻 2.5，用三集校ê（8、15、22）。整批走到第三集就
# 破功：081 兩逝字幕明明各佇家己ê槽內（904..929、953..990），帶ê比
# 煞才 2.0（伊帶頂懸是燒色ê攝影棚，分母大起來），予人誤擋；079 是
# 2.8，嘛差一點。量過ê分布：有帶 2.0–22、無帶 0.8–1.0。
#
# 換做「字幕逝敢有囥佇槽內」做主證據了後，這个數字就免閣掠門檻——
# 一个無咧做判定ê量測，就袂判毋著。留咧是予人看ê證據。
BAND_SCORE = 1.5
# 比ê時提ê兩塊：區ê下沿，佮區頂懸外口彼幾逝。
LOWER_ROWS = 24
ABOVE_ROWS = 46
ABOVE_GAP = 16

# --- 文字逝ê判準（量過ê） ----------------------------------------------
# 一逝字幕ê平均 ink：量著 83–453；雜訊（無字幕ê集）8–37。
INK_FLOOR = 50.0
# 逐逝字ê懸度：量著 17–37 列。傷薄ê是雜線，傷厚ê是規塊圖。
ROW_MIN = 8
JOIN = 6
# 無帶ê時，欲分「這集本底就無字幕」佮「版型毋著」：看剖面ê對比
# （上懸ê逝 / 中位數）。量著ê：無字幕ê集 1.12（88，亮攝影棚）佮 1.35
# （90），新聞版型 4.04——差三倍，門檻园佇中央。
CONTRAST = 2.0


def slots_of(preset):
    """[(top, bottom)…] absolute rows, from the preset's declared lines."""
    lines = preset.get("lines") or []
    if len(lines) != 2:
        raise PipelineError(
            "這條檢查是予兩逝ê版型用ê，preset 宣告ê是 %d 逝——"
            "新聞彼款一逝ê用 scripts.news.verify_band" % len(lines))
    top = preset["region"][1]
    out = []
    for line in lines:
        out.append((top + line["y"], top + line["y"] + line["h"]))
    return out


def band_fraction(rgb):
    """Per row, the share of pixels that look like the band."""
    frame = rgb.astype(int)
    red = frame[:, :, 0]
    green = frame[:, :, 1]
    blue = frame[:, :, 2]
    high = frame.max(axis=2)
    low = frame.min(axis=2)
    band = ((high - low >= BAND_SATURATION) & (red >= green)
            & (green >= blue) & (high >= BAND_BRIGHT))
    return band.mean(axis=1)


def measure(video, region, spec, start=START, duration=DURATION, fps=FPS):
    """(band share per row, ink per row) over a window, both means.

    The probed region is grown upward so the rows just above the band get
    measured too: the band's own share means nothing without them, and a
    layout whose band starts higher shows up as a band that never ends.
    """
    probe = cuelib.normalize_region(
        (region[0], region[1] - ABOVE_ROWS - ABOVE_GAP, region[2],
         region[3] + ABOVE_ROWS + ABOVE_GAP))
    band = np.zeros(probe[3])
    ink = np.zeros(probe[3])
    frames = 0
    for _stamp, rgb in cuelib.stream_region(video, probe, fps=fps,
                                            start=start, duration=duration):
        band += band_fraction(rgb)
        ink += cuelib.text_mask(rgb, spec).sum(axis=1)
        frames += 1
    if not frames:
        raise PipelineError("%s 解碼無半格" % video)
    return band / frames, ink / frames, probe[1], frames


def band_score(band, probe_top, region):
    """How much more band-coloured the region's foot is than what is above.

    Measured over 240 sampled frames: 8.0 (164), 15 (068) and 22 (083)
    where the band is up; 0.85 for an episode carrying no subtitles and
    0.8 for a news episode fed to this preset.
    """
    band = np.asarray(band, dtype=float)
    foot = region[1] + region[3]
    inside = band[foot - LOWER_ROWS - probe_top:foot - probe_top].mean()
    above_hi = region[1] - ABOVE_GAP
    outside = band[above_hi - ABOVE_ROWS - probe_top:
                   above_hi - probe_top].mean()
    if outside <= 0.01:
        outside = 0.01
    return float(inside / outside)


def band_extent(band, probe_top, region):
    """(first, last + 1) absolute rows the band covers inside the region.

    083's band starts some 60 rows below the region's top -- it carries
    one row of text, not two -- and the bright studio picture above it is
    not subtitle. Rows outside this are not looked at.
    """
    band = np.asarray(band, dtype=float)
    lo = region[1] - probe_top
    hi = lo + region[3]
    window = band[lo:hi]
    if not len(window) or window.max() <= 0:
        return region[1], region[1] + region[3]
    limit = window.max() * BAND_ROW
    rows = np.where(window >= limit)[0]
    if not len(rows):
        return region[1], region[1] + region[3]
    return int(rows[0]) + region[1], int(rows[-1]) + 1 + region[1]


def runs_of(ink, probe_top, lo, hi, floor=INK_FLOOR, join=JOIN,
            min_run=ROW_MIN):
    """[(first row, last row + 1)…] of text-shaped ink between lo and hi.

    The floor is absolute, not a share of the busiest row. A share does
    not work here: the Formosan row carries two to three times the ink of
    the Chinese one (measured 219-453 against 83-143), so a relative floor
    drops the Chinese row of a quiet episode -- it dropped 164's -- while
    letting a bright picture through.
    """
    inky = []
    for row in range(lo, hi):
        index = row - probe_top
        if 0 <= index < len(ink) and ink[index] >= floor:
            inky.append(row)
    if not inky:
        return []
    runs = []
    start = previous = inky[0]
    for row in inky[1:]:
        if row - previous > join:
            runs.append((start, previous + 1))
            start = row
        previous = row
    runs.append((start, previous + 1))

    out = []
    for run_lo, run_hi in runs:
        if run_hi - run_lo >= min_run:
            out.append((run_lo, run_hi))
    return out


def contrast_of(ink, probe_top, region):
    """The ink profile's peak over its median, inside the region.

    Flat means nothing is painted there: an episode with no subtitles
    measures 1.1 to 1.4 whether its studio is bright (88) or dark (90). A
    news episode fed to this preset measures 4.0 -- its red lower-third and
    name supers are a block of ink where our band's rows would be.
    """
    ink = np.asarray(ink, dtype=float)
    lo = region[1] - probe_top
    window = ink[lo:lo + region[3]]
    if not len(window):
        return 0.0
    middle = float(np.median(window))
    return float(window.max()) / max(middle, 1.0)


def rows_fit(runs, slots):
    """(True, []) when each text row sits in a slot of its own.

    This is the primary evidence, and it is deliberately the only thing
    that can return "ok". The band's colour used to gate this, and that
    was wrong twice over: the threshold had been calibrated on three
    episodes, and 081 -- whose two rows sit squarely in their slots --
    scored 2.0 against a 2.5 bar because the studio above its band is
    warm enough to lift the denominator. A measurement that decides
    nothing cannot mis-decide; the colour is reported and left at that.
    """
    problems = []
    taken = {}
    for lo, hi in runs:
        home = None
        for index, (slot_lo, slot_hi) in enumerate(slots):
            if slot_lo <= lo and hi <= slot_hi:
                home = index
        if home is None:
            problems.append(
                "字幕逝 y=%d..%d 無囥佇任何一个宣告ê槽內（槽是 %s）"
                % (lo, hi, _say(slots)))
        elif home in taken:
            problems.append(
                "y=%d..%d 佮 y=%d..%d 落佇仝一个槽（%d..%d）——"
                "一个槽干焦囥一逝字"
                % (taken[home][0], taken[home][1], lo, hi,
                   slots[home][0], slots[home][1]))
        else:
            taken[home] = (lo, hi)
    return (bool(runs) and not problems), problems


def verdict(score, runs, slots, region, contrast=0.0):
    """(state, [problem…]) -- see the module docstring for the states."""
    fits, problems = rows_fit(runs, slots)
    if fits:
        return "ok", []

    # 逐逝無囥佇槽內（抑是連一逝都無）。剖面ê對比講伊是佗一款：
    # 平坦ê是這集本底就無字幕（88 彼款亮攝影棚，規區一塊平ê墨水；
    # 90、98 是連墨水都無），有對比ê是別个版型ê物件囥佇遮（新聞ê
    # 紅帶佮名牌）。
    if contrast >= CONTRAST:
        problems.append(
            "剖面對比 %.1f 倍中位數（帶ê色 %.1f 倍）——區內有物件，"
            "毋過毋是這个版型ê兩逝字幕，莫切" % (contrast, score))
        return "mismatch", problems
    return "no-band", []


def _say(pairs):
    parts = []
    for lo, hi in pairs:
        parts.append("%d..%d" % (lo, hi))
    return "、".join(parts)


def load_preset(name, presets_path=None):
    path = presets_path or paths.ENGINE_PRESETS
    with open(path, encoding="utf-8") as handle:
        presets = json.load(handle)
    if name not in presets:
        raise PipelineError("無 %r 這个 preset（有ê是：%s）"
                            % (name, "、".join(sorted(presets))))
    return presets[name]


def check(video, preset, start=START, duration=DURATION):
    """(state, problems, report) for one episode."""
    region = cuelib.normalize_region(preset["region"])
    spec = cuelib.MaskSpec.from_dict(preset.get("mask", {}))
    band, ink, probe_top, frames = measure(video, region, spec, start,
                                           duration)
    score = band_score(band, probe_top, region)
    lo, hi = band_extent(band, probe_top, region)
    if score < BAND_SCORE:
        lo, hi = region[1], region[1] + region[3]
    runs = runs_of(ink, probe_top, lo, hi)
    slots = slots_of(preset)
    contrast = contrast_of(ink, probe_top, region)
    state, problems = verdict(score, runs, slots, region, contrast)
    return state, problems, {"score": score, "band": (lo, hi), "runs": runs,
                             "slots": slots, "frames": frames,
                             "contrast": contrast}


DEFAULT_PRESET = "aiyalaeho-bilingual"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("video")
    ap.add_argument("--preset", default=DEFAULT_PRESET)
    ap.add_argument("--presets", default="")
    ap.add_argument("--start", type=float, default=START)
    ap.add_argument("--duration", type=float, default=DURATION)
    ap.add_argument("--quiet", action="store_true", help="干焦印結論")
    args = ap.parse_args(argv)

    preset = load_preset(args.preset, args.presets or None)
    state, problems, report = check(args.video, preset, args.start,
                                    args.duration)
    name = os.path.basename(args.video)
    if not args.quiet:
        print("%s  preset=%s  取樣 %d 格"
              % (name, args.preset, report["frames"]))
        print("帶：%.1f 倍（愛 %.1f 以上），罩著 y=%d..%d；槽 %s"
              % (report["score"], BAND_SCORE, report["band"][0],
                 report["band"][1], _say(report["slots"])))
        print("字幕逝：%s；剖面對比 %.1f 倍中位數"
              % (_say(report["runs"]) or "無",
                 report["contrast"]))
    for line in problems:
        print("PROBLEM", line)
    if state == "no-band":
        print("NO-BAND  %s（這集看起來無字幕，切出來會是 0 條 cue）" % name)
        return 0
    print("%s  %s" % ("MISMATCH" if state == "mismatch" else "OK", name))
    return 1 if state == "mismatch" else 0


if __name__ == "__main__":
    sys.exit(main())
