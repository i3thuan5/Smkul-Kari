"""claude_mt: batch files out, disciplined ingest back.

Same rules the vision pass earned the hard way: the reply must carry
exactly the requested ids -- a stranger id or a missing line rejects the
whole batch, because a silently mis-numbered translation lands on the
wrong subtitle and nothing downstream can tell.
"""
import os
import tempfile
import unittest

from scripts.asrmt.align import claude_mt
from scripts.asrmt.align import mtclient


class Fixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.cache = mtclient.MTCache(os.path.join(self.root, "mt-cache"))

    def tearDown(self):
        self._tmp.cleanup()

    def _reply(self, name, text):
        path = os.path.join(self.root, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path


class TestWriteBatches(unittest.TestCase):
    def test_batches_are_numbered_and_capped(self):
        with tempfile.TemporaryDirectory() as tmp:
            items = []
            for i in range(5):
                items.append((i + 1, "kamu %d" % i))
            paths = claude_mt.write_batches(items, "f2z", "ami_Xiug",
                                            tmp, size=2)
        names = []
        for path in paths:
            names.append(os.path.basename(path))
        self.assertEqual(names, ["b01.f2z.tsv", "b02.f2z.tsv",
                                 "b03.f2z.tsv"])

    def test_empty_texts_are_not_sent_for_translation(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = claude_mt.write_batches([(1, "kako"), (2, "")],
                                            "f2z", "ami_Xiug", tmp)
            with open(paths[0], encoding="utf-8") as handle:
                body = handle.read()
        self.assertIn("1\tkako", body)
        self.assertNotIn("2\t", body)


class TestIngest(Fixture):
    def _request(self):
        return self._reply("b01.f2z.tsv", "3\tkako\n7\tmikeriday\n")

    def test_a_good_reply_lands_in_the_cache(self):
        request = self._request()
        reply = self._reply("b01.reply.tsv", "3\t我\n7\t主持\n")
        count = claude_mt.ingest_reply(request, reply, self.cache,
                                       "f2z", "ami_Xiug")
        self.assertEqual(count, 2)
        self.assertEqual(
            self.cache.get("claude", "f2z", "ami_Xiug", "kako"), "我")
        self.assertEqual(
            self.cache.get("claude", "f2z", "ami_Xiug", "mikeriday"),
            "主持")

    def test_a_stranger_id_rejects_the_whole_batch(self):
        request = self._request()
        reply = self._reply("b01.reply.tsv", "3\t我\n99\t幽靈\n7\t主持\n")
        with self.assertRaises(SystemExit):
            claude_mt.ingest_reply(request, reply, self.cache,
                                   "f2z", "ami_Xiug")
        self.assertIsNone(
            self.cache.get("claude", "f2z", "ami_Xiug", "kako"))

    def test_a_missing_line_rejects_the_whole_batch(self):
        request = self._request()
        reply = self._reply("b01.reply.tsv", "3\t我\n")
        with self.assertRaises(SystemExit):
            claude_mt.ingest_reply(request, reply, self.cache,
                                   "f2z", "ami_Xiug")

    def test_a_duplicate_id_rejects_the_whole_batch(self):
        request = self._request()
        reply = self._reply("b01.reply.tsv", "3\t我\n3\t我再\n7\t主持\n")
        with self.assertRaises(SystemExit):
            claude_mt.ingest_reply(request, reply, self.cache,
                                   "f2z", "ami_Xiug")

    def test_translation_may_itself_contain_a_tab(self):
        request = self._reply("b02.f2z.tsv", "1\tkako\n")
        reply = self._reply("b02.reply.tsv", "1\t我\t真的\n")
        claude_mt.ingest_reply(request, reply, self.cache,
                               "f2z", "ami_Xiug")
        self.assertEqual(
            self.cache.get("claude", "f2z", "ami_Xiug", "kako"), "我\t真的")


if __name__ == "__main__":
    unittest.main()
