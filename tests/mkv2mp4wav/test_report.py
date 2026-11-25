"""對照表佮紀錄：逐集一筆、鍵是 srt_name，進度行嘛入紀錄檔。

背景跑ê時終端機看袂著，紀錄檔是唯一看會著進度ê所在；對照表是日後篩
「選ê毋是第一條音軌」「走混合路徑」ê根據。
"""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tools.mkv2mp4wav import cli
from tools.mkv2mp4wav import run

from tests.mkv2mp4wav import fakes

NAME = "開會了_107_Hla'alua_拉阿魯哇"


class ReportCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.reports = os.path.join(self.tmp, "reports")
        self.work = os.path.join(self.tmp, "work")

    def main(self, program, tools, extra=()):
        argv = ["--report-dir", self.reports, "--work", self.work]
        argv += list(extra)
        with mock.patch.object(cli, "preflight", return_value=[]):
            return cli.main(program, argv, tools=tools)

    def manifest(self):
        for name in os.listdir(self.reports):
            if name.endswith(".manifest.json"):
                with open(os.path.join(self.reports, name),
                          encoding="utf-8") as handle:
                    return json.load(handle)
        raise AssertionError("無對照表")

    def log_text(self):
        for name in os.listdir(self.reports):
            if name.endswith(".log"):
                with open(os.path.join(self.reports, name),
                          encoding="utf-8") as handle:
                    return handle.read()
        raise AssertionError("無紀錄檔")


class TestEntry(ReportCase):
    def test_every_field_the_spec_asks_for(self):
        os.makedirs(self.work)
        tools = fakes.FakeTools(levels=[-91.0, -25.0])
        program = fakes.FakeProgram([NAME])
        entry = run.one_episode(fakes.make_job(NAME), program,
                                self.work, False, lambda text: None, tools)
        self.assertEqual(entry["音軌"], {"第幾條": 2, "平均音量": -25.0})
        self.assertEqual(entry["來源"]["遠端"], "/docker/src/%s.mkv" % NAME)
        self.assertIn("位元組數", entry["來源"])
        for kind in ("預覽檔", "音檔"):
            for key in ("遠端", "位元組數", "驗收", "結果"):
                self.assertIn(key, entry[kind], kind + key)
        self.assertEqual(entry["預覽檔"]["編碼路徑"], "硬體")
        self.assertEqual(entry["預覽檔"]["影格數"],
                         {"來源": fakes.FRAMES, "預覽檔": fakes.FRAMES})


class TestManifest(ReportCase):
    def test_keyed_by_srt_name(self):
        program = fakes.FakeProgram([NAME, "開會了_108_Paiwan_排灣"])
        code = self.main(program, fakes.FakeTools())
        self.assertEqual(code, 0)
        loaded = self.manifest()
        names = []
        for entry in loaded["檔案"]:
            names.append(entry["srt_name"])
        self.assertEqual(names, [NAME, "開會了_108_Paiwan_排灣"])
        self.assertTrue(loaded["已收尾"])
        self.assertEqual(loaded["來源"], program.SOURCE)

    def test_progress_lines_are_in_the_log(self):
        program = fakes.FakeProgram([NAME, "開會了_108_Paiwan_排灣"])
        self.main(program, fakes.FakeTools())
        text = self.log_text()
        self.assertIn("全部 2 支", text)
        self.assertIn("[第 1／2 支]", text)
        self.assertIn("[第 2／2 支]", text)
        self.assertIn("預計還要", text)
        self.assertIn("總用時", text)

    def test_mxf2mkv_folder_is_untouched(self):
        program = fakes.FakeProgram([NAME])
        self.main(program, fakes.FakeTools())
        self.assertEqual(os.listdir(self.tmp).count("mxf2mkv"), 0)


class TestDefaultFolder(unittest.TestCase):
    def test_each_programme_has_its_own_folder(self):
        self.assertEqual(cli.default_report_dir("aiyalaeho"),
                         os.path.join(cli.ROOT, "kithann", "mkv2mp4wav",
                                      "aiyalaeho"))
        self.assertEqual(cli.default_report_dir("news"),
                         os.path.join(cli.ROOT, "kithann", "mkv2mp4wav",
                                      "news"))
        self.assertNotIn("mxf2mkv", cli.default_report_dir("news"))


class TestExitCodes(ReportCase):
    def test_a_failure_makes_it_non_zero(self):
        program = fakes.FakeProgram([NAME], missing={NAME})
        self.assertEqual(self.main(program, fakes.FakeTools()), 1)

    def test_interrupt_returns_130(self):
        program = fakes.FakeProgram([NAME])
        tools = fakes.FakeTools()
        tools.encode_error = KeyboardInterrupt()
        self.assertEqual(self.main(program, tools), 130)


class TestDryRun(ReportCase):
    def test_lists_and_touches_nothing(self):
        program = fakes.FakeProgram(
            [NAME, "開會了_108_Paiwan_排灣"],
            listed={"/home/aiyalaeho/mp4/%s.mp4" % NAME,
                    "/home/aiyalaeho/wav/%s.wav" % NAME})
        tools = fakes.FakeTools()
        with mock.patch("builtins.print") as printed:
            code = self.main(program, tools, ["--dry-run"])
        self.assertEqual(code, 0)
        self.assertEqual(tools.fetched, [])
        self.assertFalse(os.path.exists(self.reports))
        self.assertFalse(os.path.exists(self.work))
        out = ""
        for call in printed.call_args_list:
            for arg in call.args:
                out += str(arg) + " "
            out += "\n"
        self.assertIn("全部 2 支，已完成 1 支", out)
        self.assertIn("/home/aiyalaeho/mp4/開會了_108_Paiwan_排灣.mp4", out)


if __name__ == "__main__":
    unittest.main()
