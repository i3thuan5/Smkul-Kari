#!/usr/bin/env python3
"""逐秒畫面特徵 → 段落表；讀者確認；段落表ê把關。

    python3 -m scripts.news.segments make WORK --language 泰雅 \\
        --duration 2880.009 --band 722,848
    python3 -m scripts.news.segments pending WORK      # 判不準ê秒數
    python3 -m scripts.news.segments apply WORK ANSWERS.tsv
    python3 -m scripts.news.segments check FILE.csv --duration 2880.009

段落表一集一檔，一段一逝，欄位見 `COLUMNS`；寫佇 work dir ê
`0-segments.csv`，確認了後 `publish` 送去
`Kari-SRT/news/1-ocr/0-segments/<年-月>/<成果檔名>.csv`。

**兩層判法**（news-segments spec）：

1. 左下角節目框無去 → 其他（片頭、過場、片尾；無節目框ê圖卡嘛落佇遮）。
   有節目框ê全螢幕圖卡像素分袂出來，讀者確認才標「全螢幕圖卡」。
2. 賰ê干焦看 x ≥ 480、y 0–700：紅色標題條連續 `ANCHOR_MIN` 秒以上是
   主播段，比中棚內參考格是攝影棚、無比中是主播外景；紅條
   `UNSURE_MIN`–`ANCHOR_MIN` 秒判不準（主播段有 14 秒ê，人名條有 18
   秒ê）；其餘外景新聞。

紅條中間斷 `RED_GAP` 秒以內當做無斷，毋過橋過去了後愛修到鏡頭邊界：
主播段了後 2 秒無紅條、隨接受訪者人名條（183 42:01–42:04），橋過去
主播段就吞入受訪者彼段——所以照主播段中心ê畫面，kā毋是仝一个鏡頭ê
頭尾修掉。

單元（島語時間、部落信箱…）看標誌；語別牌換（他族插播）看 `badge`。
這兩種攏判不準：島語時間教ê語言愛讀者看標誌講（7/14 拉阿魯哇那集
教泰雅語），他族插播嘛愛讀者確認是佗一族。

判不準ê段 `依據` 寫 `PENDING`，`check()` 會擋，所以無確認ê段落表入袂
了 store。
"""
import argparse
import csv
import math
import os
import sys

from scripts import languages
from scripts.news import paths
from scripts.errors import PipelineError

COLUMNS = ("起秒", "迄秒", "類型", "單元語別", "字幕上緣y", "字幕下緣y",
           "依據", "受訪者語言別代號")

# 受訪者名條尾ê族名（「莊良賢(pasuya) Cou」）換做語言別代號，一段有幾
# 族就空白隔開。空ê＝猶未查；查過、彼段無受訪者名條寫「無」。單元語別
# 看語別牌，這欄才講受訪者本身是佗一族——講ê毋一定是本集ê族語（使用
# 者裁定 2026-09-24 愛另外標）。
INTERVIEWEE = "受訪者語言別代號"
NONE_SEEN = "無"

TYPES = ("攝影棚", "主播外景", "外景新聞", "全螢幕圖卡", "文化小辭典",
         "島語時間", "部落信箱", "帶外專題", "他族插播", "單元片頭", "其他")
BASES = ("自動", "Claude Vision 確認", "人工", "讀者回報")
PENDING = "待確認"
CONFIRMED = "Claude Vision 確認"

# 字幕佇佗：一般段落用字幕帶（呼叫ê人照 preset 傳），帶外單元有家己ê
# 區域（`presets.json` ê帶外 preset），「其他」無收字幕。
AREAS = {
    "島語時間": (940, 1060),
    "部落信箱": (600, 980),
    "單元片頭": (690, 880),
    "帶外專題": (930, 1040),
}
NO_SUBTITLE = ("其他",)

RED_MIN = 0.5        # 紅條彼幾列純紅比例超過這个，算有紅條
RED_GAP = 2          # 紅條斷幾秒以內當做無斷
ANCHOR_MIN = 26      # 連續幾秒以上確定是主播段
UNSURE_MIN = 12      # 這个到 ANCHOR_MIN 之間判不準
SNAP = 0.04          # 佮主播段中心畫面差偌濟以內算仝一个鏡頭
STUDIO_ALONE = 3     # 無紅條、比中棚內參考格連續幾秒，嘛算攝影棚
UNIT_MATCH = 0.08    # 單元標誌距離低過這个算有標誌
UNIT_MIN = 10        # 標誌連續幾秒以上才算一段單元
BADGE_CHANGED = 0.15  # 語別牌佮開頭差超過這个算換牌
BADGE_MIN = 60       # 換牌連續幾秒以上才是他族插播候選
SHORTEST = 2         # 比這短ê段併入頭前彼段
# 2024-08 起ê版型（有 `name` 特徵）：毋像棚內ê紅條段，純紅比例到這个
# 就是受訪者人名條（實測 ≥0.47，主播標題條 0.24–0.43）；低過
# NOT_A_BAR 是紅色背景（跑道、圖卡，<0.1），毋是紅條。
NAME_BAR = 0.45
NOT_A_BAR = 0.2


def _runs(flags, gap=0):
    """(起, 迄) ê True 區段，中間 False 無超過 `gap` 就接起來。"""
    out = []
    start = last = None
    for index in range(len(flags)):
        if not flags[index]:
            continue
        if start is None:
            start = index
        elif index - last - 1 > gap:
            out.append((start, last + 1))
            start = index
        last = index
    if start is not None:
        out.append((start, last + 1))
    return out


def _distance(pictures, target):
    """逐格畫面佮 `target` ê距離：區塊差ê第 25 百分位。

    毋是中位數：棚內右爿ê虛擬螢幕佔一半以上，換畫面ê時中位數綴咧走，
    主播段就予人當做換鏡頭修短（2024-12-01 晚間卑南 276–307）。佮比棚
    內參考格（`shots.STUDIO_PERCENTILE`）仝一个道理。
    """
    import numpy as np
    from scripts.news import shots
    diff = np.abs(pictures.astype(np.float32) - target[None]).mean(axis=-1)
    return np.percentile(diff, shots.STUDIO_PERCENTILE, axis=-1)


def _snap(pictures, start, end):
    """kā [start, end) 修到主播段中心彼个鏡頭：頭尾毋是仝鏡頭ê修掉。"""
    import numpy as np
    quarter = (end - start) // 4
    core = pictures[start + quarter:end - quarter or end].astype(np.float32)
    close = _distance(pictures[start:end], np.median(core, axis=0)) < SNAP
    lit = np.nonzero(close)[0]
    if not len(lit):
        return start, end
    return start + int(lit[0]), start + int(lit[-1]) + 1


def _anchor_kind(studio):
    """(類型, 依據)：比中棚內參考格是攝影棚；賰ê攏問讀者。

    紅條長毋過毋像棚內ê段，有戶外主播、嘛有「VS」受訪者（2021noon
    抽查 4/50 格判毋著）、有棚內螢幕換做文化小辭典ê，像素分袂開。
    """
    import numpy as np
    from scripts.news import shots
    if np.isnan(studio).all():
        return "主播外景", PENDING
    if float(np.nanmedian(studio)) < shots.STUDIO_MATCH:
        return "攝影棚", "自動"
    return "主播外景", PENDING


def label(feats):
    """逐秒 (類型, 依據)，照上面ê兩層判法。"""
    import numpy as np
    from scripts.news import shots
    count = len(feats["box"])
    kinds = ["外景新聞"] * count
    basis = ["自動"] * count
    pictures = feats["picture"]
    studio = np.asarray(feats["studio"], dtype=np.float32)

    red = np.asarray(feats["red"]) > RED_MIN
    for start, end in _runs(red, RED_GAP):
        if end - start < UNSURE_MIN:
            continue
        start, end = _snap(pictures, start, end)
        if end - start < UNSURE_MIN:
            continue
        kind, why = _anchor_kind(studio[start:end])
        if kind != "攝影棚" and "name" in feats:
            share = float(np.median(feats["name"][start:end]))
            if share >= NAME_BAR or share < NOT_A_BAR:
                continue
        # 比中棚內參考格就夠確定，免看紅條偌長（2024-12 主播導言 19–25
        # 秒、距離 0.000）；毋是棚內ê短紅條才問。
        if end - start < ANCHOR_MIN and kind != "攝影棚":
            why = PENDING
        for index in range(start, end):
            kinds[index], basis[index] = kind, why

    alone = np.nan_to_num(studio, nan=1.0) < shots.STUDIO_MATCH
    for start, end in _runs(alone):
        if end - start >= STUDIO_ALONE:
            for index in range(start, end):
                if kinds[index] == "外景新聞":
                    # 無紅條就問：176 ê全螢幕灰底圖卡平坦ê區塊佮
                    # 佈景相仝，自動判會判做棚內。
                    kinds[index], basis[index] = "攝影棚", PENDING

    present = np.asarray(feats["box"]) < shots.BOX_ABSENT
    badge = np.asarray(feats.get("badge", np.zeros(count)))
    changed = present & (badge > BADGE_CHANGED)
    for start, end in _runs(changed, 10):
        if end - start >= BADGE_MIN:
            for index in range(start, end):
                kinds[index], basis[index] = "他族插播", PENDING

    for index in range(count):
        if not present[index]:
            kinds[index], basis[index] = "其他", "自動"

    for key in sorted(feats):
        if not key.startswith("unit:"):
            continue
        name = key[len("unit:"):]
        found = np.asarray(feats[key]) < UNIT_MATCH
        for start, end in _runs(found, 3):
            if end - start >= UNIT_MIN:
                for index in range(start, end):
                    kinds[index], basis[index] = name, PENDING
    return kinds, basis


def _collapse(kinds, basis):
    """逐秒標籤 → [起, 迄, 類型, 依據]，傷短ê段併入頭前。"""
    spans = []
    for index in range(len(kinds)):
        key = (kinds[index], basis[index])
        if spans and (spans[-1][2], spans[-1][3]) == key:
            spans[-1][1] = index + 1
        else:
            spans.append([index, index + 1, key[0], key[1]])
    merged = []
    for span in spans:
        if merged and span[1] - span[0] < SHORTEST:
            merged[-1][1] = span[1]
        elif (merged and (merged[-1][2], merged[-1][3])
              == (span[2], span[3])):
            merged[-1][1] = span[1]
        else:
            merged.append(span)
    if len(merged) > 1 and merged[0][1] - merged[0][0] < SHORTEST:
        merged[1][0] = merged[0][0]
        merged.pop(0)
    return merged


def rows_of(kind, language, band):
    """(字幕上緣y, 字幕下緣y)，照類型。"""
    if kind in NO_SUBTITLE:
        return "", ""
    lo, hi = AREAS.get(kind, band)
    return str(lo), str(hi)


def classify(feats, language, duration, band=(722, 844)):
    """逐秒特徵 → 段落表（list of dict，值攏是字串）。

    `language` 是目錄ê族語別（中文），做逐段ê預設單元語別；`duration`
    是影片長度，做上尾一段ê迄秒。
    """
    kinds, basis = label(feats)
    out = []
    spans = _collapse(kinds, basis)
    for position, (start, end, kind, why) in enumerate(spans):
        top, bottom = rows_of(kind, language, band)
        last = position + 1 == len(spans)
        out.append({"起秒": str(start),
                    "迄秒": "%.3f" % duration if last else str(end),
                    "類型": kind, "單元語別": language,
                    "字幕上緣y": top, "字幕下緣y": bottom, "依據": why,
                    INTERVIEWEE: ""})
    return out


def judge_seconds(rows):
    """判不準ê段逐段揀三格（頭、中、尾）予 `shots judge` 截原圖。"""
    seconds = set()
    for row in rows:
        if row["依據"] != PENDING:
            continue
        start = int(float(row["起秒"]))
        end = int(math.ceil(float(row["迄秒"])))
        last = max(start, end - 2)
        for second in (min(start + 1, last), (start + end) // 2, last):
            seconds.add(second)
    return sorted(seconds)


JUDGE_WIDTH = 480
JUDGE_PER_SHEET = 6
JUDGE_GUTTER = 150


def judge_sheets(work, rows):
    """判不準ê段逐段三格縮細拼一逝、一張 6 段 → [(組合圖, [起秒…])]。

    一集判不準約 10 段、29 張全解析原圖；逐張交讀者一集八萬 token，縮做
    480 闊一張 6 段，一集兩張。逐逝倒爿印起秒，讀者照伊回答。
    """
    from PIL import Image, ImageDraw
    from scripts.news import opening
    from scripts.news import shots
    judge = shots.judge_dir(work)
    out_dir = os.path.join(paths.shots_dir(work), "sheets")
    os.makedirs(out_dir, exist_ok=True)
    pending = []
    for row in rows:
        if row["依據"] == PENDING:
            pending.append(row)
    height = JUDGE_WIDTH * 9 // 16
    made = []
    for first in range(0, len(pending), JUDGE_PER_SHEET):
        group = pending[first:first + JUDGE_PER_SHEET]
        page = Image.new("RGB", (JUDGE_GUTTER + 3 * JUDGE_WIDTH,
                                 len(group) * (height + 6)), "white")
        draw = ImageDraw.Draw(page)
        starts = []
        for position, row in enumerate(group):
            y = position * (height + 6)
            starts.append(row["起秒"])
            draw.text((6, y + 8), "%s\n%s" % (row["起秒"], row["類型"]),
                      fill="black", font=opening._font(22))
            for column, second in enumerate(judge_seconds([row])):
                path = os.path.join(judge, "%05d.png" % second)
                if not os.path.exists(path):
                    continue
                tile = Image.open(path).convert("RGB").resize(
                    (JUDGE_WIDTH, height))
                page.paste(tile, (JUDGE_GUTTER + column * JUDGE_WIDTH, y))
        target = os.path.join(out_dir, "judge_%02d.png" % (len(made) + 1))
        page.save(target)
        made.append((target, starts))
    return made


def apply(rows, answers, band=(722, 844)):
    """讀者ê回答 {起秒: (類型, 單元語別)} → 新ê段落表。"""
    out = []
    for row in rows:
        row = dict(row)
        answer = answers.get(row["起秒"])
        if answer is not None:
            kind, language = answer
            row["類型"], row["單元語別"] = kind, language
            row["字幕上緣y"], row["字幕下緣y"] = rows_of(
                kind, language, (int(row["字幕上緣y"] or band[0]),
                                 int(row["字幕下緣y"] or band[1])))
            row["依據"] = CONFIRMED
        out.append(row)
    return out


def check(rows, name, duration):
    """段落表入 store 進前ê把關：一項一句，指名檔佮逝（表頭是第 1 逝）。"""
    problems = []
    if not rows:
        return ["%s：段落表是空ê" % name]
    if float(rows[0]["起秒"]) != 0:
        problems.append("%s 第 2 逝：起秒 %s，頭一段愛對 0 開始"
                        % (name, rows[0]["起秒"]))
    for index in range(len(rows)):
        row = rows[index]
        line = index + 2
        if index and float(row["起秒"]) != float(rows[index - 1]["迄秒"]):
            problems.append("%s 第 %d 逝：起秒 %s 佮頂一逝迄秒 %s 無相接"
                            % (name, line, row["起秒"],
                               rows[index - 1]["迄秒"]))
        if row["類型"] not in TYPES:
            problems.append("%s 第 %d 逝：類型 %r 毋是正式名稱（%s）"
                            % (name, line, row["類型"], "、".join(TYPES)))
        if not row["單元語別"].strip():
            problems.append("%s 第 %d 逝：單元語別 空ê" % (name, line))
        if row["依據"] not in BASES:
            problems.append("%s 第 %d 逝：依據 %r 毋是 %s"
                            % (name, line, row["依據"], "、".join(BASES)))
        for code in _unknown_codes(row.get(INTERVIEWEE, "")):
            problems.append("%s 第 %d 逝：%s %r 毋是語言別代號"
                            % (name, line, INTERVIEWEE, code))
    if abs(float(rows[-1]["迄秒"]) - float(duration)) > 0.0005:
        problems.append("%s 第 %d 逝：迄秒 %s，上尾一段愛到影片長度 %.3f"
                        % (name, len(rows) + 1, rows[-1]["迄秒"],
                           float(duration)))
    return problems


def write(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, COLUMNS, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def read(path):
    """段落表；2026-09-24 以前ê表無受訪者欄，讀做空ê（猶未查）。"""
    with open(path, encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        if row.get(INTERVIEWEE) is None:
            row[INTERVIEWEE] = ""
    return rows


def _unknown_codes(value):
    value = value.strip()
    if not value or value == NONE_SEEN:
        return []
    known = set()
    for table in (languages.LANGUAGES, languages.OTHER_GROUPS):
        for _english, code in table.values():
            known.add(code)
    for table in languages.VARIETIES.values():
        for code in table.values():
            known.add(code)
    out = []
    for code in value.split():
        if code not in known:
            out.append(code)
    return out


def read_answers(path):
    """讀者 TSV：`起秒<TAB>類型<TAB>單元語別`，`#` 開頭是註解。"""
    answers = {}
    with open(path, encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            line = line.rstrip("\n")
            if not line.strip() or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) != 3:
                raise PipelineError("%s 第 %d 逝：愛三欄（起秒、類型、單元語別）"
                                    % (path, number))
            answers[parts[0].strip()] = (parts[1].strip(), parts[2].strip())
    return answers


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="command", required=True)
    make = sub.add_parser("make", help="特徵 → work dir 0-segments.csv")
    make.add_argument("work")
    make.add_argument("--language", required=True)
    make.add_argument("--duration", type=float, required=True)
    make.add_argument("--band", default="722,844")
    pend = sub.add_parser("pending", help="判不準ê秒數，一逝一个")
    pend.add_argument("work")
    ans = sub.add_parser("apply", help="讀者回答 → 改寫 0-segments.csv")
    ans.add_argument("work")
    ans.add_argument("answers")
    chk = sub.add_parser("check", help="驗一份段落表")
    chk.add_argument("file")
    chk.add_argument("--duration", type=float, required=True)
    args = ap.parse_args(argv)

    if args.command == "make":
        from scripts.news import shots
        band = []
        for part in args.band.split(","):
            band.append(int(part))
        rows = classify(shots.load(args.work), args.language, args.duration,
                        band=band)
        write(paths.segments_file(args.work), rows)
        waiting = 0
        for row in rows:
            if row["依據"] == PENDING:
                waiting += 1
        print("%s：%d 段，判不準 %d 段"
              % (paths.segments_file(args.work), len(rows), waiting))
        return 0
    if args.command == "pending":
        for second in judge_seconds(read(paths.segments_file(args.work))):
            print(second)
        return 0
    if args.command == "apply":
        target = paths.segments_file(args.work)
        write(target, apply(read(target), read_answers(args.answers)))
        return 0
    name = os.path.splitext(os.path.basename(args.file))[0]
    problems = check(read(args.file), name, args.duration)
    for line in problems:
        print(line)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
