"""rebuild: put every delivered SRT back together from the store alone.

This is the store's core promise in executable form -- code plus
`1-cues/` plus `2-vision/` reproduce `3-srt/` and `smkul.csv` byte for
byte, with no video and no model. If it holds, everything in the
workspace really is a cache.
"""
import json
import os
import shutil
import tempfile
import unittest

from scripts.aiyalaeho import paths
from scripts.aiyalaeho import rebuild
from scripts.aiyalaeho import tracker
from scripts.errors import PipelineError


class Store(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="aiya-rebuild-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.cues = os.path.join(self.tmp, "1-cues")
        self.vision = os.path.join(self.tmp, "2-vision")
        self.srt = os.path.join(self.tmp, "3-srt")
        for folder in (self.cues, self.vision, self.srt):
            os.makedirs(folder)
        self.inventory = os.path.join(self.tmp, "inventory.json")
        self.table = os.path.join(self.tmp, "smkul.csv")
        self.abnormal = os.path.join(self.tmp, "smkul-字幕版型異常.csv")
        self._patch(paths, "KARI_CUES", self.cues)
        self._patch(paths, "KARI_VISION", self.vision)
        self._patch(paths, "SRT_DIR", self.srt)
        self._patch(paths, "INVENTORY", self.inventory)
        self._patch(paths, "TRACKER_STORE", self.table)
        self._patch(paths, "ABNORMAL_STORE", self.abnormal)
        self.entries = []

    def _patch(self, module, name, value):
        old = getattr(module, name)
        setattr(module, name, value)
        self.addCleanup(setattr, module, name, old)

    def abnormal_episode(self, number, reason="無字幕", seconds=2969.967,
                         pending=False):
        """登記矣、有理由、`1-ocr/` 底下一隻檔都無ê集。"""
        name = "開會了_%03d_Atayal_泰雅" % number
        entry = {
            "file": "%d-泰雅語-無字幕.mp4" % number,
            "video": "ilrdf-corpus/族語節目/開會了/%d-泰雅語-無字幕.mp4"
                     % number,
            "srt_name": name,
            "節目名稱": "開會了",
            "集數": str(number),
            "族語別(英)": "Atayal",
            "族語別(中)": "泰雅",
            "語言別": "",
            "語言代號": "tay",
            "理由": reason,
            "影片長度秒": seconds,
        }
        if pending:
            entry["pending"] = True
        self.entries.append(entry)
        self._write_inventory()
        self.deliver()
        return name

    def episode(self, number, cues=2, rows=True, pending=False,
                deliver=True):
        name = "開會了_%03d_Amis_阿美" % number
        entry = {
            "file": "%03d-x.mp4" % number,
            "video": "ilrdf-corpus/族語節目/開會了/%03d-x.mp4" % number,
            "srt_name": name,
            "節目名稱": "開會了",
            "集數": str(number),
            "族語別(英)": "Amis",
            "族語別(中)": "阿美",
            "語言別": "",
            "語言代號": "ami",
        }
        if pending:
            entry["pending"] = True
        self.entries.append(entry)

        manifest = {"duration": 3000.0,
                    "lines": [{"name": "formosan", "y": 12, "h": 60},
                              {"name": "han", "y": 72, "h": 64}],
                    "cues": []}
        for index in range(1, cues + 1):
            manifest["cues"].append({"index": index, "start": 10.0 * index,
                                     "end": 10.0 * index + 4.0})
        with open(os.path.join(self.cues, name + ".json"), "w",
                  encoding="utf-8") as handle:
            json.dump(manifest, handle, ensure_ascii=False)

        if rows and cues:
            folder = os.path.join(self.vision, name)
            os.makedirs(folder, exist_ok=True)
            lines = []
            for index in range(1, cues + 1):
                lines.append("%d\tformosan\ta%d" % (index, index))
                lines.append("%d\than\t甲%d" % (index, index))
            with open(os.path.join(folder, "b01.tsv"), "w",
                      encoding="utf-8") as handle:
                handle.write("\n".join(lines) + "\n")

        self._write_inventory()
        if deliver:
            self.deliver()
        return name

    def _write_inventory(self):
        with open(self.inventory, "w", encoding="utf-8") as handle:
            json.dump(self.entries, handle, ensure_ascii=False)

    def deliver(self):
        """Produce the deliverables the way the pipeline would have."""
        built = rebuild.rebuild_all()
        for name in built["srt"]:
            with open(os.path.join(self.srt, name + ".srt"), "w",
                      encoding="utf-8") as handle:
                handle.write(built["srt"][name])
        tracker.write_tracker(built["rows"], self.table)
        if built["abnormal"]:
            tracker.write_tracker(built["abnormal"], self.abnormal,
                                  tracker.ABNORMAL_FIELDS)


class TestRebuild(Store):
    def test_a_delivered_batch_rebuilds_byte_for_byte(self):
        self.episode(68)
        self.episode(82, cues=3)
        self.assertEqual(rebuild.verify(), [])

    def test_the_two_rows_come_back_labelled(self):
        name = self.episode(68)
        with open(os.path.join(self.srt, name + ".srt"),
                  encoding="utf-8") as handle:
            body = handle.read()
        self.assertIn("族語：a1", body)
        self.assertIn("華語：甲1", body)

    def test_an_abnormal_episode_needs_no_inputs_at_all(self):
        # 無切、無讀、無組裝——`1-ocr/` 底下一隻檔都無，猶原愛過。
        self.episode(68)
        self.abnormal_episode(88)
        self.assertEqual(rebuild.verify(), [])

    def test_a_changed_deliverable_is_reported(self):
        name = self.episode(68)
        with open(os.path.join(self.srt, name + ".srt"), "a",
                  encoding="utf-8") as handle:
            handle.write("\n999\n00:00:01,000 --> 00:00:02,000\n族語：x\n")
        self.assertEqual(rebuild.verify(), [name + ".srt"])

    def test_a_changed_table_is_reported(self):
        self.episode(68)
        with open(self.table, "a", encoding="utf-8") as handle:
            handle.write("開會了,99,Amis,阿美,,ami,x,,開會了_099_Amis_阿美\n")
        self.assertEqual(rebuild.verify(), ["smkul.csv"])


class TestMissing(Store):
    def test_a_missing_timeline_is_named(self):
        name = self.episode(68)
        os.remove(os.path.join(self.cues, name + ".json"))
        with self.assertRaises(PipelineError):
            rebuild.verify()

    def test_missing_transcripts_are_named(self):
        name = self.episode(68)
        shutil.rmtree(os.path.join(self.vision, name))
        problems = rebuild.check_inputs(paths.load_inventory())
        self.assertEqual(len(problems), 1)
        self.assertIn(name, problems[0])

    def test_a_pending_episode_is_skipped_not_demanded(self):
        # 登記矣、猶未做煞ê集數：無交付品嘛袂使予驗證失敗。
        self.episode(68)
        self.entries.append({
            "file": "085-x.mp4",
            "video": "ilrdf-corpus/族語節目/開會了/085-x.mp4",
            "srt_name": "開會了_085_Amis_阿美",
            "節目名稱": "開會了", "集數": "85",
            "族語別(英)": "Amis", "族語別(中)": "阿美",
            "語言別": "", "語言代號": "ami", "pending": True})
        self._write_inventory()
        self.assertEqual(rebuild.check_inputs(paths.load_inventory()), [])
        self.assertEqual(rebuild.verify(), [])


class TestAbnormalTable(Store):
    """第二張表嘛愛干焦靠 store 逐 byte 重建會出來。"""

    def test_it_is_rebuilt_and_compared(self):
        self.episode(68)
        self.abnormal_episode(88)
        self.assertEqual(rebuild.verify(), [])

    def test_a_changed_second_table_is_reported(self):
        self.episode(68)
        self.abnormal_episode(88)
        with open(self.abnormal, "a", encoding="utf-8") as handle:
            handle.write("開會了,99,Amis,阿美,,ami,x,,開會了_099_Amis_阿美,"
                         "無字幕\n")
        self.assertEqual(rebuild.verify(),
                         [os.path.basename(self.abnormal)])

    def test_its_length_comes_from_the_inventory_not_a_video(self):
        self.episode(68)
        self.abnormal_episode(88, seconds=2969.967)
        rebuild.verify()
        with open(self.abnormal, encoding="utf-8-sig") as handle:
            self.assertIn("00:49:30", handle.read())

    def test_a_missing_second_table_is_named(self):
        self.episode(68)
        self.abnormal_episode(88)
        os.remove(self.abnormal)
        with self.assertRaises(PipelineError):
            rebuild.verify()

    def test_no_abnormal_episodes_means_no_second_table_is_required(self):
        self.episode(68)
        self.assertFalse(os.path.exists(self.abnormal))
        self.assertEqual(rebuild.verify(), [])


if __name__ == "__main__":
    unittest.main()
