#!/usr/bin/env python3
"""已經讀完字ê集數，補切一段帶外字幕（2021 年帶外專題）。

    python3 -m scripts.news.offband_backfill prepare <成果檔名> <起秒> <迄秒> VIDEO
    #   2021 文化小辭典：加 --preset titv-news-dict-2021 --kind 文化小辭典 --probe
    #   （先量字幕列，照量到的列切）
    #   → 讀者讀 <out>/4-sheets/，寫 TSV（編號照圖頂懸印ê）
    python3 -m scripts.news.offband_backfill apply <成果檔名> <讀者 TSV> \
        [--keep-store-table]

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

prepare 把新 cue 裁在 [起秒, 迄秒] 裡面（`clip`），新 cue 和範圍外的 cue
重疊就擋，apply 再擋一次（`check_overlaps`）。段落表從哪一份開始見
`starting_table`：Kari-SRT 有表就照 Kari-SRT 現在的，補切目錄或上一次 plan
記的表跟它不一樣時照 Kari-SRT 並印警告。

apply 寫段落表之前先跟 prepare 當時比（`check_table`）：plan 記了 Kari-SRT
段落表的 sha（`store_segments_sha`），現在不一樣就擋——補切目錄那份是從
prepare 當時的表做的，寫進去會把之後的訂正蓋回去（128 晚 2421–2649 兩列
外景新聞）。舊格式 plan 沒記 sha，補切目錄的表跟 Kari-SRT 不一樣也擋。
擋下來可以重做 prepare，或加 `--keep-store-table`：時間軸、TSV、SRT 照樣
入庫，段落表不動，Kari-SRT 那份要另外看要不要改。
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


def plan_kind(plan):
    """plan 記ê段落類型；較早ê plan 無這欄，當做帶外專題。

    島語時間、部落信箱嘛用這支補切（work dir 清掉ê集干焦會當直接改
    Kari-SRT），類型愛是段落表認得ê，拍毋著就擋。
    """
    kind = plan.get("kind", KIND)
    if kind not in segments.TYPES:
        raise PipelineError("補切類型 %r 毋是段落類型（%s）"
                            % (kind, "、".join(segments.TYPES)))
    return kind


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


def clip(new, lo, hi):
    """新 cue 裁到 [lo, hi] 裡面；裁完沒剩的拿掉。傳進來的不動。

    精修會把邊界往外推：187 晚末條迄點 1572.204 超過 hi 1572.121，壓到
    範圍外的下一條。範圍是呼叫的人照段落表給的，外面的字不歸這次補切。
    """
    out = []
    for item in new:
        item = dict(item)
        item["start"] = round(max(float(item["start"]), lo), 3)
        item["end"] = round(min(float(item["end"]), hi), 3)
        if item["start"] >= item["end"]:
            continue
        sample = item.get("sample_ts")
        if sample is not None and not \
                item["start"] <= sample <= item["end"]:
            item["sample_ts"] = round((item["start"] + item["end"]) / 2, 3)
        out.append(item)
    return out


def fresh_overlaps(spliced, fresh):
    """新 cue 和前後 cue 重疊的地方（文字說明）；只看有新 cue 的那一對。

    時間軸本來就有的重疊（323 午 1198／1199、361 晚 1014／1015）不在補切
    範圍內，不歸這支擋。
    """
    wanted = set(fresh)
    out = []
    for position in range(1, len(spliced)):
        before, after = spliced[position - 1], spliced[position]
        if int(before["index"]) not in wanted and \
                int(after["index"]) not in wanted:
            continue
        if float(before["end"]) > float(after["start"]):
            out.append("cue %d（%.3f–%.3f）和 cue %d（%.3f–%.3f）重疊"
                       % (int(before["index"]), float(before["start"]),
                          float(before["end"]), int(after["index"]),
                          float(after["start"]), float(after["end"])))
    return out


def check_overlaps(spliced, fresh):
    found = fresh_overlaps(spliced, fresh)
    if found:
        raise PipelineError(
            "補切的 cue 和範圍外的 cue 重疊：%s。範圍邊上有一條舊 cue 跨過 "
            "lo／hi，換一個不切到它的範圍，或先用 place_cue bounds 調它"
            % "；".join(found))


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
    same = _same_kind_row(rows, lo, hi, kind)
    out = []
    placed = False
    for row in rows:
        start, end = float(row["起秒"]), float(row["迄秒"])
        if end <= lo or start >= hi:
            if start >= hi and not placed:
                out.append(_row(rows, lo, hi, kind, basis, rows_y, same))
                placed = True
            out.append(dict(row))
            continue
        if start < lo:
            head = dict(row)
            head["迄秒"] = _stamp(lo)
            out.append(head)
        if not placed:
            out.append(_row(rows, lo, hi, kind, basis, rows_y, same))
            placed = True
        if end > hi:
            tail = dict(row)
            tail["起秒"] = _stamp(hi)
            out.append(tail)
    if not placed:
        out.append(_row(rows, lo, hi, kind, basis, rows_y, same))
    return out


KEPT_FIELDS = ("單元語別", "字幕上緣y", "字幕下緣y", segments.INTERVIEWEE,
               segments.SPEECH)


def _same_kind_row(rows, lo, hi, kind):
    """[lo, hi) 裡跟這次補切同類型、重疊最長的那一列，沒有就 None。

    299 晚 1216–2567 帶外專題在 Kari-SRT 已經確認成「鄒 890–970、受訪者
    無、無」，prepare 卻照第一列的語別（布農）和重切的區域（690–1040）
    重寫一列；303 晚、304 午、352 晚、057 晚也一樣。同類型的列本來就在
    的話，語別、上下緣、受訪者那幾欄照它的。
    """
    best = None
    longest = 0.0
    for row in rows:
        if row.get("類型") != kind:
            continue
        length = min(float(row["迄秒"]), hi) - max(float(row["起秒"]), lo)
        if length > longest:
            best, longest = row, length
    return best


def _row(rows, lo, hi, kind, basis, rows_y=None, same=None):
    language = rows[0]["單元語別"] if rows else ""
    top, bottom = segments.rows_of(kind, language, (722, 844))
    if rows_y:
        top, bottom = str(rows_y[0]), str(rows_y[1])
    out = {"起秒": _stamp(lo), "迄秒": _stamp(hi), "類型": kind,
           "單元語別": language, "字幕上緣y": top, "字幕下緣y": bottom,
           "依據": basis, segments.INTERVIEWEE: "", segments.SPEECH: ""}
    if same is not None:
        for field in KEPT_FIELDS:
            out[field] = same.get(field) or ""
    return out


def _value(field, text):
    text = (text or "").strip()
    if field in ("起秒", "迄秒", "字幕上緣y", "字幕下緣y") and text:
        try:
            return round(float(text), 3)
        except ValueError:
            return text
    return text


def same_table(mine, theirs):
    """兩份段落表的值是否相同；「依據」不比（Kari-SRT 不存這欄）。

    比值不比字串：100.500 和 100.5 是同一個秒數。舊做法用 `store_text`
    比原始字串，數字寫法不同就發假警告、「依據」也被換成「人工」。
    """
    if len(mine) != len(theirs):
        return False
    for one, two in zip(mine, theirs):
        for field in segments.STORE_COLUMNS:
            if _value(field, one.get(field)) != _value(field, two.get(field)):
                return False
    return True


# ------------------------------------------------------------ I/O


def _entry(name):
    for entry in episodes.load():
        if entry["srt_name"] == name:
            return entry
    raise PipelineError("目錄內底無 %s" % name)


def out_dir(name):
    return os.path.join(paths.NEWS_OUT, "offband", paths.month_of(name), name)


def _filled(rows):
    # Kari-SRT 的表不存「依據」；寫回補切目錄時變空字串，
    # segments.check 會擋。入庫時這欄又會拿掉，這裡只是過關用。
    for row in rows:
        if not row.get("依據"):
            row["依據"] = "人工"
    return rows


def _unapplied_plan(out, timeline):
    """補切目錄裡上一次 prepare 的 plan，若它還沒 apply；否則 None。

    apply 會改時間軸，所以時間軸的 sha 還是 plan 記的那個＝沒 apply。
    """
    plan_path = os.path.join(out, "plan.json")
    if not (os.path.exists(plan_path) and os.path.exists(timeline)):
        return None
    with open(plan_path, encoding="utf-8") as handle:
        plan = json.load(handle)
    if plan.get("store_sha") != _sha(timeline):
        return None
    return plan


def starting_table(name, out, store=None, timeline=None, notes=None):
    """補切之前的段落表，從哪裡來；都沒有回 None（要重算）。

    - Kari-SRT 有入庫的表：一律照它現在的內容（已確認入庫的表不可被 2021
      判準重算的蓋掉，`20241209_344_晚間_Amis_阿美`）。候選的另一份——上一次
      prepare 還沒 apply 時它記的開始表，否則補切目錄那份——值跟它一樣
      （`same_table`）才用候選那份，「依據」才留得住；不一樣代表候選那份
      是舊的（060 午：Kari-SRT 之後訂正過，舊表把三列合成一列攝影棚蓋回
      去；plan 記攝影棚、Kari-SRT 之後訂正成外景新聞），照 Kari-SRT 的並在
      `notes` 說明。
    - Kari-SRT 沒有表：上一次 prepare 還沒 apply（同一集換範圍重做）就用它
      開始時那份，不然它蓋上去的列會留在表裡（187 晚）；再來是補切目錄
      那份。2021 那幾集原本沒有段落表，060 晚間分三段補切，第二段起要接在
      前一段的表上。

    `notes` 是給人看的警告，prepare 會印出來。
    """
    if notes is None:
        notes = []
    stretch = paths.segments_file(out)
    stored = paths.stage_path(store or paths.SEGMENTS_STORE, name, ".csv")
    plan = _unapplied_plan(out, timeline or paths.stage_path(
        paths.KARI_CUES, name, ".json"))
    if os.path.exists(stored):
        rows = _filled(segments.read(stored))
        if plan is not None and "start_table" in plan:
            mine = plan["start_table"]
            if mine is not None and same_table(mine, rows):
                return _filled(mine)
            notes.append(
                "%s 上一次 prepare（%s–%s）還沒 apply，它開始時的段落表跟 "
                "Kari-SRT 現在的不一樣（%s），照 Kari-SRT 的"
                % (name, plan.get("lo"), plan.get("hi"),
                   "那次是重算的" if mine is None else "之後訂正過"))
            return rows
        if plan is None and os.path.exists(stretch):
            mine = segments.read(stretch)
            if same_table(mine, rows):
                return _filled(mine)
            notes.append(
                "%s 補切目錄的段落表 %s 跟 Kari-SRT 的不一樣，照 Kari-SRT 的。"
                "若差的是前一段補切還沒入庫的列，先把那段入庫再 prepare"
                % (name, stretch))
        return rows
    if plan is not None:
        if "start_table" in plan:
            # null＝上一次也是重算的，這次照樣重算
            if plan["start_table"] is None:
                return None
            return _filled(plan["start_table"])
        if os.path.exists(stretch):
            notes.append(
                "%s 上一次 prepare（%s–%s）還沒 apply，舊的 plan 沒記開始時的"
                "段落表；接著用補切目錄的表，上一次蓋上去的列可能還在，"
                "prepare 完要看段落表" % (name, plan.get("lo"), plan.get("hi")))
    if os.path.exists(stretch):
        return _filled(segments.read(stretch))
    return None


def _store_table_sha(name):
    path = paths.stage_path(paths.SEGMENTS_STORE, name, ".csv")
    if not os.path.exists(path):
        return None
    return _sha(path)


def check_table(name, plan, out):
    """apply 寫段落表之前：Kari-SRT 那份跟 prepare 當時一樣才放行。

    補切目錄的表是從 prepare 當時的表做的；Kari-SRT 之後訂正過還照寫，
    訂正就被蓋回去，而且沒有警告（128 晚 2421–2649 兩列外景新聞，10-21
    prepare、10-23 訂正）。新格式 plan 比 `store_segments_sha`；舊格式沒記，
    補切目錄的表跟 Kari-SRT 不一樣就擋（2026-11-03 還沒 apply 的 6 份
    plan 全是這種）。在寫任何檔之前呼叫。
    """
    now = _store_table_sha(name)
    how = ("重做 prepare，或加 --keep-store-table：時間軸、TSV、SRT 照樣入庫，"
           "段落表不動")
    if "store_segments_sha" in plan:
        if now != plan["store_segments_sha"]:
            raise PipelineError(
                "%s Kari-SRT 的段落表在 prepare 之後改過，補切目錄那份寫進去會"
                "把訂正蓋回去。%s" % (name, how))
        return
    if now is None:
        return
    stored = segments.read(paths.stage_path(paths.SEGMENTS_STORE, name,
                                            ".csv"))
    mine = segments.read(paths.segments_file(out))
    if not same_table(mine, stored):
        raise PipelineError(
            "%s 的 plan 是舊格式（沒記 prepare 當時 Kari-SRT 段落表的 sha），"
            "補切目錄的段落表跟 Kari-SRT 現在的不一樣，分不出是 prepare 時"
            "蓋上去的還是 Kari-SRT 之後的訂正。%s" % (name, how))


def sheet_mask(preset, presets=None):
    """重切彼个 preset ê遮罩設定，予組合圖照仝款ê判準裁圖條。

    組合圖照遮罩ê墨水欄裁圖條；交空ê `{}` 就是預設白字判準，
    titv-news-flower ê彩色花字會算做背景、予人裁掉（2024-06-03
    155 晚間規句無去ê有 434、621）。`presets` 是量字幕列後這段專用的
    preset 檔（`--probe`），沒有就照 presets.json。
    """
    with open(presets or paths.ENGINE_PRESETS, encoding="utf-8") as handle:
        return dict(json.load(handle)[preset].get("mask", {}))


def sunken_presets():
    """可以配 `--probe` 的 preset：字幕沉到帶下、高低逐集不同的那幾個。"""
    from scripts.news import segment_recut
    out = set()
    for name, _until in segment_recut.SUNKEN.values():
        out.add(name)
    return out


def fit_rows(name, lo, hi, video, preset, probe, out):
    """量這段字幕在哪幾列，寫這段專用的 preset 檔；回檔名，量不到回 None。

    2021 文化小辭典的字幕高低逐集不同（2021-11 量到 770–838 到 815–870），
    照 preset 固定的比對列切，20211124 晚一條 cue 長 31.2 秒、兩句整句不見。
    量不到穩定的字（整段背景在動）照原 preset 切並印警告，不中止。
    """
    from scripts.news import segment_recut
    rows = segment_recut.text_rows(probe(video, lo, hi))
    if not rows:
        print("注意：%s %s–%s 量不到穩定的字幕列，照 %s 原本的區域切"
              % (name, _stamp(lo), _stamp(hi), preset))
        return None
    fitted, region = segment_recut._fitted(out, preset, rows, lo,
                                           segment_recut._presets())
    print("%s：量到字幕列 y %d–%d，區域 %s"
          % (name, segment_recut.PROBE_TOP + rows[0],
             segment_recut.PROBE_TOP + rows[1], region))
    return fitted


def _sha(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def prepare(name, lo, hi, video, preset=PRESET, kind=KIND, probe=None):
    """重切、精修、算編號、出組合圖、算段落表；寫 `<out>/plan.json`。

    `preset` 預設 `titv-news-offband`（對白 y≈940–1035）；060 晚間ê兩逝
    戲劇字幕（878–989）用 `titv-news-offband-high`。`kind` 是這段ê段落
    類型（島語時間、部落信箱…），預設帶外專題。`probe` 是量字幕列的函式
    （`segment_recut._probe`），只准配 `sunken_presets()`；有給就先量列、
    照量到的列切（`fit_rows`），plan 的 region 是量過的。
    """
    kind = plan_kind({"kind": kind})
    if probe is not None and preset not in sunken_presets():
        raise PipelineError(
            "--probe 只配字幕沉到帶下的 preset（%s），不配 %s"
            % ("、".join(sorted(sunken_presets())), preset))
    from scripts.news import segment_recut
    from scripts.news import shots
    from scripts.ocr import sheets
    entry = _entry(name)
    store = paths.stage_path(paths.KARI_CUES, name, ".json")
    with open(store, encoding="utf-8") as handle:
        book = json.load(handle)
    out = out_dir(name)
    fresh_dir = os.path.join(out, "recut")
    fitted = None
    if probe is not None:
        fitted = fit_rows(name, lo, hi, video, preset, probe, out)
    if fitted:
        coarse = segment_recut._recut(video, lo, hi - lo, fresh_dir, preset,
                                      presets=fitted)
        refined = segment_recut._refine(video, coarse, preset,
                                        presets=fitted)
    else:
        coarse = segment_recut._recut(video, lo, hi - lo, fresh_dir, preset)
        refined = segment_recut._refine(video, coarse, preset)
    with open(refined, encoding="utf-8") as handle:
        stretch = json.load(handle)
    if not stretch.get("refined"):
        raise PipelineError("%s 重切ê彼段無精修" % name)
    new = []
    for item in clip(stretch["cues"], lo, hi):
        item["area"] = kind
        new.append(item)
    spliced = splice(book["cues"], lo, hi, new)
    fresh = fresh_numbers(spliced, book["cues"])
    check_overlaps(spliced, fresh)

    strips = paths.strips_dir(out)
    os.makedirs(strips, exist_ok=True)
    for path in glob.glob(os.path.join(paths.strips_dir(fresh_dir), "*")):
        shutil.copy2(path, os.path.join(strips, os.path.basename(path)))
    wanted = set(fresh)
    shown = []
    for item in spliced:
        if int(item["index"]) in wanted:
            shown.append(item)
    manifest = {"lines": stretch["lines"],
                "mask": sheet_mask(preset, fitted),
                "cues": shown}
    sheet_dir = paths.sheets_dir(out)
    if os.path.isdir(sheet_dir):
        shutil.rmtree(sheet_dir)
    made = sheets.build_sheets(out, manifest)

    table_path = paths.segments_file(out)
    notes = []
    table = starting_table(name, out, timeline=store, notes=notes)
    for note in notes:
        print("注意：" + note)
    start_table = None
    if table is not None:
        start_table = []
        for row in table:
            start_table.append(dict(row))
    if table is None:
        with open(paths.ENGINE_PRESETS, encoding="utf-8") as handle:
            layout = json.load(handle)["titv-news"].get("shots", {})
        feats = shots.features(shots.thumbnails(video),
                               shots.load_refs(name[:4]), layout)
        table = segments.classify(feats, entry["族語別(中)"],
                                  book["duration"])
    region = stretch.get("region") or [0, 930, 1920, 110]
    segments.write(table_path, override(
        table, lo, hi, kind, band=(region[1], region[1] + region[3])))

    plan = {"srt_name": name, "lo": lo, "hi": hi, "store_sha": _sha(store),
            "spliced": spliced, "fresh": fresh, "old_total": len(book["cues"]),
            "region": stretch.get("region"), "preset": preset, "kind": kind,
            "start_table": start_table,
            "store_segments_sha": _store_table_sha(name)}
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


def next_tsv_number(existing):
    """下一份 bNN.tsv 的號碼：現有最大號 + 1，不是份數 + 1。

    號碼會有缺（034 晨只有 b01、b02、b04、b05），照份數算會蓋掉最後一份。
    """
    largest = 0
    for path in existing:
        stem = os.path.basename(path)[1:-len(".tsv")]
        if stem.isdigit():
            largest = max(largest, int(stem))
    return largest + 1


def apply(name, reader, keep_store_table=False):
    """讀者 TSV 收入去：TSV 改編號、時間軸、SRT、段落表入庫。

    `keep_store_table` 為真時段落表不動（`check_table` 擋下來、確定 Kari-SRT
    那份才對的時候用）。
    """
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
    check_overlaps(plan["spliced"], plan["fresh"])
    if not keep_store_table:
        check_table(name, plan, out)
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
    target = os.path.join(folder, "b%02d.tsv" % next_tsv_number(existing))
    _write_tsv(target, sorted(rows))

    book["cues"] = plan["spliced"]
    areas = dict(book.get("areas", {}))
    areas[plan_kind(plan)] = {"preset": plan.get("preset", PRESET),
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
    if keep_store_table:
        print("段落表沒有動（--keep-store-table）；補切目錄那份在 %s"
              % table_path)
    elif problems:
        print("段落表猶未入庫：%s" % problems[0])
    else:
        dest = paths.stage_path(paths.SEGMENTS_STORE, name, ".csv")
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        segments.write_store(dest, table_rows)
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
    one.add_argument("--kind", default=KIND, help="段落類型，預設帶外專題")
    one.add_argument("--probe", action="store_true",
                     help="先量字幕列、照量到的列切（只配 titv-news-dict-2021）")
    two = sub.add_parser("apply")
    two.add_argument("name")
    two.add_argument("tsv")
    two.add_argument("--keep-store-table", action="store_true",
                     help="段落表不動，只收時間軸、TSV、SRT")
    args = ap.parse_args(argv)
    if args.command == "prepare":
        probe = None
        if args.probe:
            from scripts.news import segment_recut
            probe = segment_recut._probe
        prepare(args.name, args.lo, args.hi, args.video, args.preset,
                args.kind, probe=probe)
    else:
        apply(args.name, args.tsv, args.keep_store_table)
    return 0


if __name__ == "__main__":
    sys.exit(main())
