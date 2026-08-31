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
        self._patch(paths, "WORK", self.work)
        self._patch(paths, "KARI_CUES", self.cues)
        self._patch(paths, "SRT_DIR", self.srt)
        self._patch(paths, "INVENTORY", self.inventory)
        self._patch(paths, "TRACKER_STORE", self.delivered)
        self._patch(paths, "TRACKER_CACHE", self.cache)
        self.entries = []

    def _patch(self, module, name, value):
        old = getattr(module, name)
        setattr(module, name, value)
        self.addCleanup(setattr, module, name, old)

    def add(self, episode, language="Amis", chinese="阿美", cues=2,
            read=None, pending=True):
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
        self._json(os.path.join(work, "cues.json"), manifest)

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


if __name__ == "__main__":
    unittest.main()
