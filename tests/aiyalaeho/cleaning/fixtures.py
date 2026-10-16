"""合成一個縮小的開會了 store，給清洗的測試吃。

真的 store 在 Kari-SRT（私人 submodule），測試不能讀它。這裡照真檔的
樣子寫：1-cues 的圖條路徑寫舊名 `strips/…`（真檔就是），2-vision 是
一 cue 兩行的 TSV，3-srt 用正式的 `make_srt` 組出來——所以相鄰同文字
的 cue 會被併成一條，跟交付檔一樣。
"""
import json
import os
import tempfile

from scripts.aiyalaeho import make_srt
from scripts.srtlib import srt


class Store(object):
    """一個暫存目錄底下的 1-cues、2-vision、3-srt 與工作區圖條。"""

    def __init__(self):
        self.root = tempfile.mkdtemp(prefix="aiya-clean-")
        self.cues_dir = os.path.join(self.root, "1-cues")
        self.vision_dir = os.path.join(self.root, "2-vision")
        self.srt_dir = os.path.join(self.root, "3-srt")
        self.work_root = os.path.join(self.root, "work")
        for folder in (self.cues_dir, self.vision_dir, self.srt_dir,
                       self.work_root):
            os.makedirs(folder, exist_ok=True)

    def episode(self, name, cues, strips=True):
        """cues：[(start, end, 族語列, 華語列)…]，cue 編號從 1 起。"""
        manifest = {"cues": [], "duration": cues[-1][1] + 5.0}
        tsv = []
        for index, (start, end, formosan, han) in enumerate(cues, start=1):
            stem = "t%08d" % round(start * 1000)
            manifest["cues"].append({
                "index": index, "start": start, "end": end,
                "images": {"formosan": "strips/%s_formosan.png" % stem,
                           "han": "strips/%s_han.png" % stem}})
            tsv.append("%d\tformosan\t%s" % (index, formosan))
            tsv.append("%d\than\t%s" % (index, han))
            if strips:
                folder = os.path.join(self.work_root, name + ".work",
                                      "2-strips")
                os.makedirs(folder, exist_ok=True)
                for row in ("formosan", "han"):
                    path = os.path.join(folder, "%s_%s.png" % (stem, row))
                    with open(path, "wb") as handle:
                        handle.write(b"\x89PNG\r\n")
        with open(os.path.join(self.cues_dir, name + ".json"), "w",
                  encoding="utf-8") as handle:
            json.dump(manifest, handle, ensure_ascii=False)
        folder = os.path.join(self.vision_dir, name)
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "b01.tsv"), "w",
                  encoding="utf-8") as handle:
            handle.write("\n".join(tsv) + "\n")
        texts = {}
        for index, (_s, _e, formosan, han) in enumerate(cues, start=1):
            texts[str(index)] = {"formosan": formosan, "han": han}
        records = make_srt.records_of(manifest, texts)
        path = os.path.join(self.srt_dir, name + ".srt")
        make_srt.write_srt(path, make_srt.entries_from(records),
                           duration=manifest["duration"])
        return path

    def srt_path(self, name):
        return os.path.join(self.srt_dir, name + ".srt")

    def srt_text(self, name):
        with open(self.srt_path(name), encoding="utf-8") as handle:
            return handle.read()


def parse(text):
    return srt.parse_srt(text)
