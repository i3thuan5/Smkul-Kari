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
