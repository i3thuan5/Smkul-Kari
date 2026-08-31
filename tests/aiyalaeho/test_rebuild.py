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
        self._patch(paths, "KARI_CUES", self.cues)
        self._patch(paths, "KARI_VISION", self.vision)
        self._patch(paths, "SRT_DIR", self.srt)
        self._patch(paths, "INVENTORY", self.inventory)
        self._patch(paths, "TRACKER_STORE", self.table)
        self.entries = []

    def _patch(self, module, name, value):
        old = getattr(module, name)
        setattr(module, name, value)
        self.addCleanup(setattr, module, name, old)

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

    def test_an_episode_with_no_subtitles_rebuilds_as_an_empty_srt(self):
        name = self.episode(88, cues=0, rows=False)
        self.assertEqual(rebuild.verify(), [])
        with open(os.path.join(self.srt, name + ".srt"),
                  encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "")

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


if __name__ == "__main__":
    unittest.main()
