"""終端機佮紀錄檔ê進度：全部幾支、做到第幾支、預計閣愛幾點幾分。

預估用**最近 10 支**真正有做ê平均用時（使用者裁定 2026-11-23）：規批平均
會予頭前幾支拖牢，網路變慢了後愛幾若點鐘才綴會著。伺服器頂懸已經有、
跳過ê毋算——一支一兩秒，算入去會印出「免一點鐘」。
"""
import unittest

from tools.mkv2mp4wav import progress

MIN = 60.0


class TestHoursMinutes(unittest.TestCase):
    def test_rounds_to_the_minute_before_splitting(self):
        """59 分 36 秒愛印「1 小時 0 分」，袂使印「0 小時 60 分」。"""
        self.assertEqual(progress.hours_minutes(59 * MIN + 36), "1 小時 0 分")

    def test_plain(self):
        self.assertEqual(progress.hours_minutes(195 * 60 * MIN + 6 * MIN),
                         "195 小時 6 分")
        self.assertEqual(progress.hours_minutes(29), "0 小時 0 分")


class TestEta(unittest.TestCase):
    def test_nothing_done_yet_has_no_estimate(self):
        self.assertIsNone(progress.eta_seconds([], 44))

    def test_fewer_than_ten_uses_what_there_is(self):
        self.assertEqual(progress.eta_seconds([6 * MIN, 8 * MIN], 10),
                         70 * MIN)


class ProgressCase(unittest.TestCase):
    def make(self, labels, done_before):
        return progress.Progress(labels, done_before)


class TestStartLine(ProgressCase):
    def test_counts(self):
        labels = ["a", "b", "c", "d"]
        got = self.make(labels, {"a"})
        line = got.start()
        self.assertIn("全部 4 支", line)
        self.assertIn("已完成 1 支", line)
        self.assertIn("這次要做 3 支", line)

    def test_only_both_outputs_count_as_done(self):
        """只有 mp4 佇、wav 無佇ê算「要做」——是呼叫ê時陣決定 done_before，
        Progress 干焦信伊。"""
        labels = ["a", "b"]
        got = progress.done_labels(
            labels, {"a": ("/p/a.mp4", "/w/a.wav"),
                     "b": ("/p/b.mp4", "/w/b.wav")},
            {"/p/a.mp4", "/w/a.wav", "/p/b.mp4"})
        self.assertEqual(got, {"a"})


class TestResumeDoesNotFakeSpeed(ProgressCase):
    def test_1200_skipped_then_two_at_six_minutes(self):
        """3153 支裡 1200 支已存在，這擺做兩支、逐支 6 分 →
        1951 × 6 分 ＝ 195 小時 6 分。"""
        labels = []
        for index in range(3153):
            labels.append("e%04d" % index)
        before = set(labels[:1200])
        got = self.make(labels, before)
        for label in labels[:1200]:
            got.finished(label, "已存在", 1.5)
        got.finished(labels[1200], "成功", 6 * MIN)
        line = got.finished(labels[1201], "成功", 6 * MIN)
        self.assertIn("[第 1202／3153 支]", line)
        self.assertIn("這次已做 2／1953 支", line)
        self.assertIn("預計還要 195 小時 6 分", line)


class TestRecentTen(ProgressCase):
    def test_speed_change_shows_within_ten(self):
        labels = []
        for index in range(100):
            labels.append("e%03d" % index)
        got = self.make(labels, set())
        for index in range(10):
            got.finished(labels[index], "成功", 6 * MIN)
        line = ""
        for index in range(10, 20):
            line = got.finished(labels[index], "成功", 9 * MIN)
        # 80 支 × 9 分 ＝ 720 分 ＝ 12 小時；整批平均 7.5 分會是 10 小時
        self.assertIn("預計還要 12 小時 0 分", line)

    def test_failures_count_as_work(self):
        labels = ["a", "b", "c"]
        got = self.make(labels, set())
        line = got.finished("a", "失敗", 4 * MIN)
        self.assertIn("預計還要 0 小時 8 分", line)


class TestBeforeFirst(ProgressCase):
    def test_no_guess_before_the_first_is_done(self):
        labels = ["a", "b"]
        got = self.make(labels, {"a"})
        line = got.finished("a", "已存在", 1.0)
        self.assertIn("預計時間：第一支做完後估算", line)


class TestNothingLeft(ProgressCase):
    def test_all_already_there_does_not_promise_an_estimate(self):
        """重跑時全部攏已存在：袂使閣印「第一支做完後估算」，彼支永遠袂來。"""
        got = self.make(["a", "b"], {"a", "b"})
        line = got.finished("a", "已存在", 1.0)
        self.assertIn("這次沒有要做的了", line)
        self.assertNotIn("第一支做完後估算", line)


class TestAppearedMidRun(ProgressCase):
    def test_skipped_mid_run_shrinks_the_work_but_not_the_speed(self):
        """開跑了後另一台先傳起去：跳過、毋算速度，「賰ê要做」嘛減一。"""
        labels = ["a", "b", "c", "d"]
        got = self.make(labels, set())
        got.finished("a", "成功", 6 * MIN)
        line = got.finished("b", "已存在", 1.0)
        self.assertIn("預計還要 0 小時 12 分", line)     # c、d 兩支 × 6 分


class TestSingleTime(ProgressCase):
    def test_this_ones_time_in_minutes_and_seconds(self):
        got = self.make(["a", "b"], set())
        line = got.finished("a", "成功", 6 * MIN + 12)
        self.assertIn("a 成功 用時 6 分 12 秒", line)


class TestSummary(ProgressCase):
    def test_totals(self):
        clock = [0.0]
        got = progress.Progress(["a", "b", "c", "d"], {"a"},
                                clock=lambda: clock[0])
        got.start()
        got.finished("a", "已存在", 1.0)
        got.finished("b", "成功", 60.0)
        got.finished("c", "失敗", 60.0)
        got.finished("d", "成功", 60.0)
        clock[0] = 2 * 3600 + 5 * 60
        line = got.summary()
        self.assertIn("總用時 2 小時 5 分", line)
        self.assertIn("成功 2 支", line)
        self.assertIn("失敗 1 支", line)
        self.assertIn("已存在 1 支", line)


if __name__ == "__main__":
    unittest.main()
