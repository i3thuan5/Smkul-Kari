"""report: 執行紀錄佮對照表囥佗位、叫啥名、按怎袂共舊ê拭掉。

外層是**來源資料夾名**（無帶時間），按呢仝一个來源走幾若擺攏佇仝
一个資料夾內底，看會出來試過幾擺、佗一擺成功。檔名才帶日期時間。
使用者裁定 2026-09-06。
"""
import json
import os
import shutil
import tempfile
import unittest

from tools.mxf2mkv import report


class ReportCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)


class TestLayout(ReportCase):
    def test_outer_folder_is_the_source_name_only(self):
        """外層無帶時間——帶ê話一擺一个資料夾，就無「囥做伙」矣。"""
        got = report.folder_for(self.tmp, "2月原始mxf檔")
        self.assertEqual(got, os.path.join(self.tmp, "2月原始mxf檔"))

    def test_file_names_carry_time_and_source(self):
        got = report.stem("2月原始mxf檔", "0905-2017")
        self.assertEqual(got, "0905-2017_2月原始mxf檔")

    def test_second_run_lands_in_the_same_folder(self):
        one = report.folder_for(self.tmp, "2月原始mxf檔")
        two = report.folder_for(self.tmp, "2月原始mxf檔")
        self.assertEqual(one, two)


class TestNeverOverwrite(ReportCase):
    def test_creates_both_files(self):
        got = report.open_run(self.tmp, "2月原始mxf檔", "0905-2017")
        self.assertTrue(os.path.exists(got.log_path))
        self.assertTrue(os.path.exists(got.manifest_path))
        got.close([])

    def test_same_minute_twice_gets_a_suffix(self):
        """仝一分鐘走兩擺會挵名，愛加後綴，袂使共頭一擺ê蓋過去。"""
        first = report.open_run(self.tmp, "src", "0905-2017")
        with open(first.log_path, "a", encoding="utf-8") as handle:
            handle.write("頭一擺\n")
        second = report.open_run(self.tmp, "src", "0905-2017")
        self.assertNotEqual(first.log_path, second.log_path)
        self.assertIn("-2", os.path.basename(second.log_path))
        with open(first.log_path, encoding="utf-8") as handle:
            self.assertIn("頭一擺", handle.read())
        first.close([])
        second.close([])

    def test_third_run_in_the_same_minute(self):
        one = report.open_run(self.tmp, "src", "0905-2017")
        two = report.open_run(self.tmp, "src", "0905-2017")
        three = report.open_run(self.tmp, "src", "0905-2017")
        paths = {one.log_path, two.log_path, three.log_path}
        self.assertEqual(len(paths), 3)
        for run in (one, two, three):
            run.close([])

    def test_a_different_minute_does_not_need_a_suffix(self):
        one = report.open_run(self.tmp, "src", "0905-2017")
        two = report.open_run(self.tmp, "src", "0906-0930")
        self.assertNotIn("-2", os.path.basename(two.log_path))
        one.close([])
        two.close([])

    def test_a_half_taken_name_does_not_leave_an_orphan(self):
        """兩个名干焦挵著一个ê時陣，袂使留一个孤鳥檔案。

        譬論講有人共舊ê .log 刣掉、manifest 留咧。彼陣 log 開會起來、
        manifest 開袂起來，若無共已經開ê彼个抾轉來，資料夾內底就會
        濟一个空ê .log，看起來若像有走過彼擺，其實無。
        """
        taken = report.open_run(self.tmp, "src", "0905-2017")
        os.remove(taken.log_path)          # 干焦賰 manifest
        run = report.open_run(self.tmp, "src", "0905-2017")
        self.assertIn("-2", os.path.basename(run.log_path))
        self.assertFalse(os.path.exists(
            os.path.join(self.tmp, "src", "0905-2017_src.log")))
        run.close([])


class TestManifest(ReportCase):
    def _write(self, entries):
        run = report.open_run(self.tmp, "src", "0905-2017")
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
        run = report.open_run(self.tmp, "2月原始mxf檔", "0905-2017")
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
