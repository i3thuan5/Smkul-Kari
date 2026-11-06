#!/usr/bin/env python3
"""補上既有 placed cue 缺的 area（`place_cue insert` 以前不寫這欄）。

    python3 -m scripts.news.fill_placed_area            # 只列出會補哪幾條
    python3 -m scripts.news.fill_placed_area --write --lock <store.lock>
    python3 -m scripts.news.fill_placed_area --write --lock <store.lock> \\
        檔案.json …

不給檔案時看全部：Kari-SRT 的時間軸（`1-ocr/1-cues/`）和還在的 work dir
時間軸。兩邊都要補，只補 Kari-SRT 的話，下一次從 work dir publish 又會
蓋回沒有 area 的那份。`--write` 一定要給 `--lock`（跟 publish 同一把
store.lock，整段拿著；外面不要再包一層 flock，同一把鎖包兩層會卡死自己）。

補哪幾條，規則跟 `place_cue.area_around` 一樣，都是沒有 area 的：

1. placed 的 cue，前後（越過同樣沒有 area 的 placed cue）是同一個 area。
2. 移植工具照首播起迄搬過來的 cue：首播那條是 placed、沒有 area（291 晚
   1036、301 晚 1399 是從 286 晚 846 搬的），重播這條沒有 placed，area 照
   首播的拿掉了。看時間軸的 `ported`（從哪一集、位移多少），扣掉位移後
   跟首播某條 placed（或同樣是這樣搬來的）cue 起迄相同才算（`inherited`）；
   範圍尾端重播自己切的 cue（314 晚 872）對不上，不算。算進來的跟 placed
   一樣照第 1、3 條補。
3. 在區域邊上、只有一邊有 area 的：段落表那一秒的類型就是那個 area，
   而且沒有 area 的那一邊的鄰居在別的段落裡，才補（305 晚 375–381 開場
   歌詞，前一條是攝影棚的頂層 cue）。兩邊鄰居在同一段、段落表對不上的
   不補，跑完列在「判斷不出來」，要人看。

不是插入、也不是從 placed 搬來的 cue 不動：269 午 462 那種前後是島語時間、
自己沒有 area 的，是當初用頂層字幕帶切出來的，area 說的是「用哪一個切法
切的」。

寫回去的排版要跟原本逐 byte 相同（`ensure_ascii=False, indent=2,
sort_keys=True`，結尾換行照原本），只多出 area 那幾行；原本不是這個排版
的檔整份重排會改到別行，所以擋下來並指名。rebuild 不讀 area，交付 SRT
不會變。

寫了以後會影響的：

- 時間軸 sha 變了，這幾集還沒 apply 的 rebroadcast_port plan 要重做
  prepare（apply 會擋「時間軸在 prepare 之後被改過」）；跑完印出是哪幾集。
- rebroadcast_port 判切法看 area：`main_setting` 量範圍裡哪一種切法佔最多
  時間，補了 area 的 cue 從「頂層 region」改算進那個 area 的設定；
  `port_areas` 檢查 areas 衝突時，範圍外有字、有 area 的 cue 變多，原本
  過得去的整段搬可能改成另存一個不衝突的 area 名字，或擋下來要人看。
"""
import argparse
import bisect
import glob
import json
import os
import sys

from scripts import datadirs
from scripts.errors import PipelineError
from scripts.news import episodes
from scripts.news import paths
from scripts.news import place_cue
from scripts.news import segments

SAME = 0.0015        # 秒；移植時起迄照首播 +位移、四捨五入到 0.001


def _blank(item, extra):
    """沒有切法可言、沒有 area 的 cue：placed 或從 placed 搬來的。"""
    if item.get("area"):
        return False
    return bool(item.get("placed")) or int(item["index"]) in extra


def _neighbours(cues, position, extra):
    before, after = position - 1, position + 1
    while before >= 0 and _blank(cues[before], extra):
        before -= 1
    while after < len(cues) and _blank(cues[after], extra):
        after += 1
    left = cues[before] if before >= 0 else None
    right = cues[after] if after < len(cues) else None
    return left, right


def _row_of(rows, item):
    for row in rows:
        if float(row["起秒"]) <= float(item["start"]) + SAME and \
                float(item["end"]) <= float(row["迄秒"]) + SAME:
            return row
    return None


def _by_segments(cues, position, rows, extra):
    """第 3 條：只有一邊有 area 時看段落表；判斷不出來回 None。"""
    left, right = _neighbours(cues, position, extra)
    row = _row_of(rows or [], cues[position])
    if row is None:
        return None
    for side, other in ((left, right), (right, left)):
        if side is None or not side.get("area"):
            continue
        area = side["area"]
        if area != row.get("類型"):
            continue
        if other is not None and other.get("area") == area:
            continue
        if other is not None and _row_of(rows, other) is row:
            continue
        return area
    return None


def _area_for(cues, position, rows, extra):
    left, right = _neighbours(cues, position, extra)
    if left is not None and right is not None and left.get("area") and \
            left["area"] == right.get("area"):
        return left["area"]
    if rows:
        return _by_segments(cues, position, rows, extra)
    return None


def fill(cues, rows=None, inherited=()):
    """(補好的 cues 複本, [(cue 號, area)…])；傳進來的不動。

    `rows` 是這集的段落表（第 3 條用），`inherited` 是從 placed cue 搬來的
    cue 號（第 2 條，`inherited()` 算的）。
    """
    extra = set(inherited)
    out = []
    for one in cues:
        out.append(dict(one))
    filled = []
    for position, one in enumerate(out):
        if not _blank(one, extra):
            continue
        area = _area_for(cues, position, rows, extra)
        if area:
            one["area"] = area
            filled.append((int(one["index"]), area))
    return out, filled


def left_out(cues, rows=None, inherited=()):
    """補不了、但至少一邊鄰居有 area 的：[(cue 號, 前面的 area, 後面的 area)]。"""
    extra = set(inherited)
    out = []
    for position, one in enumerate(cues):
        if not _blank(one, extra) or _area_for(cues, position, rows, extra):
            continue
        left, right = _neighbours(cues, position, extra)
        left_area = left.get("area") if left else None
        right_area = right.get("area") if right else None
        if left_area or right_area:
            out.append((int(one["index"]), left_area, right_area))
    return out


def _ported_blanks(book, books, known):
    """這集從別集 placed（或 known 裡）cue 照起迄搬來、沒有 area 的 cue 號。"""
    out = set()
    for entry in book.get("ported") or []:
        source = books.get(entry.get("from"))
        if source is None:
            continue
        offset = float(entry["offset"])
        lo, hi = entry["range"]
        theirs = known.get(entry["from"], set())
        starts = []
        pool = []
        for item in sorted(source["cues"], key=lambda one: one["start"]):
            if _blank(item, theirs):
                starts.append(float(item["start"]))
                pool.append(item)
        for item in book["cues"]:
            if item.get("area") or item.get("placed"):
                continue
            middle = (float(item["start"]) + float(item["end"])) / 2
            if not lo <= middle < hi:
                continue
            start = float(item["start"]) - offset
            end = float(item["end"]) - offset
            at = bisect.bisect_left(starts, start - SAME)
            while at < len(pool) and starts[at] <= start + SAME:
                if abs(float(pool[at]["end"]) - end) <= SAME:
                    out.add(int(item["index"]))
                    break
                at += 1
    return out


def inherited(books, known=None):
    """{集名: {從 placed cue 搬來的 cue 號}}；搬了又搬的一路算到底。

    `known` 是已經算好的（work dir 的時間軸拿 Kari-SRT 算好的來接）。
    """
    found = {}
    for name in books:
        found[name] = set()
    base = dict(known or {})
    changed = True
    while changed:
        changed = False
        merged = dict(base)
        merged.update(found)
        for name in books:
            more = _ported_blanks(books[name], books, merged) - found[name]
            if more:
                found[name] |= more
                changed = True
    return found


def _layout(doc, newline):
    return json.dumps(doc, ensure_ascii=False, indent=2,
                      sort_keys=True) + ("\n" if newline else "")


def fill_file(path, write=False, rows=None, inherited_cues=(),
              undecided=None):
    """補一份時間軸；回補了哪幾條。`write` 為假只算不寫。

    `undecided` 給一個 list 的話，判斷不出來的（`left_out`）加進去。
    """
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    book = json.loads(text)
    newline = text.endswith("\n")
    cues, filled = fill(book.get("cues", []), rows, inherited_cues)
    if undecided is not None:
        undecided.extend(left_out(cues, rows, inherited_cues))
    if not filled or not write:
        return filled
    if _layout(book, newline) != text:
        raise PipelineError("%s 不是 indent=2、sort_keys 的排版，整份重排會"
                            "改到別行，沒有寫" % path)
    book["cues"] = cues
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(_layout(book, newline))
    return filled


def default_paths():
    """[(時間軸, 成果檔名)]：Kari-SRT 的，加上 work dir 裡讀者用的那份。"""
    found = []
    for path in sorted(glob.glob(os.path.join(paths.KARI_CUES, "*",
                                              "*.json"))):
        found.append((path, os.path.basename(path)[:-len(".json")]))
    names = {}
    for entry in episodes.load():
        names[entry["slug"]] = entry["srt_name"]
    for work in sorted(glob.glob(os.path.join(paths.WORK, "*",
                                              "*" + paths.WORK_EXT))):
        timeline = datadirs.cues_to_read(work)
        if timeline:
            slug = os.path.basename(work)[:-len(paths.WORK_EXT)]
            found.append((timeline, names.get(slug)))
    return found


def _name_guess(path):
    """給檔案時：Kari-SRT 的時間軸檔名就是成果檔名。"""
    base = os.path.basename(path)
    if base.endswith(".json") and base[:8].isdigit():
        return base[:-len(".json")]
    return None


def _segment_rows(name):
    if not name:
        return None
    path = paths.stage_path(paths.SEGMENTS_STORE, name, ".csv")
    if not os.path.exists(path):
        return None
    return segments.read(path)


def _load(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _all_store_books():
    books = {}
    for path in sorted(glob.glob(os.path.join(paths.KARI_CUES, "*",
                                              "*.json"))):
        books[os.path.basename(path)[:-len(".json")]] = _load(path)
    return books


def run(targets, write):
    """補 `targets`（[(路徑, 成果檔名或 None)]），印結果；回離開碼。"""
    store_books = _all_store_books()
    known = inherited(store_books)
    total = files = 0
    refused = []
    undecided = []
    touched = []
    for path, name in targets:
        if name in store_books and \
                os.path.dirname(os.path.dirname(path)) == paths.KARI_CUES:
            mine = known.get(name, set())
        else:
            book = _load(path)
            mine = _ported_blanks(book, store_books, known)
        stuck = []
        try:
            filled = fill_file(path, write, _segment_rows(name), mine, stuck)
        except PipelineError as error:
            refused.append(str(error))
            continue
        for number, left, right in stuck:
            undecided.append("%s cue %d（前 %s、後 %s）"
                             % (name or path, number, left or "頂層",
                                right or "頂層"))
        if not filled:
            continue
        files += 1
        total += len(filled)
        if name and name not in touched:
            touched.append(name)
        shown = []
        for number, area in filled:
            shown.append("%d（%s）" % (number, area))
        print("%s：%s" % (path, "、".join(shown)))
    print("%s %d 份、%d 條" % ("補了" if write else "會補", files, total))
    if undecided:
        print("判斷不出來、沒補的 %d 條（要人看）：" % len(undecided))
        for line in undecided:
            print("  " + line)
    if touched:
        print("%s時間軸的 %d 集，還沒 apply 的 rebroadcast_port plan 要重做 "
              "prepare（時間軸 sha 會變）：%s"
              % ("改了" if write else "寫下去會改到", len(touched),
                 "、".join(touched)))
    for line in refused:
        print("沒寫：" + line)
    return 1 if refused else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("files", nargs="*", help="不給就看全部時間軸")
    ap.add_argument("--write", action="store_true", help="真的寫回去")
    ap.add_argument("--lock", default=None,
                    help="store.lock 的路徑；--write 一定要給，整段拿著")
    args = ap.parse_args(argv)
    if args.write and not args.lock:
        ap.error("--write 會寫 Kari-SRT 和 work dir 的時間軸，要給 --lock"
                 "（跟 publish 同一把 store.lock）")
    targets = []
    for path in args.files:
        targets.append((path, _name_guess(path)))
    with place_cue.store_lock(args.lock if args.write else None):
        return run(targets or default_paths(), args.write)


if __name__ == "__main__":
    sys.exit(main())
