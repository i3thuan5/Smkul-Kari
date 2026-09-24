#!/usr/bin/env python3
"""已經讀完字ê集數，補切一段帶外字幕（2021 年帶外專題）。

    python3 -m scripts.news.offband_backfill prepare <成果檔名> <起秒> <迄秒> VIDEO
    #   → 讀者讀 <out>/4-sheets/，寫 TSV（編號照圖頂懸印ê）
    python3 -m scripts.news.offband_backfill apply <成果檔名> <讀者 TSV>

2021 年 7–8 月十幾集ê專題，對白印佇 y≈940–1035；字幕帶切出來ê cue 是照
帶內ê名牌、衣服切ê，讀者照規矩留空。這集已經入庫、讀完字矣，所以愛：

1. `prepare`：用 `titv-news-offband` 重切彼段、精修，照時間接轉時間軸
   （`splice.splice_time`），算出最後ê編號；干焦為新 cue 出組合圖（圖頂懸
   印ê就是最後ê編號）；順紲用影片算段落表，彼段人工記「帶外專題」。
2. 讀者讀新 cue ê組合圖。
3. `apply`：確認 store ê時間軸猶是 prepare 彼時彼份；舊 cue 照**時間**
   （毋是照號碼）對著新編號，store 內底逐份 TSV 改寫、hőng換掉ê彼幾條
   提掉；讀者 TSV 加做下一个 bNN.tsv；時間軸、SRT、段落表入庫。

號碼徙毋著，文字就落佇別條字幕，無一个所在會報錯——所以對應干焦認
(start, end) 完全相仝ê，讀者 TSV 愛拄好是新 cue 彼幾號。
"""
import argparse
import glob
import hashlib
import json
import os
import shutil
import sys
import tempfile

from scripts import datadirs
from scripts.errors import PipelineError
from scripts.news import episodes
from scripts.news import paths
from scripts.news import segments
from scripts.news import splice as splicing

KIND = "帶外專題"
PRESET = "titv-news-offband"


# ------------------------------------------------------------ 純算術


def splice(old, lo, hi, new):
    """中點落佇 [lo, hi) ê舊 cue 換做新 cue，照時間排、重編。"""
    return splicing.splice_time(old, lo, hi, new)


def _key(item):
    return (round(float(item["start"]), 3), round(float(item["end"]), 3))


def moves(old, spliced):
    """{舊號: 新號}，干焦 (start, end) 完全相仝ê；hőng換掉ê無佇內底。"""
    where = {}
    for item in spliced:
        where[_key(item)] = int(item["index"])
    out = {}
    for item in old:
        found = where.get(_key(item))
        if found is not None:
            out[int(item["index"])] = found
    return out


def fresh_numbers(spliced, old=None):
    """新接入去ê cue ê號碼（佮舊時間軸對袂著ê彼幾條）。"""
    known = set()
    for item in old or []:
        known.add(_key(item))
    out = []
    for item in spliced:
        if old is None and not item.get("area"):
            continue
        if old is not None and _key(item) in known:
            continue
        out.append(int(item["index"]))
    return out


def rewrite(rows, table, total):
    """[(舊號, 文字)] → [(新號, 文字)]；hőng換掉ê提掉，文字原樣。

    `total` 是舊時間軸ê條數：比伊較大ê號碼本底就無彼條，是 TSV 本身有
    問題，擋落來，毋是恬恬提掉。
    """
    out = []
    for number, text in rows:
        if number < 1 or number > total:
            raise PipelineError("TSV 有 cue %d，舊時間軸干焦 %d 條"
                                % (number, total))
        if number in table:
            out.append((table[number], text))
    out.sort(key=lambda row: row[0])
    return out


def check_reader(rows, fresh):
    """讀者 TSV 愛拄好是新 cue 彼幾號，一條都袂使少、袂使加。"""
    got = set()
    for number, _text in rows:
        got.add(number)
    want = set(fresh)
    missing = sorted(want - got)
    extra = sorted(got - want)
    if missing or extra:
        raise PipelineError("讀者 TSV 無合：欠 %s，加出 %s"
                            % (missing or "無", extra or "無"))


def _stamp(value):
    value = float(value)
    if value == int(value):
        return str(int(value))
    return "%.3f" % value


def override(rows, lo, hi, kind, basis="人工", band=None):
    """段落表 [lo, hi) 彼段換做一逝 `kind`，前後ê段照切。

    `band` 是這段字幕ê (上緣, 下緣)，無講就照類型ê預設區域。
    """
    rows_y = band
    out = []
    placed = False
    for row in rows:
        start, end = float(row["起秒"]), float(row["迄秒"])
        if end <= lo or start >= hi:
            if start >= hi and not placed:
                out.append(_row(rows, lo, hi, kind, basis, rows_y))
                placed = True
            out.append(dict(row))
            continue
        if start < lo:
            head = dict(row)
            head["迄秒"] = _stamp(lo)
            out.append(head)
        if not placed:
            out.append(_row(rows, lo, hi, kind, basis, rows_y))
            placed = True
        if end > hi:
            tail = dict(row)
            tail["起秒"] = _stamp(hi)
            out.append(tail)
    if not placed:
        out.append(_row(rows, lo, hi, kind, basis, rows_y))
    return out


def _row(rows, lo, hi, kind, basis, rows_y=None):
    language = rows[0]["單元語別"] if rows else ""
    top, bottom = segments.rows_of(kind, language, (722, 844))
    if rows_y:
        top, bottom = str(rows_y[0]), str(rows_y[1])
    return {"起秒": _stamp(lo), "迄秒": _stamp(hi), "類型": kind,
            "單元語別": language, "字幕上緣y": top, "字幕下緣y": bottom,
            "依據": basis, segments.INTERVIEWEE: ""}


# ------------------------------------------------------------ I/O


def _entry(name):
    for entry in episodes.load():
        if entry["srt_name"] == name:
            return entry
    raise PipelineError("目錄內底無 %s" % name)


def out_dir(name):
    return os.path.join(paths.NEWS_OUT, "offband", paths.month_of(name), name)


def starting_table(name, out, store=None):
    """補切進前ê段落表：頂一段補切ê > Kari-SRT 已入庫ê > None（愛重算）。

    仝一集分幾段補切（060 晚間三段），第二擺起愛佇頂一擺ê表頂懸蓋，
    若無頂一段ê「帶外專題」會予人洗掉；已經確認入庫ê表（2024-12）嘛
    愛接落去，毋通用重算ê蓋掉讀者確認過ê逝。
    """
    for path in (paths.segments_file(out),
                 paths.stage_path(store or paths.SEGMENTS_STORE, name,
                                  ".csv")):
        if os.path.exists(path):
            return segments.read(path)
    return None


def _sha(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def prepare(name, lo, hi, video, preset=PRESET):
    """重切、精修、算編號、出組合圖、算段落表；寫 `<out>/plan.json`。

    `preset` 預設 `titv-news-offband`（對白 y≈940–1035）；060 晚間ê兩逝
    戲劇字幕（878–989）用 `titv-news-offband-high`。
    """
    from scripts.news import segment_recut
    from scripts.news import shots
    from scripts.ocr import sheets
    entry = _entry(name)
    store = paths.stage_path(paths.KARI_CUES, name, ".json")
    with open(store, encoding="utf-8") as handle:
        book = json.load(handle)
    out = out_dir(name)
    fresh_dir = os.path.join(out, "recut")
    coarse = segment_recut._recut(video, lo, hi - lo, fresh_dir, preset)
    refined = segment_recut._refine(video, coarse, preset)
    with open(refined, encoding="utf-8") as handle:
        stretch = json.load(handle)
    if not stretch.get("refined"):
        raise PipelineError("%s 重切ê彼段無精修" % name)
    new = []
    for item in stretch["cues"]:
        item = dict(item)
        item["area"] = KIND
        new.append(item)
    spliced = splice(book["cues"], lo, hi, new)
    fresh = fresh_numbers(spliced, book["cues"])

    strips = paths.strips_dir(out)
    os.makedirs(strips, exist_ok=True)
    for path in glob.glob(os.path.join(paths.strips_dir(fresh_dir), "*")):
        shutil.copy2(path, os.path.join(strips, os.path.basename(path)))
    wanted = set(fresh)
    shown = []
    for item in spliced:
        if int(item["index"]) in wanted:
            shown.append(item)
    manifest = {"lines": stretch["lines"], "mask": {}, "cues": shown}
    sheet_dir = paths.sheets_dir(out)
    if os.path.isdir(sheet_dir):
        shutil.rmtree(sheet_dir)
    made = sheets.build_sheets(out, manifest)

    table_path = paths.segments_file(out)
    table = starting_table(name, out)
    if table is None:
        with open(paths.ENGINE_PRESETS, encoding="utf-8") as handle:
            layout = json.load(handle)["titv-news"].get("shots", {})
        feats = shots.features(shots.thumbnails(video),
                               shots.load_refs(name[:4]), layout)
        table = segments.classify(feats, entry["族語別(中)"],
                                  book["duration"])
    region = stretch.get("region") or [0, 930, 1920, 110]
    segments.write(table_path, override(
        table, lo, hi, KIND, band=(region[1], region[1] + region[3])))

    plan = {"srt_name": name, "lo": lo, "hi": hi, "store_sha": _sha(store),
            "spliced": spliced, "fresh": fresh, "old_total": len(book["cues"]),
            "region": stretch.get("region"), "preset": preset}
    with open(os.path.join(out, "plan.json"), "w", encoding="utf-8") as fh:
        json.dump(plan, fh, ensure_ascii=False, indent=2, sort_keys=True)
    print("%s：舊 %d 條 → 新 %d 條，新 cue %d 條（%s–%s 號），組合圖 %d 張"
          % (name, len(book["cues"]), len(spliced), len(fresh),
             fresh[0] if fresh else "-", fresh[-1] if fresh else "-", made))
    return plan


def _read_tsv(path):
    rows = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            parts = line.rstrip("\n").split("\t", 2)
            if len(parts) >= 2 and parts[0].isdigit():
                rows.append((int(parts[0]),
                             parts[2] if len(parts) > 2 else ""))
    return rows


def _write_tsv(path, rows):
    with open(path, "w", encoding="utf-8") as handle:
        for number, text in rows:
            handle.write("%d\than\t%s\n" % (number, text))


def apply(name, reader):
    """讀者 TSV 收入去：TSV 改編號、時間軸、SRT、段落表入庫。"""
    from scripts.news import rebuild
    from scripts.news import redump_store
    out = out_dir(name)
    with open(os.path.join(out, "plan.json"), encoding="utf-8") as handle:
        plan = json.load(handle)
    store = paths.stage_path(paths.KARI_CUES, name, ".json")
    if _sha(store) != plan["store_sha"]:
        raise PipelineError("%s ê時間軸 prepare 了後 hőng改過，重做 prepare"
                            % name)
    with open(store, encoding="utf-8") as handle:
        book = json.load(handle)
    table = moves(book["cues"], plan["spliced"])
    rows = _read_tsv(reader)
    check_reader(rows, plan["fresh"])

    folder = paths.stage_path(paths.KARI_VISION, name)
    existing = sorted(glob.glob(os.path.join(folder, "b*.tsv")))
    rewritten = []
    for path in existing:
        rewritten.append((path, rewrite(_read_tsv(path), table,
                                        plan["old_total"])))
    for path, new_rows in rewritten:
        _write_tsv(path, new_rows)
    target = os.path.join(folder, "b%02d.tsv" % (len(existing) + 1))
    _write_tsv(target, sorted(rows))

    book["cues"] = plan["spliced"]
    areas = dict(book.get("areas", {}))
    areas[KIND] = {"preset": plan.get("preset", PRESET),
                   "region": plan.get("region")}
    book["areas"] = areas
    with open(store, "w", encoding="utf-8") as handle:
        handle.write(redump_store.dump(datadirs.store_timeline(book)))

    tmp = tempfile.mkdtemp(prefix="offband-")
    os.makedirs(os.path.join(tmp, "srt"))
    rebuild.rebuild_one(_entry(name) | {"srt_name": name}, tmp)
    shutil.copy2(os.path.join(tmp, "srt", name + ".srt"),
                 paths.stage_path(paths.SRT_DIR, name, ".srt"))
    shutil.rmtree(tmp)

    # 平行語料是 whisper 段落配交付 SRT 做出來ê，SRT 一改就愛重做。
    from scripts.news import pairs_run
    if pairs_run.in_scope(name):
        pairs_run.main([name])

    table_path = paths.segments_file(out)
    table_rows = segments.read(table_path)
    problems = segments.check(table_rows, name, book["duration"])
    if problems:
        print("段落表猶未入庫：%s" % problems[0])
    else:
        dest = paths.stage_path(paths.SEGMENTS_STORE, name, ".csv")
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy2(table_path, dest)
    print("%s：%d 份 TSV 改編號，新增 %s（%d 逝）"
          % (name, len(existing), os.path.basename(target), len(rows)))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="command", required=True)
    one = sub.add_parser("prepare")
    one.add_argument("name")
    one.add_argument("lo", type=float)
    one.add_argument("hi", type=float)
    one.add_argument("video")
    one.add_argument("--preset", default=PRESET)
    two = sub.add_parser("apply")
    two.add_argument("name")
    two.add_argument("tsv")
    args = ap.parse_args(argv)
    if args.command == "prepare":
        prepare(args.name, args.lo, args.hi, args.video, args.preset)
    else:
        apply(args.name, args.tsv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
