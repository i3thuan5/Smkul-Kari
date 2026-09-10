#!/usr/bin/env python3
"""官方族語辭典 xlsx → store 內底ê詞庫 txt。

辭典佇 SFTP：`/docker/族語辭典_單詞與例句/`，16 族逐族一个 xlsx，
4728 到 33402 筆。原檔五十外 MB、二進位，**莫入 store**；蒸餾做
一逝一詞ê純文字（逐族約 1.1 到 1.5 萬詞）才入，án-ne判定才有法度
離線重走，`rebuild --verify` 才涵蓋會著。

**用標準函式庫讀。** xlsx 是 zip 包 XML，`zipfile` 加
`xml.etree.ElementTree` 就讀了了，照 CLAUDE.md「裝得越少越好」，
無引進 openpyxl。

三件會出代誌ê，攏量過：

  欄位靠位置    真檔 16 欄。靠位置ê話欄序換一擺規份歪去，而且是
                恬恬歪去。一律靠表頭名，揣無就指名喝停。
  彎撇無正規化  辭典寫 `ngaʼay`（U+02BC），字幕寫 `nga'ay`。無
                正規化ê話喉塞音彼類詞規排對袂著（切詞 script.words
                內底處理）。
  干焦收單字    068 ê涵蓋率會對 81% 落到 75%。例句原文內底彼款
                變化形才是實際講出來ê——族語是黏著語，辭典收ê是
                原形，講出來ê是變化形。
"""
import os
import zipfile
import xml.etree.ElementTree as ET

from scripts.aiyalaeho.langcheck import script
from scripts.errors import PipelineError

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

# 蒸餾食ê三欄。單字是原形、詞根是構詞ê底、例句原文是實際講出來ê
# 變化形——三欄鬥起來涵蓋率才夠（068：干焦單字 75%，鬥齊 81%）。
SOURCE_COLUMNS = ("單字", "詞根", "例句原文")


def _shared_strings(book):
    """xlsx kā逐个無仝ê字串收做一份表，儲存格才指過去（t="s"）。"""
    out = []
    if "xl/sharedStrings.xml" not in book.namelist():
        return out
    for item in ET.fromstring(book.read("xl/sharedStrings.xml")):
        text = []
        for node in item.iter(NS + "t"):
            text.append(node.text or "")
        out.append("".join(text))
    return out


def _sheet_name(book):
    sheets = []
    for name in book.namelist():
        if name.startswith("xl/worksheets/sheet") and name.endswith(".xml"):
            sheets.append(name)
    if len(sheets) != 1:
        raise PipelineError(
            "辭典 xlsx 應該干焦一个工作表，煞有 %d 个：%s"
            % (len(sheets), ", ".join(sorted(sheets))))
    return sheets[0]


def rows(path):
    """逐逝ê儲存格文字。頭一逝是表頭。"""
    with zipfile.ZipFile(path) as book:
        shared = _shared_strings(book)
        sheet = ET.fromstring(book.read(_sheet_name(book)))
    for row in sheet.iter(NS + "row"):
        cells = []
        for cell in row.iter(NS + "c"):
            value = cell.find(NS + "v")
            text = "" if value is None else (value.text or "")
            if cell.get("t") == "s" and text:
                text = shared[int(text)]
            cells.append(text)
        yield cells


def words_of(path):
    """一个辭典檔內底所有ê族語詞（set）。"""
    stream = rows(path)
    try:
        header = next(stream)
    except StopIteration:
        raise PipelineError("辭典 %s 內底一逝都無" % os.path.basename(path))

    # 靠名毋靠位置。欄位揣無ê時愛指名喝停，莫恬恬收較少ê資料——
    # 彼款失敗會變做「涵蓋率變低」，看袂出是欄名換去。
    wanted = {}
    for column in SOURCE_COLUMNS:
        if column not in header:
            raise PipelineError(
                "辭典 %s 揣無「%s」欄；有ê是：%s"
                % (os.path.basename(path), column, "、".join(header)))
        wanted[column] = header.index(column)

    out = set()
    for cells in stream:
        for index in wanted.values():
            if index < len(cells):
                out.update(script.words(cells[index]))
    return out


def write(words, path):
    """詞庫檔：一逝一詞、排過。排過 diff 才看會出改著佗一逝。"""
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        for word in sorted(words):
            handle.write(word + "\n")
    return path


def load(path):
    """詞庫檔 → set。判定食ê是這搭，毋是辭典原檔。"""
    if not os.path.exists(path):
        raise PipelineError("詞庫欠件：%s" % path)
    out = set()
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            word = line.strip()
            if word:
                out.add(word)
    return out


def distil(xlsx_path, lexicon_path):
    """辭典 xlsx → 詞庫 txt。"""
    return write(words_of(xlsx_path), lexicon_path)
