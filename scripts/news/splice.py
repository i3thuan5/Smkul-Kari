#!/usr/bin/env python3
"""重切一段、接轉去時間軸ê純算術，`rescan_band` 佮 `segment_recut` 公家。

重切一段會改變彼段有幾條 cue，**後壁逐條攏重新編號**。`rescan_band`
是讀完字了後ê補救（範圍外ê TSV 愛照 `mapping` 徙號碼），
`segment_recut` 是讀字進前做（猶無 TSV，重新編號無代價）；兩爿切、接
ê算術仝款，所以囥佇遮，一份測試（`tests/news/test_rescan_band.py`）。
"""
import json
import os
import shutil
import subprocess
import sys

from scripts import datadirs
from scripts.errors import PipelineError


def splice(cues, lo, hi, replacement):
    """`cues` with [lo, hi] (1-based, inclusive) replaced, renumbered 1..N.

    Times are carried through untouched -- the replacement's own times come
    from the re-cut and are already absolute, because `ocr-cli cues` was
    given `--start` and keeps real seconds.
    """
    if lo < 1 or hi > len(cues) or hi < lo:
        raise PipelineError("範圍 %d–%d 佮 %d 條 cue 無合" % (lo, hi, len(cues)))
    if not replacement:
        raise PipelineError(
            "換入去ê是空ê。「這段無字幕」是一項結論，愛家己講出來，"
            "袂使當做重切ê結果恬恬做出來")
    out = []
    for cue in cues[:lo - 1]:
        out.append(dict(cue))
    for cue in replacement:
        out.append(dict(cue))
    for cue in cues[hi:]:
        out.append(dict(cue))
    for number, cue in enumerate(out, 1):
        cue["index"] = number
    return out


def mapping(total, lo, hi, count):
    """{old cue number: new cue number} for the cues that survive.

    Cues inside [lo, hi] are gone -- they were replaced -- so they have no
    entry at all rather than a `None`, which makes "was it dropped?" a
    membership test the callers cannot get subtly wrong.
    """
    shift = count - (hi - lo + 1)
    out = {}
    for old in range(1, total + 1):
        if lo <= old <= hi:
            continue
        out[old] = old if old < lo else old + shift
    return out


def remap_rows(rows, moves):
    """[(cue, text)] renumbered by `moves`; rows of dropped cues are gone.

    Text is passed through byte for byte -- a reader's trailing space or an
    embedded tab is what they saw on screen, and this step has no business
    tidying it.
    """
    out = []
    for cue, text in rows:
        if cue not in moves:
            continue
        out.append((moves[cue], text))
    out.sort(key=lambda row: row[0])
    return out


def splice_time(cues, lo, hi, replacement):
    """`cues` 內底中點落佇 [lo, hi) 秒ê換做 `replacement`，重編 1..N。

    照時間毋是照號碼：帶外段落是段落表講ê秒數，彼段內底原本有幾條
    cue、甚至有無 cue 攏無一定。換入去ê是空ê就是彼段拿掉——帶外段落
    本底照字幕帶切出來ê（單字卡、花字）嘛毋是欲收ê。
    """
    out = []
    for item in cues:
        middle = (float(item["start"]) + float(item["end"])) / 2.0
        if lo <= middle < hi:
            continue
        out.append(dict(item))
    for item in replacement:
        out.append(dict(item))
    out.sort(key=lambda item: (float(item["start"]), float(item["end"])))
    for number, item in enumerate(out, 1):
        item["index"] = number
    return out


def recut(video, start, duration, out, region=None, presets=None,
          preset=None, venv=None, runner=subprocess.run, keep=False):
    """對一段影片重新切 cue，回彼段ê cue（時間是規集ê絕對秒數）。

    區域用 `region`（x,y,w,h），抑是 `presets`＋`preset`。讀ê是切 cue
    寫ê粗切階段 `1-cues/cues.json`——本底讀 `<out>/cues.json`，分階段
    了後彼个檔永遠無，重切就倒。`keep` 毋清掉 `out`（測試用）。
    """
    if os.path.exists(out) and not keep:
        shutil.rmtree(out)
    python = venv or sys.executable
    cmd = [python, "-m", "scripts.ocr.cli", "cues", video, "-o", out,
           "--start", "%.3f" % start, "--duration", "%.3f" % duration,
           "--no-sheets"]
    if region:
        cmd += ["--region", region]
    if preset:
        cmd += ["--presets", presets, "--preset", preset]
    env = dict(os.environ, PYTHONPATH=".")
    with open(os.devnull) as devnull:
        done = runner(cmd, stdin=devnull, env=env, capture_output=True,
                      text=True)
    if done.returncode:
        raise PipelineError("重切失敗：%s" % done.stderr[-400:])
    with open(datadirs.coarse_cues(out), encoding="utf-8") as handle:
        return json.load(handle)["cues"]
