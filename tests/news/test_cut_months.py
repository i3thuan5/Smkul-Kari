"""cut_months：一個月接一個月跑 `fetch_sftp.sh`，磁碟不夠就停下來等。

量到的（2026-09-24）：一集 work dir 約 345 MB（圖條 141 MB、判斷格
132 MB、組合圖 67 MB），2024-12 一個月 69 集就是 23 GB；那時磁碟
只剩 42 GB。2021-11～2024-11 剩下的集數全部切完要好幾百 GB，所以
不可以一口氣切完再讀字——每個月開始前要看剩多少，不夠就等讀字那邊
入庫、清掉 work dir 再切。月份中途不檢查：一個月開始了就讓它做完，
門檻要留夠一個月的量。

離線：`fetch_sftp.sh`、`plan_month --todo`、磁碟、時鐘、睡眠全部注入。
"""
import csv
import os
import tempfile
import unittest

from scripts.news import cut_months


class TestMonthRange(unittest.TestCase):

    def test_the_range_crosses_years_and_keeps_both_ends(self):
        got = cut_months.month_range("2021-11", "2022-02")
        self.assertEqual(got, ["2021-11", "2021-12", "2022-01", "2022-02"])

    def test_a_backwards_range_is_refused(self):
        with self.assertRaises(ValueError):
            cut_months.month_range("2022-02", "2021-11")


class Fake(object):
    """注入用：待切清單、fetch 的離線碼、磁碟、時鐘。"""

    def __init__(self, todo, free, fetch_code=None):
        self.todo = dict(todo)          # 月份 → 待切集數（每次呼叫依序取）
        self.free = list(free)          # 每次問磁碟回的 GB，用完就停在最後
        self.fetch_code = fetch_code or {}
        self.fetched = []
        self.slept = []
        self.said = []

    def todo_count(self, month):
        counts = self.todo[month]
        if isinstance(counts, list):
            return counts.pop(0) if len(counts) > 1 else counts[0]
        return counts

    def free_gb(self):
        return self.free.pop(0) if len(self.free) > 1 else self.free[0]

    def fetch(self, month):
        self.fetched.append(month)
        return self.fetch_code.get(month, 0)

    def sleep(self, seconds):
        self.slept.append(seconds)

    def say(self, text):
        self.said.append(text)


class TestRun(unittest.TestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.progress = os.path.join(tmp.name, "cut-progress.tsv")

    def run_months(self, fake, months, need=50):
        return cut_months.run(months, need_gb=need, progress=self.progress,
                              todo_count=fake.todo_count,
                              free_gb=fake.free_gb, fetch=fake.fetch,
                              sleep=fake.sleep, say=fake.say,
                              now=lambda: "2026-09-24 22:30")

    def rows(self):
        with open(self.progress, encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle, delimiter="\t"))

    def test_a_month_with_nothing_left_is_not_fetched(self):
        # 試做過的月份（2022-01 等）有幾集已經切好；整月都切好的不必下載。
        fake = Fake({"2022-01": 0, "2022-02": [70, 0]}, [200])
        self.run_months(fake, ["2022-01", "2022-02"])
        self.assertEqual(fake.fetched, ["2022-02"])
        self.assertEqual(self.rows()[0]["結果"], "無待切")

    def test_it_waits_for_disk_before_a_month_and_then_goes_on(self):
        fake = Fake({"2022-02": [70, 0]}, [42, 42, 80])
        self.run_months(fake, ["2022-02"], need=50)
        self.assertEqual(len(fake.slept), 2)
        self.assertEqual(fake.fetched, ["2022-02"])
        mentioned = False
        for line in fake.said:
            if "42" in line:
                mentioned = True
        self.assertTrue(mentioned)

    def test_a_failed_month_is_recorded_and_the_next_one_still_runs(self):
        # fetch_sftp.sh 可以重跑，倒一個月不要把後面整排卡住。
        fake = Fake({"2022-02": [70, 3], "2022-03": [66, 0]}, [200],
                    fetch_code={"2022-02": 1})
        code = self.run_months(fake, ["2022-02", "2022-03"])
        self.assertEqual(fake.fetched, ["2022-02", "2022-03"])
        rows = self.rows()
        self.assertEqual(rows[0]["結果"], "失敗（離開碼 1）")
        self.assertEqual(rows[0]["切後待切"], "3")
        self.assertEqual(rows[1]["結果"], "切完")
        self.assertEqual(code, 1)

    def test_episodes_left_uncut_are_not_called_done(self):
        # fetch 回 0 但還有集數沒切到（下載失敗會記 log、繼續下一集）。
        fake = Fake({"2022-02": [70, 2]}, [200])
        self.run_months(fake, ["2022-02"])
        self.assertEqual(self.rows()[0]["結果"], "還剩 2 集沒切")

    def test_progress_rows_are_appended_with_a_header_once(self):
        fake = Fake({"2022-02": [70, 0]}, [200])
        self.run_months(fake, ["2022-02"])
        self.run_months(Fake({"2022-03": [66, 0]}, [200]), ["2022-03"])
        rows = self.rows()
        months = []
        for row in rows:
            months.append(row["月份"])
        self.assertEqual(months, ["2022-02", "2022-03"])
        self.assertEqual(list(rows[0]),
                         ["月份", "開始", "結束", "切前待切", "切後待切",
                          "結果"])


if __name__ == "__main__":
    unittest.main()
