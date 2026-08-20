"""asrmt_batch: the shard filter that lets N workers split the batch.

Sharding is by stable inventory position, so concurrent workers never
race for the same episode and a rerun lands on the same partition.
"""
import unittest

from scripts.news import asrmt_batch
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


if __name__ == "__main__":
    unittest.main()
