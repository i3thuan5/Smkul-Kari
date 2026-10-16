"""合成一个上細ê xlsx，予辭典蒸餾ê測試有物件通食。

真正ê辭典 16 个檔、五十外 MB、佇 SFTP 頂懸，測試袂使食伊：離線、
合成，是 CLAUDE.md ê TDD 規定。這搭合成ê檔案照真檔ê寫法——字串
囥佇 sharedStrings、儲存格用 `t="s"` 指過去——án-ne讀ê彼條路才有
真正走過。
"""
import os
import zipfile

CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/'
    'content-types">'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats'
    '-package.relationships+xml"/>'
    '</Types>'
)

RELS = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
    'relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/'
    'officeDocument/2006/relationships/officeDocument"'
    ' Target="xl/workbook.xml"/>'
    '</Relationships>'
)

WORKBOOK = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/'
    'main"><sheets><sheet name="工作表1" sheetId="1" r:id="rId1"'
    ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/'
    'relationships"/></sheets></workbook>'
)

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def _escape(text):
    out = text.replace("&", "&amp;").replace("<", "&lt;")
    return out.replace(">", "&gt;")


def write_xlsx(path, rows):
    """`rows` 是一逝一 list ê儲存格文字，頭一逝就是表頭。"""
    table = []
    for row in rows:
        table.append(list(row))

    # 逐个無仝ê字串收做一份 sharedStrings，儲存格才指過去——真檔就是
    # án-ne寫ê（阿美彼个檔 112805 條），讀ê彼條路愛食著這款。
    order = []
    index = {}
    for row in table:
        for cell in row:
            if cell not in index:
                index[cell] = len(order)
                order.append(cell)

    strings = ['<?xml version="1.0" encoding="UTF-8"?>',
               '<sst xmlns="%s" count="%d" uniqueCount="%d">'
               % (MAIN_NS, sum(len(r) for r in table), len(order))]
    for text in order:
        strings.append('<si><t xml:space="preserve">%s</t></si>'
                       % _escape(text))
    strings.append('</sst>')

    sheet = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<worksheet xmlns="%s"><sheetData>' % MAIN_NS]
    for number, row in enumerate(table, start=1):
        sheet.append('<row r="%d">' % number)
        for column, cell in enumerate(row):
            sheet.append('<c r="%s%d" t="s"><v>%d</v></c>'
                         % (_column_name(column), number, index[cell]))
        sheet.append('</row>')
    sheet.append('</sheetData></worksheet>')

    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as book:
        book.writestr("[Content_Types].xml", CONTENT_TYPES)
        book.writestr("_rels/.rels", RELS)
        book.writestr("xl/workbook.xml", WORKBOOK)
        book.writestr("xl/sharedStrings.xml", "".join(strings))
        book.writestr("xl/worksheets/sheet1.xml", "".join(sheet))
    return path


def _column_name(index):
    name = ""
    number = index
    while True:
        name = chr(ord("A") + number % 26) + name
        number = number // 26 - 1
        if number < 0:
            return name


# 真辭典ê 16 欄，照原本ê順序。測試用著ê是其中三欄。
DICT_HEADER = ["ID", "族別", "語別", "單字", "詞根", "單字音檔ID",
               "單字音檔檔名", "單字音檔連結", "釋義ID", "中文釋義",
               "例句ID", "例句原文", "例句中文", "例句音檔ID",
               "例句音檔檔名", "例句音檔連結"]


def dict_row(word="", stem="", sentence="", variety="秀姑巒阿美語"):
    """一逝辭典列，干焦填測試看ê彼三欄。"""
    row = []
    for column in DICT_HEADER:
        if column == "單字":
            row.append(word)
        elif column == "詞根":
            row.append(stem)
        elif column == "例句原文":
            row.append(sentence)
        elif column == "語別":
            row.append(variety)
        else:
            row.append("")
    return row


# ------------------------------------------------------------- E樂園

# 語言別編號表（真檔名 E樂園方言編號.txt）照真檔的寫法：開頭 BOM、tab 縮排、第 12 號空白。
DIALECT_TABLE = (
    "﻿方言編號：\n"
    "\t 1: 南勢阿美語\n"
    "\t 2: 秀姑巒阿美語\n"
    "\t11: 宜蘭澤敖利泰雅語\n"
    "\t12: \n"
    "\t13: 賽夏語\n"
    "\t23: 東排灣語\n"
    "\t38: 南王卑南語\n"
    "\t40: 西群卑南語\n"
)


def write_text(path, text):
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


def write_csv(path, header, rows):
    """E樂園 的句子 CSV：UTF-8 有 BOM（真檔就是）。"""
    import csv
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        for row in rows:
            writer.writerow(row)
    return path


def klokah_tree(root):
    """一棵縮小的 E樂園 解壓目錄，涵蓋真檔出現過的每一種寫法。"""
    write_text(os.path.join(root, "E樂園方言編號.txt"), DIALECT_TABLE)
    # 句子 CSV：dialectId／sentenceAb／sentenceCh。
    write_csv(os.path.join(root, "3.圖畫故事篇", "klokah_story_sentence.csv"),
              ["autoId", "textId", "dialectId", "sentenceAb", "sentenceCh",
               "sentenceOrder"],
              [["1", "9", "40", "zi harem mu", "今天", "1"],
               ["2", "9", "38", "garem", "今天", "2"]])
    # 文化篇單字表：欄名換成 dialect_id／word_ab。
    write_csv(os.path.join(root, "6.文化篇", "klokah_cuture_word.csv"),
              ["dialect_id", "lesson_no", "word_order", "word_ab", "word_ch"],
              [["1", "1", "1", "kaku", "我"]])
    # 繪本清單：沒有族語欄，也沒有語別欄——不是文本表，略過。
    write_csv(os.path.join(root, "9.繪本平台", "klokah_picture_book.csv"),
              ["aid", "title_ch"], [["1", "小熊"]])
    # 句型篇：languageId（族）和 dialectId（語別）不同；choice 開頭的欄；
    # matchAAbA 的 Ab 在中間；一格三個異體用 / 分。
    write_text(os.path.join(root, "1.句型篇國中", "xml", "38", "1.xml"),
               '<?xml version="1.0" encoding="utf-8"?><dataroot><item>'
               '<languageId>12</languageId><dialectId>38</dialectId>'
               '<classCh>數字</classCh>'
               '<wordAb>sa / saya / misasa</wordAb><wordCh>一</wordCh>'
               '<choiceOneAAb>kiyaumalr</choiceOneAAb>'
               '<choiceOneACh>choice華語</choiceOneACh>'
               '<matchAAbA>Pinaski</matchAAbA><matchAChA>下賓朗</matchAChA>'
               '</item></dataroot>')
    write_text(os.path.join(root, "1.句型篇國中", "xml", "class.xml"),
               '<?xml version="1.0" encoding="UTF-8"?><dataroot><item>'
               '<typeId>1</typeId><typeCh>基本詞彙</typeCh>'
               '</item></dataroot>')
    # 生活會話篇、閱讀書寫篇：語別只寫在資料夾名。
    write_text(os.path.join(root, "4.生活會話篇", "13", "conversation.xml"),
               "<?xml version='1.0' encoding='utf-8'?><dataroot><lesson>"
               "<lessonId>1</lessonId><lessonAB>kayzaeh ka</lessonAB>"
               "<lessonCH>你好</lessonCH></lesson><content>"
               "<con_AB1>So:o'</con_AB1><con_CH1>是</con_CH1>"
               "</content></dataroot>")
    write_text(os.path.join(root, "5.閱讀書寫篇", "11", "reading.xml"),
               "<?xml version='1.0' encoding='utf-8'?><dataroot><content>"
               "<Ab_1>lokah su’</Ab_1><Ch_1>你好</Ch_1>"
               "<article_ab>Tayal balay</article_ab>"
               "<article_ch>真正的人</article_ch></content></dataroot>")
    write_text(os.path.join(root, "5.閱讀書寫篇", "23", "reading.xml"),
               "<?xml version='1.0' encoding='utf-8'?><dataroot><content>"
               "<Ab_1>masalu</Ab_1></content></dataroot>")
    return root


# 真的 words.txt：前三行、後三行是模型用的符號，不是詞。
KALDI_WORDS = ("<eps> 0\n<SIL> 1\n<UNK> 2\n"
               "garem 3\nharem 4\nmenaʼu 5\nLikavung 6\n"
               "#0 7\n<s> 8\n</s> 9\n")
