"""讀 Word 97-2003（.doc）的正文——一個 OLE2 複合檔，不是壓縮檔。

盤點初期把《開會了》029 集那兩個 `.doc` 判成壞檔，理由寫「zip 裡沒有
`word/document.xml`」。那是錯的：它們是正常的 Word 97-2003 檔（OLE2 複合
檔，魔術數 ``D0 CF 11 E0 A1 B1 1A E1``），LibreOffice 開得起來。

會誤判是因為當時拿 ``zipfile.is_zipfile()`` 當分派器：Word 會把佈景主題
當一小段 zip 塞在 OLE 檔尾，``is_zipfile()`` 在檔尾找到 EOCD 就回報「是
zip」。所以本模組完全不碰 ``zipfile``，直接走 OLE2 自己的容器格式。

**讀法只服務這個語料實際遇到的兩個檔**，不是通用 OLE2／Word97 函式庫：
目錄項用線性掃描而不是走紅黑樹（真檔案只有個位數個串流，樹用不上）；
文字抽取假設 CLX 裡最多只有 Prc（0x01）記錄接一個 Pcdt（0x02），沒有更
複雜的分片表版本。這些簡化都在真實的兩個檔上驗證過（見模組結尾的手動
核對步驟）。
"""
from scripts.errors import PipelineError

_FREESECT = 0xFFFFFFFF
_ENDOFCHAIN = 0xFFFFFFFE
_DIFSECT = 0xFFFFFFFC
_FATSECT = 0xFFFFFFFD
_NORMAL_SECTOR_CEILING = 0xFFFFFFFA   # 值 >= 這個是特殊標記，不是磁區號


def _u32(data, offset):
    return int.from_bytes(data[offset:offset + 4], "little")


def _u16(data, offset):
    return int.from_bytes(data[offset:offset + 2], "little")


def read_streams(raw):
    """回傳 {串流名: bytes}，走 DIFAT／FAT／miniFAT／目錄。

    只回傳型別為 stream（2）的項目；Root Entry 不算一個串流，只用來定位
    mini stream 的資料。
    """
    if raw[:8] != b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        raise PipelineError("不是 OLE2 複合檔（Word 97-2003）：開頭位元組不符")

    sector_size = 1 << _u16(raw, 30)
    mini_sector_size = 1 << _u16(raw, 32)
    n_fat_sectors = _u32(raw, 44)
    dir_start = _u32(raw, 48)
    mini_fat_start = _u32(raw, 60)
    difat_start = _u32(raw, 68)
    n_difat_sectors = _u32(raw, 72)

    def sector(index):
        offset = 512 + index * sector_size
        chunk = raw[offset:offset + sector_size]
        if len(chunk) != sector_size:
            raise PipelineError("OLE2 磁區 %d 讀不到完整內容（檔案被截斷？）"
                                % index)
        return chunk

    # 前 109 個 FAT 磁區號存在 header 裡；超過的接在 DIFAT 磁區鏈上。
    difat = []
    for i in range(109):
        value = _u32(raw, 76 + i * 4)
        if value < _NORMAL_SECTOR_CEILING:
            difat.append(value)
    cursor = difat_start
    for _ in range(n_difat_sectors):
        if cursor >= _NORMAL_SECTOR_CEILING:
            break
        block = sector(cursor)
        for i in range(0, sector_size - 4, 4):
            value = _u32(block, i)
            if value < _NORMAL_SECTOR_CEILING:
                difat.append(value)
        cursor = _u32(block, sector_size - 4)

    fat = []
    fat_sector_ids = difat[:n_fat_sectors] if n_fat_sectors else difat
    for sector_id in fat_sector_ids:
        block = sector(sector_id)
        for i in range(0, sector_size, 4):
            fat.append(_u32(block, i))

    def chain(start):
        visited = []
        cur = start
        while cur < _NORMAL_SECTOR_CEILING:
            if cur in visited:
                raise PipelineError("OLE2 磁區鏈繞圈：磁區 %d 重複出現" % cur)
            visited.append(cur)
            cur = fat[cur] if cur < len(fat) else _ENDOFCHAIN
        return visited

    def read_chain(start, size=None):
        buf = b"".join(sector(i) for i in chain(start))
        return buf[:size] if size is not None else buf

    dir_bytes = read_chain(dir_start)
    entries = []
    for offset in range(0, len(dir_bytes), 128):
        entry = dir_bytes[offset:offset + 128]
        if len(entry) < 128:
            break
        name_len = _u16(entry, 64)
        if name_len < 2:
            continue      # 未使用的目錄項
        entries.append({
            "name": entry[:name_len - 2].decode("utf-16-le", "replace"),
            "type": entry[66],
            "start": _u32(entry, 116),
            "size": int.from_bytes(entry[120:128], "little"),
        })

    root = next((e for e in entries if e["type"] == 5), None)
    if root is None:
        raise PipelineError("OLE2 目錄裡找不到 Root Entry")

    mini_fat = []
    for sector_id in chain(mini_fat_start):
        block = sector(sector_id)
        for i in range(0, sector_size, 4):
            mini_fat.append(_u32(block, i))

    mini_stream = (read_chain(root["start"], root["size"])
                   if root["size"] else b"")

    def read_mini_chain(start, size):
        out = []
        cur = start
        while cur < _NORMAL_SECTOR_CEILING:
            offset = cur * mini_sector_size
            out.append(mini_stream[offset:offset + mini_sector_size])
            cur = mini_fat[cur] if cur < len(mini_fat) else _ENDOFCHAIN
        return b"".join(out)[:size]

    streams = {}
    for entry in entries:
        if entry["type"] != 2:
            continue
        if entry["size"] < 4096 and mini_stream:
            streams[entry["name"]] = read_mini_chain(
                entry["start"], entry["size"])
        else:
            streams[entry["name"]] = read_chain(entry["start"], entry["size"])
    return streams


# FIB（File Information Block）裡固定偏移的欄位。offset 是相對 WordDocument
# 串流開頭；這些數字是照 [MS-DOC] FibBase／FibRgFcLcb97 核對過真檔案而來。
_FIB_FLAGS = 10          # 2 bytes：bit 9 是 fWhichTblStm
_FIB_FC_CLX = 0x01A2     # 4 bytes：CLX 在 table 串流裡的偏移
_FIB_LCB_CLX = 0x01A6    # 4 bytes：CLX 的長度


def extract_text(raw):
    """一個 .doc 的 bytes → 正文字串。

    流程：選對 table 串流（0Table 或 1Table，看 fWhichTblStm）→ 從 table
    串流取出 CLX → 在 CLX 裡找到 Pcdt（跳過可能在前面的 Prc 記錄）→ 照
    PlcPcd 逐段讀 WordDocument 串流，段落各自標記是壓縮（cp1252，1
    byte/字）還是不壓縮（UTF-16LE，2 byte/字）。
    """
    streams = read_streams(raw)
    if "WordDocument" not in streams:
        raise PipelineError("OLE2 檔缺少 WordDocument 串流")
    word_document = streams["WordDocument"]

    flags = _u16(word_document, _FIB_FLAGS)
    table_name = "1Table" if (flags >> 9) & 1 else "0Table"
    if table_name not in streams:
        raise PipelineError("WordDocument 指定用 %s，但檔案裡沒有這個串流"
                            % table_name)
    table = streams[table_name]

    fc_clx = _u32(word_document, _FIB_FC_CLX)
    lcb_clx = _u32(word_document, _FIB_LCB_CLX)
    clx = table[fc_clx:fc_clx + lcb_clx]

    position = 0
    while position < len(clx) and clx[position] == 0x01:      # Prc，跳過
        cb = _u16(clx, position + 1)
        position += 3 + cb
    if position >= len(clx) or clx[position] != 0x02:          # Pcdt
        raise PipelineError("CLX 裡找不到 Pcdt（分片表），格式不是預期的樣子")

    lcb = _u32(clx, position + 1)
    plc = clx[position + 5:position + 5 + lcb]

    n_runs = (len(plc) - 4) // 12
    char_positions = [_u32(plc, k * 4) for k in range(n_runs + 1)]

    parts = []
    for k in range(n_runs):
        offset = (n_runs + 1) * 4 + k * 8
        fc = _u32(plc, offset + 2)
        compressed = bool(fc & 0x40000000)
        base = (fc & ~0x40000000) // 2 if compressed else fc
        length = char_positions[k + 1] - char_positions[k]
        if compressed:
            piece = word_document[base:base + length]
            chunk = piece.decode("cp1252", "replace")
        else:
            piece = word_document[base:base + length * 2]
            chunk = piece.decode("utf-16-le", "replace")
        parts.append(chunk)
    return "".join(parts)
