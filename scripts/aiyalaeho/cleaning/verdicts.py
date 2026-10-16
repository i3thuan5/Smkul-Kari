"""送 Claude 判定的分批檔，與判定結果的匯入驗證。

兩種判定，都是 Opus subagent 讀「待判-bNN.csv」、寫回「bNN.csv」：

  文字分類  送判的詞形逐個分成 錯字／語言別差異／不同詞／斷詞不同／不確定，
            錯字要附建議寫法（判準 brief_text.md）
  看圖      錯字逐處、和「’ 夾空白」逐處，看原生圖條分成 OCR 讀錯／
            播出端錯字／看不出來（判準 brief_image.md）

判定是這條線唯一花錢、重跑不會得到同樣結果的步驟：存檔；已經送過的
不再送；匯入時少列、多列、類別寫錯一律指名中止。

批次大小：判定類的批次固定開銷（系統提示、判準逐回合重送）遠大於
逐列成本，使用者 2026-09-08 裁定一批至少 200 列、愈大愈好。文字分類
一列含三句上下文約 400 bytes，300 列約 12 萬 bytes，還留得下推理空間。
看圖一處一到兩張 1920×60 的圖條，60 處約等於 4 張組合圖。
"""
import collections
import csv
import glob
import os
import re

from scripts.aiyalaeho.cleaning import candidates
from scripts.aiyalaeho.langcheck.report import write_table
from scripts.errors import PipelineError

TEXT_BATCH = 300
IMAGE_BATCH = 60
CONTEXTS = 3

TEXT_SEND_HEADER = ["詞形", "出現集數", "該集語別", "辭典", "E樂園見過的語別",
                    "Kaldi詞表", "最接近的辭典詞條", "相近寫法", "上下文"]
TEXT_RESULT_HEADER = ["詞形", "類別", "建議寫法", "理由"]
TEXT_CLASSES = ("錯字", "語言別差異", "不同詞", "斷詞不同", "不確定")
TYPO = "錯字"

IMAGE_SEND_HEADER = ["成果檔名", "字幕編號", "詞形", "建議寫法", "族語列",
                     "華語列", "圖條"]
IMAGE_RESULT_HEADER = ["成果檔名", "字幕編號", "詞形", "類別", "畫面上的寫法",
                       "理由"]
OCR_MISREAD = "OCR 讀錯"
BROADCAST_TYPO = "播出端錯字"
UNREADABLE = "看不出來"
IMAGE_CLASSES = (OCR_MISREAD, BROADCAST_TYPO, UNREADABLE)

TextVerdict = collections.namedtuple("TextVerdict",
                                     "kind suggestion reason batch")
ImageVerdict = collections.namedtuple("ImageVerdict",
                                      "kind screen reason batch")
ImageItem = collections.namedtuple(
    "ImageItem", "srt_name number word suggestion formosan han strips")

SENT = re.compile(r"^待判-(b\d+)\.csv$")


def read_rows(path):
    with open(path, encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _sent(folder):
    """{批號: 待判檔路徑}，照批號排。"""
    found = {}
    for path in glob.glob(os.path.join(folder, "待判-b*.csv")):
        match = SENT.match(os.path.basename(path))
        if match:
            found[match.group(1)] = path
    return dict(sorted(found.items()))


def _next_batch(folder):
    numbers = [0]
    for batch in _sent(folder):
        numbers.append(int(batch[1:]))
    return max(numbers) + 1


def _write_batches(folder, header, rows, size):
    os.makedirs(folder, exist_ok=True)
    written = []
    number = _next_batch(folder)
    for start in range(0, len(rows), size):
        path = os.path.join(folder, "待判-b%02d.csv" % number)
        write_table(path, header, rows[start:start + size])
        written.append(path)
        number += 1
    return written


# --------------------------------------------------------------- 文字分類

def _context(word, texts):
    seen = []
    for place in word.occurrences:
        if place not in seen:
            seen.append(place)
    parts = []
    for srt_name, number in seen[:CONTEXTS]:
        entry = texts[(srt_name, number)]
        parts.append("%s#%d 族語：%s／華語：%s"
                     % (candidates.episode_number(srt_name), number,
                        entry.formosan, entry.han))
    return " | ".join(parts)


def _varieties(word, considered):
    out = []
    for srt_name, _number in word.occurrences:
        for variety in considered[srt_name]:
            if variety not in out:
                out.append(variety)
    return ";".join(out)


def export_text(built, texts, considered, folder, size=TEXT_BATCH):
    """還沒送過的送判詞形寫成待判批次，回傳新寫的檔。

    texts：{(成果檔名, 字幕編號): Entry}；considered：{成果檔名: 語別…}。
    """
    already = set()
    for path in _sent(folder).values():
        for row in read_rows(path):
            already.add(row["詞形"].lower())
    rows = []
    for key in built.to_send():
        if key in already:
            continue
        word = built.words[key]
        near = []
        for other in word.neighbours:
            near.append(built.described(other))
        rows.append([
            word.display, ";".join(sorted(word.episodes)),
            _varieties(word, considered), "有" if word.in_dict else "無",
            ";".join(word.varieties), "有" if word.in_kaldi else "無",
            ";".join(word.nearest[:3]), "、".join(near),
            _context(word, texts),
        ])
    return _write_batches(folder, TEXT_SEND_HEADER, rows, size)


def _answers(folder):
    """每個待判批次配上它的回答；沒回答的批次一起指名。"""
    pairs = []
    missing = []
    for batch, sent in _sent(folder).items():
        answer = os.path.join(folder, batch + ".csv")
        if os.path.exists(answer):
            pairs.append((batch, sent, answer))
        else:
            missing.append(os.path.basename(sent))
    if missing:
        raise PipelineError("%s 還沒有判定結果：%s"
                            % (folder, "、".join(missing)))
    return pairs


def _listed(keys):
    names = []
    for key in keys:
        names.append(str(key))
    return "、".join(names) or "無"


def _same_keys(batch, sent_keys, got_keys):
    lacking = sorted(set(sent_keys) - set(got_keys))
    extra = sorted(set(got_keys) - set(sent_keys))
    if lacking or extra:
        raise PipelineError("%s 判定和送出的對不上；缺：%s；多：%s"
                            % (batch, _listed(lacking), _listed(extra)))


def load_text(folder):
    """{詞形小寫: TextVerdict}。"""
    out = {}
    for batch, sent, answer in _answers(folder):
        sent_words = []
        for row in read_rows(sent):
            sent_words.append(row["詞形"])
        rows = read_rows(answer)
        got_words = []
        for row in rows:
            got_words.append(row["詞形"])
        _same_keys(batch, sent_words, got_words)
        for row in rows:
            kind = row["類別"].strip()
            if kind not in TEXT_CLASSES:
                raise PipelineError("%s「%s」的類別「%s」不是 %s 之一"
                                    % (batch, row["詞形"], kind,
                                       "／".join(TEXT_CLASSES)))
            suggestion = row["建議寫法"].strip()
            if kind == TYPO and not suggestion:
                raise PipelineError("%s「%s」判錯字卻沒有建議寫法"
                                    % (batch, row["詞形"]))
            out[row["詞形"].lower()] = TextVerdict(
                kind, suggestion, row["理由"].strip(), batch)
    return out


# ------------------------------------------------------------------- 看圖

def _image_key(row):
    return (row["成果檔名"], int(row["字幕編號"]), row["詞形"])


def export_image(items, folder, size=IMAGE_BATCH):
    """還沒送過的看圖項目寫成待判批次（逐處，不是逐詞）。"""
    already = set()
    for path in _sent(folder).values():
        for row in read_rows(path):
            already.add(_image_key(row))
    rows = []
    for item in sorted(items, key=lambda i: (i.srt_name, i.number, i.word)):
        if (item.srt_name, item.number, item.word) in already:
            continue
        rows.append([item.srt_name, str(item.number), item.word,
                     item.suggestion, item.formosan, item.han,
                     ";".join(item.strips)])
    return _write_batches(folder, IMAGE_SEND_HEADER, rows, size)


def load_image(folder):
    """{(成果檔名, 字幕編號, 詞形): ImageVerdict}。"""
    out = {}
    for batch, sent, answer in _answers(folder):
        sent_keys = []
        for row in read_rows(sent):
            sent_keys.append(_image_key(row))
        rows = read_rows(answer)
        got_keys = []
        for row in rows:
            got_keys.append(_image_key(row))
        _same_keys(batch, sent_keys, got_keys)
        for row in rows:
            key = _image_key(row)
            kind = row["類別"].strip()
            if kind not in IMAGE_CLASSES:
                raise PipelineError("%s %s 的類別「%s」不是 %s 之一"
                                    % (batch, key, kind,
                                       "／".join(IMAGE_CLASSES)))
            screen = row["畫面上的寫法"].strip()
            if kind == OCR_MISREAD and not screen:
                raise PipelineError("%s %s 判 OCR 讀錯，卻沒寫畫面上的寫法"
                                    % (batch, key))
            out[key] = ImageVerdict(kind, screen, row["理由"].strip(), batch)
    return out


# ------------------------------------------------------------- 人工改判

OVERRIDES = "人工改判.csv"


def load_overrides(path):
    """{族語別: {詞形小寫: 理由}}；檔案不存在就是沒有改判。

    使用者看過結果後裁定「這幾個錯字列待討論、不改」的詞（2026-10-15：
    082 odal 可能是南勢寫法、087 z 開頭的可能是西群寫法、087#286
    tatena 改了會多一個撇號）。Claude 的原判照留，報表的依據欄寫出改判
    理由。手寫的檔，放在 3-判定/ 底下。
    """
    if not os.path.exists(path):
        return {}
    out = {}
    for row in read_rows(path):
        word = row["詞形"].strip()
        if word:
            out.setdefault(row["族語別"].strip(), {})[word.lower()] = \
                row["理由"].strip()
    return out
