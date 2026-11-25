"""report: 執行紀錄佮對照表按怎袂共舊ê拭掉、按怎逐筆寫入。

囥佗一个資料夾、檔名按怎號，是呼叫ê工具家己決定ê（mxf2mkv 見
tests/mxf2mkv/test_failure.py ê TestReportLayout；mkv2mp4wav 見
tests/mkv2mp4wav/test_report.py）。這搭管ê是兩个工具共用ê規矩。
"""
import json
import os
import shutil
import tempfile
import unittest

from tools.sftpbatch import report

HEADER = {"來源資料夾": "2月原始mxf檔", "開始時間": "0905-2017"}


class ReportCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)


class TestNeverOverwrite(ReportCase):
    def test_creates_both_files(self):
        got = report.open_run(self.tmp, "0905-2017_2月原始mxf檔", HEADER)
        self.assertTrue(os.path.exists(got.log_path))
        self.assertTrue(os.path.exists(got.manifest_path))
        got.close([])

    def test_same_minute_twice_gets_a_suffix(self):
        """仝一分鐘走兩擺會挵名，愛加後綴，袂使共頭一擺ê蓋過去。"""
        first = report.open_run(self.tmp, "0905-2017_src", {})
        with open(first.log_path, "a", encoding="utf-8") as handle:
            handle.write("頭一擺\n")
        second = report.open_run(self.tmp, "0905-2017_src", {})
        self.assertNotEqual(first.log_path, second.log_path)
        self.assertIn("-2", os.path.basename(second.log_path))
        with open(first.log_path, encoding="utf-8") as handle:
            self.assertIn("頭一擺", handle.read())
        first.close([])
        second.close([])

    def test_third_run_in_the_same_minute(self):
        one = report.open_run(self.tmp, "0905-2017_src", {})
        two = report.open_run(self.tmp, "0905-2017_src", {})
        three = report.open_run(self.tmp, "0905-2017_src", {})
        paths = {one.log_path, two.log_path, three.log_path}
        self.assertEqual(len(paths), 3)
        for run in (one, two, three):
            run.close([])

    def test_a_different_minute_does_not_need_a_suffix(self):
        one = report.open_run(self.tmp, "0905-2017_src", {})
        two = report.open_run(self.tmp, "0906-0930_src", {})
        self.assertNotIn("-2", os.path.basename(two.log_path))
        one.close([])
        two.close([])

    def test_a_half_taken_name_does_not_leave_an_orphan(self):
        """兩个名干焦挵著一个ê時陣，袂使留一个孤鳥檔案。

        譬論講有人共舊ê .log 刣掉、manifest 留咧。彼陣 log 開會起來、
        manifest 開袂起來，若無共已經開ê彼个抾轉來，資料夾內底就會
        濟一个空ê .log，看起來若像有走過彼擺，其實無。
        """
        taken = report.open_run(self.tmp, "0905-2017_src", {})
        os.remove(taken.log_path)          # 干焦賰 manifest
        run = report.open_run(self.tmp, "0905-2017_src", {})
        self.assertIn("-2", os.path.basename(run.log_path))
        self.assertFalse(os.path.exists(
            os.path.join(self.tmp, "0905-2017_src.log")))
        run.close([])


class TestWrittenAsItGoes(ReportCase):
    """對照表本來規批走煞才寫：kithann/mxf2mkv/ 有 3 份空ê對照表，就是
    走到一半停去留落來ê。mkv2mp4wav 新聞走十幾工，這个缺口愛補。"""

    def _load(self, run):
        with open(run.manifest_path, encoding="utf-8") as handle:
            return json.load(handle)

    def test_first_n_entries_are_readable_mid_run(self):
        run = report.open_run(self.tmp, "0905-2017_src", {"來源": "x"})
        run.write([{"src": "a"}])
        run.write([{"src": "a"}, {"src": "b"}])
        loaded = self._load(run)
        self.assertEqual(len(loaded["檔案"]), 2)
        self.assertFalse(loaded["已收尾"])
        self.assertEqual(loaded["來源"], "x")

    def test_close_marks_it_finished(self):
        run = report.open_run(self.tmp, "0905-2017_src", {})
        run.write([{"src": "a"}])
        run.close([{"src": "a"}])
        self.assertTrue(self._load(run)["已收尾"])

    def test_a_crash_while_writing_leaves_the_previous_complete_json(self):
        """寫暫存檔寫到一半當掉，磁碟頂懸ê對照表猶原是頂一擺完整ê JSON。"""
        run = report.open_run(self.tmp, "0905-2017_src", {})
        run.write([{"src": "a"}])

        class Boom(Exception):
            pass

        real_dump = report.json.dump

        def half_dump(document, handle, **kwargs):
            handle.write('{"檔案": [')
            raise Boom()

        report.json.dump = half_dump
        try:
            with self.assertRaises(Boom):
                run.write([{"src": "a"}, {"src": "b"}])
        finally:
            report.json.dump = real_dump
        loaded = self._load(run)
        self.assertEqual(loaded["檔案"], [{"src": "a"}])
        self.assertFalse(os.path.exists(run.manifest_path + ".tmp"))


class TestManifest(ReportCase):
    def _write(self, entries):
        run = report.open_run(self.tmp, "0905-2017_src", {})
        run.close(entries)
        with open(run.manifest_path, encoding="utf-8") as handle:
            return handle.read()

    def test_json_is_readable_by_a_person(self):
        """照 CLAUDE.md：排版過、中文無跳脫、鍵有排序。"""
        raw = self._write([{"src": "夜間/b.mxf", "結果": "成功"}])
        self.assertIn("\n  ", raw)                 # indent
        self.assertIn("夜間/b.mxf", raw)            # ensure_ascii=False
        loaded = json.loads(raw)
        self.assertEqual(loaded["檔案"][0]["src"], "夜間/b.mxf")

    def test_keys_are_sorted(self):
        raw = self._write([{"z": 1, "a": 2}])
        entry = raw[raw.index('"檔案"'):]
        self.assertLess(entry.index('"a"'), entry.index('"z"'))

    def test_run_level_fields(self):
        run = report.open_run(self.tmp, "0905-2017_2月原始mxf檔", HEADER)
        run.close([])
        with open(run.manifest_path, encoding="utf-8") as handle:
            loaded = json.load(handle)
        self.assertEqual(loaded["來源資料夾"], "2月原始mxf檔")
        self.assertEqual(loaded["開始時間"], "0905-2017")
        self.assertEqual(loaded["檔案"], [])

    def test_entry_carries_everything_needed_to_sort_it_out_later(self):
        """這幾欄就是日後欲接目錄、欲決定提佗一軌做語音辨識ê根據。"""
        entry = {
            "src": "夜間/b.mxf", "src_bytes": 19012345678,
            "remote": "/home/mkv-raw/2月原始mxf檔/夜間/b.mkv",
            "remote_bytes": 2540000000,
            "audio_tracks_src": 2, "audio_tracks_kept": 1,
            "音軌": "兩軌相同，留一軌", "音訊逐位元相符": True,
            "seconds": 1180, "結果": "成功",
        }
        raw = self._write([entry])
        loaded = json.loads(raw)["檔案"][0]
        self.assertEqual(loaded, entry)


if __name__ == "__main__":
    unittest.main()
