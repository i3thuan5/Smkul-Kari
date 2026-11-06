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


def seconds_label(lo, hi):
    """「2004.602–2249 秒」：`name_area` 另存名字用的範圍寫法。"""
    texts = []
    for value in (lo, hi):
        texts.append(("%.3f" % float(value)).rstrip("0").rstrip("."))
    return "%s–%s 秒" % (texts[0], texts[1])


def name_area(areas, kept, kind, setting, label):
    """這次重切的設定記在 `areas` 的哪一格 → (新的 areas, 名字)。

    一格一個名字，本來名字就是段落類型。同一類型第二次用別種設定切
    （20210714_195_晚間 第一次 x 420、這輪 x 392），範圍外 `kept` 還有
    cue 用舊設定的話，舊的留原名，這次的另存「類型（label）」，新 cue
    要標回傳的名字；已經有一格是同一個設定就沿用那格。範圍外沒有 cue
    再用舊設定，就直接換掉（留著只會誤導）。傳進來的 `areas` 不動。
    """
    out = dict(areas or {})
    have = out.get(kind)
    if have is None or have == setting:
        out[kind] = setting
        return out, kind
    still_used = False
    for item in kept:
        if item.get("area") == kind:
            still_used = True
            break
    if not still_used:
        out[kind] = setting
        return out, kind
    for name in sorted(out):
        if name.startswith(kind + "（") and out[name] == setting:
            return out, name
    base = "%s（%s）" % (kind, label)
    name = base
    number = 1
    while out.get(name) is not None and out[name] != setting:
        number += 1
        name = "%s-%d" % (base, number)
    out[name] = setting
    return out, name


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
        # 輸出干焦是記錄：中文字切一半ê位元組換做替代字元，毋通規段倒。
        done = runner(cmd, stdin=devnull, env=env, capture_output=True,
                      text=True, errors="replace")
    if done.returncode:
        raise PipelineError("重切失敗：%s" % done.stderr[-400:])
    with open(datadirs.coarse_cues(out), encoding="utf-8") as handle:
        return json.load(handle)["cues"]
