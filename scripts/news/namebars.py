#!/usr/bin/env python3
"""受訪者名條 → 段落表「受訪者語言別代號」。

    python3 -m scripts.news.namebars grab <work> <影片>   # 名條截圖、分組
    #   → 讀者讀 8-namebars/ 逐組頭一張，寫 `<秒><TAB><族名>`
    python3 -m scripts.news.namebars apply <work> <讀者 TSV>

單元語別看語別牌，是這集ê族；受訪者毋一定是——邵語那集ê受訪者名條
標 Cou、排灣那集標 Atayal。講ê可能是別族語抑是華語，所以另外標（使用
者裁定 2026-09-24）。

2024-08 起ê版型：受訪者名條是純紅（`shots` 逐秒量ê `name` 比例），右爿
黃字「莊良賢(pasuya) Cou」，族名是節目目錄ê英文拼法（`scripts/languages`）。
逐擺名條出現截一格、干焦裁名條右爿；仝一个人講幾若擺就出現幾若擺，
黃字ê形相仝ê歸做一組，一組讀一擺。
"""
import argparse
import json
import os
import sys

import numpy as np

from scripts import languages
from scripts.errors import PipelineError
from scripts.news import paths
from scripts.news import segments

# 規條紅色名條到畫面正爿邊：2024-08 起ê版型，1920×1080。本底干焦裁 x 900 起，名條
# 短ê時族名頭前半截落佇 900 左爿，讀者干焦看著「an」「mis」。
REGION = (350, 938, 1570, 84)
SAME = 0.85          # 黃字遮罩 Jaccard 超過這个算仝一張名條
# 名條外號佮播出端錯字 → 節目目錄ê拼法（名條實際印過ê）。
ALIASES = {
    "Tao": "Yami", "Yami(Tao)": "Yami", "Yami/Tao": "Yami",
    "tao": "Yami",                       # 2022-08 b105-s060「Yami/tao」小寫
    "Paiwna": "Paiwan",                  # 2022-08 b105-s040，wa 顛倒
    "Apaci": "Apache",                   # 2022-08 b105-s084 Littlefeather
    "Ruaki": "Rukai",                    # 2024-12-08 午間伍麗華等 4 人
    "Pinuyummayan": "Pinuyumayan",       # 2024-12-08 晚間陳瑩
    "Aims": "Amis",                      # 2024-12-23 午間舒米·如妮
    "Pikangcu": "Bigambul",              # 畢甘布（Pikambul）轉寫走樣
    "Silaya": "Siraya",
    "Silaiya": "Siraya",                 # 2023-06-10 晨間楊振綸
    "Makataw": "Makatao", "Makatau": "Makatao",
    "Kanakanvu": "Kanakanavu",           # 2021-11-04 晚間 217 秒
    "Seeidq": "Seediq",                  # 2021-11 Walis Pawan
    "Seetiq": "Seediq",                  # 2022-01 2537 秒
    "Bunu": "Bunun",                     # 2023-06-23 午間 342 秒
    "Tawkase": "Taokas", "Taukat": "Taokas",   # 道卡斯，劉新苗
    "Maori": "Māori",
    "Pacay": "Pazeh",                    # 2023-07 潘英傑
    "Pacaicu": "Pazeh",                  # 2023-09-23 午間愛蘭教會，巴宰族語自稱
    "Bazii": "Pazeh",                    # 2023-06-10 晨間潘英傑
    "Maulii": "Māori",                   # 2023-09 毛利族語拼法
    "Paipulacu": "拍瀑拉",               # 2023-10 拍瀑拉族羅馬字
    "Tenetehara": "Tembé",               # 2023-10 巴西 Tembé 別稱
    "kahabu": "Kaxabu",                  # 2023-07 潘正浩，小寫
    "Kahabu": "Kaxabu",                  # 2023-07 黃子豪等 3 人
    "Dawulong": "Taivoan",               # 大武壠音譯，2023-08-10 小林 3 人
    "Paiwang": "Paiwan",                 # 2023-08-24 午間蔡靜婷
    "Paywang": "Paiwan",                 # 2023-11 第 68 批 s091
    "Rukay": "Rukai",                    # 2023-11 第 68 批 s090
    "Tao/Yami": "Yami",                  # 2023-11 第 68 批 s092
    "Makadaw": "Makatao",                # 2023-11 潘信州，馬卡道
    "kebalan": "Kavalan", "Kebalan": "Kavalan",   # 噶瑪蘭自稱，2023-07 小寫
    "Aatayal": "Atayal",                 # 2023-12 第 69 批 s082
    "Paiawn": "Paiwan",                  # 2023-12 第 69 批 s103
    "Paypula": "拍瀑拉",                 # 2023-12 潘明燈
    "Taukas": "Taokas",                  # 2023-12 王商益，道卡斯
    "Seejiq": "Seediq",                  # 2023-12 賽德克自稱
    "Seejiq Truku": "Seediq",            # 2023-12 Awi Walis，一人一族名
    "Aymara cuku": "Aymara",             # 2024-02 第 70 批，cuku＝卡語「族」
    "Puyuma": "Pinuyumayan",             # 2024-03 第 71 批林志興、潘調志
    "Ta'urung": "Taivoan",               # 2024-03 李文瑞，仝人另一條「大武壠族」
    "makataw": "Makatao",                # 2024-03 潘玉燕，小寫
    "Rukau": "Rukai",                    # 2022-10 第 107 批 s005
    "羅姆人": "羅姆",                    # 2022-10 第 107 批 s057 Erika Varga
    "Kehau": "Kaxabu",                   # 2022-11 第 108 批 s027 噶哈巫 4 人
    "因紐特族": "因紐特",                # 2022-11 第 108 批 s046 Rex Holwell
    "Kaha'u": "Kaxabu",                  # 2022-12 第 109 批 s037 潘仁和
    "Sicangu Lakota": "Lakota",          # 2022-12 第 109 批 s082 Katrina Fuller
    "Mawri": "Māori",                    # 2024-05 第 73 批 s103
    "Paipura": "拍瀑拉",                 # 2024-05 白俊忠
    "Piawan": "Paiwan",                  # 2024-04 達比烏蘭·古勒勒
    "SaySiyta": "SaySiyat",              # 2024-05 第 73 批 s008
    "Sámi": "Sami",                      # 2024-05 Mariela Idivuoma
    "Taulong": "Taivoan",                # 2024-05 楊山樟，大武壠
    "嘎哈巫族": "Kaxabu", "嘎哈巫": "Kaxabu",   # 2024-07 第 75 批 s013
    "Daukas": "Taokas",                  # 2024-07 劉新苗、劉秋雲，道卡斯
    "Kwukasu": "Taokas",                 # 2024-07 仝兩人，頂排印 Twukasu
    "Eastern Kuku Yalanji": "Kuku Yalanji",   # 2021-12 第 76 批 s016
    "Ivatan族": "Ivatan",                 # 2024-08 第 78 批 s027
    "Taulun": "Taivoan",                 # 2024-08 小林村王民亮，仝人別條「大武壠族」
    "Ta`ulung": "Taivoan",               # 2024-08-10 晨間，反引號
    "Tgdaya": "Seediq",                  # 2024-08 郭明正，德固達雅語群
    "Paiwn": "Paiwan",                   # 2024-08 第 78 批 s026
    "Pinuyunayan": "Pinuyumayan",        # 2024-08 陳豪毅
    "Thao": "Thau",                      # 2024-08 高淑真，仝人別條 Thau
    "Papura": "拍瀑拉",                  # 2024-08 羅義惇「klgan Papura」
    "Ruki": "Rukai",                     # 2024-09 柯浩軒，仝人別條 Rukai
    "Kahau": "Kaxabu",                   # 2024-09「Kahau(噶哈巫族)」
    "Dawkas": "Taokas",                  # 2024-09-26 張壽琴、王商益，道卡斯
    "Buryatia": "Buryat",                # 2024-01-10 晚間，名條印地名
    "Pwaiwan": "Paiwan",                 # 2024-01-20 午間陳偉哲，拍毋著
    "Piikani cu": "Piikani",             # 2024-01-06 午間 Lowell Yellowhorn
    "Sakilaya": "Sakizaya",              # 2024-10-20 晚間「Sakilaya(撒奇萊雅族)」
    "Papula": "拍瀑拉",                  # 2024-10-23 晚間 3 人
    "Kaitakorangcu": "凱達格蘭",         # 2024-11-16 午間潘正育
    "Kaitakʉran": "凱達格蘭",            # 2024-11-24 午間，ʉ
    "Metis": "Métis",                    # 2024-11-05 午間，無重音符
    "Gullah Geechee": "Gullah",          # 2021-12-17 晚間 3 人，族名有空白
    "Samoya": "薩摩亞",                  # 2022-01-05 晚間 b85-s009
    "Paiwani": "Paiwan",                 # 2022-01-16 晨間 b87-s005 白惠蘭
    "paypolacu": "拍瀑拉",               # 2022-01-22 午間 b88-s006 白俊忠
    "Rukia": "Rukai",                    # 2022-06-08 午間 b100-s006 陳小姐
    "Pacai": "Pazeh",                    # 2022-06-26 午間 b100-s065 平埔專題 3 人
    "SaySiyal": "SaySiyat",              # 2022-06-26 晚間 b100-s066，t 印做 l
    "SaySiat": "SaySiyat",               # 2022-07 b102-s001，掉一个 y
    "Naabeehó": "Navajo",                # 2022-07 b103-s019，Navajo 族語自稱
    "Kevalan": "Kavalan",                # 2022-01-25 午間 b90-s013 潘靜英
    "Bunum": "Bunun",                    # 2022-01-30 晚間 b90-s033 田春梅
    "大滿族": "Taivoan",                 # 大武壠別稱，2024-06 潘資洲「大滿族」
    "Ta'urong": "Taivoan",               # 2022-03 第 94 批王民亮，仝人別條「Taulun」
    "Paiwa": "Paiwan",                   # 2022-02 第 93 批 giyu(郭復明)，播出端漏 n
    "Pinuyumayyan": "Pinuyumayan",       # 2022-03 第 94 批洪志彰、呂蓓蒂，雙 y
    "SaySyat": "SaySiyat",               # 2022-03 第 94 批 b94-s062，漏 i
    "Kvalan": "Kavalan",                 # 2022-04 第 95 批 b95-s007，漏 a
    "Pajay": "巴宰",                     # 2022-04-28 午間愛蘭教會，巴宰音譯
    "Pajiay": "巴宰",                    # 仝彼則 b95-s085，閣拼一款
    "Paiouia": "拍瀑拉",                 # 2022-04 b95-s017 白俊忠，96 批印拍瀑拉族
    "Rapa Nui": "Rapanui",               # 2022-05 b96-s015 Veronica Tuqui，有空白
}


def appearances(name, threshold=segments.NAME_BAR):
    """逐擺名條出現，揀一秒來截：出現彼段ê中央。

    有ê名條一字一字淡入，族名要幾若秒才出現；本底截「出現了後 1 秒」，
    2024-12 頭 20 集 754 張內底 14 張族名猶未出來。
    """
    on = np.asarray(name) >= threshold
    out = []
    start = None
    for index in range(len(on) + 1):
        lit = index < len(on) and bool(on[index])
        if lit and start is None:
            start = index
        elif not lit and start is not None:
            out.append(start + (index - start) // 2)
            start = None
    return out


SHORT = 5            # 名條 run 短過這幾秒，加截後壁兩格

# 名條ê版型綴 preset：2024-08 起黃字純紅條（`shots` ê `name` 特徵）；
# 進前是白字，上排細字職稱、下排置中人名＋族名，愛家己掃。
STYLES = {"titv-news-2024-08": "new", "titv-news-848": "old",
          "titv-news": "old"}

# 舊版型：掃 y 840–1020 規闊；逐秒三个數（20211101_305 晚間量ê）。
OLD_SCAN = (840, 180)
OLD_TITLE_ROWS = (20, 60)        # y 860–900 職稱細字
OLD_NAME_ROWS = (90, 160)        # y 930–1000 人名＋族名
OLD_RED_ROWS = (70, 90)          # y 910–930 兩排中央ê紅
OLD_COLS = (400, 1700)
OLD_TITLE_MIN = 1000             # 名條 2100–2800，標題 0
OLD_NAME_SPAN = (1000, 25000)    # 名條 1 萬–1.3 萬，大字標題 3.5 萬
OLD_RED_MIN = 0.3                # 紅條 0.41，亮背景 0
OLD_REGION = (392, 850, 1528, 170)   # 天氣框右緣 391 起，包兩排


def style_for(preset):
    return STYLES.get(preset)


def old_tries(title, name, red):
    """舊版型：職稱排有字、人名排有字毋是大字標題、紅條佇咧。"""
    title = np.asarray(title)
    name = np.asarray(name)
    red = np.asarray(red)
    on = ((red > OLD_RED_MIN) & (title > OLD_TITLE_MIN)
          & (name > OLD_NAME_SPAN[0]) & (name < OLD_NAME_SPAN[1]))
    return _tries(on)


def tries(name, threshold=segments.NAME_BAR):
    """逐擺名條出現愛截ê秒數：長ê截中央；短ê中央加出現後第 2、4 秒。

    `name` 特徵比名條本身早落（12-02 午間 111 秒只算一秒，畫面上名條
    猶佇到 114 秒，族名 112 秒才淡入完成），短 run ê中央傷早。
    """
    return _tries(np.asarray(name) >= threshold)


def _tries(on):
    out = []
    start = None
    for index in range(len(on) + 1):
        lit = index < len(on) and bool(on[index])
        if lit and start is None:
            start = index
        elif not lit and start is not None:
            middle = start + (index - start) // 2
            if index - start >= SHORT:
                out.append([middle])
            else:
                seconds = [middle]
                for later in (start + 2, start + 4):
                    if later < len(on) and later not in seconds:
                        seconds.append(later)
                out.append(seconds)
            start = None
    return out


def fullest(crops, mask=None):
    """幾張仝一擺名條ê截圖，揀字上濟彼張（族名淡入完成）。"""
    mask = mask or yellow
    best, most = 0, -1
    for index, rgb in enumerate(crops):
        count = int(mask(rgb).sum())
        if count > most:
            best, most = index, count
    return best


def yellow(rgb):
    rgb = np.asarray(rgb).astype(np.int16)
    return (rgb[..., 0] > 180) & (rgb[..., 1] > 150) & (rgb[..., 2] < 110)


def white(rgb):
    return np.asarray(rgb).min(axis=-1) > 200


def group(crops, mask=None):
    """逐張名條歸組：黃字遮罩佮頭前某一組相仝就歸伊，無就開新組。

    回傳逐張ê組號（組號＝彼組頭一張ê位置）。無黃字ê袂佮別張黏做伙。
    """
    mask_of = mask or yellow
    masks = []
    out = []
    for index, rgb in enumerate(crops):
        mask = mask_of(rgb)
        found = index
        if mask.any():
            for other, seen in masks:
                union = np.logical_or(mask, seen).sum()
                if union and np.logical_and(mask, seen).sum() / union >= SAME:
                    found = other
                    break
            if found == index:
                masks.append((index, mask))
        out.append(found)
    return out


def code_of(word):
    """名條頂懸ê族名（英文拼法抑是中文）→ 語言別代號；無族名回空。"""
    word = word.strip()
    if not word:
        return ""
    # 名條ê寫法：「布農族」「Thau(邵族)」「Silaya(西拉雅族)」「Yami(達悟)族」。
    if word.endswith(")族"):
        word = word[:-1]
    forms = [ALIASES.get(word, word)]
    if word.endswith(")") and "(" in word:
        outer, inner = word[:-1].split("(", 1)
        forms = [ALIASES.get(outer, outer), inner]
    for form in forms:
        form = form.strip()
        if form.endswith("族"):
            form = form[:-1]
        code = _lookup(form)
        if code:
            return code
    raise PipelineError("名條族名 %r 對無語言別代號（scripts/languages.py"
                        " ê LANGUAGES、OTHER_GROUPS）"
                        % word)


def _lookup(word):
    tables = (languages.LANGUAGES, languages.OTHER_GROUPS)
    for table in tables:
        for chinese, (english, code) in table.items():
            if word in (chinese, english) or word.lower() == english.lower():
                if code != "und":
                    return code
    return ""


def codes_of(answer):
    """讀者答案（VS 名條兩人就兩个族名，空白隔開）→ 代號清單。

    族名本身有空白（「Wakka Wakka」）就先整个查，查無才切做兩人。
    """
    whole = answer.strip()
    if " " in whole and _lookup(ALIASES.get(whole, whole)):
        return [_lookup(ALIASES.get(whole, whole))]
    out = []
    # 「Pinuyumayan/Amis」：一人兩族用斜線隔開。
    for word in answer.replace("/", " ").split():
        code = code_of(word)
        if code and code not in out:
            out.append(code)
    return out


def assign(rows, seen):
    """{秒: 代號} → 逐段填受訪者欄；查過無名條ê段寫「無」。"""
    out = []
    for row in rows:
        row = dict(row)
        lo, hi = float(row["起秒"]), float(row["迄秒"])
        codes = []
        for second in sorted(seen):
            if not lo <= second < hi:
                continue
            for code in seen[second].split():
                if code not in codes:
                    codes.append(code)
        row[segments.INTERVIEWEE] = " ".join(codes) or segments.NONE_SEEN
        # 講族語抑是華語，名條看袂出來：先標未定，後壁用華語 ASR 判。
        row[segments.SPEECH] = segments.UNSURE if codes else segments.NONE_SEEN
        out.append(row)
    return out


# ------------------------------------------------------------ I/O


def folder(work):
    return os.path.join(work, "8-namebars")


def _frames(stream, size):
    """Pipe 一格一格讀出來；無夠一格就結束。"""
    while True:
        chunk = stream.read(size)
        if len(chunk) < size:
            return
        yield chunk


def scan_old(video, threads=2):
    """舊版型逐秒（職稱字量, 人名字量, 紅條比例）。

    一格一格讀、算了就放掉：本底規支讀入記憶體（一集 3 GB 原始資料，
    閣轉 int16），切 cue 六集同齊走，2026-09-25 早起食了記憶體、VS Code
    予 OOM 刣。`threads` 照 fetch_sftp.sh ê慣例：6 集同齊走。
    """
    import subprocess
    top, height = OLD_SCAN
    cmd = ["ffmpeg", "-v", "error", "-nostdin", "-threads", str(threads),
           "-i", video, "-vf",
           "fps=1,crop=1920:%d:0:%d" % (height, top),
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    lo, hi = OLD_COLS
    titles, names, reds = [], [], []
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    try:
        for chunk in _frames(proc.stdout, 1920 * height * 3):
            frame = np.frombuffer(chunk, np.uint8).reshape(height, 1920, 3)
            frame = frame[:, lo:hi].astype(np.int16)
            bright = frame.min(axis=-1) > 200
            red = ((frame[..., 0] > 110)
                   & (frame[..., 0] - frame[..., 1] > 60)
                   & (frame[..., 0] - frame[..., 2] > 50))
            rows = OLD_TITLE_ROWS
            titles.append(int(bright[rows[0]:rows[1]].sum()))
            rows = OLD_NAME_ROWS
            names.append(int(bright[rows[0]:rows[1]].sum()))
            rows = OLD_RED_ROWS
            reds.append(float(red[rows[0]:rows[1]].mean()))
    finally:
        proc.stdout.close()
        if proc.wait() != 0:
            raise PipelineError("名條掃描讀影片失敗：%s" % video)
    return np.array(titles), np.array(names), np.array(reds)


def grab(work, video, style="new"):
    """名條逐擺截、裁、短ê揀字上濟彼格、歸組；寫 `index.json`。"""
    from PIL import Image
    from scripts.news import shots
    if style == "old":
        runs = old_tries(*scan_old(video))
        region, mask = OLD_REGION, white
    else:
        runs = tries(shots.load(work)["name"])
        region, mask = REGION, yellow
    wanted = []
    for seconds in runs:
        for second in seconds:
            wanted.append(second)
    out = folder(work)
    frames = os.path.join(out, "frames")
    os.makedirs(out, exist_ok=True)
    shots.grab(video, wanted, frames)
    x, y, w, h = region
    seconds = []
    crops = []
    for candidates in runs:
        parts = []
        for second in candidates:
            with Image.open(os.path.join(frames, "%05d.png" % second)) as im:
                parts.append(im.convert("RGB").crop((x, y, x + w, y + h)))
        pick = fullest(parts, mask)
        parts[pick].save(os.path.join(out, "%05d.png" % candidates[pick]))
        seconds.append(candidates[pick])
        crops.append(np.asarray(parts[pick]))
    for second in set(wanted):
        os.remove(os.path.join(frames, "%05d.png" % second))
    if os.path.isdir(frames):
        os.rmdir(frames)
    groups = group(crops, mask)
    index = {}
    for position, second in enumerate(seconds):
        index[str(second)] = seconds[groups[position]]
    with open(os.path.join(out, "index.json"), "w", encoding="utf-8") as fh:
        json.dump(index, fh, ensure_ascii=False, indent=2, sort_keys=True)
    print("%s：名條 %d 擺、%d 組"
          % (os.path.basename(work), len(seconds), len(set(index.values()))))
    return index


def read_index(work):
    path = os.path.join(folder(work), "index.json")
    with open(path, encoding="utf-8") as fh:
        index = json.load(fh)
    out = {}
    for second, lead in index.items():
        out[int(second)] = int(lead)
    return out


def leaders(work):
    return sorted(set(read_index(work).values()))


def read_answers(path):
    """讀者 TSV：`<秒><TAB><名條頂懸ê族名>`（無族名第二欄留空）。"""
    out = {}
    with open(path, encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            line = line.rstrip("\n")
            if not line.strip() or line.startswith("#"):
                continue
            parts = line.split("\t")
            if not parts[0].strip().isdigit():
                raise PipelineError("%s 第 %d 逝：頭一欄愛是秒數" % (path, number))
            out[int(parts[0])] = parts[1].strip() if len(parts) > 1 else ""
    return out


def apply(work, answers_path):
    """讀者答案 → work dir ê段落表受訪者欄。"""
    index = read_index(work)
    answers = read_answers(answers_path)
    missing = []
    for lead in sorted(set(index.values())):
        if lead not in answers:
            missing.append(lead)
    if missing:
        raise PipelineError("%s：讀者 TSV 欠 %s 秒" % (answers_path, missing))
    seen = {}
    for second, lead in index.items():
        seen[second] = " ".join(codes_of(answers[lead]))
    path = paths.segments_file(work)
    rows = assign(segments.read(path), seen)
    segments.write(path, rows)
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="command", required=True)
    one = sub.add_parser("grab")
    one.add_argument("work")
    one.add_argument("video")
    one.add_argument("--preset", default="titv-news-2024-08",
                     help="照 preset 揀名條版型；無名條版型ê preset 就跳過")
    two = sub.add_parser("apply")
    two.add_argument("work")
    two.add_argument("tsv")
    args = ap.parse_args(argv)
    if args.command == "grab":
        style = style_for(args.preset)
        if style is None:
            print("%s 無名條版型，跳過" % args.preset)
            return 0
        grab(args.work, args.video, style)
    else:
        apply(args.work, args.tsv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
