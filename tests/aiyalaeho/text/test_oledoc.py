"""讀 Word 97-2003（.doc，OLE2 複合檔）的正文。

盤點初期把開會029 那兩個 `.doc` 判成壞檔，理由寫「zip 裡沒有
`word/document.xml`」。那是錯的：它們是正常的 Word 97-2003 檔，
`zipfile.is_zipfile()` 對 OLE2 回傳 True 是因為 Word 把佈景主題當一小段
zip 塞在 OLE 檔尾——這正是本模組要避開、不要重蹈的坑。

fixture 全部程式化組出最小 OLE2 複合檔，不放二進位檔進 repo。真檔案的
驗證留給 `scripts/aiyalaeho/text/oledoc.py` 模組文件裡記的手動核對步驟。
"""
import struct
import unittest

from scripts.aiyalaeho.text import oledoc

FREESECT = 0xFFFFFFFF
ENDOFCHAIN = 0xFFFFFFFE
FATSECT = 0xFFFFFFFD
NOSTREAM = 0xFFFFFFFF
SECT = 512
MINI = 64


def _u16(v):
    return struct.pack("<H", v)


def _u32(v):
    return struct.pack("<I", v)


def _dir_entry(name, obj_type, start, size):
    """一逝 128-byte 目錄項；毋免建紅黑樹指標——這个模組ê讀法是逐逝
    掃過去揣類型佮名，毋是行樹（真檔案嘛是仝款方式驗過ê），所以左右
    子節點統一寫 NOSTREAM 就好。
    """
    name_utf16 = name.encode("utf-16-le")
    raw_name = (name_utf16 + b"\x00\x00").ljust(64, b"\x00")
    namelen = len(name_utf16) + 2
    entry = bytearray(128)
    entry[0:64] = raw_name
    entry[64:66] = _u16(namelen)
    entry[66] = obj_type
    entry[67] = 1
    entry[68:72] = _u32(NOSTREAM)
    entry[72:76] = _u32(NOSTREAM)
    entry[76:80] = _u32(NOSTREAM)
    entry[116:120] = _u32(start)
    entry[120:128] = struct.pack("<Q", size)
    return bytes(entry)


def build_ole2(streams):
    """組一个上蓋簡單、猶原合法ê OLE2 複合檔。

    逐个串流攏行 mini stream（<4096 bytes）——毋是因為真正ê .doc 是
    按呢（開會029 彼兩个實際上攏行一般 FAT，因為超過 4096），是為著
    予這个 fixture 細細粒、閣會使試著 miniFAT 這條路。streams 上濟
    3 逝（加 Root Entry 拄好 4 逝排滿一个目錄磁區）。
    """
    if len(streams) > 3:
        raise ValueError("fixture 干焦支援上濟 3 个串流")

    blob = bytearray()
    minifat_entries = []
    starts = {}
    for name, data in streams.items():
        n = max(1, -(-len(data) // MINI))
        first = len(minifat_entries)
        starts[name] = first
        for i in range(n):
            chunk = data[i * MINI:(i + 1) * MINI].ljust(MINI, b"\x00")
            blob.extend(chunk)
            minifat_entries.append(
                first + i + 1 if i < n - 1 else ENDOFCHAIN)
    root_size = len(blob)
    root_data_sectors = max(1, -(-root_size // SECT))

    fat = [FREESECT] * 128
    fat[0] = FATSECT
    fat[1] = ENDOFCHAIN
    fat[2] = ENDOFCHAIN
    for i in range(root_data_sectors):
        sec = 3 + i
        fat[sec] = (sec + 1) if i < root_data_sectors - 1 else ENDOFCHAIN

    entries = [_dir_entry("Root Entry", 5, 3, root_size)]
    for name, data in streams.items():
        entries.append(_dir_entry(name, 2, starts[name], len(data)))
    while len(entries) < 4:
        entries.append(b"\x00" * 128)
    dir_sector = b"".join(entries)

    minifat_sector = bytearray(b"\xff" * 512)
    for i, val in enumerate(minifat_entries):
        struct.pack_into("<I", minifat_sector, i * 4, val)

    fat_sector = b"".join(_u32(v) for v in fat)

    header = bytearray(512)
    header[0:8] = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
    header[24:26] = _u16(0x003E)
    header[26:28] = _u16(0x0003)
    header[28:30] = b"\xfe\xff"
    header[30:32] = _u16(9)     # sector shift: 2**9 = 512
    header[32:34] = _u16(6)     # mini sector shift: 2**6 = 64
    header[40:44] = _u32(0)
    header[44:48] = _u32(1)     # 一逝 FAT 磁區
    header[48:52] = _u32(1)     # 目錄磁區起始
    header[52:56] = _u32(0)
    header[56:60] = _u32(0x1000)
    header[60:64] = _u32(2)     # miniFAT 磁區起始
    header[64:68] = _u32(1)     # 一逝 miniFAT 磁區
    header[68:72] = _u32(ENDOFCHAIN)
    header[72:76] = _u32(0)
    difat = bytearray(b"\xff" * (109 * 4))
    struct.pack_into("<I", difat, 0, 0)
    header[76:512] = difat

    data_sectors = bytes(blob).ljust(root_data_sectors * SECT, b"\x00")

    body = fat_sector + dir_sector + bytes(minifat_sector) + data_sectors
    return bytes(header) + body


def build_word97(runs, table_name="1Table", other_table_junk=b"JUNK"):
    """組一份最小ê Word97 WordDocument＋table 串流。

    runs：[(文字, 是毋是壓縮ê)] 一組一組接落去。壓縮ê行 cp1252（1
    byte／字），無壓縮ê行 UTF-16LE（2 byte／字）——這就是 CLX/PlcPcd
    分片表會使混用兩種編碼ê彼件事。
    """
    text_base = 0x300     # 拄好過 FIB 固定區（到 0x1AA），免濟想
    wd = bytearray(text_base)
    flags = 0x0200 if table_name == "1Table" else 0x0000
    wd[10:12] = struct.pack("<H", flags)

    cps = [0]
    pcd_list = []
    cursor = text_base
    for text, compressed in runs:
        if compressed:
            raw_bytes = text.encode("cp1252")
            fc = (cursor * 2) | 0x40000000
        else:
            raw_bytes = text.encode("utf-16-le")
            fc = cursor
        wd.extend(raw_bytes)
        pcd_list.append(b"\x00\x00" + struct.pack("<I", fc) + b"\x00\x00")
        cps.append(cps[-1] + len(text))
        cursor += len(raw_bytes)

    plc = b"".join(struct.pack("<I", c) for c in cps) + b"".join(pcd_list)
    clx = b"\x02" + struct.pack("<I", len(plc)) + plc

    wd[0x01A2:0x01A6] = struct.pack("<I", 0)
    wd[0x01A6:0x01AA] = struct.pack("<I", len(clx))

    other_name = "0Table" if table_name == "1Table" else "1Table"
    return bytes(wd), {table_name: clx, other_name: other_table_junk}


class TestContainer(unittest.TestCase):
    """走 FAT／miniFAT／目錄取著串流，內容照原樣，字節毋捌走精。"""

    def test_gets_back_the_exact_bytes_of_each_stream(self):
        raw = build_ole2({
            "WordDocument": b"hello world" * 5,
            "1Table": b"table stream content here",
        })
        streams = oledoc.read_streams(raw)
        self.assertEqual(streams["WordDocument"], b"hello world" * 5)
        self.assertEqual(streams["1Table"], b"table stream content here")

    def test_single_small_stream_round_trips(self):
        raw = build_ole2({"WordDocument": b"x"})
        streams = oledoc.read_streams(raw)
        self.assertEqual(streams["WordDocument"], b"x")


class TestTableSelection(unittest.TestCase):
    """fWhichTblStm（flags 的 bit 9）決定用 0Table 抑是 1Table；選毋著
    就解毋出正確ê分片表，會讀著另外一份無仝ê內容。
    """

    def test_flag_set_reads_1table(self):
        wd, tables = build_word97([("only in 1Table", True)],
                                  table_name="1Table",
                                  other_table_junk=b"\x02" + b"\x00" * 60)
        streams = {"WordDocument": wd}
        streams.update(tables)
        raw = build_ole2(streams)
        self.assertEqual(oledoc.extract_text(raw), "only in 1Table")

    def test_flag_clear_reads_0table(self):
        wd, tables = build_word97([("only in 0Table", True)],
                                  table_name="0Table",
                                  other_table_junk=b"\x02" + b"\x00" * 60)
        streams = {"WordDocument": wd}
        streams.update(tables)
        raw = build_ole2(streams)
        self.assertEqual(oledoc.extract_text(raw), "only in 0Table")


class TestDualEncoding(unittest.TestCase):
    """分片表ê逐條紀錄各自標記是壓縮（cp1252，1 byte／字）抑是
    UTF-16LE（2 byte／字），兩種攏愛解會開，中文一定行後者。
    """

    def test_compressed_run_decodes_via_cp1252(self):
        wd, tables = build_word97([("ke' na", True)])
        streams = {"WordDocument": wd}
        streams.update(tables)
        raw = build_ole2(streams)
        self.assertEqual(oledoc.extract_text(raw), "ke' na")

    def test_uncompressed_run_decodes_via_utf16(self):
        wd, tables = build_word97([("意思", False)])
        streams = {"WordDocument": wd}
        streams.update(tables)
        raw = build_ole2(streams)
        self.assertEqual(oledoc.extract_text(raw), "意思")

    def test_mixed_runs_concatenate_in_order(self):
        wd, tables = build_word97([("ke' na", True), ("意思", False)])
        streams = {"WordDocument": wd}
        streams.update(tables)
        raw = build_ole2(streams)
        self.assertEqual(oledoc.extract_text(raw), "ke' na意思")


if __name__ == "__main__":
    unittest.main()
