"""批次ê失敗處理：一支倒袂使拖累其他支。

一批走幾若點鐘，為著一支歹檔案停落來傷貴。所以記落來、行下一支，
規批走煞才用離開碼講「有出代誌」。
"""
import os
import shutil
import tempfile
import unittest

from tools.mxf2mkv import batch


class BatchCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.src = os.path.join(self.tmp, "2月原始mxf檔")
        os.makedirs(self.src)
        for name in ["a.mxf", "b.mxf", "c.mxf"]:
            with open(os.path.join(self.src, name), "w") as handle:
                handle.write("x")
        self.reports = os.path.join(self.tmp, "reports")
        self.work = os.path.join(self.tmp, "work")
        os.makedirs(self.work)

    def go(self, one_file, **kwargs):
        return batch.run(
            src_root=self.src, dst_root="/home/mkv-raw",
            work_dir=self.work, report_root=self.reports,
            stamp="0905-2017", one_file=one_file, **kwargs)


class TestKeepGoing(BatchCase):
    def test_one_failure_does_not_stop_the_rest(self):
        seen = []

        def one_file(job, log):
            seen.append(job.relative)
            if job.relative == "b.mxf":
                raise RuntimeError("音訊對袂起來")
            return {"結果": "成功"}

        result = self.go(one_file)
        self.assertEqual(seen, ["a.mxf", "b.mxf", "c.mxf"])
        self.assertEqual(result.failed, ["b.mxf"])

    def test_exit_code_is_non_zero_when_anything_failed(self):
        def one_file(job, log):
            if job.relative == "b.mxf":
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

    def test_the_worker_can_write_to_the_run_log(self):
        """逐支ê外部指令 stderr 愛入 log，所以 worker 提會著伊。"""
        def one_file(job, log):
            log("ffmpeg 講：%s 有代誌" % job.relative)
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
            if job.relative == "b.mxf":
                raise RuntimeError("倒去")
            return {"結果": "成功"}

        result = self.go(one_file)
        names = []
        for entry in result.entries:
            names.append(entry["src"])
        self.assertEqual(names, ["a.mxf", "b.mxf", "c.mxf"])
        self.assertEqual(result.entries[1]["結果"], "失敗")


class TestUnsafeNames(BatchCase):
    def test_a_dangerous_name_fails_that_file_only(self):
        with open(os.path.join(self.src, 'q"uote.mxf'), "w") as handle:
            handle.write("x")

        def one_file(job, log):
            return {"結果": "成功"}

        result = self.go(one_file)
        self.assertIn('q"uote.mxf', result.failed)
        self.assertEqual(result.exit_code, 1)


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


class TestLimit(BatchCase):
    def test_limit_stops_after_n_files(self):
        seen = []

        def one_file(job, log):
            seen.append(job.relative)
            return {"結果": "成功"}

        self.go(one_file, limit=2)
        self.assertEqual(seen, ["a.mxf", "b.mxf"])


class TestDryRun(BatchCase):
    def test_dry_run_touches_nothing(self):
        """試走袂使建、改、抑是刣任何檔案，嘛袂使送出改變遠端ê指令。"""
        called = []

        def one_file(job, log):
            called.append(job.relative)
            return {"結果": "成功"}

        result = self.go(one_file, dry_run=True)
        self.assertEqual(called, [])
        self.assertFalse(os.path.exists(self.reports))
        self.assertEqual(result.exit_code, 0)

    def test_dry_run_lists_source_and_remote(self):
        def one_file(job, log):
            return {"結果": "成功"}

        result = self.go(one_file, dry_run=True)
        planned = []
        for job in result.planned:
            planned.append((job.relative, job.remote))
        self.assertEqual(planned[0],
                         ("a.mxf", "/home/mkv-raw/2月原始mxf檔/a.mkv"))


if __name__ == "__main__":
    unittest.main()
