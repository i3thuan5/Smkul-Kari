"""build_inventory scans a folder; it cannot speak for episodes it never saw.

Since the inventory moved into the store, this and `add_episodes` write the
same file. They know about different episodes: this one scans the February
masters sitting on a local disk, `add_episodes` registers what came over SFTP
and was deleted the moment its cues were cut. A scan that wrote its own
result over the top would delete every SFTP-registered episode -- and on a
machine that only ever used SFTP the folder it scans does not exist at all.
"""
import unittest

from scripts.news import build_inventory


def entry(slug, **extra):
    base = {"slug": slug, "srt_name": slug, "truncated": ""}
    base.update(extra)
    return base


class TestMerge(unittest.TestCase):
    def test_keeps_episodes_the_scan_never_saw(self):
        existing = [entry("from-sftp"), entry("also-from-sftp")]
        merged, added = build_inventory.merge([entry("scanned")], existing)
        slugs = []
        for item in merged:
            slugs.append(item["slug"])
        self.assertEqual(slugs, ["from-sftp", "also-from-sftp", "scanned"])
        self.assertEqual(len(added), 1)

    def test_leaves_an_episode_it_already_knows_untouched(self):
        # The scan sees the original short master; the inventory already
        # records that a complete source turned up later. The scan is the
        # stale one, so it does not get to overwrite.
        existing = [entry("ep", partial="來源僅 11:13", 文稿位置="somewhere")]
        scanned = [entry("ep", truncated="上傳不完整")]
        merged, added = build_inventory.merge(scanned, existing)
        self.assertEqual(len(merged), 1)
        self.assertEqual(added, [])
        self.assertEqual(merged[0]["partial"], "來源僅 11:13")
        self.assertEqual(merged[0]["truncated"], "")

    def test_running_order_is_stable(self):
        # Episodes keep their place, so the tracker rows keep theirs and the
        # rebuilt smkul.csv still compares byte-for-byte.
        existing = [entry("a"), entry("b")]
        merged, _ = build_inventory.merge([entry("b"), entry("c")], existing)
        slugs = []
        for item in merged:
            slugs.append(item["slug"])
        self.assertEqual(slugs, ["a", "b", "c"])


if __name__ == "__main__":
    unittest.main()
