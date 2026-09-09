"""一個來源檔（docx／doc／txt）→ (UTF-8 正文, 格式標記)。

**分派只看副檔名，不嗅探內容。** 盤點初期拿 `zipfile.is_zipfile()` 當
分派器，對開會029那兩個 `.doc` 回傳 True——Word 把佈景主題（一小段合法
zip）塞在 OLE2 複合檔尾，`is_zipfile()` 從檔尾找到 EOCD 就說「是
zip」——那次就是這樣把兩個好檔判成壞檔。掃過全部 129 個 doc/docx，
副檔名與內容 100% 一致，本來就分得開；出事是分派器選錯了東西，不是
副檔名不可信。

**解不開就中止，不改用另一種方式重試，也不吞掉當沒事。** 這是一次跑完
243 個檔的批次，半份結果比沒有結果更危險。
"""
import io
import os
import zipfile
import xml.etree.ElementTree as ET

from scripts.aiyalaeho.text import oledoc
from scripts.errors import PipelineError

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

# 純文字編碼探測順序：UTF-16 靠 BOM 直接判定；沒有 BOM 的一律當 Big5
# （這批語料實測沒有無 BOM 的 UTF-8，有 BOM 的另外判）。
_UTF16_BOMS = (b"\xff\xfe", b"\xfe\xff")
_UTF8_BOM = b"\xef\xbb\xbf"


def _normalize_apostrophes(text):
    """族語正字的喉塞音是 ASCII `'`；文書軟體的自動更正換成印刷彎撇，
    這裡換回來。"""
    return text.replace("’", "'").replace("‘", "'")


def _decode_txt(raw, name):
    if raw[:2] in _UTF16_BOMS:
        try:
            return raw.decode("utf-16"), "utf-16"
        except UnicodeDecodeError as exc:
            raise PipelineError("%s：UTF-16 解碼失敗（%s）" % (name, exc))
    if raw[:3] == _UTF8_BOM:
        try:
            return raw.decode("utf-8-sig"), "utf-8"
        except UnicodeDecodeError as exc:
            raise PipelineError("%s：UTF-8 解碼失敗（%s）" % (name, exc))
    try:
        return raw.decode("cp950"), "big5"
    except UnicodeDecodeError as exc:
        raise PipelineError("%s：Big5 解碼失敗（%s）" % (name, exc))


def _decode_docx(raw, name):
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            xml_bytes = archive.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError) as exc:
        raise PipelineError("%s：不是合法的 .docx（%s）" % (name, exc))

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise PipelineError("%s：word/document.xml 不是合法 XML（%s）"
                            % (name, exc))

    lines = []
    for paragraph in root.iter(_W + "p"):
        buf = []
        for node in paragraph.iter():
            if node.tag == _W + "t":
                buf.append(node.text or "")
            elif node.tag == _W + "br":
                buf.append("\n")
            elif node.tag == _W + "tab":
                buf.append("\t")
        lines.append("".join(buf))
    return "\n".join(lines), "docx"


def _decode_doc(raw, name):
    try:
        return oledoc.extract_text(raw), "doc"
    except PipelineError as exc:
        raise PipelineError("%s：%s" % (name, exc))


_READERS = {
    ".txt": _decode_txt,
    ".docx": _decode_docx,
    ".doc": _decode_doc,
}


def decode(path):
    """(UTF-8 正文, 格式標記)。副檔名決定用哪個讀法；讀不開就中止。"""
    name = os.path.basename(path)
    ext = os.path.splitext(name)[1].lower()
    reader = _READERS.get(ext)
    if reader is None:
        raise PipelineError("%s：不認得的副檔名 %r（只認 .txt/.docx/.doc）"
                            % (name, ext))

    with open(path, "rb") as handle:
        raw = handle.read()

    text, fmt = reader(raw, name)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return _normalize_apostrophes(text), fmt
