"""mxf2mkv 對批次迴圈ê接法：掃資料夾、--limit、對照表格式。

失敗續跑、中斷、危險檔名、工作目錄ê測試已經綴迴圈搬去
tests/sftpbatch/test_batch.py；這搭干焦賰 mxf2mkv 家己ê部分。
"""
import json
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


class TestLimit(BatchCase):
    def test_limit_stops_after_n_files(self):
        seen = []

        def one_file(job, log):
            seen.append(job.relative)
            return {"結果": "成功"}

        self.go(one_file, limit=2)
        self.assertEqual(seen, ["a.mxf", "b.mxf"])


class TestReportLayout(unittest.TestCase):
    """外層是**來源資料夾名**（無帶時間），按呢仝一个來源走幾若擺攏佇仝
    一个資料夾內底，看會出來試過幾擺、佗一擺成功。檔名才帶日期時間，
    閣重複來源名，檔案拖出去嘛講會出是啥。使用者裁定 2026-09-06。
    """

    def test_outer_folder_is_the_source_name_only(self):
        """外層無帶時間——帶ê話一擺一个資料夾，就無「囥做伙」矣。"""
        got = batch.report_folder("/r", "2月原始mxf檔")
        self.assertEqual(got, os.path.join("/r", "2月原始mxf檔"))

    def test_file_names_carry_time_and_source(self):
        got = batch.report_stem("2月原始mxf檔", "0905-2017")
        self.assertEqual(got, "0905-2017_2月原始mxf檔")


class TestPlan(BatchCase):
    def test_dry_run_lists_source_and_remote(self):
        def one_file(job, log):
            return {"結果": "成功"}

        result = self.go(one_file, dry_run=True)
        planned = []
        for job in result.planned:
            planned.append((job.relative, job.remote))
        self.assertEqual(planned[0],
                         ("a.mxf", "/home/mkv-raw/2月原始mxf檔/a.mkv"))

    def test_manifest_entries_are_still_keyed_by_src(self):
        """批次迴圈搬去 tools/sftpbatch 了後，mxf2mkv 對照表逐筆ê鍵
        猶原是 src——對照表格式袂使因為搬位改變。"""
        def one_file(job, log):
            return {"結果": "成功"}

        result = self.go(one_file)
        with open(result.manifest_path, encoding="utf-8") as handle:
            loaded = json.load(handle)
        names = []
        for entry in loaded["檔案"]:
            names.append(entry["src"])
        self.assertEqual(names, ["a.mxf", "b.mxf", "c.mxf"])
        self.assertEqual(loaded["來源資料夾"], "2月原始mxf檔")

    def test_log_and_manifest_land_where_they_always_did(self):
        """紀錄落點佮檔名佮搬位進前完全仝款：
        <report>/<來源名>/<MMDD-HHMM>_<來源名>.log、.manifest.json。"""
        def one_file(job, log):
            return {"結果": "成功"}

        result = self.go(one_file)
        folder = os.path.join(self.reports, "2月原始mxf檔")
        self.assertEqual(result.log_path,
                         os.path.join(folder, "0905-2017_2月原始mxf檔.log"))
        self.assertEqual(
            result.manifest_path,
            os.path.join(folder, "0905-2017_2月原始mxf檔.manifest.json"))


if __name__ == "__main__":
    unittest.main()
