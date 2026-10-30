#!/usr/bin/env python3
"""伺服器上ê新聞影片：搬去 `/home/news/mkv/<年-月>/<成果檔名>.mkv`。

    python3 -m scripts.news.video_names                 # 仝 plan：唯讀，毋連伺服器
    python3 -m scripts.news.video_names plan
    python3 -m scripts.news.video_names probe 成果檔名   # 搬一支過去閣搬轉來
    python3 -m scripts.news.video_names apply           # 逐支搬（先寫清單）
    python3 -m scripts.news.video_names check [--manifest 清單]
    python3 -m scripts.news.video_names undo 清單
    python3 -m scripts.news.video_names prune [--execute]   # 最後一步：刪空資料夾
    python3 -m scripts.news.video_names locate 成果檔名  # 路徑<TAB>大小<TAB>來源

影片本底囥佇 `/home/mkv-raw/` 底下 53 个資料夾，檔名是交付時留落來ê，
月份佮播出月份嘛無對。搬去成果檔名ê位置了後，影片、SRT、預覽檔仝名
仝月份，一目了然。搬是 rename（移動），毋是複製：全部約 7 TB，伺服器
干焦賰 5.3 TB。

位置是成果檔名ê純函式（`paths.video_path`），目錄 `smkul.csv` 毋另設欄，
`原始影片檔案位置` 原樣留咧，記交付時ê位置，嘛是新位置揣無ê時ê退路。

怎麼對伺服器下指令由呼叫ê傳入來，測試傳假ê。
"""
import argparse
import collections
import csv
import datetime
import os
import posixpath
import subprocess
import sys

from scripts.errors import PipelineError
from scripts.news import episodes
from scripts.news import name_catalogue
from scripts.news import opening
from scripts.news import paths
from scripts.news import resolve_slug
from scripts.news import sources

MKV_RAW = "/home/mkv-raw/"
SFTP_SCRIPT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "sftp.sh")

Move = collections.namedtuple("Move", "name old new")
Located = collections.namedtuple("Located", "path size source")
Result = collections.namedtuple("Result", "moved skipped problems manifest")

MANIFEST_FIELDS = ["成果檔名", "舊位置", "新位置", "大小"]


def _text(raw):
    """sftp 輸出ê字串；位元組愛先解八進位 `\\ooo`，文字就原樣。"""
    if isinstance(raw, str):
        return raw
    return opening._decode(raw or b"")


class Sftp(object):
    """對真伺服器下指令，一支 `sftp.sh` 一个動作。

    路徑攏是 `sftp.sh` ê獨立引數，伊會擋雙引號、反斜線佮控制字元；撇號
    無要緊（雙引號內底就是普通字元）。`run` 預設是 subprocess.run，測試
    傳假ê。
    """

    def __init__(self, run=None):
        # 呼叫ê時才提 subprocess.run：測試 patch `subprocess.run` 才會生效。
        self._run = run or subprocess.run

    def _call(self, *args):
        done = self._run(["bash", SFTP_SCRIPT] + list(args),
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        text = _text(done.stdout) + "\n" + _text(done.stderr)
        return done.returncode, text

    def stat(self, path):
        """檔案大小；伺服器講「揣無」回 None；其他失敗（逾時、權限）raise。

        `sftp.sh ls` 失敗一律 exit 1，愛看訊息才分會出來。毋是「揣無」
        就毋通當做無這个檔——網路一抖就退去讀原始位置，會讀著過時ê檔。
        """
        code, text = self._call("ls", path)
        if code == 0:
            for line in text.splitlines():
                if line.startswith("-"):
                    return int(line.split(None, 8)[4])
            return None
        if "not found" in text:
            return None
        raise PipelineError("sftp ls %s 失敗（%d）：%s"
                            % (path, code, text.strip()))

    def scan(self, folder):
        """資料夾內底：`({檔名: 大小}, [子資料夾名])`；資料夾無佇咧回 None。

        一个資料夾問一擺就知影內底全部，比逐支問省真濟（3,153 支逐支問，
        光是問就愛個外鐘頭）。其他失敗（逾時、權限）raise，莫當做資料夾無。
        """
        code, text = self._call("ls", folder)
        if code != 0:
            if "not found" in text:
                return None
            raise PipelineError("sftp ls %s 失敗（%d）：%s"
                                % (folder, code, text.strip()))
        files = {}
        dirs = []
        for line in text.splitlines():
            if line.startswith("-"):
                parts = line.split(None, 8)
                files[parts[8].strip()] = int(parts[4])
            elif line.startswith("d"):
                dirs.append(line.split(None, 8)[8].strip())
        return files, dirs

    def listdir(self, folder):
        """`{檔名: 大小}`（毋算子資料夾）；資料夾無佇咧回 None。"""
        found = self.scan(folder)
        return None if found is None else found[0]

    def mkdir(self, path):
        """建一層資料夾；已經有袂算錯（`sftp.sh mkdir` 家己吞）。"""
        code, text = self._call("mkdir", path)
        if code != 0:
            raise PipelineError("sftp mkdir %s 失敗（%d）：%s"
                                % (path, code, text.strip()))

    def rmdir(self, path):
        """刪一个資料夾。毋是空ê，伺服器會拒絕——這个失敗毋吞（`sftp.sh
        rmdir` 無加前導 `-`）。"""
        code, text = self._call("rmdir", path)
        if code != 0:
            raise PipelineError("sftp rmdir %s 失敗（%d）：%s"
                                % (path, code, text.strip()))

    def rename(self, old, new):
        code, text = self._call("rename", old, new)
        if code != 0:
            raise PipelineError("sftp rename %s → %s 失敗（%d）：%s"
                                % (old, new, code, text.strip()))


def plan(rows, excluded, to_path=resolve_slug.server_path):
    """[Move(成果檔名, 舊位置, 新位置)]，目錄逐逝各一組，照目錄ê順序。

    `excluded` 是排除清單ê伺服器路徑（寫法抑是 `home/…`、`/home/…` 攏會
    使，會先換做絕對路徑才比）。**排除ê影片毋動**：規劃內底無伊，目錄
    逝ê來源若佇排除清單，規个規劃停落來。

    下列任一種情形規个規劃拒絕、一支都毋搬——搬一半ê話，後壁ê逝就揣袂
    著檔：兩逝指著仝一个舊位置、兩逝算出仝一个新位置、舊位置毋佇
    `/home/mkv-raw/` 底下（開會了佇 `/docker/…`，其他人唯讀）、舊位置
    空白抑是是分號並列ê候選清單（愛先決定是佗一支，莫臆）。
    """
    barred = set()
    for path in excluded:
        barred.add(to_path(path))
    moves = []
    by_old = {}
    by_new = {}
    for row in rows:
        name = row["成果檔名"]
        cell = (row.get("原始影片檔案位置") or "").strip()
        if not cell:
            raise PipelineError("%s：原始影片檔案位置 空ê，規劃袂出舊位置"
                                % name)
        if ";" in cell:
            raise PipelineError("%s：原始影片檔案位置 是分號並列ê候選清單，"
                                "愛先決定是佗一支：%s" % (name, cell))
        old = to_path(cell)
        if not old.startswith(MKV_RAW):
            raise PipelineError("%s：舊位置 %s 毋佇 %s 底下，這爿毋搬"
                                % (name, old, MKV_RAW))
        if old in barred:
            raise PipelineError("%s：來源 %s 佇排除影片內，毋通搬"
                                % (name, old))
        new = paths.video_path(name)
        if old in by_old:
            raise PipelineError("%s 佮 %s 指著仝一个舊位置 %s"
                                % (by_old[old], name, old))
        if new in by_new:
            raise PipelineError("%s 佮 %s 算出仝一个新位置 %s"
                                % (by_new[new], name, new))
        by_old[old] = name
        by_new[new] = name
        moves.append(Move(name, old, new))
    return moves


def locate(entry, sftp, say=print):
    """這集影片現此時佇伺服器佗位：`Located(路徑, 大小, 來源)`。

    先問正規位置（由成果檔名推導）。**干焦伺服器講「揣無」才退回** `原始
    影片檔案位置`（有幾若條候選就照匯入ê挑檔規則揀一支，毋提第一條）；
    退ê時用 `say` 講「退回原始位置」，袂當恬恬仔讀。兩位攏無就報錯，兩个
    路徑攏指名。連線逾時、權限錯誤這款毋是「揣無」ê失敗，`sftp.stat` 會
    直接 raise，這爿袂去問原始位置。
    """
    name = entry["srt_name"]
    canonical = paths.video_path(name)
    size = sftp.stat(canonical)
    if size is not None:
        return Located(canonical, size, "正規")
    original, problem = sources.pick(entry)
    if not original:
        raise PipelineError(
            "%s：正規位置 %s 揣無，原始影片檔案位置嘛無（%s）"
            % (name, canonical, "空ê" if problem == sources.NO_SOURCE
               else problem))
    original = resolve_slug.server_path(original)
    size = sftp.stat(original)
    if size is None:
        raise PipelineError("%s：正規位置 %s 佮原始位置 %s 攏揣無"
                            % (name, canonical, original))
    say("退回原始位置：%s（正規位置 %s 揣無）" % (original, canonical))
    return Located(original, size, "原始")


def _now():
    """檔名用ê時間：臺灣時間（CLAUDE.md 規定，容器是 UTC）。"""
    zone = datetime.timezone(datetime.timedelta(hours=8))
    return datetime.datetime.now(zone).strftime("%Y%m%d-%H%M%S")


def _states(moves, sftp):
    """逐組ê現況：`done`（新有舊無）、`todo`（舊有新無）、`both`、`neither`。

    一个資料夾問一擺（舊位置 53 个、新位置 48 个），毋是逐支問。
    回 ([(Move, 狀態, 大小)])；大小取有ê彼邊。
    """
    listings = {}

    def listed(folder):
        if folder not in listings:
            found = sftp.listdir(folder)
            listings[folder] = {} if found is None else found
        return listings[folder]

    out = []
    for move in moves:
        old_size = listed(posixpath.dirname(move.old)).get(
            posixpath.basename(move.old))
        new_size = listed(posixpath.dirname(move.new)).get(
            posixpath.basename(move.new))
        if old_size is not None and new_size is not None:
            state, size = "both", old_size
        elif old_size is not None:
            state, size = "todo", old_size
        elif new_size is not None:
            state, size = "done", new_size
        else:
            state, size = "neither", None
        out.append((move, state, size))
    return out


def apply(moves, sftp, manifest_dir, now=None, say=print):
    """逐支搬（rename），先寫清單、後搬；可中斷續跑，絕毋覆寫。

    `Result(moved, skipped, problems, manifest)`。步驟：
    1. 問各資料夾現況。**兩邊攏有**就規个停落來（毋覆寫，一个都毋搬）。
    2. 先寫完整ê清單（`manifest_dir/<時間>.csv`：成果檔名、舊位置、新位置、
       大小）才搬第一支——搬到一半斷掉，清單已經完整，會當還原抑是續跑。
    3. 月份資料夾一層一層建（sftp ê mkdir 毋是遞迴ê），逐个只建一擺。
    4. 逐支 rename。新有舊無＝已經搬矣，跳過；兩邊攏無＝指名，其他照搬。
    搬失敗就直接 raise，已經搬ê留咧，重跑會接落去。
    """
    states = _states(moves, sftp)
    both = []
    for move, state, _size in states:
        if state == "both":
            both.append(move)
    if both:
        names = []
        for move in both:
            names.append("%s（%s ê新舊位置攏有）" % (move.name, move.new))
        raise PipelineError("新舊位置攏有，毋覆寫、一支都毋搬：%s"
                            % "；".join(names))

    os.makedirs(manifest_dir, exist_ok=True)
    manifest = os.path.join(manifest_dir, (now or _now()) + ".csv")
    with open(manifest, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(MANIFEST_FIELDS)
        for move, _state, size in states:
            writer.writerow([move.name, move.old, move.new,
                             "" if size is None else size])

    moved = []
    skipped = []
    problems = []
    made = set()
    for move, state, _size in states:
        if state == "done":
            skipped.append(move.name)
            continue
        if state == "neither":
            problems.append((move.name, "新舊位置攏無：%s／%s"
                             % (move.old, move.new)))
            continue
        for level in paths.video_dirs_to_make(move.name):
            if level not in made:
                sftp.mkdir(level)
                made.add(level)
        sftp.rename(move.old, move.new)
        moved.append(move.name)
        if len(moved) % 100 == 0:
            say("搬了 %d 支" % len(moved))
    return Result(moved, skipped, problems, manifest)


FALLBACK_ROOT = "/home/mkv-raw/news/mkv"
MANIFEST_DIR = os.path.join(paths.NEWS_OUT, "video-rename")


def probe(move, sftp, say=print):
    """搬一支過去再搬回來，確認跨資料夾 rename 會使，才做全部。

    驗證兩件代誌：rename 會使跨資料夾（`/home` 佮 `/home/mkv-raw` 若是
    無仝子卷，會失敗，從 sftp 看袂出來）；撇號佇真伺服器嘛會使（揀含
    撇號ê檔做探針）。
    - 搬過去失敗：停落來、毋做別項，講可能是跨子卷，備案是新樹改囥
      `/home/mkv-raw/news/mkv/`（改 `paths.VIDEO_ROOT`）。
    - 搬過去成功、搬回失敗：明講檔案這馬佇佗位，毋準恬恬。
    """
    size = sftp.stat(move.old)
    if size is None:
        raise PipelineError("探針ê檔無佇咧：%s" % move.old)
    if sftp.stat(move.new) is not None:
        raise PipelineError("探針ê新位置已經有檔，毋搬：%s" % move.new)
    for level in paths.video_dirs_to_make(move.name):
        sftp.mkdir(level)
    try:
        sftp.rename(move.old, move.new)
    except PipelineError as error:
        raise PipelineError(
            "探針搬過去失敗：%s——可能是跨子卷（rename 袂使跨子卷）。備案："
            "新樹改囥 %s（同一个子卷內），改 paths.VIDEO_ROOT 就好"
            % (error, FALLBACK_ROOT))
    if sftp.stat(move.new) != size:
        raise PipelineError("探針搬過去了，新位置ê大小對袂著：%s" % move.new)
    say("探針：已搬去 %s（%d bytes）" % (move.new, size))
    try:
        sftp.rename(move.new, move.old)
    except PipelineError as error:
        raise PipelineError("探針搬回失敗：%s——檔案現在佇 %s，愛家己搬轉去"
                            % (error, move.new))
    if sftp.stat(move.old) != size or sftp.stat(move.new) is not None:
        raise PipelineError("探針搬回了，狀態佮探針進前無仝：%s" % move.old)
    say("探針：已搬轉來 %s，狀態佮進前仝款" % move.old)
    return size


def check(moves, excluded, sftp, sizes=None, to_path=resolve_slug.server_path):
    """對伺服器核對搬移ê結果，回問題清單（空ê就是全部到位）。

    - 新位置恰好是目錄逐集各一支：缺ê逐一指名（成果檔名佮預期位置），
      多出來ê嘛逐一指名；`sizes`（`{成果檔名: 大小}`，清單記ê）有傳就
      逐支比大小。
    - 舊位置（搬移清單內各檔所佇ê資料夾，加排除清單內底佇 `/home/mkv-raw`
      底下ê資料夾）賰ê，愛恰好是排除清單上ê檔：猶佇原位ê搬袂著ê、無佇
      目錄嘛無佇排除清單ê多出來ê，指名。
    排除清單兩款情形毋算問題：（1）路徑毋是佇 `/home/mkv-raw` 底下（有一
    列佇 `/docker/…`，彼个資料夾有幾百个別ê檔，本底攏當做「多出」）；
    （2）清單記ê檔伺服器頂已經無（22 列有 4 列搬進前就無矣，是予人取代ê
    重複檔、分段檔）。搬移本底就毋碰排除ê檔，袂是搬移害ê。
    一个資料夾問一擺，毋是逐支問。
    """
    problems = []
    barred = set()
    for path in excluded:
        absolute = to_path(path)
        if absolute.startswith(MKV_RAW):
            barred.add(absolute)

    expected = {}
    new_folders = []
    for move in moves:
        expected[move.new] = move
        folder = posixpath.dirname(move.new)
        if folder not in new_folders:
            new_folders.append(folder)
    listings = {}
    for folder in new_folders:
        found = sftp.listdir(folder)
        listings[folder] = {} if found is None else found
    for move in moves:
        folder = posixpath.dirname(move.new)
        size = listings[folder].get(posixpath.basename(move.new))
        if size is None:
            problems.append("缺：%s，預期佇 %s" % (move.name, move.new))
        elif sizes is not None and sizes.get(move.name) is not None \
                and size != sizes[move.name]:
            problems.append("大小無仝：%s（%s）伺服器 %d、清單 %d"
                            % (move.name, move.new, size, sizes[move.name]))
    for folder in new_folders:
        for name in sorted(listings[folder]):
            path = folder + "/" + name
            if path not in expected:
                problems.append("新位置多出：%s" % path)

    old_folders = []
    for move in moves:
        folder = posixpath.dirname(move.old)
        if folder not in old_folders:
            old_folders.append(folder)
    for path in sorted(barred):
        folder = posixpath.dirname(path)
        if folder not in old_folders:
            old_folders.append(folder)
    by_old = {}
    for move in moves:
        by_old[move.old] = move
    for folder in old_folders:
        found = sftp.listdir(folder)
        for name in sorted(found or {}):
            path = folder + "/" + name
            if path in by_old:
                problems.append("沒搬：%s 猶佇舊位置 %s"
                                % (by_old[path].name, path))
            elif path not in barred:
                problems.append("舊位置多出：%s（無佇目錄，嘛無佇排除清單）"
                                % path)
    return problems


def _levels(path):
    """`path` 所佇資料夾ê逐層，上層佇頭前：`/a/b/c.mkv` → `/a`、`/a/b`。"""
    parts = posixpath.dirname(path).strip("/").split("/")
    out = []
    for index in range(len(parts)):
        out.append("/" + "/".join(parts[:index + 1]))
    return out


def undo(manifest, sftp, say=print):
    """依搬移清單反向搬（新位置 → 舊位置）；`Result(moved, skipped, problems, manifest)`。

    舊位置若已經被佔用（舊有新也有）：彼一組拒絕、指名、毋覆寫，其他
    照搬。舊有新無＝已經還原，跳過；兩邊攏無＝指名。舊資料夾若已經清掉
    （`prune` 了後），會一層一層重建。
    """
    with open(manifest, encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    moves = []
    for row in rows:
        moves.append(Move(row["成果檔名"], row["舊位置"], row["新位置"]))
    moved = []
    skipped = []
    problems = []
    made = set()
    for move, state, _size in _states(moves, sftp):
        if state == "both":
            problems.append((move.name, "舊位置已經有檔，毋覆寫：%s" % move.old))
            continue
        if state == "neither":
            problems.append((move.name, "新舊位置攏無：%s／%s"
                             % (move.old, move.new)))
            continue
        if state == "done":
            for level in _levels(move.old):
                if level not in made:
                    sftp.mkdir(level)
                    made.add(level)
            sftp.rename(move.new, move.old)
            moved.append(move.name)
        else:
            skipped.append(move.name)
    return Result(moved, skipped, problems, manifest)


Renamed = collections.namedtuple("Renamed", "old new source")


def rename_episode(entry, new_name, sftp, say=print):
    """改成果檔名ê時，伺服器頂ê影片綴咧搬去新名稱ê正規位置。

    現在佇佗位用 `locate` 揣：舊名稱ê正規位置有檔就對遐搬；無，原始位置
    有，表示這集猶無搬進正式位置，就對原始位置直接搬去新名稱ê正規位置；
    兩位攏無就拒絕（`locate` 報錯，兩个路徑攏指名），**袂只改本機**，
    害目錄佮伺服器分家。新位置已經有檔也拒絕，毋覆寫。月份若無仝（改
    日期跨月），月份資料夾會先建。
    回 `Renamed(舊, 新, 來源)`；本機後壁ê步驟若失敗，`rename_back` 試著
    搬轉去。
    """
    located = locate(entry, sftp, say=say)
    target = paths.video_path(new_name)
    if located.path == target:
        return Renamed(located.path, target, located.source)
    if sftp.stat(target) is not None:
        raise PipelineError("新名稱ê位置已經有檔，毋搬：%s" % target)
    for level in paths.video_dirs_to_make(new_name):
        sftp.mkdir(level)
    sftp.rename(located.path, target)
    say("影片已搬：%s → %s" % (located.path, target))
    return Renamed(located.path, target, located.source)


def rename_back(renamed, sftp, say=print):
    """`rename_episode` ê反向：搬轉去原本ê位置（舊資料夾若無，一層一層重建）。

    搬袂轉去就 raise，訊息明講影片這馬佇佗——毋準恬恬。
    """
    try:
        for level in _levels(renamed.old):
            sftp.mkdir(level)
        sftp.rename(renamed.new, renamed.old)
    except PipelineError as error:
        raise PipelineError("影片搬袂轉去：%s——影片這馬佇 %s，原本佇 %s"
                            % (error, renamed.new, renamed.old))
    say("影片已搬轉去：%s" % renamed.old)


def prune(moves, sftp, execute=False, say=print):
    """最後一步：清掉搬空ê舊資料夾，**干焦刪空ê**；回（會）刪ê資料夾。

    範圍：搬移清單內各檔舊位置所佇ê資料夾，加伊佇 `/home/mkv-raw/` 底下
    ê上層；由深到淺處理（子資料夾刪了，上層才有可能空），**永遠毋刪
    `/home/mkv-raw` 本身**。含排除檔ê資料夾自然毋是空ê，留咧。
    預設（`execute=False`）干焦列出，毋送 `rmdir`。雙重保險：先列內容
    確認空ê才刪，刪ê指令若失敗（資料夾其實有檔）就停落來指名，毋吞。
    空ê判斷看伺服器實際內容，毋靠排除清單。
    """
    folders = set()
    for move in moves:
        for level in _levels(move.old):
            if level.startswith(MKV_RAW):
                folders.add(level)
    ordered = sorted(folders, key=lambda path: (-path.count("/"), path))
    removed = set()
    out = []
    for folder in ordered:
        found = sftp.scan(folder)
        if found is None:
            continue
        files, subdirs = found
        remaining = []
        for name in subdirs:
            if folder + "/" + name not in removed:
                remaining.append(name)
        if files or remaining:
            continue
        if execute:
            try:
                sftp.rmdir(folder)
            except PipelineError as error:
                raise PipelineError("刪資料夾失敗，停落來：%s（%s）"
                                    % (folder, error))
            say("已刪：%s" % folder)
        removed.add(folder)
        out.append(folder)
    return out


def excluded_paths(path=None):
    """排除影片.csv 內底ê伺服器路徑；無彼份表就是空ê。"""
    source = path or paths.EXCLUDED_STORE
    if not os.path.exists(source):
        return []
    with open(source, encoding="utf-8-sig", newline="") as handle:
        out = []
        for row in csv.DictReader(handle):
            out.append(row["伺服器路徑"])
    return out


def newest_manifest(folder):
    """清單資料夾內底上新ê一份（檔名是時間）；無就是 None。"""
    if not os.path.isdir(folder):
        return None
    names = []
    for name in sorted(os.listdir(folder)):
        if name.endswith(".csv"):
            names.append(name)
    return os.path.join(folder, names[-1]) if names else None


def manifest_sizes(manifest):
    """`{成果檔名: 大小}`，清單內底記ê搬進前ê大小。"""
    out = {}
    with open(manifest, encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["大小"] != "":
                out[row["成果檔名"]] = int(row["大小"])
    return out


def _parser():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="command")
    sub.add_parser("plan", help="唯讀規劃（預設）")
    one = sub.add_parser("probe", help="搬一支過去閣搬轉來")
    one.add_argument("name", help="成果檔名")
    sub.add_parser("apply", help="逐支搬")
    one = sub.add_parser("check", help="對伺服器核對")
    one.add_argument("--manifest", help="清單；無指定用上新ê")
    one = sub.add_parser("undo", help="依清單反向搬")
    one.add_argument("manifest")
    one = sub.add_parser("prune", help="刪搬空ê舊資料夾（預設干焦列出）")
    one.add_argument("--execute", action="store_true", help="真正刪")
    one = sub.add_parser("locate", help="揣這集影片現此時佇佗")
    one.add_argument("name", help="成果檔名")
    return ap


def main(argv=None, sftp_factory=Sftp, catalogue=None, excluded_path=None,
         manifest_dir=None, out=None, err=None):
    """指令列。無子指令＝規劃，唯讀、毋連伺服器；`apply` 愛明講。

    `sftp_factory`、目錄、排除清單、清單資料夾攏會當傳入來（測試用）。
    離開碼：0 成功；1 有問題（搬無完、核對無過、揣無影片）；2 用法毋著
    抑是指名ê成果檔名目錄內底無。
    """
    out = out or sys.stdout
    err = err or sys.stderr
    args = _parser().parse_args(argv)
    command = args.command or "plan"
    folder = manifest_dir or MANIFEST_DIR

    def say(line):
        print(line, file=out)

    try:
        rows, _head = name_catalogue.read(catalogue)
        moves = plan(rows, excluded_paths(excluded_path))
        if command == "plan":
            months = set()
            for move in moves:
                months.add(posixpath.dirname(move.new))
            say("%d 組、%d 個月份資料夾、排除清單 %d 列（唯讀，無連伺服器）"
                % (len(moves), len(months),
                   len(excluded_paths(excluded_path))))
            for move in moves[:3]:
                say("%s\t%s → %s" % (move.name, move.old, move.new))
            return 0
        if command == "locate":
            return _locate(args.name, catalogue, sftp_factory, out, err)
        if command == "undo":
            result = undo(args.manifest, sftp_factory(), say=say)
            return _report(result, out, err)
        if command == "probe":
            chosen = None
            for move in moves:
                if move.name == args.name:
                    chosen = move
            if chosen is None:
                print("目錄內底無這集：%s" % args.name, file=err)
                return 2
            probe(chosen, sftp_factory(), say=say)
            return 0
        if command == "apply":
            result = apply(moves, sftp_factory(), folder, say=say)
            return _report(result, out, err)
        if command == "prune":
            done = prune(moves, sftp_factory(), execute=args.execute,
                         say=say)
            hint = "" if args.execute else "（加 --execute 才真正刪）"
            verb = "已刪" if args.execute else "會刪"
            say("%s %d 个資料夾%s" % (verb, len(done), hint))
            for path in done:
                say(path)
            return 0
        manifest = args.manifest or newest_manifest(folder)
        sizes = manifest_sizes(manifest) if manifest else None
        problems = check(moves, excluded_paths(excluded_path),
                         sftp_factory(), sizes=sizes)
        for line in problems:
            say(line)
        verdict = "通過" if not problems else "有問題"
        say("核對%s（%d 个問題）" % (verdict, len(problems)))
        return 1 if problems else 0
    except PipelineError as error:
        print(str(error), file=err)
        return 1


def _report(result, out, err):
    print("搬 %d、跳過 %d、問題 %d；清單 %s"
          % (len(result.moved), len(result.skipped), len(result.problems),
             result.manifest), file=out)
    for name, why in result.problems:
        print("%s：%s" % (name, why), file=err)
    return 1 if result.problems else 0


def _locate(name, catalogue, sftp_factory, out, err):
    found = None
    for entry in episodes.load(catalogue, srt_dir=set()):
        if entry["srt_name"] == name:
            found = entry
    if found is None:
        print("目錄內底無這集：%s" % name, file=err)
        return 2

    def say(line):
        print(line, file=err)

    got = locate(found, sftp_factory(), say=say)
    print("%s\t%d\t%s" % (got.path, got.size, got.source), file=out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
