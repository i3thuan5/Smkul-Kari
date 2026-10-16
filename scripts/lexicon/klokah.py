#!/usr/bin/env python3
"""族語E樂園 教材匯出 → 各語別詞表（一行一詞的 txt）。

官方辭典一族只收一個語別（阿美＝秀姑巒、泰雅＝賽考利克、卑南＝南王），
E樂園 的教材有 43 個語別、逐句標了語言別編號，是手上唯一分得出語別的
族語文本。原始匯出在 `kithann/E樂園/`（音檔一起包，大的 tar 1–2 GB），
只解文字檔（csv、xml）出來給這支讀。

**用標準函式庫讀**（csv、xml.etree），不引進新套件。

量到會錯的幾件事（2026-10-15 解開真檔時）：

  族語欄名十幾種    wordAb、sentenceAAb、lessonAB、con_AB1、Ab_1、
                    article_ab、matchAAbA……一律靠 is_formosan_field 認
  ch 不是華語記號   choiceOneAAb 的 ch 是 choice，不能「含 ch 就丟」
  兩個編號          句型篇 languageId 是族、dialectId 才是語別
  語別在資料夾名    生活會話篇 `<語言別編號>/conversation.xml` 裡沒有 dialectId
  欄名換一套        文化篇單字表是 dialect_id、word_ab
  語言別編號表        開頭 BOM、tab 縮排、第 12 號空白

切詞用 `script.words`，跟字幕、辭典同一把尺：撇號正規化、小寫、
`/` 和括號都是分界（`sa / saya / misasa` 自然拆成三個異體）。
"""
import csv
import os
import re
import xml.etree.ElementTree as ET

from scripts import languages
from scripts.errors import PipelineError
from scripts.lexicon import script

# 族語欄：結尾是 Ab／AB（後面可以再接一個 A–E 的題號或數字），或
# _ab，或 Ab_<數字>。華語欄一律是 Ch／CH／_ch，這條規則碰不到它們。
FORMOSAN_FIELD = re.compile(r"(?:Ab|AB)(?:[A-E]|\d+)?$|_ab$|^Ab_\d+$")

DIALECT_FIELDS = ("dialectId", "dialect_id")


def is_formosan_field(name):
    return bool(FORMOSAN_FIELD.search(name))


def dialect_names(path):
    """語言別編號表 → {編號: 語別全名}。空白的編號不收。"""
    found = {}
    with open(path, encoding="utf-8-sig") as handle:
        for line in handle:
            number, sep, name = line.partition(":")
            number = number.strip()
            if sep and number.isdigit() and name.strip():
                found[number] = name.strip()
    return found


def variety_of(full_name):
    """「南勢阿美語」→ ("阿美", "南勢", "ami-x-iams")。

    先剝掉「<族名>語」；剝完查不到時試整個名字（對照表收的是
    「東排灣」「東魯凱」，不是「東」）。沒有變體的族語回空字串、
    代號退族語別代號。對不上任何一族、或剝出來的語別對照表沒有，
    都指名中止——代號不能用猜的。
    """
    base = full_name[:-1] if full_name.endswith("語") else full_name
    language = None
    for name in sorted(languages.LANGUAGES, key=len, reverse=True):
        if base.endswith(name):
            language = name
            break
    if language is None:
        raise PipelineError("E樂園 語別 %r 對不上任何族語別" % full_name)
    variety = base[:-len(language)]
    if not variety:
        return language, "", languages.code_for(language, "")
    table = languages.VARIETIES.get(language) or {}
    if languages.key(variety) not in table:
        if languages.key(base) in table:
            variety = base
        else:
            raise PipelineError(
                "E樂園 語別 %r：%s 底下沒有「%s」這個語言別"
                % (full_name, language, variety))
    return language, variety, languages.code_for(language, variety)


def _csv_records(path):
    with open(path, encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        header = reader.fieldnames or []
        texts = []
        for name in header:
            if is_formosan_field(name):
                texts.append(name)
        if not texts:
            return
        dialect = None
        for name in DIALECT_FIELDS:
            if name in header:
                dialect = name
        if dialect is None:
            raise PipelineError(
                "%s 有族語欄（%s）卻沒有語別欄（%s）"
                % (path, "、".join(texts), "、".join(DIALECT_FIELDS)))
        for row in reader:
            for name in texts:
                yield (row.get(dialect) or "").strip(), row.get(name) or ""


def _xml_records(path):
    folder = os.path.basename(os.path.dirname(path))
    root = ET.parse(path).getroot()
    for record in root:
        dialect = (record.findtext("dialectId") or "").strip()
        if not dialect and folder.isdigit():
            dialect = folder
        for node in record.iter():
            text = node.text or ""
            if not is_formosan_field(node.tag) or not text.strip():
                continue
            if not dialect:
                raise PipelineError(
                    "%s 的 <%s> 有族語文字，卻找不到語別（沒有 dialectId，"
                    "資料夾名也不是語言別編號）" % (path, node.tag))
            yield dialect, text


def records(root):
    """(語言別編號, 族語文字) 逐筆。照路徑排序，重跑順序固定。"""
    found = []
    for folder, _dirs, files in os.walk(root):
        for name in files:
            if name.endswith(".csv") or name.endswith(".xml"):
                found.append(os.path.join(folder, name))
    for path in sorted(found):
        if path.endswith(".csv"):
            stream = _csv_records(path)
        else:
            stream = _xml_records(path)
        for dialect, text in stream:
            yield path, dialect, text


def vocabularies(root, names_path):
    """{語別全名: set(詞)}。編號表沒有的編號指名中止。"""
    names = dialect_names(names_path)
    for name in names.values():
        variety_of(name)   # 先全部驗一遍，對照表缺項在開頭就喊
    out = {}
    for path, dialect, text in records(root):
        if dialect not in names:
            raise PipelineError("%s 用了語言別編號 %r，編號表 %s 沒有"
                                % (path, dialect, names_path))
        out.setdefault(names[dialect], set()).update(script.words(text))
    return out


def write_all(vocabs, folder):
    """一個語別一個 `<語別全名>.txt`，一行一詞、排過。"""
    os.makedirs(folder, exist_ok=True)
    written = []
    for name in sorted(vocabs):
        path = os.path.join(folder, name + ".txt")
        with open(path, "w", encoding="utf-8") as handle:
            for word in sorted(vocabs[name]):
                handle.write(word + "\n")
        written.append(path)
    return written


def load_all(folder):
    """write_all 的反向：{語別全名: set(詞)}。"""
    if not os.path.isdir(folder):
        raise PipelineError("E樂園 詞表欠件：%s" % folder)
    out = {}
    for name in sorted(os.listdir(folder)):
        if not name.endswith(".txt"):
            continue
        words = set()
        with open(os.path.join(folder, name), encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    words.add(line.strip())
        out[name[:-len(".txt")]] = words
    return out
