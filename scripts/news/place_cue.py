#!/usr/bin/env python3
"""Put a cue where frame-stepping says one belongs, or move a cue's ends.

    python3 -m scripts.news.place_cue <work-dir stem> insert <start> <end> \\
        --text "畫面頂懸彼句"
    python3 -m scripts.news.place_cue <work-dir stem> bounds <cue> \\
        <start> <end>
    python3 -m scripts.news.place_cue <work-dir stem> delete <cue>
    python3 -m scripts.news.place_cue <work-dir stem> merge <cue>
    python3 -m scripts.news.place_cue <work-dir stem> area <cue> <area>
    python3 -m scripts.news.place_cue --store --lock <store.lock> \
        <work-dir stem> delete <cue>      # work dir 已清掉的集

WHY
---
`split_cue` divides a cue that exists. Some lines never got a cue at all:
2021-12-03 337 晚間 at 1178–1180 s shows two one-character captions, 山 then
海, over an aerial shot of breaking waves. The surf alone carries 314–504
ink per sample, a single character adds about 150, and consecutive masks
differ by 0.41–0.73 -- past the 0.35 change threshold every time -- so the
segmenter (and a re-cut with the same preset) sees one unstable blur. 山
has no cue; 海's cue starts 0.58 s late and runs into the next one.

The times here come from stepping native frames, the same as `split_cue`;
nothing is re-segmented. Both operations refuse to make cues overlap: if a
measured span runs into a neighbour, move that neighbour first with
`bounds`, so every change is one the caller chose.

The inserted cue has no strip (`images` is empty, as for split_cue's second
half) and is marked `placed`; later cues are renumbered without renaming
their strips, for the reasons in `split_cue`.

插入的 cue 跟著前後 cue 的 `area`（兩邊同一個才寫；在區域邊界上判斷
不出來就不寫，要的話用 `--area` 指定）。原本完全不寫，286 晚 846、210 晨
860／867／877 這類 placed cue 前後都有 area、只有自己沒有，靠 area 挑切法
設定的程式會把它當成頂層字幕帶；既有的用 `fill_placed_area` 補。

`delete` 刪一條、`merge` 把一條和下一條併成一條，後面的號碼往前移，
TSV、sheets.json 跟著改。用來清殘留的空白 cue（259 晚排灣 903 只有
0.017 秒）、同一句被切成兩條（353 午噶瑪蘭 528／529 都是「好像不太夠」）。
有字的 cue 不能直接刪（字會從 SRT 消失），要加 `--drop-text`；併的兩條
字不同時要用 `--text` 說清楚併成什麼。併的兩條切法要一樣：一條有 area、
另一條是頂層字幕帶切的（沒有 placed、沒有 area）不併，不然頂層那條會被
整條標成那個 area。

`area` 只改一條 cue 的 area（空字串是拿掉，也就是頂層字幕帶切的），
時間、號碼、TSV 都不動，交付 SRT 也不變（rebuild 不讀 area）。060 午
cue 429「我們下次見」在部落信箱裡卻寫島語時間（搬移時沒換到）、
fill_placed_area 判斷不出來的 placed cue，看過畫面用它補，不要手改 JSON。
名字要是這集用過的 area（打錯一個字誰都對不到 areas 的設定）。

號碼變了，訂正紀錄也要跟著改（暫存區的 `renumber_fixes`），每次做完會印
該下的指令（`renumber_hint`）。`--shift K 差` 是「≥K 的號碼加差」：刪 K 是
`--shift K+1 -1`、併 K 是 `--shift K+2 -1`；被刪的 K、被併掉的 K+1 原本
的訂正要人工看（照「--shift K -1」做，K 本身也被減 1，訂正落到前一條上，
不會報錯）。

work dir 已經清掉或改名 `.stale-*` 的集（259 晚排灣、248 午噶瑪蘭、353 午
噶瑪蘭）沒有時間軸可改，加 `--store` 直接改 Kari-SRT 的時間軸和 TSV，
重做交付 SRT（`pairs_run.in_scope` 範圍內的再重做平行語料）；這時候要給
`--lock`（跟 publish 同一把 store.lock，外面不要再包一層 flock）。還有
work dir 的集不准用 `--store`：之後 publish 會用 work dir 那份蓋回去。
"""
import argparse
import contextlib
import fcntl
import glob
import json
import os
import shutil
import sys
import tempfile

from scripts import datadirs
from scripts.errors import PipelineError
from scripts.news import episodes
from scripts.news import paths
from scripts.news import split_cue


def _mid(start, end):
    return round((start + end) / 2, 3)


def _no_area(item):
    """插入時沒寫 area 的 cue：找鄰居 area 時要越過它。"""
    return bool(item.get("placed")) and not item.get("area")


def area_around(cues, before, after):
    """0 起算的位置 `before`、`after` 之間那個空檔該有的 area，或 None。

    兩邊都往外越過同樣是插入、沒有 area 的 cue；兩邊同一個 area 才算，
    碰到時間軸頭尾也不算。
    """
    while before >= 0 and _no_area(cues[before]):
        before -= 1
    while after < len(cues) and _no_area(cues[after]):
        after += 1
    if before < 0 or after >= len(cues):
        return None
    left = cues[before].get("area")
    if left and left == cues[after].get("area"):
        return left
    return None


def insert(cues, start, end, area=None):
    """(cues with a new cue over [start, end], its 1-based index).

    `area` None 時照前後 cue 判（`area_around`）；給字串就用它，空字串是
    明講不要 area。
    """
    if not start < end:
        raise PipelineError("插入ê cue 起迄 %.3f–%.3f 毋著" % (start, end))
    index = len(cues) + 1
    for position, one in enumerate(cues):
        if one["start"] >= end:
            index = position + 1
            break
    before = cues[index - 2] if index > 1 else None
    after = cues[index - 1] if index <= len(cues) else None
    if (before and before["end"] > start) or (after and after["start"] < end):
        raise PipelineError(
            "%.3f–%.3f 硩著隔壁ê cue，先用 bounds 調彼條" % (start, end))
    new = {"start": start, "end": end, "frames": 0, "ink": 0,
           "sample_ts": _mid(start, end), "images": {}, "placed": True}
    if area is None:
        area = area_around(cues, index - 2, index - 1)
    if area:
        new["area"] = area
    out = []
    for one in cues[:index - 1]:
        out.append(dict(one))
    out.append(new)
    for one in cues[index - 1:]:
        out.append(dict(one))
    for number, one in enumerate(out, 1):
        one["index"] = number
    return out, index


def set_bounds(cues, index, start, end):
    """cues with cue `index` moved to [start, end]; neighbours untouched."""
    if index < 1 or index > len(cues):
        raise PipelineError("cue %d 佇 %d 條內底無" % (index, len(cues)))
    if not start < end:
        raise PipelineError("cue %d 起迄 %.3f–%.3f 毋著" % (index, start, end))
    before = cues[index - 2] if index > 1 else None
    after = cues[index] if index < len(cues) else None
    if (before and before["end"] > start) or (after and after["start"] < end):
        raise PipelineError(
            "cue %d 調做 %.3f–%.3f 會硩著隔壁，先調隔壁彼條"
            % (index, start, end))
    out = []
    for one in cues:
        out.append(dict(one))
    moved = out[index - 1]
    moved["start"] = start
    moved["end"] = end
    if not start <= moved.get("sample_ts", start) <= end:
        moved["sample_ts"] = _mid(start, end)
    return out


def set_area(cues, index, area):
    """cues with cue `index`'s area set to `area`（空字串是拿掉）。"""
    _check_index(cues, index)
    out = []
    for one in cues:
        out.append(dict(one))
    if area:
        out[index - 1]["area"] = area
    else:
        out[index - 1].pop("area", None)
    return out


def _renumber(cues):
    for number, one in enumerate(cues, 1):
        one["index"] = number
    return cues


def _check_index(cues, index):
    if index < 1 or index > len(cues):
        raise PipelineError("cue %d 在 %d 條裡面沒有" % (index, len(cues)))


def delete(cues, index):
    """cues without cue `index`; later cues move up, strips not renamed."""
    _check_index(cues, index)
    out = []
    for position, one in enumerate(cues, 1):
        if position != index:
            out.append(dict(one))
    return _renumber(out)


def merge(cues, index):
    """cues with cue `index` and the next one made one cue.

    起點是第一條的、迄點是兩條較晚的那個（重疊的兩條也成立）；strip、
    sample_ts 用第一條的（讀者看過的那張）。兩條切法不同不併——area 不同
    是跨區域，多半是量錯了；一條有 area、一條是頂層字幕帶切的（沒有
    placed、沒有 area），併了頂層那條會被標成那個 area。placed 的 cue 沒有
    切法，跟誰都能併。
    """
    _check_index(cues, index)
    if index == len(cues):
        raise PipelineError("cue %d 是最後一條，沒有下一條可以併" % index)
    first, second = cues[index - 1], cues[index]
    areas = []
    settings = []
    for one in (first, second):
        if one.get("area") and one["area"] not in areas:
            areas.append(one["area"])
        if one.get("area"):
            settings.append(one["area"])
        elif not one.get("placed"):
            settings.append("頂層字幕帶")
    if len(set(settings)) > 1:
        raise PipelineError("cue %d、%d 的切法不同（%s），不併"
                            % (index, index + 1, "／".join(settings)))
    joined = dict(first)
    joined["end"] = max(first["end"], second["end"])
    joined["frames"] = first.get("frames", 0) + second.get("frames", 0)
    joined["ink"] = max(first.get("ink", 0), second.get("ink", 0))
    if areas:
        joined["area"] = areas[0]
    if not first.get("images") and second.get("images"):
        joined["images"] = dict(second["images"])
    if not joined["start"] <= joined.get("sample_ts", joined["start"]) \
            <= joined["end"]:
        joined["sample_ts"] = _mid(joined["start"], joined["end"])
    out = []
    for one in cues[:index - 1]:
        out.append(dict(one))
    out.append(joined)
    for one in cues[index + 1:]:
        out.append(dict(one))
    return _renumber(out)


def merged_text(first, second, text=None):
    """併起來那條的字：給了 `text` 就用；一樣或一邊空白就取有字的。"""
    if text is not None:
        return text
    if first == second or not second:
        return first
    if not first:
        return second
    raise PipelineError("兩條的字不同（%r／%r），用 --text 說要併成什麼"
                        % (first, second))


def check_droppable(texts, keep_text):
    """有字的 cue 不刪，除非呼叫的人明講（`keep_text`）。"""
    for text in texts:
        if text.strip() and not keep_text:
            raise PipelineError("這條有字（%r），刪掉 SRT 就少這句；"
                                "確定要刪加 --drop-text" % text)


def drop_rows(rows, index):
    """[(cue, text)] without cue `index`'s rows, later cues moved up."""
    out = []
    for number, text in rows:
        if number == index:
            continue
        out.append((number - 1 if number > index else number, text))
    return out


def merge_rows(rows, index, text, here):
    """[(cue, text)] after `merge(index)`.

    兩條原本的列都拿掉；`here` 是這個檔要放併好的那一列。第二條的列若在
    別的檔，留著就會變成同一號出現在兩個檔，`ingest` 整集擋。
    """
    out = []
    for number, old in rows:
        if number in (index, index + 1):
            continue
        out.append((number - 1 if number > index + 1 else number, old))
    if here:
        out.append((index, text))
        out.sort(key=lambda row: row[0])
    return out


def drop_from_sheets(sheets, index):
    """`sheets.json` with cue `index` gone and later cues moved up."""
    out = {}
    for name in sheets:
        moved = []
        for number in sheets[name]:
            if number == index:
                continue
            moved.append(number - 1 if number > index else number)
        out[name] = sorted(moved)
    return out


def renumber_hint(op, index):
    """改號之後要怎麼改訂正紀錄（暫存區的 renumber_fixes），一段給人看的字。

    `--shift K 差` 是「≥K 的號碼加差」。刪 K 照「--shift K -1」做，K 本身
    也被減 1，K 的訂正落到前一條上，不會報錯。
    """
    tool = "renumber_fixes <成果檔名>"
    if op == "insert":
        return "訂正紀錄改號：%s --shift %d 1" % (tool, index)
    if op == "delete":
        return ("訂正紀錄改號：%s --shift %d -1；指著 cue %d（刪掉的那條）的訂正"
                "要人工看，現在的 %d 是原本的 %d"
                % (tool, index + 1, index, index, index + 1))
    if op == "merge":
        return ("訂正紀錄改號：%s --shift %d -1；指著 cue %d（併進 %d 的那條）"
                "的訂正要人工看，不然會留在現在的 %d（原本的 %d）上"
                % (tool, index + 2, index + 1, index, index + 1, index + 2))
    raise PipelineError("不認得的操作 %r" % op)


def shift_rows(rows, index):
    """[(cue, text)] with every cue at or after `index` moved up by one."""
    out = []
    for number, text in rows:
        out.append((number + 1 if number >= index else number, text))
    return out


def remap_rows(rows, index, text):
    """shift_rows plus the new row, in cue order."""
    out = shift_rows(rows, index)
    out.append((index, text))
    out.sort(key=lambda row: row[0])
    return out


def remap_sheets(sheets, index):
    """`sheets.json` after an insert: later cues shift, the new cue joins
    the sheet of the cue before it (the first sheet if it is cue 1), so
    `ingest` still finds every cue on some sheet."""
    home = None
    for name in sorted(sheets):
        if (index - 1) in sheets[name] or (index == 1 and 1 in sheets[name]):
            home = name
    out = {}
    for name in sheets:
        moved = []
        for number in sheets[name]:
            moved.append(number + 1 if number >= index else number)
        if name == home:
            moved.append(index)
        out[name] = sorted(moved)
    return out


# ------------------------------------------------------------------ I/O


def _entry_of(stem):
    for entry in episodes.load():
        if entry["slug"] == stem:
            return entry
    raise PipelineError("inventory 內底揣無 %s" % stem)


def _name_of(stem):
    return _entry_of(stem)["srt_name"]


def _book(stem, store=False):
    """(work dir 或 None, 時間軸路徑, 時間軸)。

    `store` 為真時改 Kari-SRT 的時間軸；那時候 work dir 不可以還有時間軸，
    不然之後 publish 會用 work dir 那份蓋回去。
    """
    work = paths.work_dir(stem)
    path = paths.cues_to_read(work)
    if store:
        if path is not None:
            raise PipelineError("%s 還有時間軸 %s，改 work dir（之後 publish），"
                                "不要加 --store" % (stem, path))
        path = paths.stage_path(paths.KARI_CUES, _name_of(stem), ".json")
        if not os.path.exists(path):
            raise PipelineError("Kari-SRT 沒有 %s 的時間軸 %s" % (stem, path))
        work = None
    elif path is None:
        stale = sorted(glob.glob(glob.escape(work) + ".stale-*"))
        where = "，只剩 %s" % "、".join(stale) if stale else ""
        raise PipelineError("%s 無時間軸%s；work dir 已經清掉的集要直接改 "
                            "Kari-SRT，加 --store --lock <store.lock>"
                            % (work, where))
    with open(path, encoding="utf-8") as handle:
        return work, path, json.load(handle)


def _save(path, book, store=False):
    with open(path, "w", encoding="utf-8") as handle:
        if store:
            handle.write(json.dumps(datadirs.store_timeline(book),
                                    ensure_ascii=False, indent=2,
                                    sort_keys=True) + "\n")
        else:
            json.dump(book, handle, ensure_ascii=False, indent=2,
                      sort_keys=True)


def _rebuild_srt(stem):
    """--store 改完：照 Kari-SRT 重做交付 SRT（跟 offband_backfill apply 一樣）。"""
    from scripts.news import pairs_run
    from scripts.news import rebuild
    entry = _entry_of(stem)
    name = entry["srt_name"]
    tmp = tempfile.mkdtemp(prefix="place-cue-")
    try:
        os.makedirs(os.path.join(tmp, "srt"))
        rebuild.rebuild_one(entry, tmp)
        shutil.copy2(os.path.join(tmp, "srt", name + ".srt"),
                     paths.stage_path(paths.SRT_DIR, name, ".srt"))
    finally:
        shutil.rmtree(tmp)
    # 平行語料是 whisper 段落配交付 SRT 做出來的，SRT 一改就要重做
    if pairs_run.in_scope(name):
        pairs_run.main([name])


@contextlib.contextmanager
def store_lock(path):
    """拿 store.lock（跟 publish、rebroadcast_port apply 同一把）；None 不拿。"""
    if path is None:
        yield
        return
    with open(path, "a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def known_areas(book):
    """這集時間軸用過的 area 名（`areas` 的鍵和 cue 上的值）。"""
    names = set(book.get("areas") or {})
    for one in book["cues"]:
        if one.get("area"):
            names.add(one["area"])
    return names


def _remap_sheets_file(work, change):
    if work is None:            # --store：沒有 work dir，也就沒有 sheets.json
        return
    sheets_path = paths.sheets_index(work)
    if os.path.exists(sheets_path):
        with open(sheets_path, encoding="utf-8") as handle:
            sheets = json.load(handle)
        _save(sheets_path, change(sheets))


def apply_insert(stem, start, end, text, area=None, store=False):
    """Insert across the timeline, sheets.json and the vision TSVs."""
    work, path, book = _book(stem, store)
    if area and area not in known_areas(book):
        raise PipelineError("這集沒有 area %r（有：%s）" % (
            area, "、".join(sorted(known_areas(book))) or "無"))
    book["cues"], index = insert(book["cues"], start, end, area)
    record = {"op": "insert", "cue": index, "start": start, "end": end,
              "text": text}
    if book["cues"][index - 1].get("area"):
        record["area"] = book["cues"][index - 1]["area"]
    book["placed"] = book.get("placed", []) + [record]
    _save(path, book, store)
    _remap_sheets_file(work, lambda sheets: remap_sheets(sheets, index))
    folder = split_cue.vision_folders(_name_of(stem))[0]
    # the new row goes in with its neighbour: the file holding the cue that
    # now comes after it (old number `index`), or the last one before it
    target = split_cue.holding(folder, index)
    for one in sorted(glob.glob(os.path.join(folder, "b*.tsv"))):
        rows = split_cue.read_tsv(one)
        if one == target:
            rows = remap_rows(rows, index, text)
        else:
            rows = shift_rows(rows, index)
        split_cue.write_tsv(one, rows)
    if store:
        _rebuild_srt(stem)
    return index, len(book["cues"]), book["cues"][index - 1].get("area")


def _texts(folder, numbers):
    """{cue: [text…]}：這幾號在各 TSV 的字。"""
    out = {}
    for number in numbers:
        out[number] = []
    for one in sorted(glob.glob(os.path.join(folder, "b*.tsv"))):
        for number, text in split_cue.read_tsv(one):
            if number in out:
                out[number].append(text)
    return out


def apply_delete(stem, index, drop_text=False, store=False):
    """Delete one cue across the timeline, sheets.json and the TSVs."""
    work, path, book = _book(stem, store)
    _check_index(book["cues"], index)
    folder = split_cue.vision_folders(_name_of(stem))[0]
    texts = _texts(folder, [index])[index]
    check_droppable(texts, drop_text)
    gone = book["cues"][index - 1]
    book["cues"] = delete(book["cues"], index)
    book["placed"] = book.get("placed", []) + [
        {"op": "delete", "cue": index, "start": gone["start"],
         "end": gone["end"], "text": "".join(texts)}]
    _save(path, book, store)
    _remap_sheets_file(work, lambda sheets: drop_from_sheets(sheets, index))
    for one in sorted(glob.glob(os.path.join(folder, "b*.tsv"))):
        split_cue.write_tsv(one, drop_rows(split_cue.read_tsv(one), index))
    if store:
        _rebuild_srt(stem)
    return len(book["cues"])


def apply_merge(stem, index, text=None, store=False):
    """Merge cue `index` with the next across timeline, sheets, TSVs."""
    work, path, book = _book(stem, store)
    folder = split_cue.vision_folders(_name_of(stem))[0]
    found = _texts(folder, [index, index + 1])
    joined = merged_text("".join(found[index]), "".join(found[index + 1]),
                         text)
    book["cues"] = merge(book["cues"], index)
    one = book["cues"][index - 1]
    book["placed"] = book.get("placed", []) + [
        {"op": "merge", "cue": index, "start": one["start"],
         "end": one["end"], "text": joined}]
    _save(path, book, store)
    _remap_sheets_file(work,
                       lambda sheets: drop_from_sheets(sheets, index + 1))
    # 併好的那列放在原本有第一條的檔；第一條沒有列就放有第二條的檔
    target = None
    if found[index] or found[index + 1]:
        target = split_cue.holding(folder,
                                   index if found[index] else index + 1)
    for tsv in sorted(glob.glob(os.path.join(folder, "b*.tsv"))):
        split_cue.write_tsv(tsv, merge_rows(split_cue.read_tsv(tsv), index,
                                            joined, tsv == target))
    if store:
        _rebuild_srt(stem)
    return len(book["cues"]), joined


def apply_bounds(stem, index, start, end, store=False):
    """Move one cue's ends in the timeline; numbering does not change."""
    _work, path, book = _book(stem, store)
    book["cues"] = set_bounds(book["cues"], index, start, end)
    book["placed"] = book.get("placed", []) + [
        {"op": "bounds", "cue": index, "start": start, "end": end}]
    _save(path, book, store)
    if store:
        _rebuild_srt(stem)
    return len(book["cues"])


def apply_area(stem, index, area, store=False):
    """Set one cue's area in the timeline; False when it already was.

    TSV、sheets.json、號碼都不動；rebuild 不讀 area，--store 也不重做 SRT。
    """
    _work, path, book = _book(stem, store)
    _check_index(book["cues"], index)
    if area and area not in known_areas(book):
        raise PipelineError("這集沒有 area %r（有：%s）" % (
            area, "、".join(sorted(known_areas(book))) or "無"))
    was = book["cues"][index - 1].get("area", "")
    if was == area:
        return False
    book["cues"] = set_area(book["cues"], index, area)
    book["placed"] = book.get("placed", []) + [
        {"op": "area", "cue": index, "area": area, "was": was}]
    _save(path, book, store)
    return True


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--store", action="store_true",
                    help="work dir 已清掉的集：直接改 Kari-SRT（要給 --lock）")
    ap.add_argument("--lock", default=None,
                    help="store.lock 的路徑；改的時候拿著（--store 一定要給）")
    ap.add_argument("stem")
    sub = ap.add_subparsers(dest="op", required=True)
    one = sub.add_parser("insert")
    one.add_argument("start", type=float)
    one.add_argument("end", type=float)
    one.add_argument("--text", required=True)
    one.add_argument("--area", default=None,
                     help="指定 area；不給就照前後 cue，空字串是不要")
    two = sub.add_parser("bounds")
    two.add_argument("cue", type=int)
    two.add_argument("start", type=float)
    two.add_argument("end", type=float)
    three = sub.add_parser("delete")
    three.add_argument("cue", type=int)
    three.add_argument("--drop-text", action="store_true",
                       help="這條有字也刪（字會從 SRT 消失）")
    four = sub.add_parser("merge")
    four.add_argument("cue", type=int, help="和下一條併")
    four.add_argument("--text", default=None,
                      help="併好的字；兩條字不同時一定要給")
    five = sub.add_parser("area")
    five.add_argument("cue", type=int)
    five.add_argument("area", help="這集用過的 area；空字串是拿掉（頂層字幕帶）")
    args = ap.parse_args(argv)
    if args.store and not args.lock:
        ap.error("--store 會寫 Kari-SRT，要給 --lock（store.lock 的路徑）")
    with store_lock(args.lock):
        return _run(args)


def _run(args):
    store = args.store
    if args.op == "insert":
        index, total, area = apply_insert(args.stem, args.start, args.end,
                                          args.text, args.area, store)
        print("%s：%.3f–%.3f 插做 cue %d，總數變 %d，area：%s"
              % (args.stem, args.start, args.end, index, total,
                 area or "無（前後 cue 不同或沒有；要的話用 --area）"))
        print(renumber_hint("insert", index))
    elif args.op == "delete":
        total = apply_delete(args.stem, args.cue, args.drop_text, store)
        print("%s：刪掉 cue %d，後面往前移一號，總數 %d"
              % (args.stem, args.cue, total))
        print(renumber_hint("delete", args.cue))
    elif args.op == "merge":
        total, text = apply_merge(args.stem, args.cue, args.text, store)
        print("%s：cue %d、%d 併成 cue %d「%s」，後面往前移一號，總數 %d"
              % (args.stem, args.cue, args.cue + 1, args.cue, text, total))
        print(renumber_hint("merge", args.cue))
    elif args.op == "area":
        changed = apply_area(args.stem, args.cue, args.area, store)
        print("%s：cue %d 的 area %s %s" % (
            args.stem, args.cue, "改成" if changed else "本來就是",
            args.area or "無（頂層字幕帶）"))
        if store:
            print("Kari-SRT 時間軸已改；交付 SRT 不受 area 影響，沒有重做")
        return 0
    else:
        total = apply_bounds(args.stem, args.cue, args.start, args.end,
                             store)
        print("%s：cue %d 調做 %.3f–%.3f（總數 %d）"
              % (args.stem, args.cue, args.start, args.end, total))
    if store:
        print("Kari-SRT 已改、交付 SRT 已重做；跑 rebuild --verify 核對")
    return 0


if __name__ == "__main__":
    sys.exit(main())
