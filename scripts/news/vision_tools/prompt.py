#!/usr/bin/env python3
"""Print the reader's brief for one batch of a first-pass vision read.

Same reason as `reread_tools/prompt.py`: the criteria keep changing, and
hand-editing the brief per batch is how one quietly stops being sent. A
February batch is ~45 batches, so the drift would be invisible.

    python3 scripts/news/vision_tools/prompt.py <slug> <batch-no> [--size N]

Batches are cut off `sheets.json`, the same order `scripts.news.batches`
uses, so the TSV name and the cue range agree with what `ingest` expects.
"""
import glob
import json
import os
import sys
from scripts.errors import PipelineError
from scripts.news import episodes
from scripts.news import paths
from scripts.news import resolve_slug
from scripts.news import sources
from scripts.ocr import sheetsize

# 一批ê大細照「這批會予讀者累積偌濟 context」決定，毋是照張數。
# **這幾个數字是量出來ê，毋是揀ê**（2026-09-11，18 輪實讀、3,367 條
# cue，usage 依回覆ê `message.id` 歸併——逐行加總會高估約 2.5 倍）：
#
#   尖峰累積 context ≈ BASE ＋ 該批視覺 token ＋ 逐逝數 × PER_ROW
#
# 對平行讀ê六輪誤差 −2.1%～+32.7%。快取失效ê線佇 175k–184k（≤175k
# 失效 0 擺；184k 彼輪失效 3 擺、重寫 166,380 token，加付 $1.04）。
# CEILING 訂 120,000，估算最壞 +32.7% 嘛才 ~160k，離彼條線猶有空；
# 訂 140,000 以上，最壞情形就貼佇 175k 頂懸。**看起來真空嘛莫調懸。**
#
# 換模型、換 harness、抑是組合圖ê打包規則改（一張裝幾條 cue 變矣）ê
# 時，這三个數字愛重量。
CEILING = 120000
BASE = 69184
PER_ROW = 17
BRIEF = os.path.join(os.path.dirname(__file__), "brief.md")
# 讀者抽原生格ê影片。mp4 來源ê集數無封存 mkv，愛對 SFTP 抓 mp4 落來，
# 抓來囥 READ_STAGE。使用者裁定 2026-09-15：沒有 mkv 就看 mp4。
# Relative to the checkout, because the brief is read by an agent standing
# in it; both have a month folder under them, like the rest of out/news/.
MKV_DIR = os.path.relpath(paths.MKV_ARCHIVE, paths.ROOT)
READ_STAGE = os.path.relpath(os.path.join(paths.NEWS_OUT, "stage-read"),
                             paths.ROOT)
REMOTE_ROOT = "/docker/ilrdf-corpus"
# `or`, not a `get` default: an exported-but-empty CLAUDE_SCRATCH counts
# as set, and `os.path.join("", name)` then hands the reader a
# relative path that lands wherever it happens to be standing.
SCRATCH = os.environ.get("CLAUDE_SCRATCH") or "/tmp/vision-scratch"


def episode(slug):
    """srt_name for a slug, off the 節目目錄.

    本底讀ê是 `Kari-SRT/news/inventory.json`。彼份檔佇 b787084 提掉矣
    （逐一欄對 `smkul.csv` 推導會出來），`batches.py` 綴leh改用
    `episodes.load()`，這爿無改著：2026-09-12 beh派 2021-01 ê讀者，
    這搭 FileNotFoundError，規个視覺辨識派袂出去。兩爿愛讀仝一份正本。
    """
    for entry in episodes.load():
        if entry["slug"] == slug:
            return entry["srt_name"]
    raise PipelineError("節目目錄內底揣無 slug：%s" % slug)


def remote_of(name):
    """這集ê來源影片，照 `sources` ê規則揀ê彼條（語料根目錄相對路徑）。"""
    for entry in episodes.load():
        if entry["srt_name"] == name:
            path, problem = sources.pick(entry)
            if not path:
                raise PipelineError("%s 揀無來源影片：%s" % (name, problem))
            return resolve_slug.normalise(path)
    raise PipelineError("節目目錄內底揣無：%s" % name)


def video_source(name):
    """(讀者用ê影片路徑, 抓檔ê講法)。有 mkv 就用 mkv，講法是空ê。"""
    month = paths.month_of(name)
    mkv = os.path.join(MKV_DIR, month, name + ".mkv")
    if os.path.exists(mkv):
        return mkv, ""
    remote = remote_of(name)
    folder = os.path.join(READ_STAGE, month)
    local = os.path.join(folder, os.path.basename(remote))
    fetch = ('——這集無封存 mkv，愛先抓 mp4：`mkdir -p %s && [ -f "%s" ] || '
             '{ bash scripts/news/sftp.sh get "%s/%s" "%s.part.$$" && '
             'mv "%s.part.$$" "%s"; }`（檔案已經佇咧就免閣抓，仝一集另外'
             '一批ê讀者可能抓好矣）'
             % (folder, local, REMOTE_ROOT, remote, local, local, local))
    return local, fetch


def estimate(weights):
    """Predicted peak context of one batch whose sheets weigh `weights`."""
    total = BASE
    for weight in weights:
        total += weight
    return total


def _assign(ordered, count):
    """Longest processing time first: heaviest sheet to the lightest batch."""
    loads = [0] * count
    batches = []
    for _ in range(count):
        batches.append([])
    for name, weight in ordered:
        lightest = 0
        for index in range(1, count):
            if loads[index] < loads[lightest]:
                lightest = index
        loads[lightest] += weight
        batches[lightest].append((weight, name))
    return batches, loads


def plan(weights, ceiling=CEILING):
    """Cut sheets into batches: a list of sheet-name lists.

    `weights` is [(sheet name, weight)]. The number of batches is the total
    weight over what one batch can hold after its fixed part; sheets go out
    heaviest first, each to the batch that is lightest so far, so batches
    come out within a few percent of each other (cutting by file name gave
    1.23-1.44 times). If a batch still ends up over the ceiling -- a few
    big sheets bunched together -- one more batch is opened and it is done
    again. No batch is empty.

    Inside a batch the sheets are listed light to heavy: whatever enters
    the context first is paid for again by every later reply, and reading
    the big ones first measured about 10% dearer. That ordering is where
    the saving is; the assignment only buys even batches.

    Ties are broken by name, so the same sheets always give the same
    batches -- `scripts.news.batches` and `brief()` have to agree.
    """
    if not weights:
        return []
    room = max(ceiling - BASE, 1)
    total = 0
    for _name, weight in weights:
        total += weight
    ordered = sorted(weights, key=lambda item: (-item[1], item[0]))
    count = min(max(-(-total // room), 1), len(ordered))
    while True:
        batches, loads = _assign(ordered, count)
        if max(loads) <= room or count >= len(ordered):
            break
        over = 0
        for index, load in enumerate(loads):
            if load > room and len(batches[index]) > 1:
                over += 1
        if not over:
            break
        count += 1
    out = []
    for batch in batches:
        batch.sort()
        names = []
        for _weight, name in batch:
            names.append(name)
        out.append(names)
    return out


def sheet_weights(work, names, sheets=None):
    """[(name, visual tokens + rows × PER_ROW)] off each sheet's PNG header."""
    if sheets is None:
        with open(paths.sheets_index(work), encoding="utf-8") as handle:
            sheets = json.load(handle)
    folder = paths.sheets_dir(work)
    out = []
    for name in names:
        tokens = sheetsize.tokens(os.path.join(folder, name))
        out.append((name, tokens + len(sheets[name]) * PER_ROW))
    return out


def pending_sheets(work):
    """[(name, cues)] of sheets whose cues are not all verified yet."""
    with open(paths.sheets_index(work), encoding="utf-8") as handle:
        sheets = json.load(handle)
    verified = {}
    path = paths.verified_file(work)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as handle:
            verified = json.load(handle)
    out = []
    for name in sorted(sheets):
        todo = []
        for index in sheets[name]:
            if not verified.get(str(index)):
                todo.append(index)
        if todo:
            out.append((name, sheets[name]))
    return out


def batches_of(work):
    """The batches still to read, as sheet-name lists -- the one planner.

    Only unverified sheets are cut: `scripts.news.batches` used to cut
    those while `brief()` cut all of them, so half way through an episode
    the two disagreed about what batch N held.
    """
    names = []
    for name, _cues in pending_sheets(work):
        names.append(name)
    return plan(sheet_weights(work, names))


def _tsv_cues(path):
    cues = set()
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            head = line.split("\t", 1)[0].strip()
            if head.isdigit():
                cues.add(head)
    return cues


def first_number(work, name):
    """The number the next batch's TSV takes: after every one already in.

    "Already in" means every cue in it is verified -- `ingest` has taken
    it. A TSV a reader is still writing (or that waits for its episode's
    other batches) is one of the batches being planned right now, so it
    must not push the numbering on, or the same batch would be told two
    names. Without this, a half-read episode's next batch was told
    `b01.tsv` again and overwrote what Kari-SRT already held.
    """
    verified = {}
    path = paths.verified_file(work)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as handle:
            verified = json.load(handle)
    folder = paths.stage_path(paths.KARI_VISION, name)
    highest = 0
    for one in glob.glob(os.path.join(folder, "b*.tsv")):
        stem = os.path.basename(one)[1:-len(".tsv")]
        if not stem.isdigit():
            continue
        cues = _tsv_cues(one)
        done = True
        for cue in cues:
            if not verified.get(cue):
                done = False
        if cues and done:
            highest = max(highest, int(stem))
    return highest + 1


def tsv_names(work, name, count):
    """`bNN.tsv` for `count` new batches, numbered on from what is in."""
    first = first_number(work, name)
    out = []
    for offset in range(count):
        out.append("b%02d.tsv" % (first + offset))
    return out


def workdir(slug):
    """Where `ocr-cli cues` left the sheets for `slug`, from the checkout."""
    return os.path.relpath(paths.work_dir(slug), paths.ROOT)


def sheets_holding(order, sheets, lo, hi):
    """The sheet names whose cues overlap [lo, hi], and every cue on them.

    A cue range almost never lands on sheet boundaries, and a half sheet is
    no use to a reader: the numbers are printed on the image, so they can
    only report what is in front of them. So the span is widened to whole
    sheets and the brief asks for every cue on them -- reading a few extra
    already-read cues is cheap, and a row missing from the TSV is not.
    """
    names = []
    cues = []
    for name in order:
        on = sheets[name]
        if max(on) < lo or min(on) > hi:
            continue
        names.append(name)
        cues += on
    if not names:
        raise PipelineError("cue %d–%d 無佇任何一張圖條頂懸" % (lo, hi))
    return names, sorted(cues)


def brief_range(slug, lo, hi, tsv=None):
    """The reader brief for one cue range rather than one numbered batch.

    What `rescan_band` leaves behind: a stretch of fresh cues in the middle
    of an episode whose other batches are already read. There is no batch
    number to ask for -- the range is what identifies the work.

    The edge sheets almost always carry cues from *outside* the range, and
    those are already in another TSV. Writing them again makes `ingest`
    refuse the whole episode ("cue 444 appears in both b02.tsv and
    b05.tsv"). 058晚 b05's reader caught that unaided -- luck, not a
    guard -- so the brief now says the range out loud whenever the sheets
    hold more than was asked for.
    """
    def pick(order, sheets):
        return sheets_holding(order, sheets, lo, hi)

    return _brief(slug, pick, tsv or "b99.tsv", asked=(lo, hi))


def brief(slug, which, tsv=None):
    """The whole reader brief for batch `which` (1-based) of `slug`."""
    name = episode(slug)
    work = workdir(slug)
    planned = batches_of(work)
    if which < 1 or which > len(planned):
        raise PipelineError("批 %d 超出範圍（猶未讀ê圖分做 %d 批）"
                            % (which, len(planned)))
    batch = planned[which - 1]
    if tsv is None:
        tsv = tsv_names(work, name, len(planned))[which - 1]

    def pick(order, sheets):
        cues = []
        for key in batch:
            cues += sheets[key]
        return batch, cues

    return _brief(slug, pick, tsv)


def _quoted(names):
    out = []
    for name in names:
        out.append("`%s`" % name)
    return out


def _brief(slug, pick, tsvname, asked=None):
    """Shared body: `pick(order, sheets)` chooses the sheets and their cues."""
    name = episode(slug)
    work = workdir(slug)
    with open(paths.sheets_index(work), encoding="utf-8") as handle:
        sheets = json.load(handle)
    order = sorted(sheets)
    names, cues = pick(order, sheets)
    with open(BRIEF, encoding="utf-8") as handle:
        text = handle.read()
    extra = ""
    if asked and (min(cues) < asked[0] or max(cues) > asked[1]):
        wanted = []
        for cue in cues:
            if asked[0] <= cue <= asked[1]:
                wanted.append(cue)
        extra = ("\n\n**干焦寫 cue %d..%d**（%d 逝）。頭一張佮尾一張圖條"
                 "頂懸有範圍以外ê cue，彼幾條別个 TSV 已經讀過矣——"
                 "閣寫一擺，`ingest` 會講「cue X 佇兩个檔攏有」，"
                 "規集擋落來。"
                 % (asked[0], asked[1], len(wanted)))
        cues = wanted
    # Scratchpad is shared across every agent running at once, so a
    # checkpoint named only for its batch (`b02/part_073.tsv`) gets
    # overwritten by another episode's agent writing the same name over
    # the same cue range -- and it looks completely normal. 057晚 b02
    # lost most of its checkpoints that way.
    scratch = os.path.join(SCRATCH, "%s-%s" % (name, tsvname[:-4]))
    # 「逐張幾條」愛算ê，莫寫死：重切了後ê圖條逐張 3 條，尾張閣較少。
    # 059晚 b09 ê提示寫「逐張 4 條」，讀者去看 `sheets.json` 才無算毋著。
    counts = set()
    for one in names:
        counts.add(len(sheets[one]))
    if len(counts) == 1:
        per = "逐張 %d 條 cue" % counts.pop()
    else:
        per = "上濟 %d 條 cue，有ê張較少" % max(counts)
    video, fetch = video_source(name)
    fill = {"name": name, "work": work, "sheets": len(names), "per": per,
            "scratch": scratch,
            # 逐張列出，毋是「頭一張–尾一張」：分出來ê批佇檔名頂懸
            # 無連紲，照範圍讀會讀著別批ê圖。名寫規个（`t00015200.png`
            # 這款無底線通剖）——讀者beh揣ê就是這个字串。
            "sheet_list": "、".join(_quoted(names)),
            # 時間軸ê路徑愛問 `paths`，莫寫做 `<work>/cues.json`：
            # 切做 `1-cues/`（粗切）佮 `3-refined/`（精修）了後，平ê
            # 彼份無矣，讀者beh抽原生格核對就開無檔——恬恬失敗，無
            # 一个所在會報錯。`cue_keyed` 傳ê是「這个 work dir 實在
            # 有ê彼份」，精修過ê贏粗切ê。
            "cues_json": paths.cue_keyed(work, name)["timeline"],
            "clo": min(cues), "chi": max(cues), "cues": len(cues),
            "tsvname": tsvname,
            "video": video,
            "fetch": fetch,
            "tsv": os.path.join(paths.KARI_VISION,
                                paths.month_of(name), name, tsvname)}
    for key, value in fill.items():
        text = text.replace("{%s}" % key, str(value))
    if extra:
        text = text.replace("一逝都莫少。", "一逝都莫少。" + extra, 1)
    return text


if __name__ == "__main__":
    # 重切了後ê提示：批次號碼無意義矣，講 cue 範圍。
    #     prompt.py <slug> --cues 292-444 --name b05.tsv
    if "--cues" in sys.argv:
        span = sys.argv[sys.argv.index("--cues") + 1]
        first, last = span.split("-")
        pick_tsv = None
        if "--name" in sys.argv:
            pick_tsv = sys.argv[sys.argv.index("--name") + 1]
        print(brief_range(sys.argv[1], int(first), int(last), pick_tsv))
        sys.exit(0)
    tsv = None
    if "--name" in sys.argv:
        tsv = sys.argv[sys.argv.index("--name") + 1]
    print(brief(sys.argv[1], int(sys.argv[2]), tsv))
