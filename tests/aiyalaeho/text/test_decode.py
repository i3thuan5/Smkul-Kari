"""來源檔（docx／doc／txt，三種編碼）→ UTF-8 正文。

副檔名決定用哪一種解讀方式，不嗅探內容——盤點初期拿
`zipfile.is_zipfile()` 當分派器，對 OLE2 複合檔（開會029 那兩個 `.doc`）
回傳 True，因為 Word 把佈景主題當一小段 zip 塞在 OLE 檔尾，那次就是這樣
把兩個好檔判成壞檔。這裡刻意不重蹈：解讀失敗就中止，不嘗試另一種格式。
"""
import os
import tempfile
import unittest
import zipfile

from scripts.aiyalaeho.text import decode
from scripts.errors import PipelineError
from tests.aiyalaeho.text.test_oledoc import build_ole2
from tests.aiyalaeho.text.test_oledoc import build_word97

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _ole2_with_zip_looking_tail(streams):
    """一份跟開會029那兩個真檔一樣、會騙過 zipfile.is_zipfile() 的 OLE2
    複合檔：Word 把佈景主題（一小段合法 zip）放在檔尾，`is_zipfile()`
    從檔尾找 EOCD，找到就說「是 zip」——一個空的 EOCD 記錄就夠騙過它。
    """
    return build_ole2(streams) + b"PK\x05\x06" + b"\x00" * 18


def _docx_bytes(paragraphs):
    """組一個最小合法的 .docx：paragraphs 是 [[(文字, 是不是換行), ...], ...]。

    每個內層 list 是一個 <w:p>；元素是 (text, is_br) —— is_br 為 True 時
    插一個 <w:br/>，不然插一個帶文字的 <w:t>。
    """
    body = []
    for para in paragraphs:
        runs = []
        for item in para:
            if item == "TAB":
                runs.append("<w:r><w:tab/></w:r>")
            elif item == "BR":
                runs.append("<w:r><w:br/></w:r>")
            else:
                runs.append("<w:r><w:t>%s</w:t></w:r>" % item)
        body.append("<w:p>%s</w:p>" % "".join(runs))
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/'
        'wordprocessingml/2006/main"><w:body>%s</w:body></w:document>'
        % "".join(body)
    )
    buf_path = None
    with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as handle:
        buf_path = handle.name
    with zipfile.ZipFile(buf_path, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr("word/document.xml", document_xml)
    with open(buf_path, "rb") as handle:
        data = handle.read()
    os.unlink(buf_path)
    return data


def _write(tmp_dir, name, data):
    path = os.path.join(tmp_dir, name)
    with open(path, "wb") as handle:
        handle.write(data)
    return path


class TestDispatchByExtension(unittest.TestCase):
    """副檔名決定讀法，不去嗅探內容——這是這個模組存在的理由。"""

    def test_docx_is_read_as_ooxml_even_though_it_is_a_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "a.docx", _docx_bytes([["hello"]]))
            text, fmt = decode.decode(path)
        self.assertEqual(text, "hello")
        self.assertEqual(fmt, "docx")

    def test_zipfile_is_zipfile_being_true_for_ole2_must_not_matter(self):
        # 盤點初期踩過的坑：Word 把佈景主題（一小段合法 zip）塞在 OLE2
        # 複合檔尾，`zipfile.is_zipfile()` 從檔尾找到 EOCD 就回報「是
        # zip」，那次就是拿這個結果當分派器，把兩個好檔判成壞檔。這裡
        # 造一個會讓 is_zipfile() 說 True 的 .doc，斷言 decode() 仍然
        # 照副檔名走 OLE2、解得出正文——證明 is_zipfile() 完全沒有
        # 參與判斷。
        wd, tables = build_word97([("qani ga ke'", True)])
        streams = {"WordDocument": wd}
        streams.update(tables)
        raw = _ole2_with_zip_looking_tail(streams)
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "a.doc", raw)
            self.assertTrue(zipfile.is_zipfile(path),
                            "這個 fixture 要能騙過 is_zipfile()，不然沒測到重點")
            text, fmt = decode.decode(path)
        self.assertEqual(text, "qani ga ke'")
        self.assertEqual(fmt, "doc")

    def test_unknown_extension_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "a.rtf", b"whatever")
            self.assertRaises(PipelineError, decode.decode, path)


class TestPlainTextEncoding(unittest.TestCase):
    def test_utf16_bom_is_not_read_as_big5(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "a.txt", "賽夏族".encode("utf-16"))
            text, fmt = decode.decode(path)
        self.assertEqual(text, "賽夏族")
        self.assertEqual(fmt, "utf-16")

    def test_no_bom_is_read_as_big5(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "a.txt", "賽夏族".encode("cp950"))
            text, fmt = decode.decode(path)
        self.assertEqual(text, "賽夏族")
        self.assertEqual(fmt, "big5")

    def test_utf8_bom_is_stripped_from_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "a.txt", "賽夏族".encode("utf-8-sig"))
            text, fmt = decode.decode(path)
        self.assertEqual(text, "賽夏族")
        self.assertNotIn("﻿", text)
        self.assertEqual(fmt, "utf-8")


class TestDocxParagraphs(unittest.TestCase):
    def test_one_p_is_one_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "a.docx",
                          _docx_bytes([["第一行"], ["第二行"]]))
            text, _ = decode.decode(path)
        self.assertEqual(text, "第一行\n第二行")

    def test_br_becomes_newline_inside_a_paragraph(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "a.docx",
                          _docx_bytes([["前半", "BR", "後半"]]))
            text, _ = decode.decode(path)
        self.assertEqual(text, "前半\n後半")

    def test_tab_becomes_a_tab_character(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "a.docx",
                          _docx_bytes([["族語", "TAB", "華語"]]))
            text, _ = decode.decode(path)
        self.assertEqual(text, "族語\t華語")


class TestApostropheNormalization(unittest.TestCase):
    """喉塞音本來就是 Big5／UTF-16 兩種真實編碼裡的字元，用這兩種真實編碼
    寫 fixture——不是虛構一個這批語料實際不會出現的無 BOM UTF-8 檔。
    """

    def test_curly_apostrophes_become_ascii_from_big5(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "a.txt", "’ita’ ‘ay".encode("cp950"))
            text, _ = decode.decode(path)
        self.assertEqual(text, "'ita' 'ay")

    def test_curly_apostrophes_become_ascii_from_utf16(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "a.txt", "’ita’ ‘ay".encode("utf-16"))
            text, _ = decode.decode(path)
        self.assertEqual(text, "'ita' 'ay")

    def test_ascii_apostrophe_is_unaffected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "a.txt", "'ita' saboeh".encode("cp950"))
            text, _ = decode.decode(path)
        self.assertEqual(text, "'ita' saboeh")


class TestFailsLoudNotSilently(unittest.TestCase):
    def test_a_docx_that_is_not_actually_a_zip_aborts_naming_the_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "broken.docx", b"not a zip at all")
            with self.assertRaises(PipelineError) as ctx:
                decode.decode(path)
        self.assertIn("broken.docx", str(ctx.exception))

    def test_a_doc_that_is_not_actually_ole2_aborts_naming_the_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "broken.doc", b"not ole2 at all")
            with self.assertRaises(PipelineError) as ctx:
                decode.decode(path)
        self.assertIn("broken.doc", str(ctx.exception))

    def test_does_not_retry_with_a_different_reader(self):
        # 一個 .doc 副檔名但內容其實是 zip（docx）：不可以「順便」試另一
        # 種讀法解出來，要照副檔名（doc → OLE2）失敗、中止。
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "mislabeled.doc", _docx_bytes([["內容"]]))
            self.assertRaises(PipelineError, decode.decode, path)


if __name__ == "__main__":
    unittest.main()
