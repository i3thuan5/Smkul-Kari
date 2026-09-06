"""make_all + publish: assembling a batch and then standing behind it.

The rule that matters here is what "finished" means for an episode whose
picture carries no subtitles at all. Three episodes in this corpus are
marked 無字幕 and cut to no cues; the news side's test -- every cue read,
and at least one cue -- reads those as unfinished and would hold the whole
batch open forever.
"""
import json
import os
import shutil
import tempfile
import unittest

from scripts import datadirs
from scripts.aiyalaeho import make_all
from scripts.aiyalaeho import paths
from scripts.aiyalaeho import publish


class Batch(unittest.TestCase):
    """A store and a workspace on disk, wired through paths."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="aiya-batch-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.store = os.path.join(self.tmp, "store")
        self.work = os.path.join(self.tmp, "work")
        self.cues = os.path.join(self.store, "1-cues")
        self.srt = os.path.join(self.store, "3-srt")
        for folder in (self.store, self.work, self.cues, self.srt):
            os.makedirs(folder)
        self.inventory = os.path.join(self.store, "inventory.json")
        self.delivered = os.path.join(self.store, "smkul.csv")
        self.cache = os.path.join(self.work, "smkul.csv")
        self.abnormal = os.path.join(self.store, "smkul-字幕版型異常.csv")
        self.abnormal_cache = os.path.join(self.work,
                                           "smkul-字幕版型異常.csv")
        self._patch(paths, "WORK", self.work)
        self._patch(paths, "KARI_CUES", self.cues)
        self._patch(paths, "SRT_DIR", self.srt)
        self._patch(paths, "INVENTORY", self.inventory)
        self._patch(paths, "TRACKER_STORE", self.delivered)
        self._patch(paths, "TRACKER_CACHE", self.cache)
        self._patch(paths, "ABNORMAL_STORE", self.abnormal)
        self._patch(paths, "ABNORMAL_CACHE", self.abnormal_cache)
        self.entries = []

    def _patch(self, module, name, value):
        old = getattr(module, name)
        setattr(module, name, value)
        self.addCleanup(setattr, module, name, old)

    def add(self, episode, language="Amis", chinese="阿美", cues=2,
            read=None, pending=True, reason="", seconds=None,
            file_name=None):
        name = "開會了_%03d_%s_%s" % (episode, language, chinese)
        entry = {
            "file": "%03d-x.mp4" % episode,
            "video": "ilrdf-corpus/族語節目/開會了/%03d-x.mp4" % episode,
            "srt_name": name,
            "節目名稱": "開會了",
            "集數": str(episode),
            "族語別(英)": language,
            "族語別(中)": chinese,
            "語言別": "",
            "語言代號": "ami",
        }
        if pending:
            entry["pending"] = True
        if reason:
            entry["理由"] = reason
            entry["影片長度秒"] = seconds if seconds is not None else 3000.0
        if file_name:
            entry["file"] = file_name
        self.entries.append(entry)
        self._write_inventory()

        work = os.path.join(self.work, name + ".work")
        os.makedirs(work, exist_ok=True)
        manifest = {"duration": 3000.0,
                    "lines": [{"name": "formosan", "y": 12, "h": 60},
                              {"name": "han", "y": 72, "h": 64}],
                    "cues": []}
        for index in range(1, cues + 1):
            manifest["cues"].append({"index": index,
                                     "start": 10.0 * index,
                                     "end": 10.0 * index + 4.0})
        os.makedirs(os.path.join(work, "1-cues"), exist_ok=True)
        self._json(datadirs.coarse_cues(work), manifest)

        if read is None:
            read = range(1, cues + 1)
        texts = {}
        verified = {}
        for index in read:
            texts[str(index)] = {"formosan": "a%d" % index,
                                 "han": "甲%d" % index}
            verified[str(index)] = {"formosan": True, "han": True}
        self._json(os.path.join(work, "transcripts.json"), texts)
        self._json(os.path.join(work, "verified.json"), verified)
        return name, work

    def _json(self, path, value):
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False)

    def _write_inventory(self):
        self._json(self.inventory, self.entries)

    def delivered_rows(self):
        with open(self.delivered, encoding="utf-8-sig") as handle:
            return handle.read().strip().split("\n")


class TestVisionComplete(Batch):
    def test_every_cue_read_is_complete(self):
        _name, work = self.add(82, cues=2)
        self.assertTrue(make_all.vision_complete(work))

    def test_a_half_read_episode_is_not(self):
        _name, work = self.add(82, cues=3, read=[1, 2])
        self.assertFalse(make_all.vision_complete(work))

    def test_an_episode_with_no_cues_is_complete(self):
        # 無字幕ê集數：無 cue 通讀，就是讀完矣。
        _name, work = self.add(88, cues=0)
        self.assertTrue(make_all.vision_complete(work))

    def test_stale_numbers_do_not_pass_for_missing_ones(self):
        # 數量湊夠袂算數：比ê是編號ê集合。
        _name, work = self.add(82, cues=3, read=[1, 2, 99])
        self.assertFalse(make_all.vision_complete(work))


class TestMakeAll(Batch):
    def test_a_finished_episode_lands_in_the_store(self):
        name, _work = self.add(82, cues=2)
        make_all.main([])
        target = os.path.join(self.srt, name + ".srt")
        self.assertTrue(os.path.exists(target))
        with open(target, encoding="utf-8") as handle:
            self.assertIn("族語：a1", handle.read())

    def test_a_no_subtitle_episode_delivers_an_empty_srt(self):
        name, _work = self.add(88, cues=0)
        make_all.main([])
        target = os.path.join(self.srt, name + ".srt")
        self.assertTrue(os.path.exists(target))
        with open(target, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "")

    def test_the_work_copy_lists_pending_episodes_too(self):
        self.add(82, cues=2)
        self.add(85, cues=2, read=[])
        make_all.main([])
        with open(self.cache, encoding="utf-8-sig") as handle:
            body = handle.read()
        self.assertIn("開會了_082_Amis_阿美", body)
        self.assertIn("開會了_085_Amis_阿美", body)

    def test_the_store_table_is_not_touched_mid_batch(self):
        self.add(82, cues=2)
        make_all.main([])
        self.assertFalse(os.path.exists(self.delivered))


class TestPublish(Batch):
    def test_an_unfinished_pending_episode_holds_the_batch(self):
        self.add(82, cues=2)
        self.add(85, cues=3, read=[1])
        make_all.main([])
        self.assertEqual(publish.main([]), 1)
        self.assertFalse(os.path.exists(self.delivered))
        self.assertTrue(self.entries[0].get("pending"))

    def test_a_finished_batch_is_written_and_cleared(self):
        name, _work = self.add(82, cues=2)
        make_all.main([])
        self.assertEqual(publish.main([]), 0)
        self.assertTrue(os.path.exists(os.path.join(self.cues,
                                                    name + ".json")))
        rows = self.delivered_rows()
        self.assertEqual(len(rows), 2)          # 表頭＋一集
        self.assertIn(name, rows[1])
        after = paths.load_inventory(self.inventory)
        self.assertNotIn("pending", after[0])

    def test_a_no_subtitle_episode_does_not_block_the_batch(self):
        self.add(82, cues=2)
        no_subs, _work = self.add(88, cues=0)
        make_all.main([])
        self.assertEqual(publish.main([]), 0)
        self.assertIn(no_subs, "\n".join(self.delivered_rows()))
        self.assertTrue(os.path.exists(os.path.join(self.cues,
                                                    no_subs + ".json")))

    def test_check_writes_nothing(self):
        self.add(82, cues=2)
        make_all.main([])
        publish.main(["--check"])
        self.assertFalse(os.path.exists(self.delivered))


class TestAbnormalEpisodes(Batch):
    """理由非空ê集：無切、無讀、無組裝、無入 smkul.csv、袂擋定版。"""

    def _abnormal(self, episode=88, reason="無字幕"):
        name = "開會了_%03d_Atayal_泰雅" % episode
        entry = {
            "file": "%d-泰雅語-無字幕.mp4" % episode,
            "video": "ilrdf-corpus/族語節目/開會了/%d-泰雅語-無字幕.mp4"
                     % episode,
            "srt_name": name,
            "節目名稱": "開會了",
            "集數": str(episode),
            "族語別(英)": "Atayal",
            "族語別(中)": "泰雅",
            "語言別": "",
            "語言代號": "tay",
            "pending": True,
            "理由": reason,
            "影片長度秒": 2969.967,
        }
        self.entries.append(entry)
        self._write_inventory()
        return name

    def test_it_is_not_assembled(self):
        name = self._abnormal()
        make_all.main([])
        self.assertFalse(os.path.exists(os.path.join(self.srt,
                                                     name + ".srt")))

    def test_the_status_says_why(self):
        name = self._abnormal(reason="僅華語字幕")
        entries = paths.load_inventory()
        for entry in entries:
            if entry["srt_name"] == name:
                self.assertIn("僅華語字幕", make_all.make_one(entry))

    def test_it_does_not_block_the_batch(self):
        self.add(82, cues=2)
        name = self._abnormal()
        make_all.main([])
        self.assertEqual(publish.main([]), 0)
        self.assertNotIn(name, "\n".join(self.delivered_rows()))

    def test_no_timeline_reaches_the_store(self):
        name = self._abnormal()
        self.add(82, cues=2)
        make_all.main([])
        publish.main([])
        self.assertFalse(os.path.exists(os.path.join(self.cues,
                                                     name + ".json")))

    def test_its_pending_is_cleared(self):
        name = self._abnormal()
        self.add(82, cues=2)
        make_all.main([])
        publish.main([])
        for entry in paths.load_inventory():
            if entry["srt_name"] == name:
                self.assertNotIn("pending", entry)

    def test_it_lands_in_the_second_table(self):
        name = self._abnormal()
        self.add(82, cues=2)
        make_all.main([])
        publish.main([])
        with open(self.abnormal, encoding="utf-8-sig") as handle:
            body = handle.read()
        self.assertIn(name, body)
        self.assertIn("無字幕", body)

    def test_the_work_copy_of_the_second_table_is_refreshed(self):
        self._abnormal()
        make_all.main([])
        self.assertTrue(os.path.exists(self.abnormal_cache))

    def test_the_report_names_a_reason_that_did_not_come_from_the_name(self):
        # 檔名講「雙語字幕」煞予量測判做無字幕ê——愛佇報告點名，
        # 予人做煞了後看一目。
        entry = {
            "file": "106-排灣語-雙語字幕.mp4",
            "video": "ilrdf-corpus/族語節目/開會了/106-排灣語-雙語字幕.mp4",
            "srt_name": "開會了_106_Paiwan_排灣",
            "節目名稱": "開會了", "集數": "106",
            "族語別(英)": "Paiwan", "族語別(中)": "排灣",
            "語言別": "", "語言代號": "pwn", "pending": True,
            "理由": "無字幕", "影片長度秒": 2900.0,
        }
        self.entries.append(entry)
        self._write_inventory()
        self.assertTrue(publish.measured_reasons(paths.load_inventory()))

    def test_a_reason_that_matches_the_file_name_is_not_flagged(self):
        self._abnormal()
        self.assertEqual(publish.measured_reasons(paths.load_inventory()), [])


class TestStoreIsReadable(Batch):
    """寫入 store ê JSON 愛人拍開就看有，而且 diff 看會出改佗一逝。

    閣有一項實際ê理由：另外一條線ê `redump_store` 會kā `1-ocr/1-cues/`
    重排做 indent=2、鍵排序。`publish` 進前是 `copy2`，會kā工作目錄
    彼份（indent=1）蓋轉去，兩爿就輪流蓋來蓋去。排版由這支決定，
    毋是綴來源檔走，這件代誌才停會落來。
    """

    def _stored(self, name):
        path = os.path.join(self.cues, name + ".json")
        with open(path, encoding="utf-8") as handle:
            return handle.read()

    def test_the_timeline_lands_indented_and_key_sorted(self):
        name, work = self.add(82, cues=2)
        # 工作目錄彼份刁工寫做緊縮ê一逝，看 publish 敢有照家己ê排版寫。
        source = datadirs.cues_to_read(work)
        with open(source, encoding="utf-8") as h:
            manifest = json.load(h)
        with open(source, "w", encoding="utf-8") as h:
            json.dump(manifest, h, ensure_ascii=False)
        make_all.main([])
        publish.main([])
        body = self._stored(name)
        self.assertIn("\n", body)
        keys = []
        for line in body.split("\n"):
            stripped = line.strip()
            if stripped.startswith('"') and '":' in stripped:
                if line.startswith("  \""):
                    keys.append(stripped.split('"')[1])
        self.assertEqual(keys, sorted(keys))

    def test_the_stored_timeline_says_the_same_thing(self):
        name, work = self.add(82, cues=2)
        make_all.main([])
        publish.main([])
        with open(datadirs.cues_to_read(work), encoding="utf-8") as h:
            source = json.load(h)
        self.assertEqual(json.loads(self._stored(name)), source)

    def test_the_inventory_is_written_key_sorted(self):
        self.add(82, cues=2)
        make_all.main([])
        publish.main([])
        with open(self.inventory, encoding="utf-8") as handle:
            body = handle.read()
        self.assertIn("\n", body)
        self.assertNotIn("\\u", body)

    def test_publishing_twice_does_not_move_a_byte(self):
        name, _work = self.add(82, cues=2)
        make_all.main([])
        publish.main([])
        with open(os.path.join(self.cues, name + ".json"), "rb") as handle:
            first = handle.read()
        publish.main([])
        with open(os.path.join(self.cues, name + ".json"), "rb") as handle:
            self.assertEqual(handle.read(), first)

    def test_the_qc_file_is_key_sorted(self):
        name, _work = self.add(82, cues=2)
        make_all.main([])
        path = os.path.join(self.srt, name + ".qc.json")
        with open(path, encoding="utf-8") as handle:
            body = handle.read()
        keys = []
        for line in body.split("\n"):
            stripped = line.strip()
            if stripped.startswith('"') and '":' in stripped:
                keys.append(stripped.split('"')[1])
        self.assertEqual(keys, sorted(keys))


if __name__ == "__main__":
    unittest.main()
