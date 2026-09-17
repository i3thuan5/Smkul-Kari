"""sheetsize：只讀 PNG 檔頭拿寬高、算視覺 token，只用標準函式庫。

切批的程式跑在系統 python3 上，那裡沒有 numpy、沒有 PIL；而
`scripts/ocr/sheets.py` 在模組層就 import 這兩個，所以切批端碰不得它。
視覺 token 的算法只能有一份，由這支供給兩邊。
"""
import os
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

from scripts.datadirs import ROOT
from scripts.ocr import sheetsize


_MADE = {}


def png_bytes(width, height):
    """最小的合法 PNG（全黑）：簽章、IHDR、IDAT、IEND。依尺寸快取。"""
    key = (width, height)
    if key in _MADE:
        return _MADE[key]

    def chunk(kind, body):
        crc = zlib.crc32(kind + body) & 0xFFFFFFFF
        return struct.pack(">I", len(body)) + kind + body + \
            struct.pack(">I", crc)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw = (b"\x00" * (1 + 3 * width)) * height
    _MADE[key] = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
                  + chunk(b"IDAT", zlib.compress(raw))
                  + chunk(b"IEND", b""))
    return _MADE[key]


class Files(unittest.TestCase):

    def write(self, data, name="sheet_001.png"):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = os.path.join(tmp.name, name)
        with open(path, "wb") as handle:
            handle.write(data)
        return path


class TestPngSize(Files):

    def test_width_and_height_come_off_the_header(self):
        self.assertEqual(sheetsize.png_size(self.write(png_bytes(57, 30))),
                         (57, 30))

    def test_a_file_that_is_not_png_is_refused(self):
        # 猜一個數字回去，批次就算錯而且沒人知道
        path = self.write(b"GIF89a" + b"\x00" * 40, "x.png")
        with self.assertRaisesRegex(ValueError, "PNG"):
            sheetsize.png_size(path)

    def test_a_truncated_header_is_refused(self):
        path = self.write(png_bytes(57, 30)[:20])
        with self.assertRaisesRegex(ValueError, "PNG"):
            sheetsize.png_size(path)

    def test_a_png_whose_first_chunk_is_not_ihdr_is_refused(self):
        data = bytearray(png_bytes(57, 30))
        data[12:16] = b"IDAT"
        with self.assertRaisesRegex(ValueError, "IHDR"):
            sheetsize.png_size(self.write(bytes(data)))


class TestTokens(Files):

    def test_whole_patches(self):
        self.assertEqual(sheetsize.visual_tokens(56, 28), 2)

    def test_one_pixel_over_costs_a_whole_patch(self):
        self.assertEqual(sheetsize.visual_tokens(57, 28), 3)
        self.assertEqual(sheetsize.visual_tokens(56, 29), 4)

    def test_one_pixel_under_is_still_the_same_patch(self):
        self.assertEqual(sheetsize.visual_tokens(55, 27), 2)

    def test_tokens_of_a_file(self):
        self.assertEqual(sheetsize.tokens(self.write(png_bytes(57, 30))), 6)

    def test_the_constants_are_the_measured_ones(self):
        self.assertEqual(sheetsize.PATCH, 28)
        self.assertEqual(sheetsize.LONG_EDGE, 2000)
        self.assertEqual(sheetsize.VISUAL_TOKENS, 4784)


class TestStandardLibraryOnly(unittest.TestCase):

    def test_imports_with_numpy_and_pil_blocked(self):
        code = (
            "import sys\n"
            "class Block:\n"
            "    def find_spec(self, name, path=None, target=None):\n"
            "        if name.split('.')[0] in ('numpy', 'PIL'):\n"
            "            raise ImportError('blocked ' + name)\n"
            "        return None\n"
            "sys.meta_path.insert(0, Block())\n"
            "from scripts.ocr import sheetsize\n"
            "print(sheetsize.visual_tokens(57, 30))\n")
        proc = subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "6")


if __name__ == "__main__":
    unittest.main()
