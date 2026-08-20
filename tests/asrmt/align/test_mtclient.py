"""mtclient: session handshake order, content-addressed cache, resume.

Pins the asr-bilingual-srt spec's 翻譯快取與可續跑 requirement: same
key never hits the service twice, a rerun continues from the cache, one
request at a time with a pause in between -- all against a fake
transport, no network.
"""
import os
import tempfile
import unittest

from scripts.asrmt.align import mtclient
from tests.asrmt import fixtures


def client_with(script, sleeps=None):
    transport = fixtures.FakeTransport(script)
    if sleeps is None:
        sleeps = []
    client = mtclient.MTClient(transport=transport,
                               pause=1.5, sleep=sleeps.append)
    return client, transport, sleeps


class TestHandshake(unittest.TestCase):
    def test_lambda_precedes_translate_and_runs_once_per_lang(self):
        client, transport, _ = client_with({
            ("lambda", "泰雅"): "ok",
            ("translate", "Blaq su hug"): "你好嗎",
            ("translate", "Blaq balay"): "很好",
        })
        client.translate("f2z", "tay_Seko", "Blaq su hug")
        client.translate("f2z", "tay_Seko", "Blaq balay")
        endpoints = []
        for endpoint, _ in transport.requests:
            endpoints.append(endpoint)
        self.assertEqual(endpoints, ["lambda", "translate", "translate"])

    def test_reverse_direction_uses_the_underscore_one_endpoints(self):
        client, transport, _ = client_with({
            ("lambda_1", "阿美"): "ok",
            ("translate_1", "我要說的是"): "O sasowalen ako",
        })
        got = client.translate("z2f", "ami_Xiug", "我要說的是")
        self.assertEqual(got, "O sasowalen ako")
        endpoints = []
        for endpoint, _ in transport.requests:
            endpoints.append(endpoint)
        self.assertEqual(endpoints, ["lambda_1", "translate_1"])

    def test_empty_text_never_reaches_the_service(self):
        client, transport, _ = client_with({})
        self.assertEqual(client.translate("f2z", "ami_Xiug", ""), "")
        self.assertEqual(transport.requests, [])


class TestPause(unittest.TestCase):
    def test_a_pause_separates_consecutive_service_calls(self):
        client, _, sleeps = client_with({
            ("lambda", "阿美"): "ok",
            ("translate", "cecay"): "一",
            ("translate", "tosa"): "二",
        })
        client.translate("f2z", "ami_Xiug", "cecay")
        client.translate("f2z", "ami_Xiug", "tosa")
        self.assertTrue(sleeps)
        for value in sleeps:
            self.assertEqual(value, 1.5)


class TestCache(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.cachedir = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_hit_makes_no_request_and_miss_is_persisted(self):
        cache = mtclient.MTCache(self.cachedir)
        client, transport, _ = client_with({
            ("lambda", "阿美"): "ok",
            ("translate", "kako"): "我",
        })
        first = client.translate_cached(cache, "ailabs", "f2z",
                                        "ami_Xiug", "kako")
        again = client.translate_cached(cache, "ailabs", "f2z",
                                        "ami_Xiug", "kako")
        self.assertEqual(first, "我")
        self.assertEqual(again, "我")
        translate_calls = 0
        for endpoint, _ in transport.requests:
            if endpoint == "translate":
                translate_calls += 1
        self.assertEqual(translate_calls, 1)

    def test_a_rerun_reads_yesterdays_cache_from_disk(self):
        cache = mtclient.MTCache(self.cachedir)
        cache.put("claude", "f2z", "ami_Xiug", "kako", "我")
        reopened = mtclient.MTCache(self.cachedir)
        self.assertEqual(reopened.get("claude", "f2z", "ami_Xiug", "kako"),
                         "我")
        self.assertTrue(os.path.exists(
            os.path.join(self.cachedir, "claude.jsonl")))

    def test_engines_do_not_share_entries(self):
        cache = mtclient.MTCache(self.cachedir)
        cache.put("claude", "f2z", "ami_Xiug", "kako", "我（claude）")
        self.assertIsNone(cache.get("ailabs", "f2z", "ami_Xiug", "kako"))


if __name__ == "__main__":
    unittest.main()
