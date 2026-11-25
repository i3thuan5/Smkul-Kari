"""批次迴圈：一支倒袂使拖累其他支，人喝停就規批停。

一批走幾若點鐘（新聞 mkv2mp4wav 走十幾工），為著一支歹檔案停落來傷貴。
所以記落來、行下一支，規批走煞才用離開碼講「有出代誌」。毋過 Ctrl+C
毋是檔案歹，是人欲規个停，袂使予「記落來、行下一支」吞去。

這份是對 tests/mxf2mkv/test_failure.py、test_interrupt.py 搬過來ê：
迴圈搬去 tools/sftpbatch 了後，mxf2mkv 佮 mkv2mp4wav 攏用仝一份。
"""
import json
import os
import shutil
import tempfile
import unittest

from tools.sftpbatch import batch
from tools.sftpbatch import report


class BatchCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.reports = os.path.join(self.tmp, "reports")
        self.work = os.path.join(self.tmp, "work")
        os.makedirs(self.work)
        self.jobs = []
        for name in ["a.mxf", "b.mxf", "c.mxf"]:
            self.jobs.append(batch.Job(name, "/home/mkv-raw/s/" + name))

    def open_report(self):
        return report.open_run(self.reports, "0905-2017", {"來源": "測試"})

    def go(self, one_file, key_field="src", **kwargs):
        return batch.run(self.jobs, self.open_report, one_file,
                         work_dir=self.work, key_field=key_field, **kwargs)


class TestKeepGoing(BatchCase):
    def test_one_failure_does_not_stop_the_rest(self):
        seen = []

        def one_file(job, log):
            seen.append(job.label)
            if job.label == "b.mxf":
                raise RuntimeError("音訊對袂起來")
            return {"結果": "成功"}

        result = self.go(one_file)
        self.assertEqual(seen, ["a.mxf", "b.mxf", "c.mxf"])
        self.assertEqual(result.failed, ["b.mxf"])

    def test_exit_code_is_non_zero_when_anything_failed(self):
        def one_file(job, log):
            if job.label == "b.mxf":
                raise RuntimeError("倒去")
            return {"結果": "成功"}

        self.assertNotEqual(self.go(one_file).exit_code, 0)

    def test_exit_code_is_zero_when_everything_worked(self):
        def one_file(job, log):
            return {"結果": "成功"}

        self.assertEqual(self.go(one_file).exit_code, 0)

    def test_skipped_files_are_not_failures(self):
        def one_file(job, log):
            return {"結果": "已存在"}

        self.assertEqual(self.go(one_file).exit_code, 0)

    def test_a_worker_reporting_failure_counts_as_failed(self):
        """mkv2mp4wav 一集內底兩種產出各自 try，倒去ê時陣是「回傳」失敗，
        毋是擲例外——按呢嘛愛算入失敗，離開碼才袂講一切順利。"""
        def one_file(job, log):
            if job.label == "b.mxf":
                return {"結果": "失敗", "原因": "音檔驗收不過"}
            return {"結果": "成功"}

        result = self.go(one_file)
        self.assertEqual(result.failed, ["b.mxf"])
        self.assertEqual(result.exit_code, 1)

    def test_the_worker_can_write_to_the_run_log(self):
        """逐支ê外部指令 stderr 愛入 log，所以 worker 提會著伊。"""
        def one_file(job, log):
            log("ffmpeg 講：%s 有代誌" % job.label)
            return {"結果": "成功"}

        result = self.go(one_file)
        with open(result.log_path, encoding="utf-8") as handle:
            self.assertIn("a.mxf 有代誌", handle.read())

    def test_the_reason_is_written_down(self):
        """歹去ê理由愛入 log——隨身硬碟拔掉了後就賰彼份通看。"""
        def one_file(job, log):
            raise RuntimeError("音訊對袂起來：第 2 軌")

        result = self.go(one_file)
        with open(result.log_path, encoding="utf-8") as handle:
            text = handle.read()
        self.assertIn("音訊對袂起來：第 2 軌", text)
        self.assertIn("b.mxf", text)

    def test_every_file_gets_a_manifest_entry(self):
        def one_file(job, log):
            if job.label == "b.mxf":
                raise RuntimeError("倒去")
            return {"結果": "成功"}

        result = self.go(one_file)
        names = []
        for entry in result.entries:
            names.append(entry["src"])
        self.assertEqual(names, ["a.mxf", "b.mxf", "c.mxf"])
        self.assertEqual(result.entries[1]["結果"], "失敗")


class TestKeyField(BatchCase):
    def test_mxf2mkv_entries_are_still_keyed_by_src(self):
        """搬去 sftpbatch 了後，mxf2mkv 對照表逐筆ê鍵猶原是 src。"""
        def one_file(job, log):
            return {"結果": "成功"}

        result = self.go(one_file, key_field="src")
        with open(result.manifest_path, encoding="utf-8") as handle:
            loaded = json.load(handle)
        self.assertEqual(loaded["檔案"][0]["src"], "a.mxf")

    def test_another_tool_can_key_by_srt_name(self):
        def one_file(job, log):
            return {"結果": "成功"}

        result = self.go(one_file, key_field="srt_name")
        self.assertEqual(result.entries[0]["srt_name"], "a.mxf")
        self.assertNotIn("src", result.entries[0])


class TestOnDone(BatchCase):
    """mkv2mp4wav 佇遮印進度行；mxf2mkv 無傳，行為佮輸出攏無變。"""

    def test_called_once_per_job_with_seconds(self):
        ticks = iter([0.0, 30.0, 30.0, 90.0, 90.0, 100.0])
        seen = []

        def one_file(job, log):
            if job.label == "b.mxf":
                raise RuntimeError("倒去")
            return {"結果": "成功"}

        def on_done(job, entry, seconds):
            seen.append((job.label, entry["結果"], seconds))

        self.go(one_file, on_done=on_done, clock=lambda: next(ticks))
        self.assertEqual(seen, [("a.mxf", "成功", 30.0),
                                ("b.mxf", "失敗", 60.0),
                                ("c.mxf", "成功", 10.0)])

    def test_without_it_nothing_changes(self):
        def one_file(job, log):
            return {"結果": "成功"}

        result = self.go(one_file)
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(len(result.entries), 3)


class TestPreFailedJob(BatchCase):
    def test_a_job_carrying_an_error_fails_without_the_worker(self):
        """目錄內底成果檔名無合規格：彼集記失敗、指名，下一集照做，
        而且袂使組出任何遠端路徑交予 worker。"""
        self.jobs[1] = batch.Job("20210103_03_晨間_X", None,
                                 error="成果檔名無合規格")
        seen = []

        def one_file(job, log):
            seen.append(job.label)
            return {"結果": "成功"}

        result = self.go(one_file, key_field="srt_name")
        self.assertEqual(seen, ["a.mxf", "c.mxf"])
        self.assertEqual(result.failed, ["20210103_03_晨間_X"])
        self.assertIn("成果檔名無合規格", result.entries[1]["原因"])


class TestUnsafeNames(BatchCase):
    def test_a_dangerous_name_fails_that_file_only(self):
        self.jobs.append(batch.Job('q"uote.mxf', "/home/x/q.mkv"))

        def one_file(job, log):
            return {"結果": "成功"}

        result = self.go(one_file)
        self.assertIn('q"uote.mxf', result.failed)
        self.assertEqual(result.exit_code, 1)


class TestDangerousPaths(unittest.TestCase):
    """sftp -b 會共批次檔逐逝重讀，所以路徑內底ê引號會共引數煞尾，
    換逝會開一條新ê指令。sftp.sh 家己嘛擋，毋過佇遮就擋起來，
    失敗ê時陣講會出是佗一支檔案。
    """

    def test_quote_is_rejected(self):
        self.assertFalse(batch.is_safe('a"b.mxf'))

    def test_backslash_is_rejected(self):
        self.assertFalse(batch.is_safe("a\\b.mxf"))

    def test_newline_is_rejected(self):
        self.assertFalse(batch.is_safe("a\nb.mxf"))

    def test_tab_and_carriage_return_are_rejected(self):
        self.assertFalse(batch.is_safe("a\tb.mxf"))
        self.assertFalse(batch.is_safe("a\rb.mxf"))

    def test_ordinary_names_pass(self):
        self.assertTrue(batch.is_safe("21NL004_41晚間族語新聞.mxf"))
        self.assertTrue(batch.is_safe("夜間/a b-c_d.mxf"))

    def test_apostrophe_in_an_episode_name_passes(self):
        """新聞、開會了ê成果檔名有撇號（Hla'alua、Sakizaya…），sftp.sh 會
        自己加雙引號，撇號毋是危險字元，袂使擋。"""
        self.assertTrue(batch.is_safe("開會了_107_Hla'alua_拉阿魯哇"))


class TestWorkDir(BatchCase):
    def test_work_dir_is_kept_when_something_failed(self):
        def one_file(job, log):
            raise RuntimeError("倒去")

        result = self.go(one_file)
        self.assertTrue(result.keep_work)

    def test_work_dir_is_disposable_when_all_is_well(self):
        def one_file(job, log):
            return {"結果": "成功"}

        self.assertFalse(self.go(one_file).keep_work)

    def test_the_work_dir_path_is_recorded_when_kept(self):
        """留現場ê時陣，路徑愛講出來，無人揣無。"""
        def one_file(job, log):
            raise RuntimeError("倒去")

        result = self.go(one_file)
        with open(result.log_path, encoding="utf-8") as handle:
            self.assertIn(self.work, handle.read())


class TestDryRun(BatchCase):
    def test_dry_run_touches_nothing(self):
        """試走袂使建、改、抑是刣任何檔案，嘛袂使送出改變遠端ê指令。"""
        called = []

        def one_file(job, log):
            called.append(job.label)
            return {"結果": "成功"}

        result = self.go(one_file, dry_run=True)
        self.assertEqual(called, [])
        self.assertFalse(os.path.exists(self.reports))
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(len(result.planned), 3)


class TestInterrupt(BatchCase):
    def test_interrupt_is_not_swallowed_as_a_failure(self):
        """「一支倒袂使拖累其他支」是講檔案歹，毋是講人喝停。"""
        seen = []

        def one_file(job, log):
            seen.append(job.label)
            raise KeyboardInterrupt()

        with self.assertRaises(KeyboardInterrupt):
            self.go(one_file)
        self.assertEqual(seen, ["a.mxf"])

    def test_interrupt_is_written_to_the_log(self):
        def one_file(job, log):
            raise KeyboardInterrupt()

        with self.assertRaises(KeyboardInterrupt):
            self.go(one_file)
        logs = []
        for name in os.listdir(self.reports):
            if name.endswith(".log"):
                logs.append(name)
        with open(os.path.join(self.reports, logs[0]),
                  encoding="utf-8") as handle:
            text = handle.read()
        self.assertIn("中斷", text)
        self.assertIn("a.mxf", text)


if __name__ == "__main__":
    unittest.main()
