"""modeleval.asr_run／mt_run：跑批的續跑佮輸出，服務用假的頂替。"""
import os
import tempfile
import unittest

from scripts.asrmt import mtclient
from scripts.modeleval import asr_run
from scripts.modeleval import mt_run

RAW = "1\n00:00:01,000 --> 00:00:05,000\n族語：ngaʼay ho\n華語：你好\n"


class TestASR(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.out = self._tmp.name
        self.sent = []

    def tearDown(self):
        self._tmp.cleanup()

    def fake_extract(self, video, out):
        with open(out, "wb") as handle:
            handle.write(b"mp3")
        return out

    def fake_recognize(self, server, audio_path, code):
        self.sent.append((os.path.basename(audio_path), code))
        return RAW

    def run_once(self, episodes):
        return asr_run.run(episodes, "http://x/", self.out,
                           recognize=self.fake_recognize,
                           extract=self.fake_extract)

    def test_raw_reply_kept_byte_for_byte_and_audio_removed(self):
        """回傳的 SRT 原樣存（族語華語兩列、ʼ 攏毋改），正規化是計分
        那步的代誌；暫存 mp3 一集 50 分鐘約 6 MB，做完就刪。"""
        self.run_once([("開會了_068_Amis_阿美", "ami-x-skl")])
        path = os.path.join(self.out, "asr", "開會了_068_Amis_阿美.srt")
        with open(path, "rb") as handle:
            self.assertEqual(handle.read(), RAW.encode("utf-8"))
        self.assertEqual(self.sent, [("開會了_068_Amis_阿美.mp3", "ami-x-skl")])
        self.assertEqual(os.listdir(os.path.join(self.out, "audio")), [])

    def test_done_episodes_are_not_resent(self):
        """sapolita 一集愛幾分鐘，斷去重跑袂使閣送做過的。"""
        self.run_once([("a", "ami-x-skl")])
        self.run_once([("a", "ami-x-skl"), ("b", "ami-x-pswl")])
        self.assertEqual(self.sent, [("a.mp3", "ami-x-skl"),
                                     ("b.mp3", "ami-x-pswl")])


class FakeClient(object):
    def __init__(self):
        self.asked = []

    def translate_cached(self, cache, direction, lang, text):
        hit = cache.get(mt_run.mtboth.ENGINE, direction, lang, text)
        if hit is not None:
            return hit
        self.asked.append((direction, lang, text))
        out = "[%s]" % text
        cache.put(mt_run.mtboth.ENGINE, direction, lang, text, out)
        return out


class TestMT(unittest.TestCase):
    def test_every_item_lands_in_the_cache_once(self):
        with tempfile.TemporaryDirectory() as folder:
            cache = mtclient.MTCache(folder)
            client = FakeClient()
            items = [("f2z", "ami_Coas", "cecay"),
                     ("z2f", "ami_Coas", "一")]
            mt_run.run(items, cache, client)
            mt_run.run(items, mtclient.MTCache(folder), client)
            self.assertEqual(client.asked, items)


if __name__ == "__main__":
    unittest.main()
