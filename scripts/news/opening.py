#!/usr/bin/env python3
"""片頭辨識：20／30／40 秒截圖 → 讀者讀語別牌佮主播 → `片頭辨識.csv`。

    python3 -m scripts.news.opening grab VIDEO WORK
    python3 -m scripts.news.opening grab-remote REMOTE WORK
    python3 -m scripts.news.opening sheet 2024-12
    python3 -m scripts.news.opening ingest READER.tsv

2026-09-23 核對新母帶 24 逝無合輪值規律ê，6 逝ê語別是標毋著ê，攏是
看片頭語別牌才揣著。所以逐集切 cue ê時（影片猶佇磁碟）就截片頭三格，
讀者讀左下角語別牌佮主播自介；語別佮目錄無仝，這集停佇遮、毋讀字。

`grab-remote` 是予已經入庫ê集數補做（2021 年）：本機無影片，整支抓
干焦為三格傷了。mp4 ê索引（moov）佇檔尾，干焦抓頭前解袂開，所以抓
頭 60 MB 佮尾 16 MB，寫入佮伺服器仝大細ê稀疏檔。密碼對 `~/.netrc` 來，
指令內底無。

讀者 TSV 一格一逝：`成果檔名<TAB>秒數<TAB>語別牌<TAB>主播`；語別牌寫
中文族名，看袂著寫 `判不準`；主播看袂著留空。
"""
import argparse
import collections
import csv
import glob
import os
import subprocess
import sys
import urllib.parse

from scripts.errors import PipelineError
from scripts.news import paths

SECONDS = (20, 30, 40)
UNREADABLE = "判不準"
COLUMNS = ("成果檔名", "畫面語別牌", "主播", "與目錄相符", "截圖秒數", "依據")
BASIS = "Claude Vision"

HEAD_BYTES = 60 * 1024 * 1024
TAIL_BYTES = 16 * 1024 * 1024

Report = collections.namedtuple(
    "Report", "written mismatched unreadable new_anchors")


def grab(video, work, threads=2):
    """截 20／30／40 秒三格到 `6-opening/`，回三个檔。"""
    target = paths.opening_dir(work)
    os.makedirs(target, exist_ok=True)
    made = []
    for second in SECONDS:
        out = os.path.join(target, "%d.png" % second)
        cmd = ["ffmpeg", "-v", "error", "-nostdin", "-y",
               "-threads", str(threads), "-ss", str(second), "-i", video,
               "-frames:v", "1", out]
        done = subprocess.run(cmd, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE)
        if done.returncode != 0 or not os.path.exists(out):
            raise PipelineError("片頭截圖失敗：%s 第 %d 秒\n%s"
                                % (video, second,
                                   done.stderr.decode("utf-8", "replace")))
        made.append(out)
    return made


def _host():
    return os.environ.get("SFTP_HOST", "ilrdf-corpus@192.168.35.10").split(
        "@")[-1]


def curl_commands(remote, size):
    """(頭, 尾) 兩條 curl；檔案細到頭一段就包規支ê時，尾是 None。

    帳號密碼攏對 `~/.netrc` 來：網址內底無 `user@`，指令列嘛無密碼。
    """
    url = "sftp://%s%s" % (_host(), urllib.parse.quote(remote))
    if size <= HEAD_BYTES:
        return (["curl", "-s", "--netrc", "-r", "0-%d" % (size - 1), url],
                None)
    head = ["curl", "-s", "--netrc", "-r", "0-%d" % (HEAD_BYTES - 1), url]
    tail = ["curl", "-s", "--netrc", "-r", "%d-" % (size - TAIL_BYTES), url]
    return head, tail


def _curl(cmd):
    done = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if done.returncode != 0:
        raise PipelineError("curl 失敗（%d）：%s" % (done.returncode, cmd[-1]))
    return done.stdout


def sparse_copy(remote, size, target, fetch=_curl):
    """頭尾兩段寫入 `size` 大ê稀疏檔；位元組數對袂著就擋。"""
    head, tail = curl_commands(remote, size)
    parts = [(0, head)]
    if tail is not None:
        parts.append((size - TAIL_BYTES, tail))
    with open(target, "wb") as handle:
        handle.truncate(size)
        for offset, cmd in parts:
            data = fetch(cmd)
            want = (size - offset) if cmd is tail else min(HEAD_BYTES, size)
            if len(data) != want:
                raise PipelineError(
                    "%s：第 %d byte 起愛 %d byte，提著 %d byte"
                    % (remote, offset, want, len(data)))
            handle.seek(offset)
            handle.write(data)
    return target


def remote_size(remote):
    """伺服器頂懸這个檔幾 byte（`sftp.sh ls`；`curl -I` 提袂著）。"""
    folder, name = os.path.split(remote)
    here = os.path.dirname(os.path.abspath(__file__))
    done = subprocess.run([os.path.join(here, "sftp.sh"), "ls", folder],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    for line in _decode(done.stdout).splitlines():
        parts = line.split(None, 8)
        if len(parts) == 9 and parts[8].strip() == name:
            return int(parts[4])
    raise PipelineError("伺服器頂懸無 %s" % remote)


def _decode(raw):
    """sftp 印非 ASCII 檔名用八進位 `\\ooo`，先解轉來。"""
    text = raw.decode("utf-8", "replace")
    out = bytearray()
    index = 0
    while index < len(text):
        if text[index] == "\\" and text[index + 1:index + 4].isdigit():
            out.append(int(text[index + 1:index + 4], 8))
            index += 4
        else:
            out.extend(text[index].encode("utf-8"))
            index += 1
    return out.decode("utf-8", "replace")


def grab_remote(remote, work, stage=None):
    """已入庫ê集數補做：頭尾兩段抓落來截三格，稀疏檔隨刪。"""
    folder = stage or os.path.join(paths.STAGE, "opening")
    os.makedirs(folder, exist_ok=True)
    target = os.path.join(folder, os.path.basename(remote))
    try:
        sparse_copy(remote, remote_size(remote), target)
        return grab(target, work)
    finally:
        if os.path.exists(target):
            os.remove(target)


# ---------------------------------------------------------------- sheets

# 字幕帶、紅條、語別牌攏佇 y 700 以下；棚內「主播 ○○」名條佇 y≈660–720，
# 裁 700 起就賰下緣一截（2021 邵語晨間主播讀袂出），所以提懸到 640。
CROP_TOP = 640
SHEET_SCALE = 2
PER_SHEET = 3
GUTTER = 108
# 成果檔名有中文（時段、族名），DejaVu 無中文字，印出來是方框——讀者
# 就對袂著檔名。先用 Noto CJK，無才退 DejaVu。
LABEL_FONTS = ("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
               "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")


def _font(size):
    from PIL import ImageFont
    for path in LABEL_FONTS:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def sheet(episodes, out_dir):
    """[(成果檔名, [三張截圖])] → Claude Vision 輸入組合圖，回檔名清單。

    逐格干焦留 y 700 以下（字幕帶ê「我是…」、紅條、左下角語別牌），縮
    一半；一集三格上下疊，一張三集。
    """
    # PIL 干焦畫圖才用：`plan_month --opening` 走系統 python3（無 PIL）
    # 嘛會 import 這支。
    from PIL import Image, ImageDraw
    os.makedirs(out_dir, exist_ok=True)
    made = []
    for first in range(0, len(episodes), PER_SHEET):
        group = episodes[first:first + PER_SHEET]
        blocks = []
        for name, frames in group:
            tiles = []
            for path in frames:
                image = Image.open(path).convert("RGB")
                image = image.crop((0, min(CROP_TOP, image.height - 1),
                                    image.width, image.height))
                image = image.resize((image.width // SHEET_SCALE,
                                      max(image.height // SHEET_SCALE, 1)))
                tiles.append((os.path.splitext(os.path.basename(path))[0],
                              image))
            blocks.append((name, tiles))
        width = GUTTER
        height = 0
        for name, tiles in blocks:
            height += 30
            for _second, image in tiles:
                width = max(width, GUTTER + image.width)
                height += image.height + 4
        page = Image.new("RGB", (width, height), (255, 255, 255))
        draw = ImageDraw.Draw(page)
        y = 0
        for name, tiles in blocks:
            draw.text((4, y + 4), name, fill=(0, 0, 0), font=_font(20))
            y += 30
            for second, image in tiles:
                draw.text((8, y + 8), "%s s" % second, fill=(0, 0, 0),
                          font=_font(22))
                page.paste(image, (GUTTER, y))
                y += image.height + 4
        target = os.path.join(out_dir, "opening_%03d.png" % (len(made) + 1))
        page.save(target)
        made.append(target)
    return made


def month_episodes(month, work_root=None):
    """這个月有截片頭、猶未入 `片頭辨識.csv` ê集：[(成果檔名, 三張)]。"""
    from scripts.news import episodes as inventory
    names = {}
    for entry in inventory.load():
        names[entry["slug"]] = entry["srt_name"]
    done = set()
    for row in _read_table(paths.OPENING_STORE):
        done.add(row["成果檔名"])
    base = os.path.join(work_root or paths.WORK, paths.check_month(month))
    out = []
    for work in sorted(glob.glob(os.path.join(base, "*" + paths.WORK_EXT))):
        slug = os.path.basename(work)[:-len(paths.WORK_EXT)]
        name = names.get(slug)
        frames = []
        for second in SECONDS:
            path = os.path.join(paths.opening_dir(work), "%d.png" % second)
            if os.path.exists(path):
                frames.append(path)
        if name and frames and name not in done:
            out.append((name, frames))
    return out


# ---------------------------------------------------------------- ingest


def _read_table(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_table(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, COLUMNS, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _catalogue(path):
    out = {}
    with open(path, encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            out[row["成果檔名"]] = row["族語別(中)"]
    return out


def _normal(name):
    """比主播名用：干焦留字母、數字、漢字，細寫，ʉ 當 u。

    2021-01 讀著ê `Xuzi·Hakaw`、`Ava'e` 佮表上ê `Xuzi Hakaw`、`Ava’e`
    干焦點、撇、空白無仝；讀者嘛有時寫 u 有時寫 ʉ。
    """
    out = []
    for char in name.lower().replace("ʉ", "u"):
        if char.isalnum():
            out.append(char)
    return "".join(out)


def _known_anchors(path):
    """主播.csv 內底ê名：規个名佮用點、空白拆開ê逐節攏算。"""
    known = set()
    if not os.path.exists(path):
        return known
    with open(path, encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            for key in ("主播族語名", "主播漢名"):
                value = (row.get(key) or "").strip()
                if not value:
                    continue
                known.add(_normal(value))
                for part in value.replace("．", " ").replace("·", " ").split():
                    if _normal(part):
                        known.add(_normal(part))
    return known


def known_anchor(who, known):
    """讀者讀著ê主播名敢佇表上（華語字幕「我是倫敦」對漢名ê頭一節）。"""
    return _normal(who) in known


def _read_tsv(path):
    frames = collections.OrderedDict()
    with open(path, encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            line = line.rstrip("\n")
            if not line.strip() or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 3:
                raise PipelineError("%s 第 %d 逝：愛有 成果檔名、秒數、語別牌"
                                    % (path, number))
            while len(parts) < 4:
                parts.append("")
            cells = []
            for part in parts[:4]:
                cells.append(part.strip())
            name, second, badge, anchor = cells
            frames.setdefault(name, []).append((second, badge, anchor))
    return frames


def _summarise(name, frames, listed):
    readable = []
    badges = collections.Counter()
    anchor = ""
    for second, badge, who in frames:
        if badge and badge != UNREADABLE:
            readable.append(second)
            badges[badge] += 1
        if who and who != UNREADABLE and not anchor:
            anchor = who
    if badges:
        seen = badges.most_common(1)[0][0]
        verdict = "是" if seen == listed else "否"
        seconds = "/".join(readable)
    else:
        seen = verdict = UNREADABLE
        shot = []
        for second, _badge, _who in frames:
            shot.append(second)
        seconds = "/".join(shot)
    return {"成果檔名": name, "畫面語別牌": seen, "主播": anchor,
            "與目錄相符": verdict, "截圖秒數": seconds, "依據": BASIS}


def ingest(tsv, table=None, catalogue=None, anchors=None):
    """讀者 TSV → `片頭辨識.csv`（同名覆寫、照成果檔名排），回 Report。"""
    table = table or paths.OPENING_STORE
    listed = _catalogue(catalogue or paths.TRACKER_STORE)
    known = _known_anchors(anchors or paths.ANCHORS_STORE)
    frames = _read_tsv(tsv)
    rows = {}
    for row in _read_table(table):
        rows[row["成果檔名"]] = row
    mismatched, unreadable, new_anchors = [], [], []
    for name, shots in frames.items():
        if name not in listed:
            raise PipelineError("目錄內底無 %s" % name)
        row = _summarise(name, shots, listed[name])
        rows[name] = row
        if row["與目錄相符"] == "否":
            mismatched.append((name, listed[name], row["畫面語別牌"]))
        elif row["與目錄相符"] == UNREADABLE:
            unreadable.append(name)
        if row["主播"] and not known_anchor(row["主播"], known):
            new_anchors.append((name, row["主播"]))
    ordered = []
    for name in sorted(rows):
        ordered.append(rows[name])
    _write_table(table, ordered)
    return Report(len(frames), mismatched, unreadable, new_anchors)


def exit_code(report):
    """語別無仝抑是三格攏讀袂著：1，這幾集袂使往落做。"""
    return 1 if report.mismatched or report.unreadable else 0


def print_report(report):
    print("片頭辨識：寫 %d 集" % report.written)
    for name, listed, seen in report.mismatched:
        print("不符    %s：目錄 %s，畫面 %s" % (name, listed, seen))
    for name in report.unreadable:
        print("判不準  %s：三格攏讀袂著語別牌" % name)
    for name, anchor in report.new_anchors:
        print("新主播  %s：%s（主播.csv 無，請補）" % (name, anchor))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="command", required=True)
    one = sub.add_parser("grab", help="影片佇本機：截三格到 6-opening/")
    one.add_argument("video")
    one.add_argument("work")
    two = sub.add_parser("grab-remote", help="已入庫ê集數：抓頭尾截三格")
    two.add_argument("remote")
    two.add_argument("work")
    three = sub.add_parser("sheet", help="這个月猶未讀ê片頭 → 組合圖")
    three.add_argument("month")
    three.add_argument("--out", default=None)
    four = sub.add_parser("ingest", help="讀者 TSV → 片頭辨識.csv")
    four.add_argument("tsv")
    args = ap.parse_args(argv)
    if args.command == "grab":
        grab(args.video, args.work)
        return 0
    if args.command == "grab-remote":
        grab_remote(args.remote, args.work)
        return 0
    if args.command == "sheet":
        out = args.out or os.path.join(paths.NEWS_OUT, "opening-sheets",
                                       args.month)
        found = month_episodes(args.month)
        made = sheet(found, out)
        for index, target in enumerate(made):
            names = []
            for name, _frames in found[index * PER_SHEET:
                                       (index + 1) * PER_SHEET]:
                names.append(name)
            print("%s\t%s" % (target, " ".join(names)))
        return 0
    report = ingest(args.tsv)
    print_report(report)
    return exit_code(report)


if __name__ == "__main__":
    sys.exit(main())
