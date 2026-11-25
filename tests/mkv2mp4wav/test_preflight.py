"""開跑進前檢查：使用者家己佇終端機打指令，缺啥就佇連線、下載進前講。

換機器了後 .sftp-pass 猶未建、PATH 無 ffprobe、無 GPU，攏愛隨停、講明
欠啥、離開碼 2——毋通下載 2.5 GB 了後才倒。密碼檔干焦看有抑無，袂使
開來讀（CLAUDE.md 憑證規定：讀著就等於上傳）。
"""
import builtins
import os
import unittest
from unittest import mock

from tools.mkv2mp4wav import cli

from tests.mkv2mp4wav import fakes


def which_all(name):
    return "/usr/bin/" + name


class TestPreflight(unittest.TestCase):
    def test_everything_present(self):
        got = cli.preflight(False, which=which_all, pass_file=__file__,
                            probe=lambda: (True, ""))
        self.assertEqual(got, [])

    def test_missing_password_file_names_the_path_without_opening_it(self):
        opened = []
        real_open = builtins.open

        def spy(path, *args, **kwargs):
            opened.append(path)
            return real_open(path, *args, **kwargs)

        with mock.patch("builtins.open", spy):
            got = cli.preflight(False, which=which_all,
                                pass_file="/nowhere/.sftp-pass",
                                probe=lambda: (True, ""))
        self.assertEqual(len(got), 1)
        self.assertIn("/nowhere/.sftp-pass", got[0])
        self.assertNotIn("/nowhere/.sftp-pass", opened)

    def test_missing_ffprobe_is_named(self):
        def which(name):
            return None if name == "ffprobe" else "/usr/bin/" + name

        got = cli.preflight(False, which=which, pass_file=__file__,
                            probe=lambda: (True, ""))
        self.assertEqual(len(got), 1)
        self.assertIn("ffprobe", got[0])

    def test_no_vaapi_says_software_flag(self):
        got = cli.preflight(False, which=which_all, pass_file=__file__,
                            probe=lambda: (False, "/dev/dri/renderD128 無存在"))
        self.assertEqual(len(got), 1)
        self.assertIn("--software", got[0])

    def test_software_skips_the_vaapi_probe(self):
        def probe():
            raise AssertionError("加 --software 袂使探測 VAAPI")

        got = cli.preflight(True, which=which_all, pass_file=__file__,
                            probe=probe)
        self.assertEqual(got, [])


class TestMainStopsEarly(unittest.TestCase):
    def test_exit_2_and_nothing_listed_or_downloaded(self):
        program = fakes.FakeProgram(["開會了_107_x"])
        tools = fakes.FakeTools()
        with mock.patch.object(cli, "preflight",
                               return_value=["揣無 SFTP 密碼檔：/x/.sftp-pass"]):
            code = cli.main(program, ["--report-dir", "/nonexistent/r"],
                            tools=tools)
        self.assertEqual(code, 2)
        self.assertEqual(program.listed_calls, 0)
        self.assertEqual(tools.fetched, [])
        self.assertFalse(os.path.exists("/nonexistent/r"))


if __name__ == "__main__":
    unittest.main()
