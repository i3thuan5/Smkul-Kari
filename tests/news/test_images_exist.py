"""`cues.json` 逐條ê `images` 指ê檔案，磁碟頂懸愛真正有。

這條是別个 session 建議ê，理由真好：**`rebuild --verify` 掠袂著這款**
——伊是對 store ê TSV 重建 SRT，**無去開 strip 檔案**。所以「`images`
指去無彼張圖」會恬恬過關。

Strip 換名（序號 → 起始時間）ê時，這條是主要ê保險：改名佮更新
`images` 是兩步，中央斷去就對袂起來。伊佇遷移進前、進後攏愛綠。

閣有一款會予這條紅ê：`rescan_band` 舊版本無條件用 index 重寫規份
`images`，遷移了後若閣走一遍，`images` 就會指去序號名——毋過磁碟
頂懸是時間名。
"""
import glob
import json
import os
import unittest

from scripts.news import paths


def episodes():
    """(srt_name, work dir, cues.json path) for episodes with strips."""
    out = []
    for entry in paths.load_inventory():
        work = os.path.join(paths.WORK, entry["slug"] + ".B.work")
        book = os.path.join(work, "cues.json")
        if os.path.isdir(os.path.join(work, "strips")) \
                and os.path.exists(book):
            out.append((entry["srt_name"], work, book))
    return out


class TestImagesExist(unittest.TestCase):
    """規批走一遍。無 work dir ê集數（快取清掉ê）跳過。"""

    def test_every_image_a_cue_names_is_on_disk(self):
        missing = []
        checked = 0
        for name, work, book in episodes():
            with open(book, encoding="utf-8") as handle:
                cues = json.load(handle)["cues"]
            for cue in cues:
                for _line, rel in (cue.get("images") or {}).items():
                    checked += 1
                    if not os.path.exists(os.path.join(work, rel)):
                        missing.append("%s cue %d → %s"
                                       % (name, cue["index"], rel))
        self.assertEqual(missing[:8], [],
                         "%d 條 cue ê images 指去無彼張圖（檢查 %d 條）"
                         % (len(missing), checked))

    # 「兩條 cue 袂使指仝一張圖」這條**毋是**真ê，試過才知：
    # `safe_resplit` kā一條 cue 拆做幾若條ê時，逐半本底就是對仝一
    # 張原圖來ê。20210201_032_午間_Atayal_泰雅 ê cue 108–111 四條
    # 攏指 `strips/00103_han.png`——彼是一條hőng拆做四條，正常。
    # 換名了後這條猶原成立：拆出來ê逐半用仝一个起始時間？無——
    # 逐半有家己ê起始時間，所以新名袂仝，毋過磁碟頂懸干焦有原本
    # 彼一張。換名ê時愛照 `images` 走，莫照 cue 走。

    def test_strips_on_disk_are_not_orphaned_wholesale(self):
        """磁碟頂ê圖若濟過 cue 真濟，就是改名做一半停落來。

        寬鬆ê門檻：拆過 cue ê集數本底就會賰幾張孤兒（原本彼條
        hőng拆做兩條，舊彼張賰佇咧），毋過袂到規半。
        """
        bad = []
        for name, work, book in episodes():
            with open(book, encoding="utf-8") as handle:
                cues = json.load(handle)["cues"]
            files = len(glob.glob(os.path.join(work, "strips", "*.png")))
            if files > len(cues) * 1.5:
                bad.append("%s：磁碟 %d 張、cue 才 %d 條"
                           % (name, files, len(cues)))
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
