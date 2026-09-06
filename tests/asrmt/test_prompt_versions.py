"""快取講「這筆是 vN 判ê」，vN ê正文著愛揣會著。

判定快取逐筆攏記版本。彼个記號ê意思是「這筆是照彼陣ê定義判ê」——
定義若無留落來，記號就無意義：後日仔無人知影 v2 佮 v6 差佇佗，嘛
重現袂出來彼陣ê判定。

本底這是一支檔案改八擺、逐擺蓋過去，磁碟頂干焦賰上尾彼版。這條
測試就是欲予彼款情形當場破。
"""
import json
import os
import unittest

from scripts.asrmt import judge

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
CACHE = os.path.join(ROOT, "Kari-SRT", "news", "2-asr", "quality-cache")


class TestVersionsAreKept(unittest.TestCase):
    def test_the_current_version_has_a_file(self):
        self.assertTrue(os.path.exists(judge.prompt_path(
            judge.PROMPT_VERSION)))

    def test_every_kept_version_is_readable(self):
        for version in judge.kept_versions():
            text = judge.prompt_text(version)
            self.assertTrue(text.strip(), version)

    def test_the_live_prompt_is_the_current_version(self):
        self.assertEqual(judge.prompt_text(),
                         judge.prompt_text(judge.PROMPT_VERSION))

    def test_every_version_in_the_cache_can_still_be_read(self):
        """快取內底出現ê版本，一个都袂使揣無。"""
        if not os.path.isdir(CACHE):
            self.skipTest("Kari-SRT 無掛起來")
        used = set()
        for name in sorted(os.listdir(CACHE)):
            if not name.endswith(".jsonl"):
                continue
            with open(os.path.join(CACHE, name), encoding="utf-8") as handle:
                for line in handle:
                    if line.strip():
                        used.add(json.loads(line)["prompt"])
        missing = []
        for version in sorted(used):
            if not os.path.exists(judge.prompt_path(version)):
                missing.append(version)
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
