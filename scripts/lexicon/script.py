#!/usr/bin/env python3
"""一逝字內底，逐種書寫系統各有偌濟字元。

四級標籤ê頭三个（`無`、`<族語>語夾華語`、`華語`）全部靠這支決定，
所以伊愛擋牢一種寫法：**用 ASCII 範圍分類**。

    'a' <= c.lower() <= 'z'          ← 毋通

語料內底有 `ʉ`（737 擺）、`ē`（37 擺）、`è`，是拉丁字母毋過無佇
a-z。按 ASCII 範圍算ê話，「pinaʉ」這款列會變做「無拉丁字母」，
閣有漢字ê話就去予判做華語。所以一律看 Unicode 一般類別。

注音符號是第三種，**莫算做漢字**。122 布農佮 093 阿美攏有
「micodad to ㄅㄆㄇㄈ」這款列——彼是講著注音符號，毋是講華語；
算做漢字ê話規列會去予標做「夾華語」。

標點、數字、空白攏無算。「1000 kamini ni 投資」愛判做夾華語
（有拉丁嘛有漢字），「5 to ko nipalomaan niyam」愛判做純拉丁。
"""
import collections
import unicodedata

# CJK 統一表意文字。中央氣象、專名、借詞攏佇遮；擴充區佮相容區
# 語料內底一个都無（量過 39 集 28486 條），所以無收——若後來出現，
# 這條愛tuè咧改，毋是恬恬歸做「毋是漢字」。
HAN_FIRST, HAN_LAST = 0x4E00, 0x9FFF

# 注音符號（含擴充ê四个聲調符號位）。
BOPOMOFO_FIRST, BOPOMOFO_LAST = 0x3100, 0x312F

# 拉丁字母：一般類別 Ll／Lu。這兩个類別內底ê字元佇這批語料攏是
# 拉丁（驗過：39 集ê族語列內底 Ll／Lu 55 種字元，無一个非拉丁）。
LETTER_CATEGORIES = ("Ll", "Lu")

# 表意文字類別。漢字佮注音攏是 Lo，愛閣看碼位才分會開。
OTHER_LETTER = "Lo"

# 族語正字法內底會出現ê非字母記號。喉塞音 ' 上要緊，`^ : -` 是長
# 音佮連字，攏是詞ê一部份，切詞ê時莫kā伊當做分界。
WORD_MARKS = "'-^:"

# 撇號有三种寫法濫做伙：辭典寫 U+02BC（ʼ）、Word 會kā ASCII 撇號
# 換做 U+2019（’）、字幕寫 ASCII。攏正規化做 ASCII，若無仝一个詞
# 佇詞庫佮字幕會變兩个，喉塞音彼類詞規排對袂著。
APOSTROPHES = "ʼ’‘"

# 兩字以下ê詞逐族攏有（to、ko、no、ka…），鑑別力等於零，留咧干焦
# 是雜訊。切詞ê時就摒掉，詞庫佮字幕兩爿才會用仝一支尺。
MIN_WORD = 3

Counts = collections.namedtuple("Counts", "latin han bopomofo")


def counts(text):
    """(拉丁字母數, 漢字數, 注音符號數)。標點、數字、空白無算。"""
    latin = han = bopomofo = 0
    for char in text:
        category = unicodedata.category(char)
        if category in LETTER_CATEGORIES:
            latin += 1
        elif category == OTHER_LETTER:
            point = ord(char)
            if HAN_FIRST <= point <= HAN_LAST:
                han += 1
            elif BOPOMOFO_FIRST <= point <= BOPOMOFO_LAST:
                bopomofo += 1
    return Counts(latin, han, bopomofo)


def words(text):
    """切詞：一逝字 → 一 list ê族語詞（細寫、撇號正規化過）。

    詞庫佮字幕**愛用仝一支**。無仝ê切法是這條線上驚ê失敗——兩爿
    各切各ê，命中率會平平低落去，看起來敢若「辭典涵蓋無夠」，其
    實是尺無仝。所以這支囥佇 script.py，dictionary 佮 vocab 攏叫伊。

    漢字、注音、數字、標點攏做分界（袂入詞）。
    """
    plain = text
    for mark in APOSTROPHES:
        plain = plain.replace(mark, "'")
    pieces = []
    for char in plain:
        if unicodedata.category(char) in LETTER_CATEGORIES:
            pieces.append(char)
        elif char in WORD_MARKS:
            pieces.append(char)
        else:
            pieces.append(" ")
    out = []
    for token in "".join(pieces).lower().split():
        # 摒掉干焦賰記號ê殘骸（像 "--"），彼毋是詞。
        if len(token) >= MIN_WORD and token.strip(WORD_MARKS):
            out.append(token)
    return out
