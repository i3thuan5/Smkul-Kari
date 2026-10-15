"""中斷佮半截ê封存：轉到一半停去ê檔案袂使上傳。

2026-10-06 查著 SFTP 頂懸有 8 支 mkv 只有 0.7 秒到 23 分 53 秒（正常
一集 48 分鐘）：檔頭佮每軌 DURATION 攏是短ê長度、解到尾無錯——ffmpeg
是收著 Ctrl+C（抑是 q）好好仔收尾，短檔照樣傳起去。音訊指紋擋袂著，
因為 encode_master.sh ê md5 是仝一擺 ffmpeg 順紲算ê，ffmpeg 停佇佗，
來源指紋就算到佗，兩爿仝款短、仝款「逐位元相符」。
"""
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from tools.mxf2mkv import __main__ as cli
from tools.mxf2mkv import batch
from tools.mxf2mkv import run as runner

FULL = 2890.0     # 一集 48 分鐘
SHORT = 21.0      # 24NL003_152 午間魯凱 實際長度


def _done(code, stderr=""):
    return subprocess.CompletedProcess([], code, "", stderr)


class OneFileCase(unittest.TestCase):
    """runner.one_file 外部指令攏換掉，干焦看伊有傳抑無傳。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.source = os.path.join(self.tmp, "a.mxf")
        with open(self.source, "w") as handle:
            handle.write("x")
        self.job = batch.Job("a.mxf", self.source, "/home/mkv-raw/s/a.mkv")
        self.put = mock.patch.object(runner.upload, "put",
                                     return_value=1).start()
        self.addCleanup(mock.patch.stopall)

    def encode_leaves(self, code, archive_seconds):
        """Make the encode step return `code` and leave a finished pair."""
        work = self.tmp

        def fake_encode(cmd, **kwargs):
            name = cmd[4]
            with open(os.path.join(work, name + ".all.mkv"), "w") as h:
                h.write("v")
            with open(os.path.join(work, name + ".src-a0.md5"), "w") as h:
                h.write("MD5=%s\n" % ("0" * 32))
            return _done(code)

        mock.patch.object(runner.subprocess, "run",
                          side_effect=fake_encode).start()
        mock.patch.object(runner, "encoded_md5s",
                          return_value=["0" * 32]).start()
        mock.patch.object(runner, "is_stream_copied",
                          return_value=False).start()

        def fake_remux(archive, keep, dst):
            with open(dst, "w") as handle:
                handle.write("v")

        mock.patch.object(runner, "remux", side_effect=fake_remux).start()

        def fake_probe(path):
            if path == self.source:
                return FULL
            return archive_seconds

        mock.patch.object(runner, "probe_duration",
                          side_effect=fake_probe).start()

    def go(self):
        return runner.one_file(self.job, self.tmp)


class TestShortArchiveIsNotUploaded(OneFileCase):
    def test_short_archive_with_matching_md5_is_refused(self):
        """ffmpeg 按 q 收尾離開碼是 0，指紋兩爿仝款短——干焦時長看會出來。

        24NL003_152 午間魯凱：來源 48 分鐘，mkv 21 秒，傳起去矣。
        """
        self.encode_leaves(0, SHORT)
        with self.assertRaises(runner.EncodeError):
            self.go()
        self.put.assert_not_called()

    def test_full_length_archive_is_uploaded(self):
        self.encode_leaves(0, FULL - 0.03)
        self.go()
        self.put.assert_called_once()


class TestInterruptedEncodeStopsEverything(OneFileCase):
    def test_ffmpeg_signal_exit_is_an_interrupt_not_a_failure(self):
        """ffmpeg 收著 SIGINT／SIGTERM／SIGHUP 好好收尾，離開碼是 255。

        當做一般失敗，batch 會「記落來、行下一支」——人按 Ctrl+C 是欲
        規个停，毋是欲跳過這支。
        """
        self.encode_leaves(255, SHORT)
        with self.assertRaises(KeyboardInterrupt):
            self.go()
        self.put.assert_not_called()

    def test_killed_by_sigint_is_an_interrupt(self):
        """bash 本身予 SIGINT 刣掉，subprocess 看著ê是 -2。"""
        self.encode_leaves(-2, SHORT)
        with self.assertRaises(KeyboardInterrupt):
            self.go()
        self.put.assert_not_called()

    def test_shell_130_is_an_interrupt(self):
        self.encode_leaves(130, SHORT)
        with self.assertRaises(KeyboardInterrupt):
            self.go()
        self.put.assert_not_called()

    def test_ordinary_failure_is_still_a_failure(self):
        """離開碼 1 是編碼真正倒去，猶原記落來、行下一支。"""
        self.encode_leaves(1, SHORT)
        with self.assertRaises(runner.EncodeError):
            self.go()
        self.put.assert_not_called()

    def test_leftovers_are_cleaned_after_interrupt(self):
        self.encode_leaves(255, SHORT)
        with self.assertRaises(KeyboardInterrupt):
            self.go()
        left = sorted(os.listdir(self.tmp))
        self.assertEqual(left, ["a.mxf"])


class TestBatchStopsOnInterrupt(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.src = os.path.join(self.tmp, "2月原始mxf檔")
        os.makedirs(self.src)
        for name in ["a.mxf", "b.mxf", "c.mxf"]:
            with open(os.path.join(self.src, name), "w") as handle:
                handle.write("x")
        self.reports = os.path.join(self.tmp, "reports")

    def go(self, one_file):
        return batch.run(
            src_root=self.src, dst_root="/home/mkv-raw",
            work_dir=self.tmp, report_root=self.reports,
            stamp="1006-2210", one_file=one_file)

    def test_interrupt_is_not_swallowed_as_a_failure(self):
        """「一支倒袂使拖累其他支」是講檔案歹，毋是講人喝停。"""
        seen = []

        def one_file(job, log):
            seen.append(job.relative)
            raise KeyboardInterrupt()

        with self.assertRaises(KeyboardInterrupt):
            self.go(one_file)
        self.assertEqual(seen, ["a.mxf"])

    def test_interrupt_is_written_to_the_log(self):
        def one_file(job, log):
            raise KeyboardInterrupt()

        with self.assertRaises(KeyboardInterrupt):
            self.go(one_file)
        folder = os.path.join(self.reports, "2月原始mxf檔")
        logs = []
        for name in os.listdir(folder):
            if name.endswith(".log"):
                logs.append(name)
        with open(os.path.join(folder, logs[0]), encoding="utf-8") as h:
            text = h.read()
        self.assertIn("中斷", text)
        self.assertIn("a.mxf", text)


class TestMainExitsOnInterrupt(unittest.TestCase):
    def test_returns_130_and_does_not_carry_on(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        src = os.path.join(tmp, "src")
        os.makedirs(src)
        with mock.patch.object(cli.batch, "run",
                               side_effect=KeyboardInterrupt()):
            code = cli.main(["--src", src, "--work",
                             os.path.join(tmp, "w"), "--report-dir",
                             os.path.join(tmp, "r")])
        self.assertEqual(code, 130)


if __name__ == "__main__":
    unittest.main()
