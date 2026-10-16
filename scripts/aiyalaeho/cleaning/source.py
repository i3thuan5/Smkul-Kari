"""讀交付 SRT 的兩列，並從字幕編號找回 cue 與原生圖條。

清洗**以交付 SRT 為準**：編號、時間、兩列文字都從 3-srt 讀，清洗版也是
逐條改 3-srt 的文字行，不在 cue 層改了再重組——重組時文字變得一樣的
相鄰兩條會被 merge_repeats 併掉，編號一位移，對照表就對不上交付版。

看圖要送原生圖條，所以要知道每個字幕編號是哪幾個 cue 組成的。這裡
不另寫組裝：用 `make_srt.records_of` 加 `srtlib.assemble.chain_with_spans`
（交付版就是它們做的）算出每條的真實區間，再找落在區間裡的 cue。
"""
import collections
import json
import os

from scripts import datadirs
from scripts.aiyalaeho import make_srt
from scripts.aiyalaeho import paths
from scripts.aiyalaeho import rebuild
from scripts.errors import PipelineError
from scripts.srtlib import assemble

Entry = collections.namedtuple("Entry", "number start end formosan han")

FORMOSAN_LABEL = make_srt.LABELS[0][1]
HAN_LABEL = make_srt.LABELS[1][1]

# 浮點秒數比較的容差：cue 的起訖與合併後區間是同一批數字，差異只會
# 來自浮點表示。
EPSILON = 1e-6


def read_srt(path):
    """交付 SRT → [Entry…]。時間戳照原字串，不換算。"""
    with open(path, encoding="utf-8") as handle:
        blocks = handle.read().replace("\r\n", "\n").strip().split("\n\n")
    entries = []
    for block in blocks:
        lines = block.split("\n")
        if len(lines) < 3:
            continue
        start, _, end = lines[1].partition(" --> ")
        rows = {FORMOSAN_LABEL: "", HAN_LABEL: ""}
        for line in lines[2:]:
            for label in rows:
                if line.startswith(label):
                    rows[label] = line[len(label):]
        entries.append(Entry(int(lines[0]), start, end,
                             rows[FORMOSAN_LABEL], rows[HAN_LABEL]))
    return entries


def cue_map(srt_name, cues_dir=None, vision_dir=None):
    """{字幕編號: [cue…]}，cue 是 1-cues 清單裡的原樣 dict。"""
    path = paths.stage_path(cues_dir or paths.KARI_CUES, srt_name, ".json")
    with open(path, encoding="utf-8") as handle:
        manifest = json.load(handle)
    texts = rebuild.episode_transcripts(srt_name, vision_dir)
    records = make_srt.records_of(manifest, texts)
    by_index = {}
    for cue in manifest["cues"]:
        by_index[cue["index"]] = cue
    carried = []
    entries = []
    for record in records:
        text = make_srt.entry_text(record)
        if text:
            carried.append(by_index[record["index"]])
            entries.append((record["start"], record["end"], text))
    rows = assemble.chain_with_spans(entries,
                                     duration=manifest.get("duration"))
    out = {}
    for row in rows:
        inside = []
        for cue in carried:
            if (cue["start"] >= row["true_start"] - EPSILON
                    and cue["end"] <= row["true_end"] + EPSILON):
                inside.append(cue)
        out[row["index"]] = inside
    return out


def checked_cue_map(srt_name, srt_path, cues_dir=None, vision_dir=None):
    """cue_map，但先確認條數與交付 SRT 一致，對不上就中止。

    2-vision 改過而 3-srt 沒重組時，對應會整串錯位，送去看圖的就是
    別條字幕的圖。
    """
    mapping = cue_map(srt_name, cues_dir, vision_dir)
    entries = read_srt(srt_path)
    if len(entries) != len(mapping):
        raise PipelineError(
            "%s：交付 SRT 有 %d 條，由 1-cues＋2-vision 組出來是 %d 條；"
            "兩邊不同步，不能用來找圖條"
            % (srt_name, len(entries), len(mapping)))
    for entry in entries:
        if not mapping.get(entry.number):
            raise PipelineError("%s 第 %d 條找不到對應的 cue"
                                % (srt_name, entry.number))
    return mapping


def strips(srt_name, cues, work_root=None):
    """這幾個 cue 的族語列原生圖條路徑。

    清單裡寫的是舊目錄名 `strips/`，實際放在 `2-strips/`，所以只取檔名、
    經 datadirs.strips_dir 解。缺圖就指名集數與 cue，不送空路徑。
    """
    if work_root is None:
        work = paths.work_dir(srt_name)
    else:
        work = os.path.join(work_root, srt_name + ".work")
    out = []
    for cue in cues:
        name = os.path.basename(cue["images"]["formosan"])
        path = os.path.join(datadirs.strips_dir(work), name)
        if not os.path.exists(path):
            raise PipelineError("%s cue %d 的族語列圖條不存在：%s"
                                % (srt_name, cue["index"], path))
        out.append(path)
    return out
