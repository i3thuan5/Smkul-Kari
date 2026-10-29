#!/usr/bin/env python3
"""重播集照首播搬時間軸和字：不必重讀，用位移移植。

    python3 -m scripts.news.rebroadcast_port measure <首播> <重播> --range LO HI
    python3 -m scripts.news.rebroadcast_port prepare <首播> <重播> \\
        (--range LO HI | --unit 秒數) [--work 工作檔] [--snaps 快照目錄] \\
        [--out DIR] [--offset 秒]
    python3 -m scripts.news.rebroadcast_port frames  <plan.json>... \\
        --side source|target --video V
    python3 -m scripts.news.rebroadcast_port check   <plan.json>
    python3 -m scripts.news.rebroadcast_port apply   <plan.json> --lock L \\
        --fixes manual-fixes.tsv --snaps 快照目錄 [--pending pending-fixes.txt] \\
        [--accept 清單]
    python3 -m scripts.news.rebroadcast_port family  <展開工作檔>...

同一段節目（島語時間、部落信箱、專題、MV）在好幾集重播，首播修好的
cue 和字要搬到重播集。重播是同一段畫面，不必整段重新 OCR：

1. `measure`／`prepare` 用兩集都只出現一次、5 字以上的句子當錨點，用
   **起點**算位移（不取整數格）；whisper 段落邊界是第二種、較粗的證據。
   p50 在一格內、八成以上在兩格內才算逐格一致；剪接、剪法不同都拒絕，
   `--offset` 只能補位移、蓋不掉這兩種拒絕。
2. `prepare` 只讀 Kari-SRT，寫輸出目錄，依重播那段的狀態自動選做法：
   - 整段搬（whole）：重播那段原本沒讀到（有字的 cue 不到首播的兩成五），
     或兩集切法設定（areas 的 preset／region）不同而且是**首播**重切過
     （首播最早那份快照的設定跟現在不同，重播現在還是首播重切前那種）。
     首播那段整段換進去（加位移、清掉 `images`），範圍兩端重播自己的
     內容先縮出去，改號照每條 cue 的身分。
   - 不搬、整件要人判（status ask）：切法設定不同而**重播**自己重切過，
     或判不出是哪一集重切過。
   - 分區搬（zone）：其他情形（含兩集都沒重切過、本來切法就不同）。首播
     修改前的快照 → 首播現在，在這段節目裡有差的 cue 併成「區」，每區往
     外擴到安全邊（兩集在那一點都沒有字跨過去）；區內整批換成首播現在的
     （起迄也用首播的，搬進來的 cue 標首播的切法設定），區外重播一律不
     動。區內重播原本的字跟首播修改前、修改後都不同的，或首播這區自己
     就有重疊的，那一區列要人判、不套，其他區照套。
   只擋這次新造成的重疊或倒置，重播原本就有的記說明。
3. `frames`／`check` 抽兩集同一位置的格，遮掉台標、天氣框、人名字卡
   比灰階平均絕對差（MAD），逐格驗收，不花 model token。以「同位移是
   局部最小」為主、相對底值的絕對值為輔（跨年代底值本來就不同）。內部
   點放在這次會改的地方（分區搬每個套用區至少一點），邊界點放在套用區
   外緣（整段搬是被換的 cue 外側），節目範圍頭尾 4 秒內不取。
4. `apply` 是唯一會寫 Kari-SRT 的指令：拿 `--lock`，sha 相符、像素驗收
   通過才寫；先替重播拍快照（標籤 x＋首播名前 12 字，已有就加
   `-r<MMDDHHMM>`），新檔先在暫存目錄做好再換進去，任何一步失敗整集
   回滾（含快照和 `.part` 暫存檔）。
5. `family` 照依賴排序（A→B 先於 B→C），真的互相依賴的集用強連通分量
   縮成一點、列成循環交給人，環外照排；沒有工作檔的組合、不是移植的工作
   檔（`--from-r3fix1027r2x` 這種）列出來。

設計與量測：見 scripts/news/README.md〈重播移植〉。
"""
import argparse
import bisect
import collections
import datetime
import difflib
import fcntl
import glob
import hashlib
import json
import math
import os
import re
import shutil
import signal
import statistics
import subprocess
import sys
import tempfile
import threading

from scripts import datadirs
from scripts.errors import PipelineError
from scripts.news import offband_backfill
from scripts.news import paths
from scripts.news import segments

FRAME = 1001 / 30000          # 29.97 fps 一格
MIN_CHARS = 5                 # 錨點句正規化後至少幾字
NEAR = 120.0                  # 首播範圍前後幾秒內也要唯一
CLUSTER_TOL = 0.1             # 錨點位移差幾秒內算同一群
P50_LIMIT = FRAME             # 同群錨點偏離中位數的 p50 上限（一格）
WITHIN = 2 * FRAME            # 「兩格內」
WITHIN_SHARE = 0.8            # 同群錨點至少幾成要在兩格內
OCR_ENOUGH = 10               # 同群幾個以上不靠 whisper 也算數
OCR_SOME = 3                  # 3–9 個要 whisper 一致才算
GRADE_A = 20                  # 同群幾個以上＋whisper 一致算證據 A
CUT_RUN = 3                   # 剪接：前後各連續幾個錨點
CUT_SHARE = 0.8               # 剪接：前後各有幾成落在自己的位移
WINDOW = 60.0                 # 剪法不同：分窗寬度
HOLE = 60.0                   # 範圍內多長沒有錨點要加取樣點
WHISPER_BIN = 0.05
WHISPER_HITS = 10
WHISPER_RATIO = 3
WHISPER_TOL = 0.1
WHISPER_SPAN = 600.0          # 範圍比這短，whisper 窗放寬到中點前後各一半
EDGE = 15.0                   # 範圍兩端幾秒內找重播自己的內容
EDGE_FRAMES = 2 * FRAME       # 邊緣那條起迄差幾格內算相同
SIMILAR = 0.5                 # 字相似度低於這個算不同句
BLANK_OVERLAP = 0.5           # 跟保留的空白 cue 重疊多少以內就修短它
DRIFT = 0.5                   # 相似的句子起點差幾秒以上算時間錯開
VERSION_WINDOW = 10.0         # 時間錯開幾秒以內還算「同一句的別的版本」
VERSIONS = 2                  # 範圍裡有幾句別的版本就擋
SHRINK_LIMIT = 60.0           # 範圍一端最多縮幾秒，超過就擋（範圍給錯了）
READ_SHARE = 0.25             # 重播那段有字的 cue 不到首播的幾成算「沒讀到」
BLANK_COVER = 0.25            # 首播一句被重播有字的 cue 蓋到不到幾成算「重播沒字」
AGREE_SHARE = 0.5             # 錨點超過幾成在一格內，錯開的句子算重播自己錯
TOL = FRAME + 0.002           # 分區搬：重播跟首播的 cue 邊差幾秒內算同一個邊
SAFE_OUT = 15.0               # 區最多擴到節目範圍外幾秒
ITEM_MARGIN = 1.0             # 工作檔 items 秒數前後放寬幾秒
NOT_UNIT = ("攝影棚", "主播外景", "外景新聞", "全螢幕圖卡", "其他")
SEG_SNAP = 3.0                # 段落表新列邊跟重播原本列邊差幾秒內用重播的
MAD_SAME = 1.5                # 同位移 MAD 一定算「畫面相同」的值
MAD_MARGIN = 0.1              # 同位移要比 ±1 格小多少才算嚴格局部最小
MATCH_SHARE = 1.0 / 3.0       # 內部點至少幾成要是嚴格局部最小
MISS_SHARE = 0.1              # 鄰格比同位移更像的點最多幾成
FAR_TIMES = 3.0               # 同位移 MAD 超過底值幾倍（且不是局部最小）算畫面不同
DIFFER_SHARE = 0.1            # 畫面不同的點，內部、邊界各最多幾成
FLOOR_MAX = 4.0               # 底值（同位移 MAD 中位數）上限
# 比對前遮掉的地方（寬、高的比例 x0, y0, x1, y1）：上面兩角（2021 台標在
# 384×216 縮圖 x 20–62、y 16–42）和字幕帶下面整條（天氣框 2021–2024 都在
# 左下 x 0–92、y 170–210；人名字卡、族語列 y 172–210 常常只有其中一次播出
# 有：025 午→026 午只遮四角時同位移 MAD 底 7.06）。字幕帶（縮圖 y 144–
# 168）不遮。
MASK = ((0.0, 0.0, 0.21, 0.22), (0.79, 0.0, 1.0, 0.22),
        (0.0, 0.78, 1.0, 1.0))
PROBE_INSIDE = 7              # 內部取樣點數
PROBE_EDGE = 1.0              # 邊界內外取樣點離邊界幾秒
PROBE_END = 4.0               # 節目範圍頭尾幾秒內不取邊界點（片頭字卡）
LOCATE_FRAMES = 5             # 像素定位：whisper 位移前後幾格
THUMB = (384, 216)

PUNCT = re.compile(r"[\s，。！？、!?,.~～…「」『』：:；;（）()．・·\-—_\"“”]")
APOSTROPHES = re.compile(r"[’‘`ʼ′]")
CUE_FIELD = re.compile(r"^([0-9]+)(?:[–-]([0-9]+))?$")


# ------------------------------------------------------------ 位移


def norm(text):
    """比對用的字：去空白、標點，彎撇直撇視為同一個。"""
    return PUNCT.sub("", APOSTROPHES.sub("'", text or ""))


def runs(cues, texts):
    """相連而且同字的 cue 併成一段：一句字幕跨好幾條 cue 是本語料的常態。"""
    out = []
    for item in cues:
        text = norm(texts.get(int(item["index"]), ""))
        start, end = float(item["start"]), float(item["end"])
        if out and text and out[-1]["text"] == text \
                and abs(out[-1]["end"] - start) < 0.05:
            out[-1]["end"] = end
            out[-1]["cues"].append(int(item["index"]))
            continue
        out.append({"text": text, "start": start, "end": end,
                    "cues": [int(item["index"])]})
    return out


def _counts(found, lo=None, hi=None):
    out = collections.Counter()
    for run in found:
        if lo is not None and not lo <= run["start"] < hi:
            continue
        out[run["text"]] += 1
    return out


def anchors(src_cues, src_texts, tgt_cues, tgt_texts, lo, hi,
            side="source"):
    """兩集都只出現一次、≥ 5 字的段，用起點算位移。

    `side="source"`：`[lo, hi)` 是首播的秒數，首播的唯一性看範圍前後
    120 秒；`side="target"`：`[lo, hi)` 是重播的秒數（盤點工作檔用）。
    不論哪一側，另一集都要整集唯一。迄點不能用：重播用別的區域切 cue 時
    迄點差 p90 1.8 秒，起點只差 0.028。
    """
    src_runs = runs(src_cues, src_texts)
    tgt_runs = runs(tgt_cues, tgt_texts)
    if side == "source":
        src_count = _counts(src_runs, lo - NEAR, hi + NEAR)
        tgt_count = _counts(tgt_runs)
    else:
        src_count = _counts(src_runs)
        tgt_count = _counts(tgt_runs, lo - NEAR, hi + NEAR)
    where = {}
    for run in tgt_runs:
        where[run["text"]] = run
    out = []
    for run in src_runs:
        text = run["text"]
        if len(text) < MIN_CHARS or src_count[text] != 1 \
                or tgt_count[text] != 1 or text not in where:
            continue
        other = where[text]
        here = run["start"] if side == "source" else other["start"]
        if not lo <= here < hi:
            continue
        out.append({"src": run["start"], "tgt": other["start"],
                    "delta": round(other["start"] - run["start"], 6),
                    "text": text})
    out.sort(key=lambda item: item["src"])
    return out


def cluster(deltas, tol=CLUSTER_TOL):
    """最大的一群（每個離種子 ≤ tol）：(中位數, 群內的索引)。"""
    if not deltas:
        return None, []
    order = sorted(range(len(deltas)), key=lambda k: deltas[k])
    values = []
    for k in order:
        values.append(deltas[k])
    best = (0, 0, 0)
    for k in range(len(values)):
        left = bisect.bisect_left(values, values[k] - tol - 1e-9)
        right = bisect.bisect_right(values, values[k] + tol + 1e-9)
        if right - left > best[0]:
            best = (right - left, left, right)
    members = values[best[1]:best[2]]
    middle = statistics.median(members)
    inside = []
    for k in range(len(deltas)):
        if abs(deltas[k] - middle) <= tol + 1e-9:
            inside.append(k)
    return middle, inside


def _deltas(found):
    out = []
    for item in found:
        out.append(item["delta"])
    return out


def find_cut(found):
    """照首播時間排，找「前面連續一段是一個位移、後面連續一段是另一個」。

    第二群不一定是剪接：182 晨部落信箱首播改過起迄的 6 條跟 41 條交錯，
    那是時間上交錯，不是前後兩段。所以前後各自要有八成落在自己的位移。
    """
    ordered = sorted(found, key=lambda item: item["src"])
    deltas = _deltas(ordered)
    best = None
    for k in range(CUT_RUN, len(ordered) - CUT_RUN + 1):
        before, members_before = cluster(deltas[:k])
        after, members_after = cluster(deltas[k:])
        if abs(before - after) <= CLUSTER_TOL:
            continue
        if len(members_before) < CUT_SHARE * k:
            continue
        if len(members_after) < CUT_SHARE * (len(deltas) - k):
            continue
        score = len(members_before) + len(members_after)
        if best is None or score > best["score"]:
            best = {"at": (ordered[k - 1]["src"] + ordered[k]["src"]) / 2.0,
                    "between": [ordered[k - 1]["src"], ordered[k]["src"]],
                    "before": before, "after": after, "n_before": k,
                    "n_after": len(deltas) - k, "score": score}
    return best


def window_medians(found, lo, width=WINDOW):
    """每 60 秒窗的位移中位數（窗內 ≥ 3 個才算）。"""
    groups = collections.defaultdict(list)
    for item in found:
        groups[int((item["src"] - lo) // width)].append(item["delta"])
    out = []
    for key in sorted(groups):
        if len(groups[key]) >= 3:
            out.append((lo + key * width, statistics.median(groups[key]),
                        len(groups[key])))
    return out


def read_sapolita(text):
    """whisper SRT 的段落起迄；不用字（族語碼不同，字就不同）。"""
    out = []
    for block in text.replace("\r\n", "\n").strip().split("\n\n"):
        lines = block.strip().split("\n")
        if len(lines) < 2 or "-->" not in lines[1]:
            continue
        first, _arrow, second = lines[1].partition("-->")
        out.append((_srt_seconds(first.strip()), _srt_seconds(second.strip())))
    return out


def _srt_seconds(value):
    clock, _comma, millis = value.partition(",")
    hours, minutes, secs = clock.split(":")
    return int(hours) * 3600 + int(minutes) * 60 + int(secs) \
        + int(millis) / 1000.0


def whisper_window(lo, hi):
    """範圍太短（< 600 秒）就放寬到範圍中點前後各 300 秒。"""
    if hi - lo >= WHISPER_SPAN:
        return lo, hi
    middle = (lo + hi) / 2.0
    return middle - WHISPER_SPAN / 2.0, middle + WHISPER_SPAN / 2.0


def whisper_offset(src_segs, tgt_segs, lo, hi):
    """whisper 段落起迄兩兩相減，0.05 秒一格投票。

    有效：峰值 ≥ 10 票，而且是「不相鄰的次高格」的 3 倍以上。無效不是
    「不一致」，是「沒有結論」。
    """
    chosen = []
    for seg in src_segs:
        if lo <= seg[0] < hi:
            chosen.append(seg)
    diffs = []
    for seg in chosen:
        for other in tgt_segs:
            diffs.append(other[0] - seg[0])
            diffs.append(other[1] - seg[1])
    if not diffs:
        return {"offset": None, "hits": 0, "runner_up": 0,
                "segments": len(chosen), "conclusive": False, "times": []}
    votes = collections.Counter()
    for diff in diffs:
        votes[round(diff / WHISPER_BIN)] += 1
    peak, _count = votes.most_common(1)[0]
    runner = 0
    for key, count in votes.most_common():
        if abs(key - peak) > 2:
            runner = count
            break
    near = []
    for diff in diffs:
        if abs(diff - peak * WHISPER_BIN) <= WHISPER_BIN + 0.01:
            near.append(diff)
    middle = statistics.median(near)
    hits = []
    times = []
    for seg in chosen:
        for other in tgt_segs:
            for side in (0, 1):
                if abs(other[side] - seg[side] - middle) <= WHISPER_BIN:
                    hits.append(other[side] - seg[side])
                    times.append(seg[side])
    offset = round(statistics.median(hits), 3)
    return {"offset": offset, "hits": len(hits), "runner_up": runner,
            "segments": len(chosen), "times": sorted(times),
            "conclusive": len(hits) >= WHISPER_HITS
            and len(hits) >= WHISPER_RATIO * runner}


def _quantile(values, share):
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1,
                       max(0, int(math.ceil(share * len(ordered))) - 1))]


def _p90(values):
    return _quantile(values, 0.9)


def holes(times, lo, hi, longest=HOLE):
    """範圍內超過 60 秒沒有錨點的段：[(起, 迄)]。"""
    points = [lo]
    for value in sorted(times):
        if lo <= value <= hi:
            points.append(value)
    points.append(hi)
    out = []
    for k in range(1, len(points)):
        if points[k] - points[k - 1] > longest:
            out.append((points[k - 1], points[k]))
    return out


def judge_offset(found, whisper, lo, hi):
    """位移和證據：status 是 ready／pixel（只有 whisper，要像素定位）／
    rejected，reasons 逐條寫原因。最後用的位移一律來自畫面。"""
    deltas = _deltas(found)
    middle, members = cluster(deltas)
    inliers = len(members)
    devs = []
    starts = []
    for k in members:
        devs.append(abs(deltas[k] - middle))
        starts.append(found[k]["src"])
    p90 = round(_p90(devs), 6)
    p50 = round(_quantile(devs, 0.5), 6)
    near = 0
    for dev in devs:
        if dev <= WITHIN + 1e-9:
            near += 1
    within_two = round(float(near) / len(devs), 3) if devs else 0.0
    agree = 0.0
    if found and middle is not None:
        close = 0
        for delta in deltas:
            if abs(delta - middle) <= TOL:
                close += 1
        agree = round(float(close) / len(found), 3)
    verdict = "沒有資料"
    if whisper and whisper.get("offset") is not None:
        verdict = "沒有結論"
        if whisper.get("conclusive"):
            verdict = "有效（沒有 OCR 可比）"
            if middle is not None:
                verdict = "不一致"
                if abs(whisper["offset"] - middle) <= WHISPER_TOL:
                    verdict = "一致"
    reasons = []
    blockers = []
    status = "ready"
    offset = middle
    pixel_at = None
    if inliers >= OCR_ENOUGH:
        pass
    elif inliers >= OCR_SOME and verdict == "一致":
        pass
    elif whisper and whisper.get("conclusive"):
        status = "pixel"
        offset = whisper["offset"]
        pixel_at = len(reasons)
        reasons.append("OCR 同群只有 %d 個，whisper 有效（%d 票，位移 %.3f），"
                       "要先用像素定位" % (inliers, whisper["hits"], offset))
    else:
        status = "rejected"
        offset = None
        blockers.append("evidence")
        reasons.append("位移證據不足：OCR 錨點 %d 個、同群 %d 個；whisper %s"
                       % (len(found), inliers, verdict))
    # 切 cue 的區域不同時，錨點會差 1–3 格（227→216 移植前 p90 0.050），
    # 所以不看 p90：p50 在一格內、八成以上在兩格內就算逐格一致，最後以
    # 像素驗收為準。
    if status == "ready" and (p50 > P50_LIMIT or within_two < WITHIN_SHARE):
        status = "rejected"
        blockers.append("spread")
        reasons.append("錨點逐格不一致：同群 %d 個偏離中位數 p50 %.3f 秒（上限"
                       "一格 %.3f）、%.0f%% 在兩格內（要八成）"
                       % (inliers, p50, P50_LIMIT, 100.0 * within_two))
    cut = find_cut(found)
    if cut:
        status = "rejected"
        blockers.append("cut")
        reasons.append(
            "剪接：首播約 %.1f 秒（%.1f–%.1f 之間），前 %d 個錨點 %+.2f、"
            "後 %d 個 %+.2f，重播剪掉約 %.2f 秒"
            % (cut["at"], cut["between"][0], cut["between"][1],
               cut["n_before"], cut["before"], cut["n_after"], cut["after"],
               abs(cut["before"] - cut["after"])))
    windows = window_medians(found, lo)
    if found and inliers < len(found) / 2.0 and len(windows) >= 2:
        values = []
        for item in windows:
            values.append(item[1])
        if max(values) - min(values) > CLUSTER_TOL:
            status = "rejected"
            blockers.append("edit")
            shown = []
            for item in windows:
                shown.append("%.2f" % item[1])
            reasons.append("剪法不同：%d 個錨點只有 %d 個同群，各 60 秒窗中位數 %s"
                           % (len(found), inliers, "／".join(shown)))
    if status == "rejected" and pixel_at is not None:
        # 剪接、剪法不同擋下時，像素定位只補位移、補不了，不可以叫人去做。
        hard = []
        for kind in blockers:
            if kind in BLOCKER_NAMES:
                hard.append(BLOCKER_NAMES[kind])
        reasons[pixel_at] = ("OCR 同群只有 %d 個，whisper 有效（%d 票，位移 "
                             "%.3f），但有%s，像素定位只補位移、補不了"
                             % (inliers, whisper["hits"], offset,
                                "、".join(hard)))
    grade = "A" if inliers >= GRADE_A and verdict == "一致" else "B"
    if verdict == "不一致":
        reasons.append("whisper %.3f 跟畫面 %.3f 差超過 %.1f 秒，只當參考"
                       % (whisper["offset"], middle, WHISPER_TOL))
    times = list(starts)
    if whisper and verdict == "一致":
        times += whisper.get("times", [])
    return {"status": status, "offset": offset, "grade": grade,
            "anchors": len(found), "inliers": inliers, "p90": p90,
            "p50": p50, "within_two": within_two, "agree": agree,
            "blockers": blockers,
            "whisper": _whisper_summary(whisper),
            "whisper_verdict": verdict, "cut": cut, "windows": windows,
            "holes": holes(times, lo, hi), "reasons": reasons}


BLOCKER_NAMES = {"cut": "剪接", "edit": "剪法不同"}


def with_offset(evidence, offset):
    """`--offset`（像素定位得到的位移）只補位移：證據不足、逐格不一致可以
    換成指定的位移；剪接、剪法不同的拒絕不能蓋掉。"""
    out = dict(evidence)
    out["reasons"] = list(evidence.get("reasons", []))
    hard = []
    for kind in evidence.get("blockers", []):
        if kind in BLOCKER_NAMES:
            hard.append(BLOCKER_NAMES[kind])
    if hard:
        out["status"] = "rejected"
        out["reasons"].append("--offset 只補位移，不能蓋掉%s的拒絕"
                              % "、".join(hard))
        return out
    out["reasons"].append("位移由像素定位指定 %.3f（量到 %s）"
                          % (offset, evidence.get("offset")))
    out["offset"] = offset
    out["status"] = "ready"
    out["grade"] = "像素定位"
    return out


def cut_setting(book, item):
    """這條 cue 是用哪一種設定切的：有 `area` 就是 areas 裡那一格（preset、
    region），沒有就是時間軸頂層的 region。比的是內容不是鍵名——227、216
    的 areas 都叫「帶外專題」，一個是島語、一個是花字。"""
    area = item.get("area")
    if area:
        found = (book.get("areas") or {}).get(area)
        if found is None:
            found = {"area": area}
        return json.dumps(found, ensure_ascii=False, sort_keys=True)
    return json.dumps({"region": book.get("region")}, sort_keys=True)


def main_setting(book, lo, hi):
    """`[lo, hi)` 裡佔最多時間的切法設定；範圍外的不算（287 頂層 region
    是 y840、331 是 y722，部落信箱那段兩集都用 mailbox）。"""
    weight = collections.Counter()
    for item in book["cues"]:
        if lo <= _middle(item) < hi:
            weight[cut_setting(book, item)] += max(0.0, _length(item))
    if not weight:
        return None
    return weight.most_common(1)[0][0]


def setting_name(setting):
    if setting is None:
        return "（沒有 cue）"
    value = json.loads(setting)
    if value.get("preset"):
        return "%s %s" % (value["preset"], value.get("region"))
    if value.get("area"):
        return "「%s」（areas 裡沒有）" % value["area"]
    return "頂層 region %s" % value.get("region")


def choose_mode(src_book, src_texts, tgt_book, tgt_texts, lo, hi, off,
                src_first=None, tgt_first=None):
    """whole（整段搬）、zone（分區搬）或 ask（不搬、整件要人判），和理由。

    - 重播那段有字的 cue 不到首播的兩成五（沒讀到）→ whole。
    - 兩集這段現在的切法設定不同，要看是哪一集重切過（`src_first`、
      `tgt_first` 是兩集最早那份快照的時間軸，沒有快照給 None）：
      - 重播自己重切過（重播現在跟它最早那份不同）→ ask：首播的切法比較
        舊，整段搬會把重播的重切換回去（358→314、254→251）。
      - 首播重切過、重播現在還是首播重切前那種 → whole（227→216）。
      - 兩集都沒重切過，只是本來切法就不同 → zone。
      - 首播沒有快照、或首播重切過而重播是第三種設定 → ask。
      - 任一集最早那份快照沒有時間軸、或這段範圍內沒有 cue（看不出當初
        的切法）→ ask；舊做法退回現在的設定，等於猜「沒重切過」。
    - 其他 → zone。
    """
    source = 0
    for item in src_book["cues"]:
        text = src_texts.get(int(item["index"]), "")
        if lo <= _middle(item) < hi and norm(text):
            source += 1
    target = 0
    count = 0
    for item in tgt_book["cues"]:
        if lo + off <= _middle(item) < hi + off:
            count += 1
            if norm(tgt_texts.get(int(item["index"]), "")):
                target += 1
    mine = main_setting(tgt_book, lo + off, hi + off)
    theirs = main_setting(src_book, lo, hi)
    stats = {"source_text": source, "target_text": target,
             "target_cues": count, "source_setting": setting_name(theirs),
             "target_setting": setting_name(mine)}
    if target <= READ_SHARE * source:
        stats["why"] = ("重播那段有字 %d 條，不到首播 %d 條的兩成五（沒讀到）"
                        % (target, source))
        return "whole", stats
    if mine is None or theirs is None or mine == theirs:
        stats["why"] = ("重播那段已經有字（%d 條，首播 %d 條），切法設定跟首播"
                        "一樣" % (target, source))
        return "zone", stats
    differ = "重播那段用 %s 切，首播現在用 %s" % (
        setting_name(mine), setting_name(theirs))
    for side, first in (("重播", tgt_first), ("首播", src_first)):
        blind = _blind_first(first, side, lo + off if side == "重播" else lo,
                             hi + off if side == "重播" else hi)
        if blind:
            stats["why"] = "%s；%s：判不出是哪一集重切過，不搬，要人判" % (
                differ, blind)
            return "ask", stats
    mine_first = mine
    if tgt_first is not None:
        mine_first = main_setting(tgt_first, lo + off, hi + off)
    stats["target_first_setting"] = setting_name(mine_first)
    if mine_first != mine:
        stats["why"] = ("%s；重播自己重切過（最早那份快照是 %s），首播的切法"
                        "比較舊，整段搬會把重播的重切換回去：不搬，要人判"
                        % (differ, setting_name(mine_first)))
        return "ask", stats
    if src_first is None:
        stats["why"] = ("%s；沒有首播的快照（--snaps），判不出是哪一集重切過："
                        "不搬，要人判" % differ)
        return "ask", stats
    theirs_first = main_setting(src_first, lo, hi)
    stats["source_first_setting"] = setting_name(theirs_first)
    if theirs_first == theirs:
        stats["why"] = ("%s；兩集都沒重切過，只是本來切法就不同：分區搬（只搬"
                        "首播改過的地方）" % differ)
        return "zone", stats
    if theirs_first == mine:
        stats["why"] = ("%s；首播重切過（最早那份快照是 %s，跟重播現在一樣），"
                        "首播的切法比較新：整段搬"
                        % (differ, setting_name(theirs_first)))
        return "whole", stats
    stats["why"] = ("%s；首播重切過（最早那份快照是 %s），重播卻是第三種設定："
                    "不搬，要人判" % (differ, setting_name(theirs_first)))
    return "ask", stats


def _blind_first(first, side, lo, hi):
    """最早那份快照看不出切法的原因（沒有時間軸、範圍內沒有 cue）；看得
    出來或沒有快照給 None。"""
    if first is None:
        return None
    if first.get("missing"):
        return "%s最早那份快照 %s 沒有時間軸" % (side, first["missing"])
    if main_setting(first, lo, hi) is None:
        return "%s最早那份快照在 %.3f–%.3f 秒沒有 cue" % (side, lo, hi)
    return None


def _whisper_summary(whisper):
    if not whisper:
        return None
    out = {}
    for key in ("offset", "hits", "runner_up", "segments", "conclusive"):
        out[key] = whisper.get(key)
    return out


# ------------------------------------------------------------ 搬


def similarity(first, second):
    first, second = norm(first), norm(second)
    if not first or not second:
        return 0.0
    return difflib.SequenceMatcher(None, first, second,
                                   autojunk=False).ratio()


def overlap(first, second):
    return max(0.0, min(float(first["end"]), float(second["end"]))
               - max(float(first["start"]), float(second["start"])))


def _middle(item):
    return (float(item["start"]) + float(item["end"])) / 2.0


def _shift(item, off):
    moved = dict(item)
    for key in ("start", "end", "sample_ts"):
        if key in moved:
            moved[key] = round(float(moved[key]) + off, 3)
    moved["images"] = {}
    return moved


def _clamp_sample(item):
    start, end = float(item["start"]), float(item["end"])
    sample = float(item.get("sample_ts", start))
    item["sample_ts"] = round(min(max(sample, start), end), 3)


def _length(item):
    return float(item["end"]) - float(item["start"])


def _same_footage(item, text, candidates, texts):
    """重播這條跟首播同時段某條是同一句：重疊至少是兩條中較短那條的一半，
    而且字相同，或字相似（≥ 0.5）而且起點在兩格內。

    覆蓋率用較短那條算：216 移植前「我傻眼」3.19 秒（舊花字切法拉長），
    227 是 1.10 秒，用重播那條的長度算就不到五成。相似但起點錯開的
    （182「體驗連結課室學習」對 152「從身體力行的…」差 2.9 秒）不是同一句。
    """
    for other in candidates:
        shared = overlap(item, other)
        if shared <= 0 or shared < 0.5 * min(_length(item), _length(other)):
            continue
        theirs = texts.get(int(other["_src"]), "")
        if norm(text) == norm(theirs):
            return True
        if similarity(text, theirs) >= SIMILAR and abs(
                float(item["start"]) - float(other["start"])) <= EDGE_FRAMES:
            return True
    return False


def _accounted(start, text, others):
    """[(起點, 字)] 裡有沒有一句跟這句相似、起點在 0.5 秒內。"""
    for when, theirs in others:
        if abs(when - start) <= DRIFT and similarity(text, theirs) >= SIMILAR:
            return True
    return False


def _other_version(item, text, candidates, texts, mine):
    """首播 10 秒內有相似的句子、但起點錯開超過 0.5 秒，而且那句首播在重播
    同時段也沒有對應：同一則新聞的另一個版本（182 晨邵語版對 152 午太魯閣
    語版）。字幕一句接一句很像（「第012句」「第013句」、歌詞重複）時，那句
    首播在重播自己的時間就對得到，不算。`mine` 是重播的 [(起點, 字)]。"""
    if len(norm(text)) < MIN_CHARS:
        return None
    found = None
    for other in candidates:
        gap = abs(float(other["start"]) - float(item["start"]))
        theirs = texts.get(int(other["_src"]), "")
        if gap > VERSION_WINDOW or similarity(text, theirs) < SIMILAR:
            continue
        if gap <= DRIFT:
            return None
        if found is None and not _accounted(float(other["start"]), theirs,
                                            mine):
            found = other
    return found


def shrink_range(candidates, texts, tgt_cues, tgt_texts, start, end):
    """範圍兩端 15 秒內，重播有字、首播同時段不是同一句的，算重播自己的
    內容，範圍縮到它外面，重複到沒有為止。碰到相似但時間錯開的句子不停，
    繼續判斷，並記成「別的版本」。回傳 (起, 迄, notes, versions)。"""
    notes = []
    versions = []
    first, last = start, end
    mine = []
    for item in tgt_cues:
        mine.append((float(item["start"]),
                     tgt_texts.get(int(item["index"]), "")))
    changed = True
    while changed:
        changed = False
        for item in tgt_cues:
            middle = _middle(item)
            if not start <= middle < end:
                continue
            if middle - start >= EDGE and end - middle >= EDGE:
                continue
            text = tgt_texts.get(int(item["index"]), "")
            if not norm(text):
                continue
            if _same_footage(item, text, candidates, texts):
                continue
            other = _other_version(item, text, candidates, texts, mine)
            if other is not None:
                versions.append((int(item["index"]), text, other["_src"],
                                 abs(float(other["start"])
                                     - float(item["start"]))))
            if middle - start < end - middle:
                notes.append("起點 %.3f→%.3f：重播 cue %d「%s」首播沒有"
                             % (start, float(item["end"]), item["index"],
                                text[:16]))
                start = float(item["end"])
            else:
                notes.append("迄點 %.3f→%.3f：重播 cue %d「%s」首播沒有"
                             % (end, float(item["start"]), item["index"],
                                text[:16]))
                end = float(item["start"])
            changed = True
            break
    if start - first > SHRINK_LIMIT or last - end > SHRINK_LIMIT:
        raise PipelineError(
            "範圍超出重播段太多：重播 %.3f–%.3f 縮到 %.3f–%.3f（一端最多縮 %.0f"
            " 秒）；請改用段落表那一段或重給範圍"
            % (first, last, start, end, SHRINK_LIMIT))
    return start, end, notes, versions


def _fit_edges(ported, removed, texts, tgt_texts, notes):
    """邊緣那條同字、一端相同一端不同：重播在那裡剪掉（較短）時，不同那端
    用重播的。只縮不伸——重播較長（216「我傻眼」舊切法拉長）時照首播。"""
    if not ported or not removed:
        return
    pairs = ((ported[-1], removed[-1], "end", "start"),
             (ported[0], removed[0], "start", "end"))
    for mine, theirs, loose, fixed in pairs:
        text = texts.get(int(mine["_src"]), "")
        if norm(text) != norm(tgt_texts.get(int(theirs["index"]), "")):
            continue
        if not norm(text):
            continue
        if abs(float(mine[fixed]) - float(theirs[fixed])) > EDGE_FRAMES:
            continue
        if abs(float(mine[loose]) - float(theirs[loose])) <= EDGE_FRAMES:
            continue
        shorter = float(theirs[loose]) < float(mine[loose]) \
            if loose == "end" else float(theirs[loose]) > float(mine[loose])
        if not shorter:
            continue
        notes.append("邊緣 cue「%s」%s用重播的 %.3f（首播搬過來是 %.3f）"
                     % (text[:10], "迄點" if loose == "end" else "起點",
                        float(theirs[loose]), float(mine[loose])))
        mine[loose] = float(theirs[loose])
        _clamp_sample(mine)


def _cut_away(item, other):
    """把 item 跟 other 重疊的那一端修掉；修完起點大於等於迄點就擋。"""
    before = [float(item["start"]), float(item["end"])]
    if float(item["start"]) < float(other["start"]):
        item["end"] = float(other["start"])
    else:
        item["start"] = float(other["end"])
    if float(item["start"]) >= float(item["end"]) - 0.0005:
        return None
    _clamp_sample(item)
    return before


def _resolve_overlaps(kept, ported, texts, tgt_texts):
    """搬進來的 cue 跟保留的重播 cue 重疊：

    - 保留的是空白、重疊 ≤ 0.5 秒 → 修短保留的那條（222 cue 444）；
    - 搬進來的是空白、保留的有字 → 修短搬進來的那條（182 尾端「休息一下
      馬上回來」重疊 0.533 秒）；
    - 兩條都有字，或保留的空白重疊太多 → 擋。
    修短後起點大於等於迄點也擋（保留 20.1–20.5、搬進 19.0–20.8 會變成
    20.8–20.5）。訊息裡的號碼是重播現在的號。
    """
    trimmed = []
    for item in kept:
        for other in ported:
            shared = overlap(item, other)
            if shared <= 0.001:
                continue
            text = tgt_texts.get(int(item["_old"]), "")
            theirs = texts.get(int(other["_src"]), "")
            where = ("重播 cue %d（%.3f–%.3f「%s」）跟搬進來的首播 cue %d（%.3f–"
                     "%.3f「%s」）重疊 %.3f 秒"
                     % (item["_old"], float(item["start"]),
                        float(item["end"]), text[:16], other["_src"],
                        float(other["start"]), float(other["end"]),
                        theirs[:16], shared))
            if norm(text) and not norm(theirs):
                before = _cut_away(other, item)
                if before is None:
                    raise PipelineError("範圍邊緣重疊：%s，搬進來的空白修短後"
                                        "沒有長度；請縮範圍" % where)
                trimmed.append({"cue": None, "source_cue": other["_src"],
                                "from": before,
                                "to": [float(other["start"]),
                                       float(other["end"])]})
                continue
            if norm(text) or shared > BLANK_OVERLAP:
                raise PipelineError("範圍邊緣重疊：%s；請縮範圍" % where)
            before = _cut_away(item, other)
            if before is None:
                raise PipelineError("範圍邊緣重疊：%s，修短後起點大於迄點；"
                                    "請縮範圍" % where)
            trimmed.append({"cue": item["_old"], "from": before,
                            "to": [float(item["start"]),
                                   float(item["end"])]})
    return trimmed


def check_timeline(cues, what="新時間軸"):
    """寫出前的把關：每條起點小於迄點、照時間遞增、不重疊。"""
    problems = []
    previous = None
    for item in cues:
        start, end = float(item["start"]), float(item["end"])
        if start >= end:
            problems.append("cue %s 起點 %.3f 不小於迄點 %.3f"
                            % (item.get("index"), start, end))
        if previous is not None and start < float(previous["end"]) - 0.0005:
            problems.append("cue %s（%.3f 起）跟前一條 cue %s（迄 %.3f）重疊"
                            % (item.get("index"), start,
                               previous.get("index"), float(previous["end"])))
        previous = item
    if problems:
        raise PipelineError("%s不合格：%s" % (what, "；".join(problems[:5])))


def timeline_problems(cues):
    """{(種類, 起迄…): 說明}：起點不小於迄點、跟前面最晚結束那條重疊。鍵只用
    起迄（號碼在移植前後不同），說明用這份時間軸自己的號。"""
    out = {}
    reach = None
    ordered = sorted(cues, key=lambda item: (float(item["start"]),
                                             float(item["end"])))
    for item in ordered:
        start = round(float(item["start"]), 3)
        end = round(float(item["end"]), 3)
        if start >= end:
            out[("倒置", start, end)] = ("cue %s 起點 %.3f 不小於迄點 %.3f"
                                       % (item.get("index"), start, end))
        if reach is not None and start < reach[1] - 0.0005:
            out[("重疊", reach[0], reach[1], start, end)] = (
                "cue %s（%.3f–%.3f）跟 cue %s（%.3f–%.3f）重疊"
                % (reach[2], reach[0], reach[1], item.get("index"), start,
                   end))
        if reach is None or end > reach[1]:
            reach = (start, end, item.get("index"))
    return out


def check_new(before, after, what="新時間軸"):
    """只擋這次新造成的重疊或倒置（跟重播原本的時間軸比）；原本就有的
    （Kari-SRT 3152 份裡 168 份本來就重疊）不擋，回傳說明。範圍內原本的
    重疊被整段換掉就不見了，那更好。"""
    old = timeline_problems(before)
    new = timeline_problems(after)
    fresh = []
    notes = []
    for key in sorted(new, key=str):
        if key in old:
            notes.append("重播原本就有的%s：%s，這次沒動" % (key[0], old[key]))
        else:
            fresh.append(new[key])
    if fresh:
        raise PipelineError("%s有這次新造成的問題：%s"
                            % (what, "；".join(fresh[:5])))
    return notes


def _inside_items(item, items):
    middle = _middle(item)
    for lo, hi in items:
        if lo - ITEM_MARGIN <= middle <= hi + ITEM_MARGIN:
            return True
    return False


def _orphans(ported, tgt_cues, texts, items):
    """首播有字、重播那段一條 cue 都沒有、又不在工作檔 items 範圍內的。"""
    out = []
    for other in ported:
        if not norm(texts.get(int(other["_src"]), "")):
            continue
        covered = False
        for item in tgt_cues:
            if overlap(item, other) > 0.001:
                covered = True
                break
        if not covered and not _inside_items(other, items):
            out.append(other)
    return out


def _run_items(items, texts, key):
    """相連而且同字的 cue 併成一段（比對別的版本用）。"""
    shaped = []
    for item in items:
        shaped.append({"index": int(item[key]), "start": item["start"],
                       "end": item["end"]})
    return runs(shaped, texts)


def _drifted(removed, ported, texts, tgt_texts):
    """範圍內重播有字的句子，首播 10 秒內有相似的、卻沒有一句在 0.5 秒內：
    整段搬會把它換成別的時間（182「體驗連結課室學習」對 152「從身體力行
    的…」差到 2.9 秒）。"""
    theirs = _run_items(ported, texts, "_src")
    mine = []
    for run in _run_items(removed, tgt_texts, "_old"):
        mine.append((run["start"], run["text"]))
    out = []
    for run in _run_items(removed, tgt_texts, "_old"):
        if len(run["text"]) < MIN_CHARS:
            continue
        near = False
        far = None
        for other in theirs:
            gap = abs(other["start"] - run["start"])
            if gap > VERSION_WINDOW or similarity(run["text"],
                                                  other["text"]) < SIMILAR:
                continue
            if gap <= DRIFT:
                near = True
                break
            if far is None and not _accounted(other["start"], other["text"],
                                              mine):
                far = other
        if not near and far is not None:
            out.append((run["cues"][0], run["text"], far["cues"][0],
                        abs(far["start"] - run["start"])))
    return out


def port(src_book, src_texts, tgt_book, tgt_texts, lo, hi, off, items=None,
         agree=None):
    """首播 `[lo, hi)` 整段搬去重播：範圍縮、邊緣、重疊、換、重編號。

    `items` 是工作檔 items 的秒數（重播時間）：首播有字、重播那段沒有 cue
    的，只有落在 items 裡才補（`None` 表示不檢查）。

    回傳 dict：range、cues（新時間軸）、moves（重播舊號→新號）、ported
    （首播號→新號）、fresh（搬進來的新號）、removed、trimmed、notes、
    texts（新號→搬進來的字）、all_texts（新號→字，全集）、added／changed
    ／ask（新號或重播舊號）。

    `agree` 是錨點在一格內的比例：超過一半時，範圍裡少數跟首播相似但時間
    錯開的句子算重播自己的時間軸錯（216 舊花字切法「這個是日本人造的橋」
    差 3.29 秒），不擋、記說明；None 或不到一半照樣擋（別的版本）。
    """
    candidates = []
    for item in src_book["cues"]:
        if lo <= _middle(item) < hi:
            moved = _shift(item, off)
            moved["_src"] = int(item["index"])
            candidates.append(moved)
    if not candidates:
        raise PipelineError("首播 %.3f–%.3f 秒內沒有 cue" % (lo, hi))
    start, end, notes, versions = shrink_range(
        candidates, src_texts, tgt_book["cues"], tgt_texts, lo + off,
        hi + off)
    ported = []
    for item in candidates:
        if start <= _middle(item) < end:
            ported.append(item)
    kept = []
    removed = []
    for item in tgt_book["cues"]:
        copy = dict(item)
        copy["_old"] = int(item["index"])
        (removed if start <= _middle(item) < end else kept).append(copy)
    versions = versions + _drifted(removed, ported, src_texts, tgt_texts)
    if len(versions) >= VERSIONS:
        shown = []
        for number, text, source, gap in versions[:4]:
            shown.append("重播 cue %d「%s」↔首播 cue %d（差 %.2f 秒）"
                         % (number, text[:12], source, gap))
        if agree is None or agree <= AGREE_SHARE:
            raise PipelineError("範圍含別的版本：%d 句跟首播相似但時間錯開，%s；"
                                "請縮範圍" % (len(versions), "；".join(shown)))
        notes.append("%d 句跟首播相似但時間錯開（%s）；%.0f%% 錨點在一格內，當成"
                     "重播自己的時間軸錯，不擋"
                     % (len(versions), "；".join(shown), 100.0 * agree))
    if items is not None:
        lost = _orphans(ported, tgt_book["cues"], src_texts, items)
        if lost:
            shown = []
            for other in lost[:4]:
                shown.append("首播 cue %d「%s」→重播 %.3f–%.3f"
                             % (other["_src"],
                                src_texts.get(other["_src"], "")[:16],
                                float(other["start"]), float(other["end"])))
            raise PipelineError("首播有字、重播那段沒有 cue，又不在工作檔 items"
                                " 範圍內（可能是首播自己的主播或別的節目）：%s"
                                % "；".join(shown))
    _fit_edges(ported, removed, src_texts, tgt_texts, notes)
    trimmed = _resolve_overlaps(kept, ported, src_texts, tgt_texts)

    merged = kept + ported
    merged.sort(key=lambda item: (float(item["start"]), float(item["end"])))
    cues = []
    moves = {}
    mapped = {}
    texts = {}
    every = {}
    for number, item in enumerate(merged, 1):
        clean = {}
        for key in item:
            if not key.startswith("_"):
                clean[key] = item[key]
        clean["index"] = number
        cues.append(clean)
        if "_old" in item:
            moves[item["_old"]] = number
            every[number] = tgt_texts.get(item["_old"], "")
        else:
            mapped[item["_src"]] = number
            texts[number] = src_texts.get(item["_src"], "")
            every[number] = texts[number]
    notes += check_new(tgt_book["cues"], cues)
    removed_numbers = []
    for item in removed:
        removed_numbers.append(item["_old"])
    added, changed, ask = _audit(cues, mapped, texts, removed, tgt_texts)
    return {"range": [round(start, 3), round(end, 3)], "cues": cues,
            "moves": moves, "ported": mapped,
            "fresh": sorted(mapped.values()), "removed": removed_numbers,
            "removed_cues": _strip(removed), "trimmed": trimmed,
            "notes": notes, "texts": texts, "all_texts": every,
            "added": added, "changed": changed, "ask": ask,
            "replaced": replaced_span(ported, removed, src_texts, tgt_texts)}


def replaced_span(ported, removed, src_texts, tgt_texts):
    """整段搬真的有換到的地方（重播時間）：搬進來的 cue 跟重播原本某條起迄
    一格內、字相同，就是沒換；其餘搬進來的和沒對上的原本 cue，最早的起點
    到最晚的迄點。全部相同給 None。像素驗收的邊界點放在它外側。"""
    matched = set()
    moments = []
    for item in ported:
        text = norm(src_texts.get(item["_src"], ""))
        twin = None
        for k, old in enumerate(removed):
            if k in matched:
                continue
            if abs(float(old["start"]) - float(item["start"])) <= TOL \
                    and abs(float(old["end"]) - float(item["end"])) <= TOL \
                    and norm(tgt_texts.get(old["_old"], "")) == text:
                twin = k
                break
        if twin is None:
            moments.append((float(item["start"]), float(item["end"])))
        else:
            matched.add(twin)
    for k, old in enumerate(removed):
        if k not in matched:
            moments.append((float(old["start"]), float(old["end"])))
    if not moments:
        return None
    first = min(moments)[0]
    last = max(moments, key=lambda pair: pair[1])[1]
    return [round(first, 3), round(last, 3)]


def _strip(items):
    out = []
    for item in items:
        out.append({"index": item["_old"], "start": float(item["start"]),
                    "end": float(item["end"])})
    return out


def _audit(cues, mapped, texts, removed, tgt_texts):
    """補進來的、改掉的、要人判的字。"""
    by_number = {}
    for item in cues:
        by_number[item["index"]] = item
    added = []
    changed = []
    for number in sorted(mapped.values()):
        mine = texts.get(number, "")
        if not norm(mine):
            continue
        theirs = []
        for item in removed:
            text = tgt_texts.get(item["_old"], "")
            if norm(text) and overlap(by_number[number], item) > 0:
                theirs.append(text)
        if not theirs:
            added.append(number)
            continue
        same = False
        for text in theirs:
            if norm(text) == norm(mine):
                same = True
        if not same:
            changed.append(number)
    ask = []
    for item in removed:
        text = tgt_texts.get(item["_old"], "")
        if not norm(text):
            continue
        best = 0.0
        covers = []
        for number in sorted(mapped.values()):
            if overlap(by_number[number], item) > 0:
                best = max(best, similarity(text, texts.get(number, "")))
                covers.append(texts.get(number, ""))
        if best < SIMILAR:
            ask.append({"cue": item["_old"], "start": float(item["start"]),
                        "end": float(item["end"]), "text": text,
                        "covered_by": covers})
    return added, changed, ask


# ------------------------------------------------------------ 分區搬


ITEM = re.compile(r"([0-9]+(?:\.[0-9]+)?)(?:\s*[-–]\s*([0-9]+(?:\.[0-9]+)?))?")


def item_ranges(items):
    """工作檔 items 的 seconds → [(起, 迄)]；看不懂的（「見 problems」「-」）
    略過，不當成 0 秒。"""
    out = []
    for item in items:
        value = str((item or {}).get("seconds") or "")
        for match in ITEM.finditer(value):
            lo = float(match.group(1))
            hi = float(match.group(2)) if match.group(2) else lo
            out.append((lo, hi))
    return out


def _touches(lo, hi, ranges, margin=ITEM_MARGIN):
    for first, last in ranges:
        if lo <= last + margin and hi >= first - margin:
            return True
    return False


def _with_text(book, texts, lo, hi):
    out = []
    for item in book["cues"]:
        if lo <= _middle(item) < hi:
            copy = dict(item)
            copy["_text"] = texts.get(int(item["index"]), "")
            out.append(copy)
    return out


def _key(item):
    return (round(float(item["start"]), 3), round(float(item["end"]), 3),
            item["_text"])


def _without(items, common):
    left = collections.Counter(common)
    out = []
    for item in items:
        if left[_key(item)]:
            left[_key(item)] -= 1
            continue
        out.append(item)
    return out


def _same_times(first, second):
    for key in ("start", "end"):
        if round(float(first[key]), 3) != round(float(second[key]), 3):
            return False
    return True


def _edit_kind(before, after):
    if not before:
        return "insert"
    if not after:
        return "delete"
    if len(before) == len(after):
        for first, second in zip(before, after):
            if not _same_times(first, second):
                return "bounds"
        return "text"
    outer = round(float(before[0]["start"]), 3) == round(
        float(after[0]["start"]), 3) and round(float(before[-1]["end"]), 3) \
        == round(float(after[-1]["end"]), 3)
    if outer and len(before) == 1:
        return "split"
    if outer and len(after) == 1:
        return "merge"
    return "replace"


def edits_between(before, before_texts, after, after_texts, lo, hi):
    """首播修改前快照 → 首播現在，在 `[lo, hi)` 的差。

    起迄和字都一樣的 cue 不算修改（範圍前面拆過 cue、號碼全部 +1 也一樣）；
    剩下的照時間重疊分組，一組是一個修改：before 是改之前那幾條、after 是
    改之後那幾條，kind 是 split／bounds／insert／text／delete／merge／
    replace。不限工作檔 items 的秒數：首播的修正常在沒有快照的步驟做，
    單元 seconds 也不一定是首播的時間（194 main 寫 1506–1517，實際改的是
    1565–1645），限了 305→306 的 5 處就全丟了。
    """
    old = _with_text(before, before_texts, lo, hi)
    new = _with_text(after, after_texts, lo, hi)
    pool = collections.Counter()
    for item in new:
        pool[_key(item)] += 1
    common = collections.Counter()
    for item in old:
        if pool[_key(item)] > common[_key(item)]:
            common[_key(item)] += 1
    marks = []
    for item in _without(old, common):
        marks.append((float(item["start"]), float(item["end"]), 0, len(marks),
                      item))
    for item in _without(new, common):
        marks.append((float(item["start"]), float(item["end"]), 1, len(marks),
                      item))
    marks.sort(key=lambda mark: mark[:4])
    groups = []
    for start, end, side, _order, item in marks:
        if groups and start < groups[-1]["hi"] - 0.0005:
            group = groups[-1]
            group["hi"] = max(group["hi"], end)
        else:
            group = {"lo": start, "hi": end, "before": [], "after": []}
            groups.append(group)
        group["after" if side else "before"].append(item)
    out = []
    for group in groups:
        out.append({"kind": _edit_kind(group["before"], group["after"]),
                    "span": [round(group["lo"], 3), round(group["hi"], 3)],
                    "before": group["before"], "after": group["after"]})
    return out


def _working(book, texts):
    out = []
    for item in book["cues"]:
        copy = dict(item)
        number = int(item["index"])
        copy["_old"] = number
        copy["_text"] = texts.get(number, "")
        copy["_orig"] = copy["_text"]
        out.append(copy)
    return out


def _labels(work, indexes):
    out = []
    for k in indexes:
        if work[k].get("_old"):
            out.append(work[k]["_old"])
    return out


def _text_spans(cues, texts, shift=0.0):
    """有字的段（相連而且同字的 cue 併成一段：同一句不可以從中間切），
    時間減 `shift`。"""
    out = []
    for run in runs(cues, texts):
        if run["text"]:
            out.append((run["start"] - shift, run["end"] - shift))
    return out


def _crossed(spans, moment, margin):
    for start, end in spans:
        if start < moment - margin and end > moment + margin:
            return True
    return False


def _safe(moment, src_spans, tgt_spans):
    """安全邊：首播現在沒有字跨過這一點，重播（加位移）也沒有字跨過（邊差
    一格內算對齊）。兩邊都是空白、只有空白 cue 跨過去也算——空白 cue 修到
    區外就好，不會切碎句子。"""
    return not _crossed(src_spans, moment, 0.0005) \
        and not _crossed(tgt_spans, moment, TOL)


def _safe_edge(moment, step, points, src_spans, tgt_spans, limit):
    """從 `moment` 往 step（-1 往前、+1 往後）找最近的安全邊；超過 limit
    就回傳 None。"""
    if _safe(moment, src_spans, tgt_spans):
        return moment
    if step < 0:
        ordered = sorted(points, reverse=True)
    else:
        ordered = sorted(points)
    for point in ordered:
        if (step < 0 and point >= moment) or (step > 0 and point <= moment):
            continue
        if (step < 0 and point < limit) or (step > 0 and point > limit):
            return None
        if _safe(point, src_spans, tgt_spans):
            return point
    return None


def find_zones(before, before_texts, after, after_texts, tgt_book, tgt_texts,
               lo, hi, off):
    """首播改過的地方併成區、擴到安全邊：[{lo, hi, edits, why?}]（首播秒數）。

    相連的修改先併（291「niqan gnklaan…」五條連續補字是一區，不是五個）；
    擴邊後重疊的再併。區最多擴到範圍外 15 秒（「前一句」迄點跟範圍內那條
    起點一起改，前一句中點在範圍外）；找不到安全邊的區記 why，整區要人判。
    """
    zones = []
    edits = edits_between(before, before_texts, after, after_texts, lo, hi)
    for edit in sorted(edits, key=lambda edit: edit["span"][0]):
        first, last = edit["span"]
        if zones and first <= zones[-1]["hi"] + 0.0005:
            zones[-1]["hi"] = max(zones[-1]["hi"], last)
            zones[-1]["edits"].append(edit)
        else:
            zones.append({"lo": first, "hi": last, "edits": [edit]})
    src_spans = _text_spans(after["cues"], after_texts)
    tgt_spans = _text_spans(tgt_book["cues"], tgt_texts, off)
    points = set()
    for item in after["cues"]:
        points.add(float(item["start"]))
        points.add(float(item["end"]))
    for item in tgt_book["cues"]:
        points.add(float(item["start"]) - off)
        points.add(float(item["end"]) - off)
    for zone in zones:
        left = _safe_edge(zone["lo"], -1, points, src_spans, tgt_spans,
                          lo - SAFE_OUT)
        right = _safe_edge(zone["hi"], 1, points, src_spans, tgt_spans,
                           hi + SAFE_OUT)
        if left is None or right is None:
            zone["why"] = ("找不到安全邊：首播 %.3f–%.3f 往外到範圍外 %.0f 秒內，"
                           "兩集總有一邊有字跨過去"
                           % (zone["lo"], zone["hi"], SAFE_OUT))
            continue
        zone["lo"], zone["hi"] = left, right
    merged = []
    for zone in sorted(zones, key=lambda zone: zone["lo"]):
        if merged and zone["lo"] < merged[-1]["hi"] - 0.0005:
            merged[-1]["hi"] = max(merged[-1]["hi"], zone["hi"])
            merged[-1]["edits"] += zone["edits"]
            if zone.get("why"):
                merged[-1]["why"] = zone["why"]
            continue
        merged.append(zone)
    return merged


def _version_cues(book, texts, first, last, off):
    """`book` 在首播 `[first, last]` 跟區重疊的 cue，加位移，帶 `_text`。"""
    out = []
    for item in book["cues"]:
        if overlap(item, {"start": first, "end": last}) <= 0.0005:
            continue
        moved = _shift(item, off)
        moved["_text"] = texts.get(int(item["index"]), "")
        moved["_src"] = int(item["index"])
        out.append(moved)
    return out


def _agrees(item, text, cues):
    """重播這條的字跟 `cues` 同時段的字一樣（一條相同，或相連幾條接起來
    相同；同一句跨幾條只算一次）。"""
    hits = []
    for other in cues:
        if overlap(item, other) > 0.0005 and norm(other["_text"]):
            hits.append(norm(other["_text"]))
    want = norm(text)
    if want in hits:
        return True
    joined = []
    for hit in hits:
        if not joined or joined[-1] != hit:
            joined.append(hit)
    return bool(joined) and want == "".join(joined)


def _overlapping_texts(item, cues):
    out = []
    for other in cues:
        if overlap(item, other) > 0.0005 and norm(other["_text"]):
            if not out or out[-1] != other["_text"]:
                out.append(other["_text"])
    return out


def _pair_cue(work, inside, used, new):
    """區內重播的哪一條是這條首播 cue 的原身：重疊最多、還沒配過的。
    回傳 (索引, 起迄是否都在一格內, 字是否相同)。"""
    best = None
    size = 0.0
    for k in inside:
        if k in used:
            continue
        shared = overlap(work[k], new)
        if shared > size:
            best, size = k, shared
    if best is None:
        return None, False, False
    old = work[best]
    close = abs(float(old["start"]) - float(new["start"])) <= TOL \
        and abs(float(old["end"]) - float(new["end"])) <= TOL
    same = norm(old["_text"]) == norm(new["_text"])
    if same and not close and size < 0.5 * min(_length(old), _length(new)):
        same = False
    return best, close, same


def _zone_one(work, zone, before, before_texts, after, after_texts, lo, hi,
              off):
    """一區套到重播（work 會被改）：("applied"|"same"|"ask", 說明)。"""
    first, last = zone["lo"], zone["hi"]
    start, end = first + off, last + off
    kinds = []
    for edit in zone["edits"]:
        kinds.append(edit["kind"])
    fresh = []
    for item in after["cues"]:
        if overlap(item, {"start": first, "end": last}) <= 0.0005:
            continue
        new = _shift(item, off)
        new["start"] = round(max(float(item["start"]), first) + off, 3)
        new["end"] = round(min(float(item["end"]), last) + off, 3)
        _clamp_sample(new)
        new["_text"] = after_texts.get(int(item["index"]), "")
        new["_old"] = None
        new["_orig"] = None
        new["_zone"] = True
        fresh.append(new)
    shown = ""
    for item in fresh:
        if norm(item["_text"]):
            shown = item["_text"]
            break
    info = {"kinds": kinds, "edits": len(zone["edits"]),
            "src": [round(first, 3), round(last, 3)],
            "tgt": [round(start, 3), round(end, 3)], "text": shown[:30]}
    inside = []
    across = []
    for k in range(len(work)):
        shared = overlap(work[k], {"start": start, "end": end})
        if shared <= 0.0005:
            continue
        if float(work[k]["start"]) >= start - TOL \
                and float(work[k]["end"]) <= end + TOL:
            inside.append(k)
        elif shared > TOL:
            across.append(k)
    info["target_cues"] = _labels(work, inside)
    if zone.get("why"):
        info["why"] = zone["why"]
        return "ask", info
    for k in across:
        if norm(work[k]["_text"]):
            info["why"] = ("區邊切到重播有字的 cue %s「%s」"
                           % (work[k].get("_old") or "（新）",
                              work[k]["_text"][:16]))
            return "ask", info
    earlier = _version_cues(before, before_texts, first, last, off)
    for k in inside:
        text = work[k]["_text"]
        if not norm(text) or _agrees(work[k], text, earlier) \
                or _agrees(work[k], text, fresh):
            continue
        theirs = _overlapping_texts(work[k], earlier)
        info["why"] = ("字不同：重播 cue %s「%s」，首播修改前是「%s」、現在是「%s」"
                       % (work[k].get("_old") or "（新）", text[:20],
                          "／".join(theirs)[:30] or "（沒有字）",
                          "／".join(_overlapping_texts(work[k], fresh))[:30]
                          or "（沒有字）"))
        return "ask", info
    for item in fresh:
        if not norm(item["_text"]) or lo <= _middle(item) - off < hi:
            continue
        covered = False
        for other in work:
            if overlap(other, item) > 0.0005 and norm(other["_text"]):
                covered = True
        if not covered:
            info["why"] = ("首播範圍外的字「%s」（%.3f–%.3f）在重播那裡沒有：可能"
                           "是首播自己的主播或別的節目"
                           % (item["_text"][:16], float(item["start"]) - off,
                              float(item["end"]) - off))
            return "ask", info

    # 起迄一律用首播現在的：只留其中幾條的重播起迄（一格內），會跟隔壁
    # 首播的 cue 疊 0.034 秒（306 cue 845／846）。
    built = []
    used = set()
    exact = 0
    for new in fresh:
        best, close, same = _pair_cue(work, inside, used, new)
        if best is not None and (same or close):
            keep = dict(work[best])
            keep["start"], keep["end"] = new["start"], new["end"]
            _clamp_sample(keep)
            if not same:
                keep["_text"] = new["_text"]
            elif close:
                exact += 1
            keep["_zone"] = True
            used.add(best)
            built.append(keep)
        else:
            built.append(new)
        # 起迄照首播切的，切法設定也標首播的（new_book 換成不衝突的名字）。
        built[-1]["_src_area"] = new.get("area")
    others = []
    for k in range(len(work)):
        if k in inside:
            continue
        item = dict(work[k])
        if k in across:
            item["_zone"] = True
            if float(item["start"]) < start and float(item["end"]) > end:
                tail = dict(item)
                tail["start"] = round(end, 3)
                tail["_old"] = None
                tail["_orig"] = None
                tail["images"] = {}
                _clamp_sample(tail)
                others.append(tail)
                item["end"] = round(start, 3)
            elif float(item["start"]) < start:
                item["end"] = round(start, 3)
            else:
                item["start"] = round(end, 3)
            _clamp_sample(item)
        others.append(item)
    kept = []
    for item in built:
        for other in others:
            if overlap(item, other) <= 0.0005:
                continue
            if float(other["start"]) <= float(item["start"]):
                item["start"] = float(other["end"])
            else:
                item["end"] = float(other["start"])
        if float(item["start"]) >= float(item["end"]) - 0.0005:
            if norm(item["_text"]):
                info["why"] = ("區邊對不齊：首播「%s」修到重播鄰條之後沒有長度"
                               % item["_text"][:16])
                return "ask", info
            continue
        _clamp_sample(item)
        kept.append(item)
    if not across and exact == len(inside) == len(kept):
        return "same", info
    candidate = others + kept
    candidate.sort(key=lambda item: (float(item["start"]),
                                     float(item["end"])))
    old = timeline_problems(work)
    problems = timeline_problems(candidate)
    for key in sorted(problems, key=str):
        if key in old:
            continue
        shown = []
        for k in range(1, len(key), 2):
            shown.append("%.3f–%.3f" % (key[k] - off, key[k + 1] - off))
        info["why"] = ("首播這一區自己的時間軸有%s（首播 %s），搬過來會在重播"
                       "造成新的%s" % (key[0], " 跟 ".join(shown), key[0]))
        return "ask", info
    work[:] = candidate
    info["new"] = len(kept)
    return "applied", info


def zone_port(before, before_texts, after, after_texts, tgt_book, tgt_texts,
              lo, hi, off):
    """分區搬：首播修改前快照（before）→ 首播現在（after）在 `[lo, hi)`
    有差的地方併成區、擴到安全邊；區內重播的 cue 整批換成首播現在的（加
    位移），區外重播一律不動。

    - 區內重播有字、跟首播修改前和修改後都不同（重播讀到首播沒有的「但是
      遇到風雨」「部落信箱」，或字形不同「漁撈」對「魚撈」）：這一區列
      `ask`、不套，其他區照套。跟首播現在一樣的算已經一樣。
    - 區內起迄一律用首播現在的（只留幾條重播起迄會跟隔壁首播的 cue 疊
      0.034 秒）；換進來的 cue 跟重播原本那條字一樣：留重播的身分、byte
      和圖條，TSV 列不動。
    - 搬進來的 cue 記首播的切法設定（`src_area`：新號 → 首播 cue 的
      area，沒有 area 是 None），new_book 照它標 area。
    - 首播這一區自己的時間軸就有重疊或倒置：那一區列 `ask`，其他區照套。
      只擋這次新造成的重疊或倒置；重播原本就有的記在 notes。
    """
    zones = find_zones(before, before_texts, after, after_texts, tgt_book,
                       tgt_texts, lo, hi, off)
    work = _working(tgt_book, tgt_texts)
    applied = []
    ask = []
    same = []
    for zone in zones:
        outcome, info = _zone_one(work, zone, before, before_texts, after,
                                  after_texts, lo, hi, off)
        {"applied": applied, "ask": ask, "same": same}[outcome].append(info)
    cues = []
    moves = {}
    texts = {}
    every = {}
    fresh = []
    was = {}
    touched = []
    olds = {}
    for item in tgt_book["cues"]:
        olds[int(item["index"])] = item
    src_area = {}
    for number, item in enumerate(work, 1):
        clean = {}
        for key in item:
            if not key.startswith("_"):
                clean[key] = item[key]
        clean["index"] = number
        cues.append(clean)
        every[number] = item["_text"]
        if item.get("_zone"):
            touched.append(number)
        if "_src_area" in item:
            src_area[number] = item["_src_area"]
        if item.get("_old") and item["_text"] == item["_orig"]:
            moves[item["_old"]] = number
            continue
        fresh.append(number)
        texts[number] = item["_text"]
        was[number] = item["_orig"] if item.get("_old") else ""
    notes = check_new(tgt_book["cues"], cues)
    removed = []
    for number in sorted(olds):
        if number not in moves:
            removed.append(number)
    blank = blank_in_target(after, after_texts, tgt_book, tgt_texts, lo, hi,
                            off, applied + ask + same)
    return {"cues": cues, "moves": moves, "fresh": fresh, "texts": texts,
            "all_texts": every, "was": was, "removed": removed,
            "removed_cues": _strip_numbers(olds, removed), "ported": {},
            "applied": applied, "ask": ask, "same": same,
            "touched": touched, "src_area": src_area, "notes": notes,
            "blank_in_target": blank}


def blank_in_target(after, after_texts, tgt_book, tgt_texts, lo, hi, off,
                    zones):
    """首播有字、重播沒字：首播現在在 `[lo, hi)` 有字的句子（相連同字的
    cue 併成一句），重播同一段（加位移）沒有 cue 或只有空白 cue——有字的
    重播 cue 蓋不到那句的 BLANK_COVER——而且那句不碰任何區（zones 是首播
    秒數）。首播從最早那份快照就有、沒改過的句子，分區搬不會碰；用 323 午
    現在的狀態模擬 269 午←323 午，嗆辣問答題目、歌詞四條就會這樣漏掉。
    只列出來，不搬。

    [{src, tgt, cues（首播 cue 號）, text, target_cues（重播那裡的空白
    cue）}]，照時間排。"""
    spans = []
    for zone in zones:
        spans.append(zone["src"])
    out = []
    for run in runs(after["cues"], after_texts):
        if not run["text"] or not lo <= (run["start"] + run["end"]) / 2 < hi:
            continue
        hit = False
        for first, last in spans:
            if run["start"] < last - 0.0005 and run["end"] > first + 0.0005:
                hit = True
        if hit:
            continue
        shifted = {"start": run["start"] + off, "end": run["end"] + off}
        covered = 0.0
        blanks = []
        for item in tgt_book["cues"]:
            shared = overlap(item, shifted)
            if shared <= 0.0005:
                continue
            if norm(tgt_texts.get(int(item["index"]), "")):
                covered += shared
            else:
                blanks.append(int(item["index"]))
        if covered > BLANK_COVER * (run["end"] - run["start"]):
            continue
        text = after_texts.get(run["cues"][0], "")
        out.append({"src": [round(run["start"], 3), round(run["end"], 3)],
                    "tgt": [round(shifted["start"], 3),
                            round(shifted["end"], 3)],
                    "cues": run["cues"], "text": text,
                    "target_cues": blanks})
    return out


def items_status(items, applied, asked, blank=()):
    """工作檔 items（重播秒數）哪幾項沒做到：有對應的區但列要人判
    （status ask，附原因）、落在首播有字重播沒字那裡（status blank，附
    首播 cue 和字），或根本不在首播改過的地方（status none）。

    先看項目真的跟哪一區重疊：碰到要人判的區就報要人判（就算旁邊 1 秒內
    有套用的區——305→306 cue 421 那區就是這樣被報成做到的）；跟哪一區都
    不重疊，才用 1 秒寬限比套用區、再比要人判區。"""
    done = []
    for info in applied:
        done.append(info["tgt"])
    out = []
    for first, last in items:
        why = None
        for info in asked:
            if _touches(first, last, [info["tgt"]], margin=0.0):
                why = info.get("why", "")
                break
        if why is None:
            if _touches(first, last, done):
                continue
            for info in asked:
                if _touches(first, last, [info["tgt"]]):
                    why = info.get("why", "")
                    break
        if why is not None:
            out.append({"range": [first, last], "status": "ask", "why": why})
            continue
        lacking = None
        for info in blank:
            if _touches(first, last, [info["tgt"]], margin=0.0):
                lacking = info
                break
        if lacking is None:
            out.append({"range": [first, last], "status": "none"})
        else:
            out.append({"range": [first, last], "status": "blank",
                        "cues": lacking["cues"], "text": lacking["text"]})
    return out


def items_lines(entries):
    """items_status 的結果寫成給人看的句子。"""
    lines = []
    for entry in entries:
        first, last = entry["range"]
        if entry["status"] == "ask":
            lines.append("工作檔項目 %s–%s 有對應的首播修改，但那一區列要人判：%s"
                         % (first, last, entry["why"]))
        elif entry["status"] == "blank":
            lines.append("工作檔項目 %s–%s 首播有字、重播沒字（首播 cue %s「%s」），"
                         "分區搬不搬，要人看"
                         % (first, last, entry["cues"], entry["text"]))
        else:
            lines.append("工作檔項目 %s–%s 不在首播改過的地方（首播這段沒改，或"
                         "秒數不是重播時間），要人看" % (first, last))
    return lines


def _strip_numbers(olds, numbers):
    out = []
    for number in numbers:
        out.append({"index": number, "start": float(olds[number]["start"]),
                    "end": float(olds[number]["end"])})
    return out


def zone_fixes(rows, src_name, tgt_name, result):
    """分區搬之後的 manual-fixes 五欄列。

    - 重播的列：cue 還在（字沒改）→ 照對應改號；那條被首播的修改換掉 →
      改號到同時段、字裡有「改後」的新 cue；找不到就擋（重播自己的訂正會被
      首播的修改蓋掉）。
    - 首播的列（manual-fixes 和 pending-fixes 轉來的）：照字對，不照號——
      「改後」在新字裡、「改前」在重播原本的字裡的，抄一份給重播。
    """
    by_number = {}
    for item in result["cues"]:
        by_number[item["index"]] = item
    gone = {}
    for item in result["removed_cues"]:
        gone[item["index"]] = item
    out = []
    for row in rows:
        if row[0] != tgt_name or not row[1].strip():
            out.append(list(row))
            continue
        parsed = _parse_cues(row[1])
        if parsed is None:
            raise PipelineError("manual-fixes 看不懂的 cue 欄：%s %r"
                                % (tgt_name, row[1]))
        news = []
        for number in _cue_list(parsed):
            if number in result["moves"]:
                news.append(result["moves"][number])
                continue
            if number not in gone:
                raise PipelineError("manual-fixes %s cue %d 在新時間軸找不到"
                                    % (tgt_name, number))
            found = None
            for new in result["fresh"]:
                if overlap(by_number[new], gone[number]) > 0 and row[3] \
                        and row[3] in result["texts"].get(new, ""):
                    found = new
                    break
            if found is None:
                raise PipelineError(
                    "重播 %s cue %d 自己的訂正「%s→%s」會被首播的修改蓋掉；要人看"
                    % (tgt_name, number, row[2], row[3]))
            news.append(found)
        out.append([row[0], _format_cues(min(news), max(news))]
                   + list(row[2:]))
    for row in rows:
        if row[0] != src_name or len(row) < 4 or not row[3]:
            continue
        for new in result["fresh"]:
            text = result["texts"].get(new, "")
            was = result["was"].get(new, "")
            if text == was or row[3] not in text:
                continue
            if row[2] not in ("", "（空白）") and row[2] not in was:
                continue
            why = row[4] if len(row) > 4 else ""
            copy = [tgt_name, str(new), row[2], row[3],
                    "%s（移植自 %s cue %s）" % (why, src_name, row[1])]
            if copy[:4] not in _heads(out):
                out.append(copy)
    return out


def source_pending_rows(lines, src_slug, src_name):
    """pending-fixes.txt 裡首播帶 cue 號的 sed → manual-fixes 五欄列（分區
    搬照字對，號碼只留著給人看）。"""
    out = []
    for line in lines:
        parts = line.split("\t")
        if len(parts) != 3 or parts[0] != src_slug:
            continue
        for cue, old, new in _sed_rows(parts[1]):
            out.append([src_name, str(cue), old, new, parts[2]])
    return out


def port_areas(tgt_areas, src_areas, ported, kept, texts=None, notes=None):
    """整段搬：搬進來的 cue 用到的區域類型，抄首播那一格；重播範圍外還有
    **有字的** cue 用同類型的別種設定 → 擋（一個類型只記一格）。範圍外只
    剩空白 cue 用舊設定的（254 舊 cue 710 那種），換成首播的、記進 notes。

    `kept` 的 `index` 要是重播現在的號（訊息給人對照用）；`texts` 是重播
    現在的字（None 表示一律當有字）。
    """
    out = dict(tgt_areas or {})
    kinds = set()
    for item in ported:
        if item.get("area"):
            kinds.add(item["area"])
    for kind in sorted(kinds):
        want = (src_areas or {}).get(kind)
        if want is None:
            raise PipelineError("首播 cue 有區域 %s，首播時間軸 areas 卻沒有"
                                % kind)
        have = out.get(kind)
        if have is not None and have != want:
            blanks = []
            for item in kept:
                if item.get("area") != kind:
                    continue
                number = item.get("index", "?")
                if texts is not None and not norm(texts.get(number, "")):
                    blanks.append(number)
                    continue
                raise PipelineError(
                    "areas 衝突：重播範圍外還有 cue %s 用「%s」%s，首播是 %s"
                    % (number, kind, have.get("preset"), want.get("preset")))
            if blanks and notes is not None:
                notes.append("範圍外空白 cue %s 原本用「%s」%s，areas 換成首播的 "
                             "%s" % (_numbers_text(blanks), kind,
                                     have.get("preset"), want.get("preset")))
        out[kind] = want
    return out


def zone_areas(tgt_areas, src_areas, kinds, src_name):
    """分區搬：搬進來的 cue 用到的首播區域類型 → (新的 areas, {首播類型:
    重播裡的名字}, 說明)。重播沒有這個類型、或設定相同，用原名；重播同名
    的是別種設定（區外重播自己的 cue 還是用它切的），首播的設定另存一個
    不衝突的名字（「島語時間（20240315_075）」，再衝突就加 -2…），搬進
    來的 cue 標那個名字——不可以掛在重播的設定底下。"""
    out = dict(tgt_areas or {})
    names = {}
    notes = []
    for kind in sorted(kinds):
        want = (src_areas or {}).get(kind)
        if want is None:
            raise PipelineError("首播 cue 有區域 %s，首播時間軸 areas 卻沒有"
                                % kind)
        base = "%s（%s）" % (kind, src_name[:12])
        name = kind
        number = 1
        while out.get(name) is not None and out[name] != want:
            number += 1
            name = base if number == 2 else "%s-%d" % (base, number - 1)
        out[name] = want
        names[kind] = name
        if name != kind:
            notes.append("分區搬進來的 cue 是首播用「%s」%s %s 切的，重播同名"
                         "的是 %s %s；首播的設定另存成「%s」"
                         % (kind, want.get("preset"), want.get("region"),
                            out[kind].get("preset"), out[kind].get("region"),
                            name))
    return out, names, notes


def _source_top_area(src_book, tgt_book, src_name):
    """首播沒有 area 的 cue 是照首播頂層 region 切的；兩集頂層 region 不同
    時，搬進來的這種 cue 要標一個 area 記首播的頂層設定，不然會落在重播
    頂層 region 底下。回傳 (加上這一格的首播 areas, 那一格的名字或
    None)。"""
    areas = dict(src_book.get("areas") or {})
    region = src_book.get("region")
    if region is None or region == tgt_book.get("region"):
        return areas, None
    name = "首播頂層（%s）" % src_name[:12]
    areas[name] = {"region": region}
    return areas, name


def _numbers_text(numbers):
    shown = []
    for number in numbers:
        shown.append(str(number))
    return "、".join(shown)


def new_book(tgt_book, src_book, result, src_name, lo, hi, off,
             tgt_texts=None, mode="whole"):
    """重播的新時間軸：重播頂層欄位都留著，換 cues、補 areas、加一筆 ported。

    首播的 `split`／`placed` 記的是首播的號碼，不抄。
    """
    book = {}
    for key in tgt_book:
        book[key] = tgt_book[key]
    back = {}
    for old in result["moves"]:
        back[result["moves"][old]] = old
    numbers = set(result["fresh"])
    kept = []
    ported = []
    for item in result["cues"]:
        if item["index"] in numbers:
            ported.append(item)
        else:
            copy = dict(item)
            copy["index"] = back.get(item["index"], item["index"])
            kept.append(copy)
    notes = list(result.get("notes", []))
    src_areas, top = _source_top_area(src_book, tgt_book, src_name)
    if mode == "zone":
        marks = dict(result.get("src_area", {}))
        kinds = set()
        for number in marks:
            if not marks[number] and top:
                marks[number] = top
            if marks[number]:
                kinds.add(marks[number])
        book["areas"], names, more = zone_areas(
            tgt_book.get("areas"), src_areas, kinds, src_name)
        notes += more
        for item in result["cues"]:
            if item["index"] not in marks:
                continue
            if marks[item["index"]]:
                item["area"] = names[marks[item["index"]]]
            else:
                item.pop("area", None)
    else:
        if top:
            for item in ported:
                if not item.get("area"):
                    item["area"] = top
        book["areas"] = port_areas(tgt_book.get("areas"), src_areas,
                                   ported, kept, tgt_texts, notes)
    if not book["areas"]:
        del book["areas"]
    book["cues"] = result["cues"]
    history = list(tgt_book.get("ported", []))
    first = min(numbers) if numbers else None
    last = max(numbers) if numbers else None
    entry = {"mode": mode, "from": src_name, "src_range": [lo, hi],
             "range": result["range"], "offset": off, "cues": [first, last],
             "removed": len(result["removed"]), "added": len(numbers),
             "notes": notes}
    if mode == "zone":
        entry["applied"] = len(result.get("applied", []))
        entry["asked"] = len(result.get("ask", []))
        entry["base"] = result.get("base")
    history.append(entry)
    book["ported"] = history
    return book


# ------------------------------------------------------------ TSV


def next_tsv_name(names):
    """新 TSV：現有最大號＋1（號碼有缺時，檔數＋1 會蓋掉既有的檔）。"""
    top = 0
    for name in names:
        match = re.match(r"^b([0-9]+)\.tsv$", os.path.basename(name))
        if match:
            top = max(top, int(match.group(1)))
    return "b%02d.tsv" % (top + 1)


def port_tsvs(files, result, total):
    """({檔名: 改號後的列}, 新檔名, 新檔的列)。文字一個 byte 都不動。"""
    rewritten = {}
    for name in sorted(files):
        rewritten[name] = offband_backfill.rewrite(files[name],
                                                   result["moves"], total)
    rows = []
    for number in sorted(result["fresh"]):
        rows.append((number, result["texts"].get(number, "")))
    return rewritten, next_tsv_name(list(files)), rows


def check_cover(files, total):
    """每條 cue 剛好在一份 TSV，沒有多出來的號碼。"""
    seen = {}
    problems = []
    for name in sorted(files):
        for number, _text in files[name]:
            if number < 1 or number > total:
                problems.append("cue %d 不在 1–%d（%s）" % (number, total, name))
            elif number in seen:
                problems.append("cue %d 同時在 %s 和 %s"
                                % (number, seen[number], name))
            else:
                seen[number] = name
    missing = []
    for number in range(1, total + 1):
        if number not in seen:
            missing.append(number)
    if missing:
        problems.append("cue %s 沒有 TSV 列" % missing[:10])
    if problems:
        raise PipelineError("；".join(problems[:5]))


# ------------------------------------------------------------ 訂正紀錄


def _parse_cues(field):
    match = CUE_FIELD.match(field.strip())
    if not match:
        return None
    first = int(match.group(1))
    last = int(match.group(2)) if match.group(2) else None
    return first, last


def _format_cues(first, last):
    if last is None or last == first:
        return str(first)
    return "%d–%d" % (first, last)


def _new_cue_overlapping(result, item):
    """重播舊 cue 時段內，搬進來的 cue 新號。"""
    numbers = set(result["ported"].values())
    out = []
    for cue in result["cues"]:
        if cue["index"] in numbers and overlap(cue, item) > 0:
            out.append(cue["index"])
    return out


def port_fixes(rows, src_name, tgt_name, tgt_cues, result):
    """manual-fixes 的五欄列（成果檔名、cue、改前、改後、理由）照移植修改。

    - 重播、範圍外：照對應改號。
    - 重播、範圍內：首播搬進來的字已經有「改後」→ 首播也有這列就作廢
      （首播那列會抄過來），沒有就改號指到搬進來的 cue；首播沒有「改後」
      → 擋：重播自己修過、首播沒有，要先收進定本。
    - 首播、範圍內：抄一份給重播集，理由加「（移植自 <首播> cue N）」。
    """
    old_cues = {}
    for item in tgt_cues:
        old_cues[int(item["index"])] = item
    removed = set(result["removed"])
    source_fixes = {}
    for row in rows:
        if row[0] != src_name:
            continue
        parsed = _parse_cues(row[1])
        if parsed is None or parsed[0] not in result["ported"]:
            continue
        for number in _cue_list(parsed):
            if number in result["ported"]:
                source_fixes[(result["ported"][number], row[3])] = row
    out = []
    for row in rows:
        if row[0] != tgt_name or not row[1].strip():
            out.append(list(row))
            continue
        parsed = _parse_cues(row[1])
        if parsed is None:
            raise PipelineError("manual-fixes 看不懂的 cue 欄：%s %r"
                                % (tgt_name, row[1]))
        numbers = _cue_list(parsed)
        inside = []
        for number in numbers:
            if number in removed:
                inside.append(number)
        if not inside:
            for number in numbers:
                if number not in result["moves"]:
                    raise PipelineError("manual-fixes %s cue %d 在新時間軸找不到"
                                        % (tgt_name, number))
            last = result["moves"][parsed[1]] if parsed[1] else None
            out.append([row[0], _format_cues(result["moves"][parsed[0]], last)]
                       + list(row[2:]))
            continue
        if len(inside) != len(numbers):
            raise PipelineError("manual-fixes %s cue %s 跨範圍邊界，要人看"
                                % (tgt_name, row[1]))
        hits = []
        for number in inside:
            found = None
            for new in _new_cue_overlapping(result, old_cues[number]):
                text = result["texts"].get(new, "")
                if row[3] and row[3] in text:
                    found = new
            if found is None:
                covers = []
                for new in _new_cue_overlapping(result, old_cues[number]):
                    covers.append(result["texts"].get(new, ""))
                raise PipelineError(
                    "重播 %s cue %d 自己的訂正「%s→%s」，首播同處是「%s」：整段搬"
                    "會蓋掉，要人看"
                    % (tgt_name, number, row[2], row[3], "／".join(covers)))
            hits.append(found)
        carried = True
        for new in hits:
            if (new, row[3]) not in source_fixes:
                carried = False
        if carried:
            continue
        out.append([row[0], _format_cues(min(hits), max(hits))]
                   + list(row[2:]))
    for row in rows:
        if row[0] != src_name:
            continue
        parsed = _parse_cues(row[1])
        if parsed is None:
            continue
        news = []
        for number in _cue_list(parsed):
            if number in result["ported"]:
                news.append(result["ported"][number])
        if not news:
            continue
        why = row[4] if len(row) > 4 else ""
        copy = [tgt_name, _format_cues(min(news), max(news)), row[2], row[3],
                "%s（移植自 %s cue %s）" % (why, src_name, row[1])]
        if copy[:4] not in _heads(out):
            out.append(copy)
    return out


def _heads(rows):
    out = []
    for row in rows:
        out.append(list(row[:4]))
    return out


def _cue_list(parsed):
    first, last = parsed
    if last is None:
        return [first]
    return list(range(first, last + 1))


# pending-fixes 的 sed 裡指 cue 號的地方（2026-10-28 全檔 683 列量過的寫法）：
#
#   /^802\t/ s/…/…/                 位址（\t 也有人寫 [[:space:]]）
#   s/^802\than\t舊/803\than\t新/     找、換開頭各一個號
#   s/^\(734\|738\|71[34]\)\than\t…   多選一（可以帶字元類），\(N\) 單一個也算
#   s/^\(682\than\t\)所以/\1那以/     號碼包在大括號開頭
#   s/^\([0-9]*\)\than\t…             照字找、不指號
#
# `^` 後面接別的東西（`7.4`、`[0-9]\{3\}`）分不出指哪幾條，一律報錯，不可以
# 當成不帶號放過去：012 晚的多選一寫法就是這樣被放過，整段搬後指到別條字幕。
CUE_ATOM = re.compile(r"(?:[0-9]|\[[0-9-]+\])+")
CUE_WILDCARD = re.compile(r"\[0-9\](?:\*|\\\+)")
CUE_TAB = re.compile(r"\\t|\[\[:space:\]\]")
REPLACE_CUE = re.compile(r"[0-9]+(?=\\than\\t)")
SED_FLAGS = "gpI0123456789"


def _unreadable(expr, why):
    return PipelineError("pending-fixes 看不懂的 sed（%s）：%s" % (why, expr))


def _bracket_end(expr, pos, end):
    """`[` 在 pos：回傳 `]` 後面的位置（`[]…]`、`[^]…]` 的第一個 `]` 是字）。"""
    i = pos + 1
    if i < end and expr[i] == "^":
        i += 1
    if i < end and expr[i] == "]":
        i += 1
    while i < end:
        if expr.startswith("[:", i):
            close = expr.find(":]", i + 2, end)
            if close < 0:
                raise _unreadable(expr, "[: 沒有收尾")
            i = close + 2
            continue
        if expr[i] == "]":
            return i + 1
        i += 1
    raise _unreadable(expr, "[ 沒有收尾")


def _regex_end(expr, pos):
    """從 pos 往後找沒跳脫的 `/`（regex 的收尾）。"""
    i = pos
    while i < len(expr):
        char = expr[i]
        if char == "\\":
            i += 2
            continue
        if char == "[":
            i = _bracket_end(expr, i, len(expr))
            continue
        if char == "/":
            return i
        i += 1
    raise _unreadable(expr, "/ 沒有收尾")


def _sed_parts(expr):
    """sed 指令 → [(種類, 起, 迄)]，種類是 address／search／replace（迄不含
    收尾的 `/`）。只認 `[/位址/] s/找/換/旗標`，`;` 接下一個；別的指令報錯。"""
    parts = []
    i = 0
    size = len(expr)
    while True:
        while i < size and expr[i] in " ;":
            i += 1
        if i >= size:
            return parts
        if expr[i] == "/":
            close = _regex_end(expr, i + 1)
            parts.append(("address", i + 1, close))
            i = close + 1
            while i < size and expr[i] == " ":
                i += 1
        if not expr.startswith("s/", i):
            raise _unreadable(expr, "只認 s/…/…/")
        middle = _regex_end(expr, i + 2)
        close = _regex_end(expr, middle + 1)
        parts.append(("search", i + 2, middle))
        parts.append(("replace", middle + 1, close))
        i = close + 1
        while i < size and expr[i] in SED_FLAGS:
            i += 1


def _group_end(expr, pos, end):
    """`\\(` 後面 pos 起，回傳對應 `\\)` 的位置；順便切出最外層的 `\\|`
    選項 → (收尾位置, [(起, 迄)])。"""
    depth = 0
    alts = []
    first = pos
    i = pos
    while i < end:
        if expr.startswith("\\(", i):
            depth += 1
            i += 2
            continue
        if expr.startswith("\\)", i):
            if depth == 0:
                alts.append((first, i))
                return i, alts
            depth -= 1
            i += 2
            continue
        if expr.startswith("\\|", i) and depth == 0:
            alts.append((first, i))
            first = i + 2
            i += 2
            continue
        if expr[i] == "\\":
            i += 2
            continue
        if expr[i] == "[":
            i = _bracket_end(expr, i, end)
            continue
        i += 1
    raise _unreadable(expr, "\\( 沒有收尾")


def _atom_numbers(atom):
    """`106[2-5]` → [1062, 1063, 1064, 1065]。"""
    heads = [""]
    for piece in re.findall(r"[0-9]|\[[0-9-]+\]", atom):
        if piece.startswith("["):
            digits = []
            body = piece[1:-1]
            i = 0
            while i < len(body):
                if i + 2 < len(body) and body[i + 1] == "-":
                    for code in range(ord(body[i]), ord(body[i + 2]) + 1):
                        digits.append(chr(code))
                    i += 3
                    continue
                digits.append(body[i])
                i += 1
        else:
            digits = [piece]
        grown = []
        for head in heads:
            for digit in digits:
                grown.append(head + digit)
        heads = grown
    out = []
    for head in heads:
        out.append(int(head))
    return sorted(set(out))


def _ref(expr, start, end, whole):
    return {"start": start, "end": end, "whole": whole,
            "numbers": _atom_numbers(expr[start:end])}


def _anchored_refs(expr, pos, end):
    """regex 開頭是 `^`、pos 在 `^` 後面：→ (指號的地方, cue 頭的資訊)。
    cue 頭的資訊給 `_sed_rows` 拆「改前」：{"groups": [各大括號裡號碼以外的
    字], "rest": 起}。"""
    if expr.startswith("\\(", pos):
        close, alts = _group_end(expr, pos + 2, end)
        refs = []
        wild = False
        inner = ""
        for first, last in alts:
            match = CUE_ATOM.match(expr, first, last)
            if match and match.end() == last:
                refs.append(_ref(expr, first, last, True))
            elif match and CUE_TAB.match(expr, match.end(), last):
                refs.append(_ref(expr, first, match.end(), False))
                inner = expr[match.end():last]
            elif CUE_WILDCARD.match(expr, first, last):
                wild = True
            else:
                raise _unreadable(expr, "^\\( 後面不是 cue 號")
        if wild and refs:
            raise _unreadable(expr, "多選一裡有號碼也有 [0-9]*")
        after = close + 2
        groups = [inner]
        if refs and refs[0]["whole"]:
            if expr.startswith("\\(", after):
                second, _alts = _group_end(expr, after + 2, end)
                if not CUE_TAB.match(expr, after + 2, second):
                    raise _unreadable(expr, "多選一後面不是 \\t")
                groups.append(expr[after + 2:second])
                after = second + 2
            elif not CUE_TAB.match(expr, after, end):
                raise _unreadable(expr, "多選一後面不是 \\t")
        for item in refs:
            if item["whole"] != refs[0]["whole"]:
                raise _unreadable(expr, "多選一的寫法混雜")
        return refs, {"groups": groups, "rest": after}
    match = CUE_ATOM.match(expr, pos, end)
    if match and CUE_TAB.match(expr, match.end(), end):
        return ([_ref(expr, pos, match.end(), False)],
                {"groups": [], "rest": match.end()})
    if CUE_WILDCARD.match(expr, pos, end):
        return [], None
    raise _unreadable(expr, "^ 後面不是 cue 號")


def _sed_commands(expr):
    """→ 每個 s 指令一筆 {address, search, replace: (起, 迄), refs: 指號的
    地方, head: search 的 cue 頭（沒有是 None）}。"""
    commands = []
    address = None
    for kind, start, end in _sed_parts(expr):
        if kind == "address":
            address = (start, end)
            continue
        if kind == "search":
            command = {"address": address, "search": (start, end),
                       "refs": [], "head": None}
            address = None
            if command["address"]:
                first, last = command["address"]
                if expr.startswith("^", first) and first < last:
                    refs, _head = _anchored_refs(expr, first + 1, last)
                    command["refs"] += refs
            if expr.startswith("^", start) and start < end:
                refs, head = _anchored_refs(expr, start + 1, end)
                command["refs"] += refs
                if refs:
                    command["head"] = head
            commands.append(command)
            continue
        command = commands[-1]
        command["replace"] = (start, end)
        match = REPLACE_CUE.match(expr, start, end)
        if match:
            item = _ref(expr, start, match.end(), False)
            item["replace"] = True
            command["refs"].append(item)
    return commands


def _sed_refs(expr):
    refs = []
    for command in _sed_commands(expr):
        refs += command["refs"]
    return refs


def _sed_cues(expr):
    """sed 指到的 cue 號（集合）。看不懂的寫法丟 PipelineError。"""
    found = set()
    for item in _sed_refs(expr):
        found.update(item["numbers"])
    return found


def _render_atom(numbers, whole, original, old):
    """改號後的號碼寫回去：跟原本一樣就原樣；一個號、同字首只差末位（寫成
    字元類）、獨立的一個選項（拆成 `\\|`），其他寫不回去就擋。"""
    numbers = sorted(set(numbers))
    if numbers == sorted(set(old)):
        return original
    texts = []
    for number in numbers:
        texts.append(str(number))
    if len(texts) == 1:
        return texts[0]
    prefix = texts[0][:-1]
    same = True
    for text in texts:
        if len(text) != len(texts[0]) or text[:-1] != prefix:
            same = False
    if same:
        tails = ""
        for text in texts:
            tails += text[-1]
        return "%s[%s]" % (prefix, tails)
    if whole:
        return "\\|".join(texts)
    raise PipelineError("pending-fixes 的 %s 改號成 %s 寫不回同一個寫法，要人看"
                        % (original, ", ".join(texts)))


def _renumber_sed(expr, moves):
    """sed 裡指的 cue 號照 `moves`（{舊號: 新號}）改，寫法照原本的。"""
    out = []
    at = 0
    for item in sorted(_sed_refs(expr), key=lambda ref: ref["start"]):
        news = []
        for number in item["numbers"]:
            news.append(moves[number])
        out.append(expr[at:item["start"]])
        out.append(_render_atom(news, item["whole"],
                                expr[item["start"]:item["end"]],
                                item["numbers"]))
        at = item["end"]
    out.append(expr[at:])
    return "".join(out)


def _unescape(text):
    return re.sub(r"\\(.)", r"\1", text)


def _strip_any(text):
    """開頭的 `.*` 拿掉（後面還有字才拿）。"""
    if text.startswith(".*") and len(text) > 2:
        return text[2:]
    return text


def _sed_rows(expr):
    """帶 cue 號的 s/// → [(cue, 改前, 改後)]，多選一的每個號碼各一筆；
    cue 頭（號碼、`\\than\\t`、包號碼的大括號）拆掉，換的那邊開頭的
    `\\1`、`\\2` 換回大括號裡的字。"""
    out = []
    for command in _sed_commands(expr):
        numbers = set()
        for item in command["refs"]:
            if not item.get("replace"):
                numbers.update(item["numbers"])
        if not numbers:
            for item in command["refs"]:
                numbers.update(item["numbers"])
        if not numbers:
            continue
        start, end = command["search"]
        old = expr[start:end]
        groups = []
        head = command["head"]
        if head is not None:
            groups = head["groups"]
            old = "".join(groups) + expr[head["rest"]:end]
            old = re.sub(r"^(?:\\t|\[\[:space:\]\])(?:hand?(?:\\\?)?"
                         r"(?:\\t|\[\[:space:\]\]))?", "", old)
        first, last = command["replace"]
        new = expr[first:last]
        while True:
            match = re.match(r"\\([1-9])", new)
            if not match:
                break
            slot = int(match.group(1)) - 1
            new = (groups[slot] if slot < len(groups) else "") + new[2:]
        new = re.sub(r"^(?:[0-9]+)?\\than\\t", "", new)
        if old.endswith("$") and not old.endswith("\\$"):
            old = old[:-1]
        old = _strip_any(old)
        new = _strip_any(new)
        for number in sorted(numbers):
            out.append((number, _unescape(old) or "（空白）",
                        _unescape(new) or "（空白）"))
    return out


def port_pending(lines, src_slug, tgt_slug, src_name, tgt_name, result):
    """pending-fixes.txt（slug、sed、理由三欄）：重播帶 cue 號的，範圍外改號、
    範圍內擋；首播範圍內帶 cue 號的，轉成重播的 manual-fixes 列。"""
    out = []
    extra = []
    removed = set(result["removed"])
    for line in lines:
        parts = line.split("\t")
        if len(parts) != 3:
            out.append(line)
            continue
        slug, expr, why = parts
        numbers = _sed_cues(expr)
        if slug == tgt_slug and numbers:
            inside = sorted(numbers & removed)
            if inside:
                raise PipelineError(
                    "pending-fixes 重播 %s 範圍內的 cue %s 有組裝前的 sed，要人看："
                    "%s" % (tgt_name, inside, expr))
            for number in numbers:
                if number not in result["moves"]:
                    raise PipelineError("pending-fixes %s cue %d 在新時間軸找不到"
                                        % (tgt_name, number))
            out.append("\t".join([slug, _renumber_sed(expr, result["moves"]),
                                  why]))
            continue
        out.append(line)
        if slug == src_slug and numbers:
            for cue, old, new in _sed_rows(expr):
                if cue in result["ported"]:
                    extra.append([tgt_name, str(result["ported"][cue]), old,
                                  new, "%s（移植自 %s cue %d）"
                                  % (why, src_name, cue)])
    return out, extra


# ------------------------------------------------------------ 段落表


def _stamp(value):
    value = round(float(value), 3)
    if value == int(value):
        return str(int(value))
    return "%.3f" % value


SAME_ROW = ("類型", "單元語別", "字幕上緣y", "字幕下緣y", segments.INTERVIEWEE,
            segments.SPEECH)


def port_segments(tgt_rows, src_rows, start, end, off, snap=SEG_SNAP):
    """重播 `[start, end)` 那幾列換成首播那幾列（加位移），新列邊跟重播
    原本的列邊差 ≤ 3 秒就用重播的，相同的相鄰列併成一列。每列補「依據」。"""
    edges = []
    for row in tgt_rows:
        edges.append(float(row["起秒"]))
        edges.append(float(row["迄秒"]))
    pieces = []
    for row in tgt_rows:
        lo, hi = float(row["起秒"]), float(row["迄秒"])
        if lo < start:
            pieces.append([lo, min(hi, start), dict(row), False])
    for row in src_rows:
        lo = max(float(row["起秒"]) + off, start)
        hi = min(float(row["迄秒"]) + off, end)
        if hi > lo:
            fresh = dict(row)
            fresh["依據"] = "人工"
            pieces.append([lo, hi, fresh, True])
    for row in tgt_rows:
        lo, hi = float(row["起秒"]), float(row["迄秒"])
        if hi > end:
            pieces.append([max(lo, end), hi, dict(row), False])
    for k in range(1, len(pieces)):
        edge = pieces[k][0]
        best = None
        for known in edges:
            if abs(known - edge) <= snap and (
                    best is None or abs(known - edge) < abs(best - edge)):
                best = known
        if best is not None:
            pieces[k][0] = best
            pieces[k - 1][1] = best
    kept = []
    for piece in pieces:
        if piece[1] - piece[0] <= 0.0005:
            continue
        if kept and kept[-1][1] != piece[0]:
            piece[0] = kept[-1][1]
        if kept and (kept[-1][3] or piece[3]) \
                and _same_row(kept[-1][2], piece[2]):
            kept[-1][1] = piece[1]
            kept[-1][3] = True
            continue
        kept.append(piece)
    out = []
    for lo, hi, row, _ported in kept:
        row = dict(row)
        row["起秒"] = _stamp(lo)
        row["迄秒"] = _stamp(hi)
        if not row.get("依據"):
            row["依據"] = "人工"
        for column in (segments.INTERVIEWEE, segments.SPEECH):
            if row.get(column) is None:
                row[column] = ""
        out.append(row)
    return out


def _same_row(first, second):
    for column in SAME_ROW:
        if (first.get(column) or "") != (second.get(column) or ""):
            return False
    return True


# ------------------------------------------------------------ 像素


def frame_centre(seconds, frame=FRAME):
    """這個時間所在那一格的中心：貼著換格的邊會抽到前後格。"""
    return (math.floor(seconds / frame + 1e-9) + 0.5) * frame


def _merged_spans(spans):
    out = []
    for first, last in sorted(spans):
        if out and first <= out[-1][1]:
            out[-1][1] = max(out[-1][1], last)
        else:
            out.append([first, last])
    return out


def _along(spans, moment):
    """`moment` 在 spans 首尾相接後的位置（不在任何一段裡給 None）。"""
    passed = 0.0
    for first, last in spans:
        if first <= moment <= last:
            return passed + moment - first
        passed += last - first
    return None


def _at(spans, position):
    """_along 的反向：首尾相接後第 `position` 秒是哪個時間。"""
    for first, last in spans:
        if position <= last - first:
            return first + position
        position -= last - first
    return spans[-1][1]


def probe_points(result, off, holes=(), frame=FRAME):
    """取樣點（首播時間和重播時間都取格中心）。

    內部 7 點平均分布在「這次會改的地方」：整段搬是整個範圍，分區搬是
    套用的區（首尾相接後切 7 格，每格一點）。每格先挑這次會改到的 cue
    （字改掉的、補進來的、分區搬改過的），沒有就挑最靠格中間的新 cue，
    再沒有就用格中間——只挑前 7 條改到的話，262 的 7 點全擠在範圍前 40%。
    分區搬另外保證每個套用區至少一個內部點（區多、區短時 7 格會整區
    跳過：190 份工作檔全量乾跑，1188 個套用區只有 651 區有點），總數不設
    上限。

    邊界點（kind edge）放在兩集都該相同的畫面：分區搬在每個套用區外 1
    秒，整段搬在第一條被換的 cue 前 1 秒、最後一條後 1 秒（沒有被換的
    cue 就不取）。落在節目範圍外、或範圍頭尾 4 秒內的不取：範圍頭尾常是
    片頭動畫、片頭字卡、主播棚，兩集本來就不同（227→216 起點內側 MAD
    41.15、迄點內側 82.93；332→151 起點後 1.89 秒 19.19，332→089 到起點後
    3.29 秒才對得上）。範圍內
    超過 60 秒沒有錨點的洞，洞中間一點。
    """
    by_number = {}
    for item in result["cues"]:
        by_number[item["index"]] = item
    focus = []
    for number in list(result.get("changed", [])) \
            + list(result.get("added", [])) + list(result.get("touched", [])):
        if number in by_number and number not in focus:
            focus.append(number)
    fresh = sorted(result.get("fresh", []))
    start, end = result["range"]
    edges = []
    if "applied" in result:
        zones = []
        for info in result["applied"]:
            zones.append(info["tgt"])
        spans = _merged_spans(zones)
        for first, last in spans:
            edges += [first - PROBE_EDGE, last + PROBE_EDGE]
    else:
        spans = [[start, end]]
        if result.get("replaced"):
            first, last = result["replaced"]
            edges = [first - PROBE_EDGE, last + PROBE_EDGE]
    if not spans:
        spans = [[start, end]]
    total = 0.0
    for first, last in spans:
        total += last - first
    width = total / float(PROBE_INSIDE)
    out = []
    for slot in range(PROBE_INSIDE):
        lo = slot * width
        hi = lo + width
        centre = (lo + hi) / 2.0
        chosen = None
        for number in focus:
            place = _along(spans, _middle(by_number[number]))
            if place is not None and lo <= place < hi:
                chosen = number
                break
        if chosen is None:
            best = None
            best_gap = None
            for number in fresh:
                place = _along(spans, _middle(by_number[number]))
                if place is None or not lo <= place < hi:
                    continue
                if best is None or abs(place - centre) < best_gap:
                    best, best_gap = number, abs(place - centre)
            chosen = best
        if chosen is None:
            out.append(_probe(_at(spans, centre), off, "inside", frame))
        else:
            out.append(_probe(_middle(by_number[chosen]), off, "inside",
                              frame, chosen))
    for first, last in sorted(_zone_list(result)):
        if _has_inside(out, first, last, frame):
            continue
        out.append(_zone_probe(first, last, focus + fresh, by_number, off,
                               frame))
    for moment in edges:
        if start + PROBE_END <= moment <= end - PROBE_END:
            out.append(_probe(moment, off, "edge", frame))
    for lo, hi in holes:
        out.append(_probe((lo + hi) / 2.0 + off, off, "hole", frame))
    return out


def _zone_list(result):
    """分區搬的每個套用區（重播時間）；整段搬沒有。"""
    out = []
    for info in result.get("applied", []):
        out.append((info["tgt"][0], info["tgt"][1]))
    return out


def _has_inside(points, first, last, frame):
    for point in points:
        if point["kind"] == "inside" and \
                first - frame <= point["tgt"] <= last + frame:
            return True
    return False


def _zone_probe(first, last, numbers, by_number, off, frame):
    """補給還沒有內部點的套用區一點：區裡這次會改到的 cue 挑最靠區中間
    的那條，沒有就取區中點（區很短也一樣）。"""
    centre = (first + last) / 2.0
    best = None
    best_gap = None
    for number in numbers:
        if number not in by_number:
            continue
        middle = _middle(by_number[number])
        if not first <= middle <= last:
            continue
        if best is None or abs(middle - centre) < best_gap:
            best, best_gap = number, abs(middle - centre)
    if best is None:
        return _probe(centre, off, "inside", frame)
    return _probe(_middle(by_number[best]), off, "inside", frame, best)


def _probe(target_time, off, kind, frame, cue=None):
    target = frame_centre(target_time, frame)
    source = frame_centre(target - off, frame)
    item = {"kind": kind, "src": source, "tgt": target}
    if cue is not None:
        item["cue"] = cue
    return item


def mad(first, second):
    """兩張灰階圖的平均絕對差（0–255）。"""
    import numpy
    return float(numpy.mean(numpy.abs(numpy.asarray(first, dtype=float)
                                      - numpy.asarray(second, dtype=float))))


def frame_mad(first, second, boxes=MASK):
    """遮掉上面兩角（台標）和字幕帶下面整條（天氣框、人名字卡）再算
    MAD；遮罩照圖的寬高比例放。"""
    import numpy
    first = numpy.asarray(first, dtype=float)
    second = numpy.asarray(second, dtype=float)
    height, width = first.shape[:2]
    keep = numpy.ones((height, width), dtype=bool)
    for x0, y0, x1, y1 in boxes:
        keep[int(round(y0 * height)):int(round(y1 * height)),
             int(round(x0 * width)):int(round(x1 * width))] = False
    return float(numpy.mean(numpy.abs(first[keep] - second[keep])))


def _verdict_of(point, limit):
    """一點的判讀：differ（同位移遠超過底值：那一格兩集畫面不同，片頭字
    卡、泛白轉場；局部最小在這裡沒有意義，不相干的兩張圖也有三成碰巧是
    局部最小）、match（同位移是嚴格局部最小）、miss（鄰格比同位移更
    像）、flat（打平，或沒抽 ±1 格）。"""
    if point["same"] > limit:
        return "differ"
    if "minus" in point and "plus" in point:
        nearest = min(point["minus"], point["plus"])
        if point["same"] + MAD_MARGIN <= nearest:
            return "match"
        if point["same"] >= nearest + MAD_MARGIN:
            return "miss"
    return "flat"


def judge_frames(points):
    """以「同位移是局部最小」為主、絕對值為輔：

    - 絕對值改成相對底值：底值＝同位移 MAD 的中位數（跨年代亮度、編碼
      不同，底值本來就不一樣：同年代 0.5–0.9，332→089 遮掉台標、天氣框 1.2），
      不可超過 FLOOR_MAX。同位移超過 max(1.5, 底值 × FAR_TIMES) 的點算
      「畫面不同」，內部、邊界各不超過 DIFFER_SHARE（片頭字卡、泛白轉場
      偶爾一點不擋；邊界點只有一兩個時，一點畫面不同就擋）。
    - 其餘的點：內部點（inside、hole）至少 MATCH_SHARE 是嚴格局部最小
      （比 ±1 格小 0.1 以上；靜態畫面打平不算數，也不算錯）；「鄰格比
      同位移更像」的不超過 MISS_SHARE——位移差一格就是這裡擋下（332→089
      差一格 74 點裡 51 點；位移對的 2 點）。
    舊 plan 的 edge_out（範圍外側）只記錄。"""
    problems = []
    used = []
    for point in points:
        if point["kind"] != "edge_out":
            used.append(point)
    sames = []
    for point in used:
        sames.append(point["same"])
    floor = statistics.median(sames) if sames else 0.0
    limit = max(MAD_SAME, FAR_TIMES * floor)
    counts = collections.Counter()
    total = collections.Counter()
    shown = collections.defaultdict(list)
    for point in used:
        group = "edge" if point["kind"] == "edge" else "inside"
        kind = _verdict_of(point, limit)
        total[group] += 1
        counts[(group, kind)] += 1
        if kind == "differ" and len(shown[group]) < 5:
            shown[group].append("首播 %.3f（同位移 %.2f）"
                                % (point.get("src", 0.0), point["same"]))
    judged = total["inside"] - counts[("inside", "differ")]
    strict = counts[("inside", "match")]
    misses = counts[("inside", "miss")] + counts[("edge", "miss")]
    clear = len(used) - counts[("inside", "differ")] \
        - counts[("edge", "differ")]
    if not total["inside"]:
        problems.append("沒有內部取樣點")
    elif strict < MATCH_SHARE * judged - 1e-9 or not judged:
        problems.append("只有 %d/%d 個內部點同位移是局部最小（要 %.0f%%）"
                        % (strict, judged, 100.0 * MATCH_SHARE))
    if clear and misses > MISS_SHARE * clear + 1e-9:
        problems.append("%d/%d 個點鄰格比同位移更像（最多 %.0f%%）：位移不對"
                        % (misses, clear, 100.0 * MISS_SHARE))
    if floor > FLOOR_MAX:
        problems.append("同位移 MAD 中位數 %.2f > %.1f：整段畫面對不上"
                        % (floor, FLOOR_MAX))
    differ = {}
    for group, name in (("inside", "內部點"), ("edge", "邊界點")):
        count = counts[(group, "differ")]
        differ[group] = count
        if total[group] and count > DIFFER_SHARE * total[group] + 1e-9:
            problems.append("%d/%d 個%s畫面不同（同位移 MAD > %.2f）：%s"
                            % (count, total[group], name, limit,
                               "；".join(shown[group])))
    return {"ok": not problems, "problems": problems, "strict": strict,
            "judged": judged, "misses": misses, "clear": clear,
            "used": len(used), "floor": round(floor, 3),
            "limit": round(limit, 3), "differ": differ}


def pixel_locate(costs):
    """{格位移: [逐點 MAD]} → 最小的那格；平均要 ≤ 1.5 而且比次小的小 0.1。"""
    means = []
    for shift in sorted(costs):
        means.append((statistics.mean(costs[shift]), shift))
    means.sort()
    if not means or means[0][0] > MAD_SAME:
        return None
    if len(means) > 1 and means[1][0] - means[0][0] < MAD_MARGIN:
        return None
    return means[0][1]


# ------------------------------------------------------------ 家族


def group_families(links):
    """[(節點, 節點, 工作檔)] → [{工作檔…}]：同一段節目連成一家。節點是
    (集, 段落表那一列的起秒)。"""
    parent = {}

    def find(node):
        while parent.setdefault(node, node) != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node
    for first, second, _unit in links:
        parent[find(first)] = find(second)
    groups = collections.defaultdict(set)
    for first, _second, unit in links:
        groups[find(first)].add(unit)
    out = []
    for key in sorted(groups, key=str):
        out.append(groups[key])
    return out


def strong_components(nodes, edges):
    """Tarjan：{節點: 分量編號}，編號照拓樸順序（上游的小）。edges 是
    {節點: [下游節點]}。"""
    index = {}
    low = {}
    stack = []
    on_stack = set()
    found = []
    counter = [0]

    def visit(node):
        index[node] = low[node] = counter[0]
        counter[0] += 1
        stack.append(node)
        on_stack.add(node)
        for other in edges.get(node, []):
            if other not in index:
                visit(other)
                low[node] = min(low[node], low[other])
            elif other in on_stack:
                low[node] = min(low[node], index[other])
        if low[node] == index[node]:
            members = []
            while True:
                other = stack.pop()
                on_stack.discard(other)
                members.append(other)
                if other == node:
                    break
            found.append(members)
    for node in sorted(nodes):
        if node not in index:
            visit(node)
    # Tarjan 先吐出下游的分量，反過來就是拓樸順序。
    out = {}
    for number, members in enumerate(reversed(found)):
        for node in members:
            out[node] = number
    return out


ROUND = re.compile(r"^(.*?)-r([0-9]+)(?:-[0-9]+)?(\.json)?$")


def unit_round(unit):
    """工作檔名 → (去掉輪次的名字, 輪次)：`B--from-A.json` 是第一輪
    （1），`B--from-A-r3.json` 是第三輪。照檔名排 `-r3` 會排在第一輪前面
    （`-` 比 `.` 小）。"""
    match = ROUND.match(unit)
    if not match:
        return unit, 1
    return match.group(1) + (match.group(3) or ""), int(match.group(2))


def family_order(units):
    """一家的工作檔 → 移植順序和報告，不湊定本。

    照依賴排：要搬進某集的（A→B）排在從那集搬出去的（B→C）前面，B 當首播
    時才看得到 A→B 搬進來的修改；照檔名排的話 A→B→C→D 的 C→D 可能先做。
    真的互相依賴的集（075↔129，或 B→C→D→B）用強連通分量縮成一個點，只有
    兩端都在環裡的那幾份列在 `cycles` 交給人，steps 裡同一步標 `cycle:
    <組號>`（cycles 裡第幾組，從 1 起），批次據此跳過；環外的照依賴排，環
    的下游排在環後面。同一對首播→重播的第二輪（`-r3`）排在第一輪後面。
    家族裡哪個首播對哪一集沒有工作檔，列在 `uncovered`。
    """
    sources = set()
    episodes = set()
    have = set()
    edges = collections.defaultdict(list)
    for unit in units:
        sources.add(unit["source"])
        episodes.add(unit["source"])
        episodes.add(unit["target"])
        have.add((unit["source"], unit["target"]))
        edges[unit["source"]].append(unit["target"])
    component = strong_components(episodes, edges)
    loops = collections.defaultdict(list)
    keyed = []
    for unit in units:
        inner = component[unit["source"]] == component[unit["target"]]
        if inner:
            loops[component[unit["source"]]].append(unit["unit"])
        stem, round_number = unit_round(unit["unit"])
        keyed.append(((component[unit["source"]], 0 if inner else 1, stem,
                       round_number, unit["unit"]), unit))
    keyed.sort(key=lambda pair: pair[0])
    cycles = []
    group_of = {}
    for number in sorted(loops):
        cycles.append(sorted(loops[number]))
        for name in loops[number]:
            group_of[name] = len(cycles)
    steps = []
    for _key, unit in keyed:
        step = {"do": "port", "from": unit["source"], "to": unit["target"],
                "unit": unit["unit"]}
        if unit["unit"] in group_of:
            step["cycle"] = group_of[unit["unit"]]
        steps.append(step)
    uncovered = []
    for source in sorted(sources):
        for name in sorted(episodes):
            if name != source and (source, name) not in have:
                uncovered.append([source, name])
    return {"sources": sorted(sources), "steps": steps,
            "uncovered": uncovered, "cycles": cycles}


# ------------------------------------------------------------ I/O


class Store(object):
    """這支程式在 Kari-SRT 讀寫的位置；測試時換成暫存目錄。"""

    def __init__(self, cues=None, vision=None, srt=None, segments=None,
                 sapolita=None, asr_raw=None, work=None, fixlog=None,
                 pairs=None, paragraph=None, root=None):
        self.root = root or datadirs.ROOT
        self.cues = cues or paths.KARI_CUES
        self.vision = vision or paths.KARI_VISION
        self.srt = srt or paths.SRT_DIR
        self.segments = segments or paths.SEGMENTS_STORE
        self.sapolita = sapolita or paths.SAPOLITA_SRT
        self.asr_raw = asr_raw or paths.ASR_RAW
        self.work = work or paths.WORK
        self.fixlog = fixlog or os.path.join(paths.OCR_STORE, "訂正紀錄.csv")
        self.pairs = pairs or paths.PAIRS_DIR
        self.paragraph = paragraph or paths.PARAGRAPH_SRT

    def under(self, base):
        """同樣的相對位置換到 `base` 底下：snap.sh 的快照照 Kari-SRT 的相對
        路徑放在 `<快照>/files/`。"""
        def moved(path):
            return os.path.join(base, os.path.relpath(path, self.root))
        return Store(cues=moved(self.cues), vision=moved(self.vision),
                     srt=moved(self.srt), segments=moved(self.segments),
                     sapolita=moved(self.sapolita),
                     asr_raw=moved(self.asr_raw), work=self.work,
                     fixlog=moved(self.fixlog), pairs=moved(self.pairs),
                     paragraph=moved(self.paragraph), root=base)

    def timeline(self, name):
        return paths.stage_path(self.cues, name, ".json")

    def vision_dir(self, name):
        return paths.stage_path(self.vision, name)

    def segments_file(self, name):
        return paths.stage_path(self.segments, name, ".csv")

    def srt_file(self, name):
        return paths.stage_path(self.srt, name, ".srt")

    def sapolita_file(self, name):
        return paths.stage_path(self.sapolita, name, ".srt")

    def asr_raw_file(self, name):
        return paths.stage_path(self.asr_raw, name, ".srt")

    def pairs_files(self, name):
        """族華平行語料（2021-01～10 的集，SRT 一變 pairs_run 會重寫）。"""
        return [paths.stage_path(self.pairs, name, ".csv"),
                paths.stage_path(self.paragraph, name, ".srt")]


def sha(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def read_tsv(path):
    rows = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            parts = line.rstrip("\n").split("\t", 2)
            if len(parts) >= 2 and parts[0].isdigit():
                rows.append((int(parts[0]),
                             parts[2] if len(parts) > 2 else ""))
    return rows


def tsv_text(rows):
    out = []
    for number, text in rows:
        out.append("%d\than\t%s\n" % (number, text))
    return "".join(out)


def load(name, store):
    """一集的時間軸、每份 TSV、字、段落表、whisper 邊界、sha。"""
    timeline = store.timeline(name)
    if not os.path.exists(timeline):
        raise PipelineError("Kari-SRT 沒有 %s 的時間軸" % name)
    with open(timeline, encoding="utf-8") as handle:
        book = json.load(handle)
    files = {}
    texts = {}
    digests = {"timeline": sha(timeline), "tsv": {}}
    for path in sorted(glob.glob(os.path.join(store.vision_dir(name),
                                              "b*.tsv"))):
        base = os.path.basename(path)
        files[base] = read_tsv(path)
        digests["tsv"][base] = sha(path)
        for number, text in files[base]:
            texts[number] = text
    table = None
    table_path = store.segments_file(name)
    if os.path.exists(table_path):
        table = segments.read(table_path)
        digests["segments"] = sha(table_path)
    whisper = None
    sapolita = store.sapolita_file(name)
    if os.path.exists(sapolita):
        with open(sapolita, encoding="utf-8") as handle:
            whisper = read_sapolita(handle.read())
    return {"name": name, "book": book, "files": files, "texts": texts,
            "table": table, "whisper": whisper, "sha": digests,
            "store": store}


def _same_unit(first, second):
    return first["類型"] == second["類型"] \
        and (first.get("單元語別") or "") == (second.get("單元語別") or "") \
        and abs(float(first["迄秒"]) - float(second["起秒"])) < 0.001


def unit_range(table, second):
    """首播段落表包含這一秒的那一段節目：(起秒, 迄秒)。

    同一段節目常被切成好幾列（251 午泰雅島語時間 1155–1266.6、1266.6–
    1276.9、1276.9–2060，字幕帶不同）：同類型、同單元語別、首尾相接的相鄰
    列併成一段。攝影棚、外景新聞這類一則一列的不併。
    """
    rows = list(table or [])
    for k, row in enumerate(rows):
        if not float(row["起秒"]) <= second < float(row["迄秒"]):
            continue
        first = last = k
        if row["類型"] not in NOT_UNIT:
            while first > 0 and _same_unit(rows[first - 1], rows[first]):
                first -= 1
            while last + 1 < len(rows) and _same_unit(rows[last],
                                                      rows[last + 1]):
                last += 1
        return float(rows[first]["起秒"]), float(rows[last]["迄秒"])
    raise PipelineError("首播段落表沒有包含 %.3f 秒的列" % second)


def measure_pair(source, target, lo, hi):
    """兩集已經 load 好：算錨點、whisper，判斷位移。"""
    found = anchors(source["book"]["cues"], source["texts"],
                    target["book"]["cues"], target["texts"], lo, hi)
    whisper = None
    if source["whisper"] and target["whisper"]:
        wlo, whi = whisper_window(lo, hi)
        whisper = whisper_offset(source["whisper"], target["whisper"], wlo,
                                 whi)
    return judge_offset(found, whisper, lo, hi)


def measure(src, tgt, lo, hi, store=None):
    store = store or Store()
    return measure_pair(load(src, store), load(tgt, store), lo, hi)


def render_srt(book, texts, out):
    """照 rebuild 同樣的做法（時間軸＋TSV 的字 → make_srt）產一集 SRT。"""
    from scripts.news import make_srt
    work = tempfile.mkdtemp(prefix="port-srt-")
    try:
        timeline = paths.coarse_cues(work)
        os.makedirs(os.path.dirname(timeline))
        with open(timeline, "w", encoding="utf-8") as handle:
            json.dump(book, handle, ensure_ascii=False, indent=2,
                      sort_keys=True)
        transcripts = paths.transcripts_file(work)
        os.makedirs(os.path.dirname(transcripts), exist_ok=True)
        resolved = {}
        for number in texts:
            resolved[str(number)] = {"han": texts[number]}
        with open(transcripts, "w", encoding="utf-8") as handle:
            json.dump(resolved, handle, ensure_ascii=False, indent=2,
                      sort_keys=True)
        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        return make_srt.run(work, out)
    finally:
        shutil.rmtree(work)


def srt_outside_problems(before, after, spans, margin=2.0):
    """`spans`（重播秒數）以外的 SRT 只能有編號變動：時間和字都不能變。"""
    from scripts.srtlib import srt

    def outside(text):
        out = []
        for entry in srt.parse_srt(text):
            hit = False
            for start, end in spans:
                if entry[1] >= start - margin and entry[0] <= end + margin:
                    hit = True
            if not hit:
                out.append(entry)
        return out
    old, new = outside(before), outside(after)
    if old == new:
        return []
    for k in range(min(len(old), len(new))):
        if old[k] != new[k]:
            return ["範圍外 SRT 變了：%r → %r" % (old[k], new[k])]
    return ["範圍外 SRT 條數 %d → %d" % (len(old), len(new))]


def _now(fmt):
    stamp = datetime.datetime.now(datetime.timezone(datetime.timedelta(
        hours=8)))
    return stamp.strftime(fmt)


def _read_lines(path):
    if not path or not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as handle:
        return handle.read().splitlines()


def _fix_rows(path):
    out = []
    for line in _read_lines(path):
        if line.strip():
            out.append(line.split("\t"))
    return out


def _slug(name, entries=None):
    for entry in entries if entries is not None else _entries():
        if entry["srt_name"] == name:
            return entry["slug"]
    raise PipelineError("目錄裡沒有 %s" % name)


def _entries():
    from scripts.news import episodes
    return episodes.load()


def out_dir(src, tgt):
    return os.path.join(paths.NEWS_OUT, "port", paths.month_of(tgt),
                        "%s--from-%s" % (tgt, src))


def snapshot_chain(snaps, name):
    """`<snaps>/<集>` 或 `<集>--<標籤>` 的快照，照 manifest.txt 的時間排：
    [(標籤, 目錄)]。沒有標籤的是最早那輪的 main。"""
    out = []
    if not snaps or not os.path.isdir(snaps):
        return out
    for entry in os.listdir(snaps):
        if entry == name:
            tag = "main"
        elif entry.startswith(name + "--"):
            tag = entry[len(name) + 2:]
        else:
            continue
        manifest = os.path.join(snaps, entry, "manifest.txt")
        if os.path.exists(manifest):
            out.append((os.path.getmtime(manifest), tag,
                        os.path.join(snaps, entry)))
    out.sort()
    chain = []
    for _when, tag, folder in out:
        chain.append((tag, folder))
    return chain


def snapshot_tag(snaps, name, src, now=None):
    """apply 前替重播拍快照的標籤：x＋首播名前 12 字；已經有了（上一輪
    移植前拍的）就加 `-r<MMDDHHMM>`，連那個也有就擋——不可以沿用舊快照，
    不然鏈式移植會把這次移植前的狀態當成上一輪的。"""
    tag = "x" + src[:12]
    if not os.path.exists(os.path.join(snaps, "%s--%s" % (name, tag))):
        return tag
    again = "%s-r%s" % (tag, now or _now("%m%d%H%M"))
    if os.path.exists(os.path.join(snaps, "%s--%s" % (name, again))):
        raise PipelineError("快照 %s--%s 已經有了，不可以沿用；隔一分鐘再 apply"
                            % (name, again))
    return again


def episode_files(store, name):
    """一集在 Kari-SRT 的檔（時間軸、每份 TSV、段落表、SRT、whisper、
    平行語料）。"""
    out = []
    for path in [store.timeline(name), store.segments_file(name),
                 store.srt_file(name), store.sapolita_file(name),
                 store.asr_raw_file(name)] + store.pairs_files(name):
        if os.path.isfile(path):
            out.append(path)
    folder = store.vision_dir(name)
    if os.path.isdir(folder):
        for base in sorted(os.listdir(folder)):
            out.append(os.path.join(folder, base))
    return sorted(out)


def take_snapshot(store, name, folder, fixes=None):
    """照 snap.sh 的樣子拍快照：`<folder>/files/` 底下照 Kari-SRT 的相對
    路徑放、`manifest.txt` 列檔（最後寫，排序用它的時間）、
    `manual-fixes.rows` 抄這集的訂正列。"""
    if os.path.exists(folder):
        raise PipelineError("快照 %s 已經有了，不可以沿用" % folder)
    rels = []
    for path in episode_files(store, name):
        rel = os.path.relpath(path, store.root)
        dest = os.path.join(folder, "files", rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy2(path, dest)
        rels.append(rel)
    rows = []
    for line in _read_lines(fixes):
        if line.startswith(name + "\t"):
            rows.append(line)
    with open(os.path.join(folder, "manual-fixes.rows"), "w",
              encoding="utf-8") as handle:
        handle.write("".join(_with_newline(rows)))
    with open(os.path.join(folder, "manifest.txt"), "w",
              encoding="utf-8") as handle:
        handle.write("".join(_with_newline(rels)))
    return folder


def unit_files(units, name, tag):
    """快照標籤 → 那個修正單元的工作檔。照規則的：main＝`units/<集>.json`、
    fu＝`units/followup/<集>.json`、x＋首播前 12 字（可帶 `-r<MMDDHHMM>`）
    ＝`units/expand/<集>--from-<首播>….json`。不照規則的也要找得到：
    `xr3fix1027r2x`、`xuserrecut102`（`--from-` 後面的字開頭相同）、
    `x216-r2-10271411`（只寫集號）。"""
    if tag == "main":
        found = [os.path.join(units, name + ".json")]
    elif tag == "fu":
        found = [os.path.join(units, "followup", name + ".json")]
    elif tag.startswith("x"):
        body = re.sub(r"-r[0-9]+(?:-[0-9]+)?$", "", tag[1:])
        head = name + "--from-"
        found = []
        for path in sorted(glob.glob(os.path.join(
                units, "expand", glob.escape(head) + "*.json"))):
            origin = os.path.basename(path)[len(head):-len(".json")]
            if origin.startswith(body) or (
                    body.isdigit() and "_%s_" % body in origin):
                found.append(path)
    else:
        found = []
    out = []
    for path in sorted(found):
        if os.path.exists(path):
            out.append(path)
    return out


def _items_of(path):
    with open(path, encoding="utf-8") as handle:
        return item_ranges(json.load(handle).get("items", []))


def prepare(src, tgt, lo=None, hi=None, out=None, store=None, unit=None,
            offset=None, fixes=None, pending=None, entries=None, work=None,
            snaps=None, units=None, target_from=None):
    """只讀 Kari-SRT，寫進 `out`：plan.json、report.txt、preview/。

    做法照 `choose_mode`：整段搬（mode whole）、分區搬（mode zone，要
    `snaps`：首播最早那份快照 → 現在的差），或不搬、整件要人判（mode 和
    status 都是 ask，切法設定不同而重播自己重切過）。判斷哪一集重切過也
    要 `snaps`。`work` 是這件的工作檔（items 的秒數是重播時間）。
    `target_from` 只給乾跑用：重播從快照目錄讀（`<快照>/files`），plan 的
    sha 跟 Kari-SRT 對不上，apply 一定擋。
    """
    store = store or Store()
    out = out or out_dir(src, tgt)
    source = load(src, store)
    target = load(tgt, store if target_from is None
                  else store.under(target_from))
    if unit is not None:
        lo, hi = unit_range(source["table"], unit)
    evidence = measure_pair(source, target, lo, hi)
    if offset is not None:
        evidence = with_offset(evidence, offset)
    items = None
    if work:
        items = _items_of(work)
    plan = {"source": src, "target": tgt, "src_range": [lo, hi],
            "offset": evidence["offset"], "evidence": evidence,
            "status": evidence["status"],
            "reasons": list(evidence["reasons"]),
            "work": work, "items": items, "mode": None,
            "sha": {"source": source["sha"], "target": target["sha"]}}
    os.makedirs(out, exist_ok=True)
    # pixel（只有 whisper）也照粗位移算一份，才有取樣點給像素定位用；
    # apply 只收 ready。
    if plan["status"] in ("ready", "pixel"):
        mode, stats = choose_mode(source["book"], source["texts"],
                                  target["book"], target["texts"],
                                  lo, hi, plan["offset"],
                                  src_first=first_book(snaps, src, store),
                                  tgt_first=first_book(snaps, tgt, store))
        plan["mode"] = mode
        plan["mode_stats"] = stats
        try:
            if mode == "ask":
                plan["status"] = "ask"
                plan["reasons"].append(stats["why"])
            elif mode == "whole":
                _prepare_port(plan, source, target, out, store, fixes,
                              pending, entries)
            else:
                _prepare_zone(plan, source, target, out, store, fixes,
                              pending, entries, snaps, units)
        except PipelineError as error:
            plan["status"] = "rejected"
            plan["reasons"].append(str(error))
    with open(os.path.join(out, "plan.json"), "w", encoding="utf-8") as fh:
        json.dump(plan, fh, ensure_ascii=False, indent=2, sort_keys=True)
    with open(os.path.join(out, "report.txt"), "w", encoding="utf-8") as fh:
        fh.write(report(plan))
    return plan


def _write_preview(plan, target, book, everything, out, table, spans,
                   store):
    """preview/：新時間軸、改過的 TSV、段落表、SRT；檢查範圍外 SRT 不變。"""
    tgt = target["name"]
    preview = os.path.join(out, "preview")
    if os.path.isdir(preview):
        shutil.rmtree(preview)
    os.makedirs(os.path.join(preview, "2-vision"))
    from scripts.news import redump_store
    with open(os.path.join(preview, "cues.json"), "w",
              encoding="utf-8") as handle:
        handle.write(redump_store.dump(book))
    changed_files = []
    emptied = []
    for name in sorted(everything):
        body = tsv_text(everything[name])
        if name in target["files"] and \
                tsv_text(target["files"][name]) == body:
            continue
        if not body:
            # 整份的列都被換掉：刪檔，不在 Kari-SRT 留空檔。
            if name in target["files"]:
                emptied.append(name)
            continue
        changed_files.append(name)
        with open(os.path.join(preview, "2-vision", name), "w",
                  encoding="utf-8") as handle:
            handle.write(body)
    if table is not None:
        segments.write(os.path.join(preview, "0-segments.csv"), table)
    texts = {}
    for name in sorted(everything):
        for number, text in everything[name]:
            texts[number] = text
    render_srt(book, texts, os.path.join(preview, tgt + ".srt"))
    delivered = target["store"].srt_file(tgt)
    if os.path.exists(delivered):
        with open(delivered, encoding="utf-8") as handle:
            before = handle.read()
        with open(os.path.join(preview, tgt + ".srt"),
                  encoding="utf-8") as handle:
            after = handle.read()
        problems = srt_outside_problems(before, after, spans)
        if problems:
            raise PipelineError(problems[0])
    return changed_files, emptied


def _tsv_everything(target, result, book):
    total = len(target["book"]["cues"])
    rewritten, new_name, new_rows = port_tsvs(target["files"], result, total)
    everything = dict(rewritten)
    if new_rows:
        everything[new_name] = new_rows
    check_cover(everything, len(book["cues"]))
    return everything, new_name


def _prepare_port(plan, source, target, out, store, fixes, pending, entries):
    """整段搬：重播那段原本沒讀到，首播的整段切法和字換進去。"""
    lo, hi = plan["src_range"]
    off = plan["offset"]
    tgt = target["name"]
    result = port(source["book"], source["texts"], target["book"],
                  target["texts"], lo, hi, off, items=plan["items"] or [],
                  agree=plan["evidence"].get("agree"))
    book = new_book(target["book"], source["book"], result, source["name"],
                    lo, hi, off, target["texts"], mode="whole")
    total = len(target["book"]["cues"])
    everything, new_name = _tsv_everything(target, result, book)
    start, end = result["range"]

    table = None
    if target["table"] is not None:
        if source["table"] is not None:
            table = port_segments(target["table"], source["table"], start,
                                  end, off)
        else:
            table = port_segments(target["table"], [], start, start, 0.0)
        problems = segments.check(table, tgt, book["duration"])
        if problems:
            raise PipelineError("段落表：%s" % problems[0])
    changed_files, emptied = _write_preview(plan, target, book, everything,
                                            out, table, [(start, end)], store)

    # 訂正紀錄現在先算一次：重播自己修過、首播沒有的，在這裡就擋下。
    # apply 在鎖裡會再算一次（那時 manual-fixes 可能又多了幾列）。
    fix_rows = []
    if fixes:
        fix_rows = port_fixes(_fix_rows(fixes), source["name"], tgt,
                              target["book"]["cues"], result)
    if pending:
        _lines, extra = port_pending(
            _read_lines(pending), _slug(source["name"], entries),
            _slug(tgt, entries), source["name"], tgt, result)
        fix_rows += extra
    plan["fixes"] = []
    for row in fix_rows:
        if row[0] == tgt:
            plan["fixes"].append(row)

    plan["range"] = result["range"]
    plan["notes"] = book["ported"][-1]["notes"]
    plan["trimmed"] = result["trimmed"]
    plan["areas"] = book.get("areas", {})
    plan["tsv"] = {"new": new_name, "changed": changed_files,
                   "emptied": emptied}
    plan["moves"] = _string_keys(result["moves"])
    plan["ported"] = _string_keys(result["ported"])
    plan["removed"] = result["removed"]
    plan["added"] = _text_list(result["added"], result["texts"])
    plan["changed"] = _changed_list(result)
    plan["ask"] = result["ask"]
    plan["replaced"] = result["replaced"]
    plan["probes"] = probe_points(result, off, evidence_holes(plan))
    plan["summary"] = {"removed": len(result["removed"]),
                       "ported": len(result["ported"]),
                       "before": total, "after": len(book["cues"]),
                       "added": len(result["added"]),
                       "changed": len(result["changed"]),
                       "ask": len(result["ask"])}


def first_book(snaps, name, store):
    """這集最早那份快照的時間軸（重切前的切法設定）；沒有快照給 None。
    有快照卻沒有時間軸的，給 `{"cues": [], "missing": 快照目錄}`——那不是
    「沒重切過」，是判不出來（choose_mode 判 ask）。"""
    chain = snapshot_chain(snaps, name)
    if not chain:
        return None
    path = store.under(os.path.join(chain[0][1], "files")).timeline(name)
    if not os.path.exists(path):
        return {"cues": [], "missing": chain[0][1]}
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _load_snapshot(name, folder, store):
    try:
        return load(name, store.under(os.path.join(folder, "files")))
    except PipelineError as error:
        raise PipelineError("快照 %s：%s" % (folder, error))


def zone_source(source, snaps, units, store):
    """首播最早那份快照（修改前）和每份快照的說明。

    差一律是最早那份 → Kari-SRT 現在：不只到下一份快照（首播的修正常在
    沒有快照的步驟做），也包含首播自己當重播時別集搬進來的（A→B 的修改
    算在 B 被修過的地方）。"""
    src = source["name"]
    chain = snapshot_chain(snaps, src)
    if not chain:
        raise PipelineError("%s 底下沒有 %s 的快照，不知道首播改過哪裡" % (snaps, src))
    units = units or os.path.join(os.path.dirname(os.path.abspath(snaps)),
                                  "units")
    notes = []
    for tag, folder in chain:
        notes.append({"tag": tag, "snapshot": folder,
                      "unit_files": unit_files(units, src, tag)})
    return _load_snapshot(src, chain[0][1], store), notes


def _prepare_zone(plan, source, target, out, store, fixes, pending,
                  entries, snaps, units):
    """分區搬：首播修改前快照 → 現在有差的地方，一區一區換進重播。"""
    lo, hi = plan["src_range"]
    off = plan["offset"]
    tgt = target["name"]
    src = source["name"]
    if not snaps:
        stats = plan["mode_stats"]
        raise PipelineError(
            "重播那段已經有字（%d 條，首播 %d 條），只能分區搬首播改過的地方；"
            "要給首播快照目錄 --snaps"
            % (stats["target_text"], stats["source_text"]))
    before, notes = zone_source(source, snaps, units, store)
    plan["steps"] = notes
    plan["base"] = os.path.basename(notes[0]["snapshot"])
    result = zone_port(before["book"], before["texts"], source["book"],
                       source["texts"], target["book"], target["texts"], lo,
                       hi, off)
    result["range"] = [round(lo + off, 3), round(hi + off, 3)]
    result["base"] = plan["base"]
    book = new_book(target["book"], source["book"], result, src, lo, hi, off,
                    target["texts"], mode="zone")
    total = len(target["book"]["cues"])
    everything, new_name = _tsv_everything(target, result, book)
    spans = []
    for info in result["applied"]:
        spans.append(info["tgt"])
    changed_files, emptied = _write_preview(plan, target, book, everything,
                                            out, None, spans, store)
    if fixes:
        rows = _fix_rows(fixes)
        if pending:
            rows += source_pending_rows(_read_lines(pending),
                                        _slug(src, entries), src)
        fix_rows = zone_fixes(rows, src, tgt, result)
        plan["fixes"] = []
        for row in fix_rows:
            if row[0] == tgt:
                plan["fixes"].append(row)
    if pending:
        port_pending(_read_lines(pending), _slug(src, entries),
                     _slug(tgt, entries), src, tgt, result)
    plan["range"] = result["range"]
    plan["notes"] = book["ported"][-1]["notes"]
    plan["trimmed"] = []
    plan["areas"] = book.get("areas", {})
    plan["tsv"] = {"new": new_name, "changed": changed_files,
                   "emptied": emptied}
    plan["moves"] = _string_keys(result["moves"])
    plan["ported"] = {}
    plan["fresh"] = result["fresh"]
    plan["was"] = _string_keys(result["was"])
    plan["removed"] = result["removed"]
    plan["removed_cues"] = result["removed_cues"]
    plan["applied"] = result["applied"]
    plan["same"] = result["same"]
    plan["unresolved"] = result["ask"]
    plan["ask"] = []
    plan["blank_in_target"] = result["blank_in_target"]
    plan["items_untouched"] = items_status(
        plan["items"] or [], result["applied"] + result["same"],
        result["ask"], result["blank_in_target"])
    plan["probes"] = probe_points(result, off, evidence_holes(plan))
    plan["summary"] = {"applied": len(result["applied"]),
                       "same": len(result["same"]),
                       "ask": len(result["ask"]),
                       "blank_in_target": len(result["blank_in_target"]),
                       "removed": len(result["removed"]),
                       "fresh": len(result["fresh"]),
                       "before": total, "after": len(book["cues"])}


def evidence_holes(plan):
    out = []
    for lo, hi in plan["evidence"].get("holes", []):
        out.append((lo, hi))
    return out


def _string_keys(mapping):
    out = {}
    for key in mapping:
        out[str(key)] = mapping[key]
    return out


def _text_list(numbers, texts):
    out = []
    for number in numbers:
        out.append({"cue": number, "text": texts.get(number, "")})
    return out


def _changed_list(result):
    by_number = {}
    for item in result["cues"]:
        by_number[item["index"]] = item
    old = {}
    for item in result["removed_cues"]:
        old[item["index"]] = item
    out = []
    for number in result["changed"]:
        before = []
        for index in sorted(old):
            if overlap(old[index], by_number[number]) > 0:
                before.append(index)
        out.append({"cue": number, "text": result["texts"].get(number, ""),
                    "was": before})
    return out


def report(plan):
    """給人看的摘要。"""
    lines = ["%s ← %s" % (plan["target"], plan["source"]),
             "狀態：%s" % plan["status"]]
    evidence = plan["evidence"]
    lines.append("位移 %s（證據 %s：OCR 錨點 %d、同群 %d、p50 %.3f、兩格內 "
                 "%.0f%%；whisper %s）"
                 % (plan.get("offset"), evidence.get("grade"),
                    evidence["anchors"], evidence["inliers"],
                    evidence.get("p50", 0.0),
                    100.0 * evidence.get("within_two", 0.0),
                    evidence["whisper_verdict"]))
    if plan.get("mode"):
        stats = plan.get("mode_stats", {})
        lines.append("做法：%s（%s）"
                     % ({"whole": "整段搬", "zone": "分區搬",
                         "ask": "不搬，整件要人判"}[plan["mode"]],
                        stats.get("why")))
    for why in plan["reasons"]:
        if why != plan.get("mode_stats", {}).get("why"):
            lines.append("原因：%s" % why)
    if "summary" not in plan:
        return "\n".join(lines) + "\n"
    summary = plan["summary"]
    lines.append("首播範圍 %s → 重播範圍 %s" % (plan["src_range"], plan["range"]))
    for note in plan["notes"]:
        lines.append("說明：%s" % note)
    if plan["mode"] == "zone":
        lines.append("首播改過的地方：快照 %s → Kari-SRT 現在" % plan["base"])
        for step in plan["steps"]:
            shown = []
            for path in step["unit_files"]:
                shown.append(os.path.basename(path))
            lines.append("首播快照 %s（工作檔 %s）"
                         % (step["tag"], "、".join(shown) or "找不到"))
        lines.append("%d 區：套 %d、已經一樣 %d、要人判 %d；總數 %d → %d；"
                     "首播有字、重播沒字 %d 句"
                     % (summary["applied"] + summary["same"] + summary["ask"],
                        summary["applied"], summary["same"], summary["ask"],
                        summary["before"], summary["after"],
                        summary.get("blank_in_target", 0)))
        for item in plan["applied"]:
            lines.append("套用：首播 %s → 重播 %s（%s；重播原 cue %s）「%s」"
                         % (item["src"], item["tgt"], "、".join(item["kinds"]),
                            item["target_cues"], item["text"]))
        for item in plan["unresolved"]:
            lines.append("要人判：首播 %s → 重播 %s（%s）：%s（重播 cue %s）"
                         % (item["src"], item["tgt"], "、".join(item["kinds"]),
                            item["why"], item["target_cues"]))
        for item in plan.get("blank_in_target", []):
            lines.append("首播有字、重播沒字（不在任何區，沒搬，要人看）：首播 %s "
                         "cue %s「%s」→ 重播 %s（%s）"
                         % (item["src"], item["cues"], item["text"],
                            item["tgt"], "空白 cue %s" % item["target_cues"]
                            if item["target_cues"] else "沒有 cue"))
        lines += items_lines(plan.get("items_untouched", []))
        return "\n".join(lines) + "\n"
    lines.append("換掉 %d 條、搬進 %d 條，總數 %d → %d"
                 % (summary["removed"], summary["ported"],
                    summary["before"], summary["after"]))
    if plan.get("replaced"):
        lines.append("真的有換到的地方：重播 %.3f–%.3f（像素驗收的邊界點放在它"
                     "外側 1 秒，落在範圍外就不取）" % tuple(plan["replaced"]))
    for item in plan["trimmed"]:
        lines.append("修短空白 cue %s：%s → %s"
                     % (item["cue"] if item["cue"] is not None
                        else "（搬進來的首播 cue %s）" % item.get("source_cue"),
                        item["from"], item["to"]))
    for item in plan["added"]:
        lines.append("補進的字：新 cue %d「%s」" % (item["cue"], item["text"]))
    for item in plan["changed"]:
        lines.append("改掉的字：新 cue %d「%s」（重播原 cue %s）"
                     % (item["cue"], item["text"], item["was"]))
    for item in plan["ask"]:
        lines.append("要人判的字：重播 cue %d %.3f–%.3f「%s」，首播同時段：%s"
                     % (item["cue"], item["start"], item["end"],
                        item["text"], "／".join(item["covered_by"])
                        or "（沒有 cue）"))
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------ 抽格


def grab(video, seconds, out, runner=subprocess.run):
    """抽一格，縮成 384×216 灰階。"""
    cmd = ["nice", "-n", "10", "ffmpeg", "-nostdin", "-loglevel", "error",
           "-y", "-ss", "%.6f" % seconds, "-i", video, "-frames:v", "1",
           "-vf", "scale=%d:%d,format=gray" % THUMB, out]
    done = runner(cmd, capture_output=True, text=True, errors="replace")
    if done.returncode or not os.path.exists(out):
        raise PipelineError("抽格失敗 %s @ %.3f：%s"
                            % (video, seconds, done.stderr[-300:]))


def _frame_file(out, side, seconds):
    return os.path.join(out, "frames", side, "%012.6f.png" % seconds)


def frames(plans, side, video, runner=subprocess.run):
    """照 plan 的取樣點抽格：首播一點一格；重播一點抽同位移和 ±1 格
    （status 是 pixel 的抽 ±5 格，讓 check 定位）。"""
    for plan_path in plans:
        with open(plan_path, encoding="utf-8") as handle:
            plan = json.load(handle)
        out = os.path.dirname(os.path.abspath(plan_path))
        probes = plan.get("probes") or []
        for probe in probes:
            if side == "source":
                times = [probe["src"]]
            else:
                width = LOCATE_FRAMES if plan["status"] == "pixel" else 1
                times = []
                for shift in range(-width, width + 1):
                    times.append(probe["tgt"] + shift * FRAME)
            for seconds in times:
                path = _frame_file(out, side, seconds)
                if os.path.exists(path):
                    continue
                os.makedirs(os.path.dirname(path), exist_ok=True)
                grab(video, seconds, path, runner)


def _image(path):
    import numpy
    from PIL import Image
    with Image.open(path) as picture:
        return numpy.asarray(picture.convert("L"), dtype=float)


def check(plan_path):
    """比對抽好的格，寫 `check.json`；回傳判決。"""
    with open(plan_path, encoding="utf-8") as handle:
        plan = json.load(handle)
    out = os.path.dirname(os.path.abspath(plan_path))
    points = []
    costs = collections.defaultdict(list)
    for probe in plan.get("probes") or []:
        source = _image(_frame_file(out, "source", probe["src"]))
        point = dict(probe)
        point["same"] = frame_mad(source, _image(_frame_file(
            out, "target", probe["tgt"])))
        neighbours = {}
        width = LOCATE_FRAMES if plan["status"] == "pixel" else 1
        for shift in range(-width, width + 1):
            path = _frame_file(out, "target", probe["tgt"] + shift * FRAME)
            if os.path.exists(path):
                neighbours[shift] = frame_mad(source, _image(path))
                if probe["kind"] in ("inside", "hole"):
                    costs[shift].append(neighbours[shift])
        if -1 in neighbours and 1 in neighbours:
            point["minus"] = neighbours[-1]
            point["plus"] = neighbours[1]
        points.append(point)
    verdict = judge_frames(points)
    verdict["points"] = points
    verdict["plan_sha"] = sha(plan_path)
    if plan["status"] == "pixel":
        shift = pixel_locate(dict(costs))
        verdict["located"] = None if shift is None else round(
            plan["offset"] + shift * FRAME, 3)
        verdict["ok"] = False
        verdict["problems"].append(
            "這份是像素定位：定位結果 %s，請用 prepare --offset 重做"
            % verdict["located"])
    with open(os.path.join(out, "check.json"), "w", encoding="utf-8") as fh:
        json.dump(verdict, fh, ensure_ascii=False, indent=2, sort_keys=True)
    return verdict


# ------------------------------------------------------------ 入庫


def temp_workdir(work, preview, no_frames=None, snapshot=None):
    """臨時 work dir：`3-refined/cues.json`＝新時間軸（帶 Kari-SRT 全部
    areas、`refined: true`），`0-segments.csv`＝新段落表。免做像素驗收的
    理由、移植前拍的快照寫進這次的移植紀錄（`ported` 最後一筆的
    `no_frames`、`snapshot`）。"""
    refined = paths.refined_cues(work)
    os.makedirs(os.path.dirname(refined), exist_ok=True)
    shutil.copy2(os.path.join(preview, "cues.json"), refined)
    if no_frames or snapshot:
        from scripts.news import redump_store
        with open(refined, encoding="utf-8") as handle:
            book = json.load(handle)
        if no_frames:
            book["ported"][-1]["no_frames"] = no_frames
        if snapshot:
            book["ported"][-1]["snapshot"] = snapshot
        with open(refined, "w", encoding="utf-8") as handle:
            handle.write(redump_store.dump(book))
    table = os.path.join(preview, "0-segments.csv")
    if os.path.exists(table):
        shutil.copy2(table, paths.segments_file(work))
    return work


class Rollback(object):
    """apply 動到的檔先各留一份；任何一步失敗就整集照原樣放回去（含改名
    的 work dir、新建的目錄、剛拍的快照、換檔留下的 `.part.<pid>`）。

    別人會同時附加的共用檔（manual-fixes.tsv、pending-fixes.txt）不整檔
    放回：`protect(..., shared=True)` 只留一份給 .bak 用；真的改寫時用
    `rewritten` 記下改寫前後的列，回滾時放回改寫前那份，再接上改寫之後
    別人附加的列。"""

    def __init__(self, folder):
        self.folder = folder
        self.saved = []
        self.renamed = []
        self.made = []
        self.created = []
        self.shared = set()
        self.rewrites = []
        os.makedirs(folder, exist_ok=True)

    def rewritten(self, path, before, after):
        self.rewrites.append((path, list(before), list(after)))

    def create(self, path):
        """這一步會新建 `path`（整個目錄），失敗時刪掉；原本沒有的上層目錄
        也一起刪。"""
        parent = os.path.dirname(path)
        while parent and not os.path.exists(parent):
            self.made.append(parent)
            parent = os.path.dirname(parent)
        self.created.append(path)

    def protect(self, path, shared=False):
        if shared:
            self.shared.add(path)
        for known, _copy in self.saved:
            if known == path:
                return
        parent = os.path.dirname(path)
        missing = []
        while parent and not os.path.exists(parent):
            missing.append(parent)
            parent = os.path.dirname(parent)
        self.made += missing
        copy = None
        if os.path.isdir(path):
            copy = os.path.join(self.folder, "%03d" % len(self.saved))
            shutil.copytree(path, copy)
        elif os.path.exists(path):
            copy = os.path.join(self.folder, "%03d" % len(self.saved))
            shutil.copy2(path, copy)
        self.saved.append((path, copy))

    def rename(self, old, new):
        os.rename(old, new)
        self.renamed.append((old, new))

    def restore(self):
        for path, _copy in self.saved:
            part = "%s.part.%d" % (path, os.getpid())
            if os.path.lexists(part):
                os.remove(part)
        for path in reversed(self.created):
            if os.path.isdir(path):
                shutil.rmtree(path)
        for old, new in reversed(self.renamed):
            if os.path.exists(new) and not os.path.exists(old):
                os.rename(new, old)
        for path, before, after in reversed(self.rewrites):
            _write_lines(path, before + _appended(_read_lines(path), after))
        for path, copy in reversed(self.saved):
            if path in self.shared:
                continue
            if os.path.isdir(path) and not os.path.islink(path):
                shutil.rmtree(path)
            elif os.path.lexists(path):
                os.remove(path)
            if copy is None:
                continue
            os.makedirs(os.path.dirname(path), exist_ok=True)
            if os.path.isdir(copy):
                shutil.copytree(copy, path)
            else:
                shutil.copy2(copy, path)
        for folder in sorted(self.made, key=len, reverse=True):
            if os.path.isdir(folder) and not os.listdir(folder):
                os.rmdir(folder)


def _install(staged, path):
    """暫存好的檔換進去：先抄成 .part 再改名。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp = "%s.part.%d" % (path, os.getpid())
    shutil.copy2(staged, temp)
    os.replace(temp, path)


def _locked(path):
    handle = open(path, "a")
    fcntl.flock(handle, fcntl.LOCK_EX)
    return handle


def _same_sha(plan, store):
    """跟 prepare 當時的 sha 比：不同就回傳是哪一份。"""
    for side, name in (("target", plan["target"]),
                       ("source", plan["source"])):
        recorded = plan["sha"][side]
        if sha(store.timeline(name)) != recorded["timeline"]:
            return "%s 的時間軸" % name
        now = {}
        for path in glob.glob(os.path.join(store.vision_dir(name),
                                           "b*.tsv")):
            now[os.path.basename(path)] = sha(path)
        if now != recorded["tsv"]:
            return "%s 的 TSV" % name
        table = store.segments_file(name)
        if os.path.exists(table) != ("segments" in recorded):
            return "%s 的段落表" % name
        if os.path.exists(table) and sha(table) != recorded["segments"]:
            return "%s 的段落表" % name
    return None


def _accepted(path):
    out = set()
    for line in _read_lines(path):
        match = re.match(r"^\s*([0-9]+)\s+\S", line)
        if match:
            out.add(int(match.group(1)))
    return out


def _write_lines(path, lines):
    """整檔重寫：先寫暫存檔再改名。內容沒變就不動。"""
    body = "".join(_with_newline(lines))
    with open(path, encoding="utf-8") as handle:
        if handle.read() == body:
            return False
    temp = "%s.part.%d" % (path, os.getpid())
    with open(temp, "w", encoding="utf-8") as handle:
        handle.write(body)
    os.replace(temp, path)
    return True


def _appended(now, written):
    """`now` 裡不在 `written` 的列（照順序，同一列出現幾次算幾次）：改寫
    之後別人附加的。"""
    left = collections.Counter(written)
    out = []
    for line in now:
        if left[line] > 0:
            left[line] -= 1
            continue
        out.append(line)
    return out


def _keep_backup(path, before):
    """入庫成功後，改過的 manual-fixes／pending 留一份改寫前的
    .bak-<MMDD-HHMMSS>。"""
    with open("%s.bak-%s" % (path, _now("%m%d-%H%M%S")), "w",
              encoding="utf-8") as handle:
        handle.write("".join(_with_newline(before)))


def _with_newline(lines):
    out = []
    for line in lines:
        out.append(line + "\n")
    return out


def _default_pairs(name):
    from scripts.news import pairs_run
    if pairs_run.in_scope(name):
        pairs_run.main([name])


def _default_fixlog(fixes):
    script = os.path.join(os.path.dirname(os.path.abspath(fixes)),
                          "fixlog.py")
    if not os.path.exists(script):
        print("沒有 %s，訂正紀錄.csv 要自己重產" % script)
        return
    env = dict(os.environ, PYTHONPATH=".")
    subprocess.run([sys.executable, script], check=True, env=env,
                   cwd=datadirs.ROOT)


def _moves_from_plan(plan):
    moves = {}
    for key in plan["moves"]:
        moves[int(key)] = plan["moves"][key]
    ported = {}
    for key in plan["ported"]:
        ported[int(key)] = plan["ported"][key]
    return moves, ported


def _result_from_plan(plan, preview):
    moves, ported = _moves_from_plan(plan)
    result = {"moves": moves, "ported": ported, "removed": plan["removed"],
              "texts": {}, "cues": []}
    with open(os.path.join(preview, "cues.json"), encoding="utf-8") as fh:
        result["cues"] = json.load(fh)["cues"]
    new_tsv = os.path.join(preview, "2-vision", plan["tsv"]["new"])
    if os.path.exists(new_tsv):
        for number, text in read_tsv(new_tsv):
            result["texts"][number] = text
    if plan.get("mode") == "zone":
        result["fresh"] = plan["fresh"]
        result["removed_cues"] = plan["removed_cues"]
        result["was"] = {}
        for key in plan["was"]:
            result["was"][int(key)] = plan["was"][key]
    return result


def _final_texts(plan, target, preview):
    """入庫後這集每條 cue 的字：改過的 TSV 用 preview 的，其餘照原本。"""
    texts = {}
    for name in sorted(target["files"]):
        if name in plan["tsv"]["emptied"] or name in plan["tsv"]["changed"]:
            continue
        for number, text in target["files"][name]:
            texts[number] = text
    for name in plan["tsv"]["changed"]:
        for number, text in read_tsv(os.path.join(preview, "2-vision",
                                                  name)):
            texts[number] = text
    return texts


def _lines_or_none(path):
    return _read_lines(path) if path else None


def _rows_of(lines):
    out = []
    for line in lines:
        if line.strip():
            out.append(line.split("\t"))
    return out


def _fix_lines(plan, target, result, fixes, pending, entries):
    """訂正紀錄改號：`fixes`、`pending` 是 manual-fixes、pending 現在的列
    （沒給檔是 None），回傳 (manual-fixes 的新行或 None, pending 的新行或
    None)。只算不讀檔：讀、改、寫要在呼叫端一氣呵成。"""
    src, tgt = plan["source"], plan["target"]
    rows = None
    pending_lines = None
    if plan.get("mode") == "zone":
        if fixes is not None:
            rows = _rows_of(fixes)
            if pending is not None:
                rows += source_pending_rows(pending, _slug(src, entries), src)
            rows = zone_fixes(rows, src, tgt, result)
        if pending is not None:
            pending_lines, _extra = port_pending(
                pending, _slug(src, entries), _slug(tgt, entries), src, tgt,
                result)
    else:
        if fixes is not None:
            rows = port_fixes(_rows_of(fixes), src, tgt,
                              target["book"]["cues"], result)
        if pending is not None:
            pending_lines, extra = port_pending(
                pending, _slug(src, entries), _slug(tgt, entries), src, tgt,
                result)
            if fixes is not None:
                rows += extra
    lines = None
    if rows is not None:
        lines = []
        for row in rows:
            lines.append("\t".join(row))
    return lines, pending_lines


def _rewrite_fixes(plan, target, result, fixes, pending, entries, back):
    """manual-fixes、pending 在這裡才讀，算完馬上寫（中間沒有 publish、
    render 這種耗時步驟）：apply 前段那幾秒別人附加的列也一起改號留著。
    寫之前再讀一次，跟算的時候不同（剛好有人附加）就重算。改寫前後記進
    `back`，回滾時只拿掉這次改的。"""
    for _attempt in range(5):
        fix_now = _lines_or_none(fixes)
        pending_now = _lines_or_none(pending)
        fix_new, pending_new = _fix_lines(plan, target, result, fix_now,
                                          pending_now, entries)
        if _lines_or_none(fixes) != fix_now \
                or _lines_or_none(pending) != pending_now:
            continue
        for path, before, after in ((fixes, fix_now, fix_new),
                                    (pending, pending_now, pending_new)):
            if after is not None and _write_lines(path, after):
                back.rewritten(path, before, after)
        return
    raise PipelineError("manual-fixes／pending 一直有人在寫，五次都沒寫成")


def apply(plan_path, lock, fixes, pending=None, accept=None, no_frames=None,
          store=None, entries=None, hooks=None, snaps=None):
    """唯一會寫 Kari-SRT 的步驟：鎖、sha、像素驗收、要人判的字、入庫。

    換進去之前先替重播拍快照（`snaps`，標籤見 `snapshot_tag`），時間軸
    `ported` 那筆記快照名——B 之後當首播時，A→B 搬進來的修改才算得進
    「首播改過的地方」。新時間軸、段落表、SRT、訂正紀錄先全部在暫存目錄
    做好，才換進 Kari-SRT；換的過程（含 pairs、fixlog）任何一步失敗、或
    收到 SIGTERM／SIGHUP／SIGINT，就整集回滾，連快照一起刪。換完之後的
    收尾（留 .bak、刪回滾備份）出錯只警告：資料已經換好，不可以讓呼叫端
    以為沒寫入。
    """
    from scripts.news import publish
    store = store or Store()
    hooks = dict(hooks or {})
    hooks.setdefault("pairs", _default_pairs)
    hooks.setdefault("fixlog", _default_fixlog)
    entries = entries if entries is not None else _entries()
    with open(plan_path, encoding="utf-8") as handle:
        plan = json.load(handle)
    out = os.path.dirname(os.path.abspath(plan_path))
    preview = os.path.join(out, "preview")
    if plan["status"] != "ready":
        raise PipelineError("plan 狀態是 %s，不能 apply：%s"
                            % (plan["status"], "；".join(plan["reasons"])))
    if plan.get("mode") == "zone" and not plan["summary"]["applied"]:
        raise PipelineError("這份 plan 沒有要搬的區（要人判 %d 區）"
                            % plan["summary"]["ask"])
    verdict_path = os.path.join(out, "check.json")
    if no_frames is None:
        if not os.path.exists(verdict_path):
            raise PipelineError("還沒做像素驗收（frames、check）；若使用者同意免做，"
                                "用 --no-frames 寫理由")
        with open(verdict_path, encoding="utf-8") as handle:
            verdict = json.load(handle)
        if verdict.get("plan_sha") != sha(plan_path) or not verdict["ok"]:
            raise PipelineError("像素驗收沒過或不是這份 plan 的：%s"
                                % "；".join(verdict.get("problems", [])))
    if plan["ask"]:
        ok = _accepted(accept)
        missing = []
        for item in plan["ask"]:
            if item["cue"] not in ok:
                missing.append(item["cue"])
        if missing:
            raise PipelineError("要人判的字還沒放行（--accept）：重播 cue %s"
                                % missing)
    tgt = plan["target"]
    entry = None
    for item in entries:
        if item["srt_name"] == tgt:
            entry = item
    if entry is None:
        raise PipelineError("目錄裡沒有 %s" % tgt)
    if os.path.exists(store.asr_raw_file(tgt)):
        raise PipelineError("%s 有 kaldi 2-srt-raw，時間軸一變就對不上，先回報使用者"
                            % tgt)
    if not snaps:
        raise PipelineError("apply 要給快照目錄 --snaps：移植前替重播拍快照，"
                            "鏈式移植才算得出首播改過的地方")

    handle = _locked(lock)
    try:
        changed = _same_sha(plan, store)
        if changed:
            raise PipelineError("%s 在 prepare 之後被改過，重做 prepare" % changed)
        target = load(tgt, store)
        result = _result_from_plan(plan, preview)
        # 先算一次：重播自己的訂正跟首播衝突這類在這裡就擋，什麼都還沒動。
        # 真的寫進去的是換檔之後那一次（_rewrite_fixes）。
        _fix_lines(plan, target, result, _lines_or_none(fixes),
                   _lines_or_none(pending), entries)

        # 先在暫存目錄做好要換進去的每一個檔。
        staging = tempfile.mkdtemp(prefix="apply-%s-" % _now("%m%d-%H%M%S"),
                                   dir=out)
        tag = snapshot_tag(snaps, tgt, plan["source"])
        shot = os.path.join(snaps, "%s--%s" % (tgt, tag))
        temp = temp_workdir(os.path.join(staging, "work"), preview,
                            no_frames, os.path.basename(shot))
        staged_cues = os.path.join(staging, "1-cues")
        staged_table = os.path.join(staging, "0-segments")
        publish.publish_one(entry, temp, cues_dir=staged_cues)
        table = publish.publish_segments(entry, temp, folder=staged_table,
                                         cues_dir=staged_cues)
        if table.startswith("wait"):
            print("段落表沒有入庫：%s" % table)
        timeline = paths.stage_path(staged_cues, tgt, ".json")
        with open(timeline, encoding="utf-8") as fh:
            book = json.load(fh)
        staged_srt = os.path.join(staging, "3-srt", tgt + ".srt")
        render_srt(book, _final_texts(plan, target, preview), staged_srt)

        back = Rollback(os.path.join(staging, "backup"))
        folder = store.vision_dir(tgt)
        guard = _SignalGuard()
        try:
            guard.interrupt()
            for path in [store.timeline(tgt), folder,
                         store.segments_file(tgt), store.srt_file(tgt),
                         store.fixlog] + store.pairs_files(tgt):
                if path:
                    back.protect(path)
            for path in (fixes, pending):
                if path:
                    back.protect(path, shared=True)
            back.create(shot)
            take_snapshot(store, tgt, shot, fixes)
            work = paths.work_dir(entry["slug"], store.work)
            if os.path.isdir(work):
                back.rename(work, "%s.stale-%s" % (work, _now("%m%d")))
            os.makedirs(folder, exist_ok=True)
            for name in plan["tsv"]["changed"]:
                _install(os.path.join(preview, "2-vision", name),
                         os.path.join(folder, name))
            for name in plan["tsv"]["emptied"]:
                os.remove(os.path.join(folder, name))
            _install(timeline, store.timeline(tgt))
            staged = paths.stage_path(staged_table, tgt, ".csv")
            if os.path.exists(staged):
                _install(staged, store.segments_file(tgt))
            _install(staged_srt, store.srt_file(tgt))
            _rewrite_fixes(plan, target, result, fixes, pending, entries,
                           back)
            hooks["pairs"](tgt)
            if fixes:
                hooks["fixlog"](fixes)
        except BaseException as error:
            guard.defer()
            try:
                back.restore()
            finally:
                guard.release()
            raise PipelineError("%s 入庫到一半失敗，已整集回滾：%s"
                                % (tgt, _describe(error)))
        # 換檔已經成功：之後的收尾（留 .bak、刪回滾備份、暫存目錄改名）出錯
        # 只警告——Kari-SRT 已經是新的，這裡丟例外會讓呼叫端以為沒寫入。
        # 收尾期間收到的信號等印完結尾那行才照原本的處理方式送回來。
        guard.defer()
        try:
            _finish_quietly(back, staging)
            print("%s：入庫完成（段落表 %s，移植前快照 %s）。下一步：verify_one "
                  "%s；整批收尾跑 rebuild --verify、name_catalogue --check"
                  % (tgt, table, shot, tgt), flush=True)
        finally:
            guard.release()
    finally:
        fcntl.flock(handle, fcntl.LOCK_UN)
        handle.close()
    return plan


class _Interrupted(BaseException):
    """換檔中途收到 SIGTERM／SIGHUP。BaseException：換檔路上別人寫的
    `except Exception` 攔不到，一路傳到回滾那一層。"""

    def __init__(self, signum):
        BaseException.__init__(self, signum)
        self.signum = signum


def _describe(error):
    if isinstance(error, _Interrupted):
        return "收到 %s" % signal.Signals(error.signum).name
    if isinstance(error, KeyboardInterrupt):
        return "收到 SIGINT"
    return str(error)


class _SignalGuard(object):
    """apply 換檔那段的 SIGTERM、SIGHUP：

    - `interrupt()`：收到就丟 `_Interrupted`，讓回滾那層整集放回去（舊
      做法照預設直接死掉，Kari-SRT 半套）。
    - `defer()`：回滾中、換檔成功後的收尾中，先記下來不處理。
    - `release()`：放回原本的處理方式；`defer` 期間收到的再送一次給自己。

    不在主執行緒（signal 只能在主執行緒設）就什麼都不做。"""

    SIGNALS = (signal.SIGTERM, signal.SIGHUP)

    def __init__(self):
        self.old = {}
        self.pending = []
        self.active = (threading.current_thread()
                       is threading.main_thread())

    def _install(self, handler):
        if not self.active:
            return
        for signum in self.SIGNALS:
            previous = signal.signal(signum, handler)
            self.old.setdefault(signum, previous)

    def interrupt(self):
        def handler(signum, _frame):
            raise _Interrupted(signum)
        self._install(handler)

    def defer(self):
        def handler(signum, _frame):
            self.pending.append(signum)
        self._install(handler)

    def release(self):
        for signum in self.old:
            signal.signal(signum, self.old[signum])
        self.old = {}
        pending, self.pending = self.pending, []
        for signum in pending:
            os.kill(os.getpid(), signum)


def _finish_quietly(back, staging):
    """換檔成功後的收尾，每一步出錯都只警告（寫 stderr）。"""
    for path, before, _after in back.rewrites:
        try:
            _keep_backup(path, before)
        except OSError as error:
            _warn("%s 改寫前的 .bak 沒留成：%s" % (path, error))
    try:
        shutil.rmtree(back.folder)
    except OSError as error:
        _warn("回滾備份 %s 沒刪成：%s" % (back.folder, error))
    try:
        os.rename(staging, "%s.stale-%s" % (staging, _now("%m%d")))
    except OSError as error:
        _warn("暫存目錄 %s 沒改名：%s" % (staging, error))


def _warn(text):
    print("警告（Kari-SRT 已經換好，只是收尾沒做完）：%s" % text,
          file=sys.stderr, flush=True)


# ------------------------------------------------------------ 家族 I/O


UNIT_NAME = re.compile(r"^(.+)--from-(.+?)\.json$")
EPISODE_ORIGIN = re.compile(r"^([0-9]{8}_[0-9]{3}_[^-]+?)(?:-r[0-9][0-9-]*)?$")
SECONDS = re.compile(r"([0-9]{2,4}(?:\.[0-9]+)?)")


def unit_source(origin):
    """展開工作檔名 `--from-` 後面那串 → 首播集名；不是集名的（那一集自己
    的修正單元：`r3fix1027r2x`、`userrecut1023`、`b1fix1027r2x`）給
    None。同一個首播的第二輪寫成 `<首播>-r3`。"""
    match = EPISODE_ORIGIN.match(origin)
    return match.group(1) if match else None


def family(unit_paths, store=None):
    """讀展開工作檔、量位移、對到首播段落表的列，排出家族和順序：
    {"families": [...], "skipped": [{unit, why}]}。不是移植的工作檔（
    `--from-` 後面不是集名）、讀不到時間軸的，列進 skipped，不當掉。"""
    store = store or Store()
    loaded = {}

    def episode(name):
        if name not in loaded:
            loaded[name] = load(name, store)
        return loaded[name]
    links = []
    units = {}
    skipped = []
    for path in unit_paths:
        match = UNIT_NAME.match(os.path.basename(path))
        if not match:
            continue
        tgt, src = match.group(1), unit_source(match.group(2))
        unit = os.path.basename(path)
        if src is None:
            skipped.append({"unit": unit,
                            "why": "「%s」不是集名：那一集自己的修正單元，"
                                   "不是移植" % match.group(2)})
            continue
        with open(path, encoding="utf-8") as handle:
            body = json.load(handle)
        items = body.get("items", [])
        seconds = []
        for item in items:
            found = SECONDS.search(item.get("seconds", "") or "")
            if found:
                seconds.append(float(found.group(1)))
        if not seconds:
            skipped.append({"unit": unit, "why": "items 沒有看得懂的秒數"})
            continue
        try:
            source, target = episode(src), episode(tgt)
        except PipelineError as error:
            skipped.append({"unit": unit, "why": str(error)})
            continue
        middle = statistics.median(seconds)
        found = anchors(source["book"]["cues"], source["texts"],
                        target["book"]["cues"], target["texts"],
                        middle - 90.0, middle + 90.0, side="target")
        evidence = judge_offset(found, None, 0.0, 1e9)
        off = evidence["offset"]
        units[unit] = {"unit": unit, "target": tgt, "source": src,
                       "items": len(items), "offset": off}
        if off is None:
            links.append(((tgt, middle), (tgt, middle), unit))
            continue
        try:
            src_row = unit_range(source["table"], middle - off)[0]
        except PipelineError:
            src_row = round(middle - off)
        try:
            tgt_row = unit_range(target["table"], middle)[0]
        except PipelineError:
            tgt_row = round(middle)
        links.append(((src, src_row), (tgt, tgt_row), unit))
    out = []
    for group in group_families(links):
        members = []
        for name in sorted(group):
            members.append(units[name])
        order = family_order(members)
        order["units"] = sorted(group)
        out.append(order)
    return {"families": out, "skipped": skipped}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="command", required=True)
    one = sub.add_parser("measure")
    one.add_argument("source")
    one.add_argument("target")
    one.add_argument("--range", nargs=2, type=float, required=True)
    two = sub.add_parser("prepare")
    two.add_argument("source")
    two.add_argument("target")
    span = two.add_mutually_exclusive_group(required=True)
    span.add_argument("--range", nargs=2, type=float)
    span.add_argument("--unit", type=float, help="首播段落表包含這秒的那列")
    two.add_argument("--out")
    two.add_argument("--offset", type=float, help="像素定位得到的位移")
    two.add_argument("--fixes", help="manual-fixes.tsv（預覽訂正紀錄改號）")
    two.add_argument("--pending", help="pending-fixes.txt")
    two.add_argument("--work", help="這件的工作檔（items 的秒數是重播時間）")
    two.add_argument("--snaps", help="快照目錄（<集>--<標籤>/files/），分區搬用")
    two.add_argument("--units", help="修正單元工作檔目錄（預設快照目錄旁的 units）")
    two.add_argument("--target-from", help="乾跑用：重播從這個快照的 files/ 讀")
    three = sub.add_parser("frames")
    three.add_argument("plans", nargs="+")
    three.add_argument("--side", choices=("source", "target"), required=True)
    three.add_argument("--video", required=True)
    four = sub.add_parser("check")
    four.add_argument("plan")
    five = sub.add_parser("apply")
    five.add_argument("plan")
    five.add_argument("--lock", required=True)
    five.add_argument("--fixes", required=True)
    five.add_argument("--pending")
    five.add_argument("--accept", help="要人判的字放行清單：一行「cue 號 理由」")
    five.add_argument("--no-frames", help="免像素驗收的理由（要使用者同意）")
    five.add_argument("--snaps", required=True,
                      help="快照目錄：入庫前替重播拍快照")
    six = sub.add_parser("family")
    six.add_argument("units", nargs="+")
    args = ap.parse_args(argv)
    if args.command == "measure":
        evidence = measure(args.source, args.target, args.range[0],
                           args.range[1])
        print(json.dumps(evidence, ensure_ascii=False, indent=2,
                         sort_keys=True))
    elif args.command == "prepare":
        lo = hi = None
        if args.range:
            lo, hi = args.range
        plan = prepare(args.source, args.target, lo, hi, args.out,
                       unit=args.unit, offset=args.offset, fixes=args.fixes,
                       pending=args.pending, work=args.work, snaps=args.snaps,
                       units=args.units, target_from=args.target_from)
        print(report(plan), end="")
        return 0 if plan["status"] == "ready" else 1
    elif args.command == "frames":
        frames(args.plans, args.side, args.video)
    elif args.command == "check":
        verdict = check(args.plan)
        for problem in verdict["problems"]:
            print(problem)
        print("像素驗收：%s" % ("通過" if verdict["ok"] else "不通過"))
        return 0 if verdict["ok"] else 1
    elif args.command == "apply":
        apply(args.plan, args.lock, args.fixes, pending=args.pending,
              accept=args.accept, no_frames=args.no_frames, snaps=args.snaps)
    else:
        print(json.dumps(family(args.units), ensure_ascii=False, indent=2,
                         sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
