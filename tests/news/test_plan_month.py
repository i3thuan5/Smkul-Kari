"""plan_month：一批的工作單位是**播出月份**，毋是來源資料夾。

資料夾佮播出月份毋是一對一：全語料有 6 个播出月份散佇兩个資料夾，
而且 `110.1-110.10/7月/` 內底 140 條有 66 條是 2 月的節目。照資料夾做，
做出來的毋是彼个月。

登記閣愛發生佇下載進前——`batches`、`ingest` 攏愛靠 inventory 查逐集的
`srt_name`，而影片切完 cue 就刣掉矣，事後無通掃。
"""
import json
import os
import tempfile
import unittest

from scripts.news import plan_month
from scripts.news import resolve_slug

HEAD = ("節目名稱,年度,集數,播出日期,播出時段,族語別(英),族語別(中),"
        "有無影片,影片檔案位置,音檔位置(mp3),音檔位置(wav),文稿位置,備註")

FEB = "ilrdf-corpus/族語新聞/110.1-110.10/2月原始mxf檔/"
JUL = "ilrdf-corpus/族語新聞/110.1-110.10/7月/"


def line(episode, date, slot, eth_en, eth_zh, paths_, have="是"):
    return ",".join([
        "%s族語新聞" % slot, "2021", episode, date, slot, eth_en, eth_zh,
        have, ";".join(paths_), "", "", "", ""])


ROWS = [
    # 這个月的兩集，來源散佇兩个資料夾
    line("32", "2021-02-01", "午間", "Atayal", "泰雅",
         [FEB + "20NL003_32午間族語新聞.mxf"]),
    line("41", "2021-02-10", "午間", "Cou", "鄒",
         [JUL + "21NL003_41午間族語新聞.mp4"]),
    # 仝一个資料夾內底，毋是這个月的
    line("186", "2021-07-05", "晚間", "Amis", "阿美",
         [JUL + "21NL003_186晚間族語新聞.mp4"]),
    # 這个月，毋過目錄講無影片
    line("34", "2021-02-03", "午間", "Cou", "鄒", [], have="否"),
    # 這个月，兩條候選揀袂出來
    line("44", "2021-02-13", "晚間", "Paiwan", "排灣",
         [JUL + "21NL003_44晚間族語新聞.mp4",
          JUL + "21NL004_44晚間族語新聞.mp4"]),
]


class Fixture(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = tmp.name
        self.catalogue = os.path.join(self.root, "ilrdf-corpus.csv")
        with open(self.catalogue, "w", encoding="utf-8-sig") as handle:
            handle.write(HEAD + "\n")
            for row in ROWS:
                handle.write(row + "\n")
        self.inventory = os.path.join(self.root, "inventory.json")
        self._write_inventory([])

    def _write_inventory(self, entries):
        with open(self.inventory, "w", encoding="utf-8") as handle:
            json.dump(entries, handle, ensure_ascii=False)

    def _read_inventory(self):
        with open(self.inventory, encoding="utf-8") as handle:
            return json.load(handle)

    def _plan(self, month="2021-02"):
        return plan_month.plan(month, resolve_slug.load(self.catalogue),
                               self.inventory)


class TestSelection(Fixture):
    def test_a_month_may_span_two_source_folders(self):
        report = self._plan()
        videos = []
        for entry in report.added:
            videos.append(entry["video"])
        self.assertEqual(len(videos), 2)
        self.assertTrue(any("2月原始mxf檔" in v for v in videos))
        self.assertTrue(any("7月" in v for v in videos))

    def test_other_months_in_the_same_folder_are_not_taken(self):
        report = self._plan()
        for entry in report.added:
            self.assertTrue(entry["播出日期"].startswith("2021-02"),
                            entry["播出日期"])

    def test_each_entry_carries_its_own_remote_path(self):
        report = self._plan()
        for entry in report.added:
            self.assertTrue(entry["video"])
            self.assertIn("族語新聞/", entry["video"])


class TestRegistrationComesFirst(Fixture):
    def test_the_plan_writes_pending_entries(self):
        report = self._plan()
        plan_month.write(report, self.inventory)
        stored = self._read_inventory()
        self.assertEqual(len(stored), 2)
        for entry in stored:
            self.assertTrue(entry["pending"])

    def test_names_are_the_store_naming(self):
        report = self._plan()
        names = []
        for entry in report.added:
            names.append(entry["srt_name"])
        self.assertIn("20210201_032_午間_Atayal_泰雅", names)

    def test_rerunning_does_not_register_twice(self):
        report = self._plan()
        plan_month.write(report, self.inventory)
        again = self._plan()
        self.assertEqual(again.added, [])
        plan_month.write(again, self.inventory)
        self.assertEqual(len(self._read_inventory()), 2)


class TestSkipped(Fixture):
    def test_an_undecidable_episode_is_skipped_not_registered(self):
        report = self._plan()
        plan_month.write(report, self.inventory)
        for entry in self._read_inventory():
            self.assertNotIn("_044_", entry["srt_name"])

    def test_the_skip_report_names_the_episode_and_its_candidates(self):
        report = self._plan()
        self.assertEqual(len(report.skipped), 1)
        label, reason = report.skipped[0]
        self.assertIn("排灣", label)
        self.assertIn("21NL003_44晚間族語新聞.mp4", reason)
        self.assertIn("21NL004_44晚間族語新聞.mp4", reason)

    def test_an_episode_with_no_source_is_only_counted(self):
        report = self._plan()
        self.assertEqual(report.no_source, 1)
        for label, _ in report.skipped:
            self.assertNotIn("2021-02-03", label)


class TestLimit(Fixture):
    """`--limit N`：一改干焦登記 N 集。

    這是「一集一批」的做法。`publish` 的規矩是「有任何 pending 未完成就
    一个字都毋寫」——彼條規矩無愛改，所以改做逐擺只予伊一集通顧。
    """

    def _plan(self, month="2021-02", limit=0):
        return plan_month.plan(month, resolve_slug.load(self.catalogue),
                               self.inventory, limit=limit)

    def test_one_at_a_time(self):
        report = self._plan(limit=1)
        self.assertEqual(len(report.added), 1)

    def test_the_next_run_takes_the_next_one(self):
        first = self._plan(limit=1)
        plan_month.write(first, self.inventory)
        second = self._plan(limit=1)
        self.assertEqual(len(second.added), 1)
        self.assertNotEqual(first.added[0]["srt_name"],
                            second.added[0]["srt_name"])

    def test_broadcast_order_is_kept(self):
        names = []
        for _ in range(2):
            report = self._plan(limit=1)
            plan_month.write(report, self.inventory)
            names.append(report.added[0]["srt_name"])
        self.assertEqual(names, sorted(names))

    def test_zero_means_the_whole_month(self):
        self.assertEqual(len(self._plan(limit=0).added), 2)

    def test_the_skip_report_is_not_truncated_by_the_limit(self):
        # 揀袂出來的集數愛逐擺攏看會著，若無，做到彼集才發現。
        report = self._plan(limit=1)
        self.assertEqual(len(report.skipped), 1)
        self.assertEqual(report.no_source, 1)


class TestTodo(Fixture):
    """抓檔的清單對 inventory 提，毋是對遠端資料夾 ls 提。

    彼是「資料夾≠月份」這條的實作面：一个月的集數會使散佇兩个資料夾，
    ls 一个資料夾提袂齊；而且 ls 出來的檔名嘛無法度講伊是佗一集。
    """

    def _todo(self, month="2021-02"):
        report = self._plan(month)
        plan_month.write(report, self.inventory)
        entries = plan_month.paths.load_inventory(self.inventory)
        return plan_month.todo(month, entries)

    def test_lists_this_months_pending_episodes(self):
        rows = self._todo()
        self.assertEqual(len(rows), 2)
        for slug, video in rows:
            self.assertTrue(slug)
            self.assertTrue(video.startswith("族語新聞/"))

    def test_the_path_is_corpus_relative_ready_for_the_server(self):
        for _slug, video in self._todo():
            self.assertFalse(video.startswith("/"))
            self.assertFalse(video.startswith("ilrdf-corpus/"))

    def test_delivered_episodes_are_not_fetched_again(self):
        report = self._plan()
        entries = []
        for entry in report.entries:
            entries.append(dict(entry, pending=False))
        self.assertEqual(plan_month.todo("2021-02", entries), [])

    def test_another_month_is_not_included(self):
        self._todo()
        entries = plan_month.paths.load_inventory(self.inventory)
        self.assertEqual(plan_month.todo("2021-07", entries), [])


class TestMerge(unittest.TestCase):
    """merge：掃描袂使刣掉別人登記的集數。

    對 `build_inventory` 徙過來的。inventory 佇 store，這爿佮
    `add_episodes` 寫仝一份檔，各人知影的集數無仝。
    """

    def entry(self, slug, **extra):
        base = {"slug": slug, "srt_name": slug, "truncated": ""}
        base.update(extra)
        return base

    def test_keeps_episodes_the_plan_never_saw(self):
        existing = [self.entry("from-sftp"), self.entry("also-from-sftp")]
        merged, added = plan_month.merge([self.entry("planned")], existing)
        slugs = []
        for item in merged:
            slugs.append(item["slug"])
        self.assertEqual(slugs, ["from-sftp", "also-from-sftp", "planned"])
        self.assertEqual(len(added), 1)

    def test_leaves_an_episode_it_already_knows_untouched(self):
        existing = [self.entry("ep", partial="來源僅 11:13",
                               文稿位置="somewhere")]
        planned = [self.entry("ep", truncated="上傳不完整")]
        merged, added = plan_month.merge(planned, existing)
        self.assertEqual(len(merged), 1)
        self.assertEqual(added, [])
        self.assertEqual(merged[0]["partial"], "來源僅 11:13")
        self.assertEqual(merged[0]["truncated"], "")

    def test_running_order_is_stable(self):
        existing = [self.entry("a"), self.entry("b")]
        merged, _ = plan_month.merge(
            [self.entry("b"), self.entry("c")], existing)
        slugs = []
        for item in merged:
            slugs.append(item["slug"])
        self.assertEqual(slugs, ["a", "b", "c"])


if __name__ == "__main__":
    unittest.main()
