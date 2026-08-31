"""publish: 一批＝一个播出月份，毋是規个 inventory。

本底 `gate()` 是行過規本 inventory ê：任何一筆 pending 無做完，
規批就擋牢。按呢 1 月一登記，2 月就綴咧等——毋過彼兩个月ê工課
本底無相干。使用者裁定（2026-08-31）：**照月份分開把關**。

「一批是一个整體」這條猶原顧牢——干焦是「一批」ê定義換做播出
月份，佮 `plan_month.py`、`fetch_sftp.sh` 講ê仝款。
"""
import unittest
from unittest import mock

from scripts.news import publish


def entry(name, pending=False):
    return {"srt_name": name, "slug": name, "truncated": "",
            "pending": pending}


FEB = "20210223_054_午間_Test_測試"
FEB2 = "20210224_055_午間_Test_測試"
JAN = "20210105_005_午間_Test_測試"


class TestGateByMonth(unittest.TestCase):
    """`gate(entries, month)` 干焦看彼个月ê。"""

    def blocked(self, entries, month, unfinished=()):
        def fake(one):
            if one["srt_name"] in unfinished:
                return "", "視覺辨識尚未讀完"
            return "work", ""
        with mock.patch.object(publish, "publishable", fake):
            return publish.gate(entries, month)

    def test_other_months_pending_does_not_block(self):
        rows = [entry(FEB, pending=True), entry(JAN, pending=True)]
        got = self.blocked(rows, "2021-02", unfinished=[JAN])
        self.assertEqual(got, [])

    def test_this_months_pending_still_blocks(self):
        rows = [entry(FEB, pending=True), entry(JAN, pending=True)]
        got = self.blocked(rows, "2021-02", unfinished=[FEB])
        self.assertEqual([name for name, _ in got], [FEB])

    def test_delivered_episodes_are_never_a_reason(self):
        rows = [entry(FEB, pending=False)]
        got = self.blocked(rows, "2021-02", unfinished=[FEB])
        self.assertEqual(got, [])

    def test_all_or_nothing_holds_inside_the_month(self):
        """仝一个月內底，一集無好勢，彼個月就規個擋牢。"""
        rows = [entry(FEB, pending=True), entry(FEB2, pending=True)]
        got = self.blocked(rows, "2021-02", unfinished=[FEB2])
        self.assertEqual([name for name, _ in got], [FEB2])

    def test_no_month_given_means_the_whole_inventory(self):
        """無講月份ê時，照原本ê款行過規本——予別ê呼叫者袂著。"""
        rows = [entry(FEB, pending=True), entry(JAN, pending=True)]
        got = self.blocked(rows, None, unfinished=[JAN])
        self.assertEqual([name for name, _ in got], [JAN])


class TestClearPending(unittest.TestCase):
    """Pending ê旗只會使清掉**這遍實在有寫出去**ê彼幾集。

    本底是行過規本 inventory 攏清掉——彼是「規本做伙發」ê時ê對做法。
    這馬一遍干焦發一部份月份，若閣攏清，無發ê彼個月會hőng標做已交付，
    store 就講伊有一項無佇咧ê交付物。
    """

    def clear(self, rows, published):
        import json
        import os
        import tempfile
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        tmp.close()
        self.addCleanup(os.unlink, tmp.name)
        with mock.patch.object(publish.paths, "INVENTORY", tmp.name):
            count = publish.clear_pending(rows, published)
        with open(tmp.name, encoding="utf-8") as handle:
            return count, json.load(handle)

    def test_only_published_names_lose_the_flag(self):
        rows = [entry(FEB, pending=True), entry(JAN, pending=True)]
        count, out = self.clear(rows, {FEB})
        self.assertEqual(count, 1)
        by = {}
        for one in out:
            by[one["srt_name"]] = one
        self.assertNotIn("pending", by[FEB])
        self.assertTrue(by[JAN]["pending"])

    def test_nothing_published_clears_nothing(self):
        rows = [entry(FEB, pending=True)]
        count, out = self.clear(rows, set())
        self.assertEqual(count, 0)
        self.assertTrue(out[0]["pending"])


class TestMonthsOf(unittest.TestCase):
    def test_groups_entries_by_broadcast_month(self):
        rows = [entry(FEB), entry(FEB2), entry(JAN)]
        self.assertEqual(publish.months_of(rows), ["2021-01", "2021-02"])

    def test_each_month_appears_once(self):
        rows = [entry(FEB), entry(FEB2)]
        self.assertEqual(publish.months_of(rows), ["2021-02"])


if __name__ == "__main__":
    unittest.main()
