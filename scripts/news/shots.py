#!/usr/bin/env python3
"""影片 → 逐秒畫面特徵，佮判不準彼幾格ê原圖。

    python3 -m scripts.news.shots extract VIDEO WORK --year 2024
    python3 -m scripts.news.shots judge VIDEO WORK 812 1440 ...

逐秒一格 160×90 縮圖（`ffmpeg fps=1`，第 k 格是 k+0.5 秒ê畫面），算：

- `box`：左下角節目框佮這集家己ê中位數框差偌濟。**干焦問框在毋在**，
  毋比框內ê內容——2021 年彼塊是天氣框＋語別牌，城市、溫度一直換，
  用 2×2 區塊差ê中位數，換字ê彼幾塊予中位數吞去。實測框在 ≤0.12、
  框無 ≥0.12（2021 三集、2023 三集）。
- `red`：紅色標題條（y 852–912、x ≥ 480）ê純紅比例。紅條上段是暗紅
  （R 30–100、G=B=0），單看 R>150 揣袂著。
- `studio`：畫面（x ≥ 480、y 0–700）佮棚內參考格上近ê距離；參考格
  佇 `shot_refs/<年>/studio-*.png`（取區塊差ê第 25 百分位）。無參考
  格就是 NaN。
- `step`：佮前一格ê距離，揣鏡頭切換用。
- `badge`：節目框頂懸ê語別牌佮開頭ê距離，揣他族插播用。
- `picture`：逐格ê區塊平均色，主播段修到鏡頭邊界用。
- `unit:<名>`：單元標誌（島語時間、部落信箱…）佇伊固定位置ê距離，
  樣板佮位置佇 `shot_refs/<年>/units.json`。

倒爿四分之一（x < 480）第二層攏毋看：2021 天氣框、2023 台標攏佇遐，
兩年欲用仝一套規則。距離攏是 0–1 ê區塊差中位數：棚內右爿ê虛擬螢幕
換內容，規格平均會起落，中位數袂。

判段（啥物格算主播段、判不準ê是佗幾秒）佇 `segments`；這支干焦
量，量著ê存 `7-shots/features.npz`，規則改了毋免重新解碼。
"""
import argparse
import glob
import json
import os
import subprocess
import sys

import numpy as np
from PIL import Image

from scripts.news import paths
from scripts.errors import PipelineError

THUMB_W, THUMB_H = 160, 90
SCALE = 1920 // THUMB_W

# 第二層ê範圍：x ≥ 480（縮圖 40）、y 0–700（縮圖 0–57）。
RIGHT = 480 // SCALE
TOP_ROWS = 700 // SCALE

# 紅色標題條：y 852–912（縮圖 71–75）。
RED_ROWS = (852 // SCALE, 912 // SCALE)

# 純紅，佮 `presets.json` ê `row_slots.exclude` 仝一組（有測試顧）。
PURE_RED = {"r_min": 20, "gb_max": 25, "r_minus_g": 15}

# 左下角節目框：縮圖 y 77–84、x 3–27（全解析 y≈924–1008、x≈36–336）。
BOX = (slice(77, 85), slice(3, 27))
# 框在ê格最遠到 0.12 以下，無框ê格（片頭、全螢幕圖卡、片尾）0.12 以上。
BOX_ABSENT = 0.12

# 語別牌：節目框頂懸彼逝（2023「Pinuyumayan」、2021「阿美」），縮圖
# y 71–76、x 3–26。一集中途換別族單元，這塊會換字。
BADGE = (slice(71, 77), slice(3, 27))

# 逐格存落來ê畫面：x ≥ 480、y 0–700 切 8×8 區塊（15×7 塊）ê平均色，
# float16。主播段愛修到鏡頭邊界，需要逐格ê畫面；縮圖本身傷大。
PICTURE_BLOCK = 8

# 佮棚內參考格ê區塊差中位數低過這个，就是棚內（spike 量ê門檻）。
STUDIO_MATCH = 0.05

# 區塊大細（縮圖像素）。
BLOCK = 4


def frame_time(index):
    """縮圖第 `index` 格是影片第幾秒ê畫面。

    `fps=1` 取ê是逐秒區間中央彼格（實測 25 fps 合成影片：第 k 格是
    k+0.48 秒）。截原圖對照愛用這个，毋是 `index`——差半秒拄好換鏡頭
    就截著隔壁彼个。
    """
    return index + 0.5


def thumbnails(video, threads=2):
    """(N, 90, 160, 3) uint8，逐秒一格。"""
    cmd = ["ffmpeg", "-v", "error", "-nostdin", "-threads", str(threads),
           "-i", video, "-map", "0:v:0",
           "-vf", "fps=1,scale=%d:%d:flags=area" % (THUMB_W, THUMB_H),
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    done = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if done.returncode != 0:
        raise PipelineError("縮圖解碼失敗：%s\n%s"
                            % (video, done.stderr.decode("utf-8", "replace")))
    raw = np.frombuffer(done.stdout, np.uint8)
    return raw.reshape(-1, THUMB_H, THUMB_W, 3)


def _unit(pixels):
    return np.asarray(pixels).astype(np.float32) / 255.0


def _block_median(diff, block):
    """(N, h, w) ê像素差 → 逐格區塊平均ê中位數。"""
    return _block_share(diff, block, 50)


def _block_share(diff, block, percentile):
    """(N, h, w) ê像素差 → 逐格區塊平均ê第 `percentile` 百分位。"""
    count, height, width = diff.shape
    height -= height % block
    width -= width % block
    diff = diff[:, :height, :width]
    diff = diff.reshape(count, height // block, block, width // block, block)
    means = diff.mean(axis=(2, 4)).reshape(count, -1)
    return np.percentile(means, percentile, axis=1)


def _picture(thumbs):
    """第二層看ê彼塊：x ≥ 480、y 0–700。"""
    return _unit(np.asarray(thumbs)[:, :TOP_ROWS, RIGHT:])


def _area(where, default):
    """preset 寫ê全解析 [[上, 下], [左, 右]] → 縮圖ê (列, 欄) slice。"""
    if where is None:
        return default
    (top, bottom), (left, right) = where
    return (slice(int(top) // SCALE, int(bottom) // SCALE),
            slice(int(left) // SCALE, int(right) // SCALE))


def box_distance(thumbs, where=None):
    """逐格左下角節目框佮這集中位數框ê距離。

    樣板用這集家己ê中位數：框佇一集內底九成五以上ê時間攏在，中位數
    就是框本身，免逐年準備樣板。2×2 區塊，因為框干焦 8×24 縮圖像素。
    `where` 照版型（preset ê `shots.box`），無寫就是舊版型ê `BOX`。
    """
    rows, cols = _area(where, BOX)
    box = _unit(np.asarray(thumbs)[:, rows, cols])
    median = np.median(box, axis=0)
    return _block_median(np.abs(box - median[None]).mean(axis=-1), 2)


def red_share(thumbs, rows=None, rule=None):
    """逐格紅條彼幾列（x ≥ 480）符合 `rule` ê比例。

    `rows` 是全解析ê (上, 下)，照版型：舊版型 y 852–912，2024-08 起
    938–1010（preset ê `shots.red_rows`）。`rule` 無講就是純紅；有
    `r_minus_b` ê是「紅明顯較懸」（2024-08 起主播段標題條是偏粉ê紅，
    RGB 約 140/56/55，純紅判準干焦掠著三四成）。
    """
    if rows is None:
        rows = slice(*RED_ROWS)
    else:
        rows = slice(int(rows[0]) // SCALE, int(rows[1]) // SCALE)
    rule = rule or PURE_RED
    pixels = np.asarray(thumbs)[:, rows, RIGHT:].astype(np.int16)
    red, green, blue = pixels[..., 0], pixels[..., 1], pixels[..., 2]
    if "r_minus_b" in rule:
        match = ((red - green >= rule.get("r_minus_g", 40))
                 & (red - blue >= rule["r_minus_b"]))
    else:
        match = ((red > rule["r_min"])
                 & (green < rule["gb_max"])
                 & (blue < rule["gb_max"])
                 & (red - green >= rule["r_minus_g"]))
    return match.mean(axis=(1, 2))


# 比棚內參考格取區塊差ê第 25 百分位，毋是中位數：2021 年ê棚右爿大
# 螢幕佔第二層範圍一半以上，中位數綴螢幕內容走（棚內段 0.07–0.15，
# 佮戶外主播 0.19–0.38 相黏）；第 25 百分位「四分之一ê區塊佮佈景相
# 仝」就算，棚內 ≤0.031（2021）／≤0.002（2023），戶外主播、受訪者
# ≥0.069（2021 三集、2023 三集ê紅條段）。
STUDIO_PERCENTILE = 25


def reference_distance(thumbs, references):
    """逐格佮上近彼張參考格ê距離；無參考格就攏是 NaN。"""
    count = len(thumbs)
    if not len(references):
        return np.full(count, np.nan, dtype=np.float32)
    picture = _picture(thumbs)
    best = np.full(count, np.inf, dtype=np.float32)
    for ref in references:
        ref_pic = _picture(np.asarray(ref)[None])[0]
        diff = np.abs(picture - ref_pic[None]).mean(axis=-1)
        best = np.minimum(best, _block_share(diff, BLOCK, STUDIO_PERCENTILE))
    return best


def step(thumbs):
    """逐格佮前一格ê距離（第 0 格 1.0：伊頭前無物件）。"""
    picture = _picture(thumbs)
    out = np.ones(len(picture), dtype=np.float32)
    if len(picture) > 1:
        diff = np.abs(picture[1:] - picture[:-1]).mean(axis=-1)
        out[1:] = _block_median(diff, BLOCK)
    return out


def badge_distance(thumbs, where=None, box=None):
    """逐格語別牌佮這集開頭語別牌ê距離。

    開頭：頭 600 秒內底框在ê格ê中位數（片頭動畫無框，毋算）；攏無框就
    提頭 600 秒全部。`where`、`box` 照版型（preset ê `shots`）。
    """
    rows, cols = _area(where, BADGE)
    badge = _unit(np.asarray(thumbs)[:, rows, cols])
    early = np.asarray(thumbs)[:600]
    present = box_distance(early, box) < BOX_ABSENT
    pool = badge[:len(early)][present] if present.any() else badge[:600]
    median = np.median(pool, axis=0)
    return np.abs(badge - median[None]).mean(axis=(1, 2, 3))


def picture(thumbs):
    """(N, 105, 3) float16：第二層範圍ê 8×8 區塊平均色。"""
    area = _picture(thumbs)
    count, height, width, _ = area.shape
    block = PICTURE_BLOCK
    height -= height % block
    width -= width % block
    area = area[:, :height, :width]
    area = area.reshape(count, height // block, block, width // block, block,
                        3).mean(axis=(2, 4))
    return area.reshape(count, -1, 3).astype(np.float16)


def unit_distance(thumbs, template, rows, cols):
    """單元標誌所在彼塊佮樣板ê距離。"""
    area = _unit(np.asarray(thumbs)[:, rows[0]:rows[1], cols[0]:cols[1]])
    ref = _unit(np.asarray(template)[rows[0]:rows[1], cols[0]:cols[1]])
    return _block_median(np.abs(area - ref[None]).mean(axis=-1), 2)


def features(thumbs, refs, layout=None):
    """{特徵名: (N,)}。`refs` 是 `load_refs()` 讀著ê，`layout` 是 preset
    ê `shots`（紅條佇佗幾列）。"""
    layout = layout or {}
    count = len(thumbs)
    # `box`／`badge` 寫 false 就關掉（2024-08 起兩个攏半透明、會換內容，
    # 分袂出在毋在）：規集當做框在、語別牌無換。
    if layout.get("box") is False:
        box = np.zeros(count, dtype=np.float32)
    else:
        box = box_distance(thumbs, layout.get("box")).astype(np.float32)
    if layout.get("badge") is False:
        badge = np.zeros(count, dtype=np.float32)
    else:
        badge = badge_distance(thumbs, layout.get("badge"),
                               layout.get("box")).astype(np.float32)
    out = {
        "box": box,
        "red": red_share(thumbs, layout.get("red_rows"),
                         layout.get("red_rule")).astype(np.float32),
        "studio": reference_distance(thumbs, refs.get("studio", [])),
        "step": step(thumbs),
        "badge": badge,
        "picture": picture(thumbs),
    }
    if layout.get("name_rule"):
        # 2024-08 起受訪者人名條是純紅、主播標題條毋是：分開量。
        out["name"] = red_share(thumbs, layout.get("red_rows"),
                                layout["name_rule"]).astype(np.float32)
    for name, unit in sorted(refs.get("units", {}).items()):
        out["unit:" + name] = unit_distance(
            thumbs, unit["template"], unit["rows"], unit["cols"]).astype(
                np.float32)
    return out


def features_path(work):
    return os.path.join(paths.shots_dir(work), "features.npz")


def save(work, feats):
    target = features_path(work)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    np.savez_compressed(target, **feats)


def load(work):
    with np.load(features_path(work)) as data:
        out = {}
        for key in data.files:
            out[key] = data[key]
        return out


REFS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shot_refs")


def load_refs(year, base=REFS):
    """這年ê參考格：棚內 `studio-*.png`，單元標誌照 `units.json`。

    無彼年ê目錄就是空ê——`studio` 攏 NaN，主播段一律判不準，交讀者。
    """
    folder = os.path.join(base, str(year))
    studio = []
    for path in sorted(glob.glob(os.path.join(folder, "studio-*.png"))):
        studio.append(np.asarray(Image.open(path).convert("RGB")))
    units = {}
    table = os.path.join(folder, "units.json")
    if os.path.exists(table):
        with open(table, encoding="utf-8") as handle:
            declared = json.load(handle)
        for name, unit in declared.items():
            image = Image.open(os.path.join(folder, unit["file"]))
            units[name] = {"template": np.asarray(image.convert("RGB")),
                           "rows": unit["rows"], "cols": unit["cols"]}
    return {"studio": studio, "units": units}


def judge_dir(work):
    return os.path.join(paths.shots_dir(work), "judge")


def grab(video, seconds, out_dir, threads=2):
    """逐个秒數截一張全解析原圖，`<秒>.png`；秒數用 `frame_time`。"""
    os.makedirs(out_dir, exist_ok=True)
    written = []
    for index in seconds:
        target = os.path.join(out_dir, "%05d.png" % int(index))
        cmd = ["ffmpeg", "-v", "error", "-nostdin", "-y",
               "-threads", str(threads),
               "-ss", "%.3f" % frame_time(int(index)), "-i", video,
               "-frames:v", "1", target]
        done = subprocess.run(cmd, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE)
        if done.returncode != 0 or not os.path.exists(target):
            raise PipelineError("截圖失敗：%s 第 %s 秒" % (video, index))
        written.append(target)
    return written


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="command", required=True)
    one = sub.add_parser("extract", help="逐秒特徵 → 7-shots/features.npz")
    one.add_argument("video")
    one.add_argument("work")
    one.add_argument("--year", required=True)
    one.add_argument("--preset", required=True,
                     help="切 cue 用ê彼个；紅條佇佗照伊 `shots`")
    one.add_argument("--threads", type=int, default=2)
    two = sub.add_parser("judge", help="截判不準彼幾秒ê原圖")
    two.add_argument("video")
    two.add_argument("work")
    two.add_argument("seconds", nargs="+", type=int)
    two.add_argument("--threads", type=int, default=2)
    args = ap.parse_args(argv)
    if args.command == "extract":
        with open(paths.ENGINE_PRESETS, encoding="utf-8") as handle:
            layout = json.load(handle)[args.preset].get("shots", {})
        thumbs = thumbnails(args.video, args.threads)
        feats = features(thumbs, load_refs(args.year), layout)
        save(args.work, feats)
        print("%s：%d 秒" % (features_path(args.work), len(thumbs)))
        return 0
    made = grab(args.video, args.seconds, judge_dir(args.work), args.threads)
    print("%s：%d 張" % (judge_dir(args.work), len(made)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
