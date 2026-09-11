"""asrmt_batch: the shard filter that lets N workers split the batch.

Sharding is by stable inventory position, so concurrent workers never
race for the same episode and a rerun lands on the same partition.
"""
import os
import tempfile
import unittest

from scripts.news import asrmt_batch
from scripts.news import paths
from scripts.errors import PipelineError


class TestShard(unittest.TestCase):
    def test_partitions_are_disjoint_and_complete(self):
        taken = []
        for position in range(10):
            owners = []
            for worker in range(3):
                if asrmt_batch.shard_ok(position, worker, 3):
                    owners.append(worker)
            self.assertEqual(len(owners), 1)
            taken.append(owners[0])
        self.assertEqual(sorted(set(taken)), [0, 1, 2])

    def test_single_worker_takes_everything(self):
        for position in range(5):
            self.assertTrue(asrmt_batch.shard_ok(position, 0, 1))

    def test_bad_spec_fails_loud(self):
        with self.assertRaises(PipelineError):
            asrmt_batch.parse_shard("3/3")
        with self.assertRaises(PipelineError):
            asrmt_batch.parse_shard("x")
        self.assertEqual(asrmt_batch.parse_shard("1/3"), (1, 3))


class TestTodoSelection(unittest.TestCase):
    """揀愛做的集數。

    「一集做到底」這款流程，語音側是佇 publish **進前**跑的——順序是
    OCR → 2-srt-raw → publish。所以 pending 的集數袂使一律跳過；指名
    彼集的時陣，是呼叫端咧講「這集的 cue 佮視覺逐字稿攏齊矣」，若無
    齊，`step_entries` 家己會大聲失敗。
    """

    def _entries(self):
        return [{"srt_name": "20210101_001_午間_Rukai_魯凱", "pending": True},
                {"srt_name": "20210102_002_午間_Seediq_賽德克", "pending": True},
                {"srt_name": "20210201_032_午間_Atayal_泰雅",
                 }]

    def _names(self, todo):
        out = []
        for entry in todo:
            out.append(entry["srt_name"])
        return out

    def test_pending_is_skipped_by_default(self):
        with tempfile.TemporaryDirectory() as raw:
            todo = asrmt_batch._todo(self._entries(), 0, 1, raw)
        self.assertEqual(self._names(todo),
                         ["20210201_032_午間_Atayal_泰雅"])

    def test_naming_one_episode_takes_it_even_while_pending(self):
        want = "20210101_001_午間_Rukai_魯凱"
        with tempfile.TemporaryDirectory() as raw:
            todo = asrmt_batch._todo(self._entries(), 0, 1, raw, only=want)
        self.assertEqual(self._names(todo), [want])

    def test_naming_one_episode_takes_only_that_one(self):
        with tempfile.TemporaryDirectory() as raw:
            todo = asrmt_batch._todo(self._entries(), 0, 1, raw,
                                     only="20210201_032_午間_Atayal_泰雅")
        self.assertEqual(self._names(todo),
                         ["20210201_032_午間_Atayal_泰雅"])

    def test_an_episode_that_already_has_its_raw_srt_is_done(self):
        name = "20210101_001_午間_Rukai_魯凱"
        with tempfile.TemporaryDirectory() as raw:
            path = paths.stage_path(raw, name, ".srt")
            os.makedirs(os.path.dirname(path))
            open(path, "w").close()
            todo = asrmt_batch._todo(self._entries(), 0, 1, raw, only=name)
        self.assertEqual(todo, [])


if __name__ == "__main__":
    unittest.main()
