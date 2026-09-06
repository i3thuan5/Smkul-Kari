"""upload: 共成品送去 SFTP，用ê是 scripts/news/sftp.sh。

無家己搝一份 SFTP 出來：密碼規定講密碼袂使入指令列，sftp.sh 已經用
SSH_ASKPASS 加密碼檔解決矣，而且路徑ê引號佮控制字元伊嘛家己擋。
測試用伊本身ê SFTP_DRY_RUN=1 驗指令兜了著無，無連線。
"""
import unittest
from unittest import mock

from tools.mxf2mkv import upload


class TestRemoteDirs(unittest.TestCase):
    """sftp ê mkdir 一擺干焦做一沿，序大若無佇咧就直接失敗——
    頭一擺傳入一个新資料夾就是這款。"""

    def test_every_level_outermost_first(self):
        got = upload.dirs_to_make("/home/mkv-raw/2月原始mxf檔/夜間/b.mkv")
        self.assertEqual(got, ["/home", "/home/mkv-raw",
                               "/home/mkv-raw/2月原始mxf檔",
                               "/home/mkv-raw/2月原始mxf檔/夜間"])

    def test_the_file_itself_is_not_a_folder(self):
        got = upload.dirs_to_make("/home/mkv-raw/y/a.mkv")
        self.assertNotIn("/home/mkv-raw/y/a.mkv", got)


class TestRemoteSize(unittest.TestCase):
    def test_reads_the_byte_count_out_of_ls(self):
        listing = ("-rw-r--r--    1 1000     1000      2540000000 "
                   "Sep  6 02:00 a.mkv\n")
        self.assertEqual(upload.parse_size(listing), 2540000000)

    def test_missing_file_has_no_size(self):
        self.assertIsNone(upload.parse_size("Can't ls: no such file\n"))

    def test_a_directory_line_is_not_a_file(self):
        self.assertIsNone(upload.parse_size("drwxr-xr-x 2 a b 4096 x y z\n"))


class TestPut(unittest.TestCase):
    """傳去暫名，位元組數對了才換做正名。

    「已經做好ê就跳過」愛有一个會準ê判準。成品幾若个位元組愛轉煞
    才知，所以袂當提位元組數去問遠端彼份完整無——彼愛先花二十分鐘
    轉一支才比得。改做：斷去ê半截檔案叫做 <名>.mkv.partial，正名
    <名>.mkv 一下出現就代表完整。
    """

    def _calls(self, sizes):
        calls = []

        def run(cmd, **kwargs):
            calls.append(cmd)
            if "ls" in cmd:
                return mock.Mock(returncode=0, stdout=sizes.pop(0))
            return mock.Mock(returncode=0, stdout="")

        return run, calls

    def test_uploads_to_a_partial_name_then_renames(self):
        run, calls = self._calls(["-rw-r--r-- 1 a b 10 x y z\n"])
        with mock.patch.object(upload.subprocess, "run", run):
            upload.put("/tmp/a.mkv", "/home/mkv-raw/y/a.mkv", 10)
        verbs = []
        for cmd in calls:
            verbs.append(cmd[2])
        self.assertIn("rename", verbs)
        self.assertLess(verbs.index("put"), verbs.index("rename"))
        for cmd in calls:
            if cmd[2] == "put":
                self.assertTrue(cmd[4].endswith(".partial"))
            if cmd[2] == "rename":
                self.assertTrue(cmd[3].endswith(".partial"))
                self.assertEqual(cmd[4], "/home/mkv-raw/y/a.mkv")

    def test_byte_count_is_checked_before_the_rename(self):
        """對袂起來就毋通換名——正名袂當出現。"""
        run, calls = self._calls(["-rw-r--r-- 1 a b 640 x y z\n"])
        with mock.patch.object(upload.subprocess, "run", run):
            with self.assertRaises(upload.UploadError):
                upload.put("/tmp/a.mkv", "/home/mkv-raw/y/a.mkv", 1000)
        for cmd in calls:
            self.assertNotEqual(cmd[2], "rename")

    def test_makes_dirs_then_puts(self):
        run, calls = self._calls(["-rw-r--r-- 1 a b 10 x y z\n"])
        with mock.patch.object(upload.subprocess, "run", run):
            upload.put("/tmp/a.mkv", "/home/mkv-raw/y/a.mkv", 10)
        verbs = []
        for cmd in calls:
            verbs.append(cmd[2])
        self.assertEqual(verbs.count("put"), 1)
        self.assertLess(verbs.index("mkdir"), verbs.index("put"))

    def test_paths_are_separate_arguments(self):
        """路徑袂使鬥做一逝指令字串——sftp -b 會共伊重讀。"""
        run, calls = self._calls(["-rw-r--r-- 1 a b 10 x y z\n"])
        with mock.patch.object(upload.subprocess, "run", run):
            upload.put("/tmp/a.mkv", "/home/mkv-raw/y/a.mkv", 10)
        for cmd in calls:
            if cmd[2] == "put":
                self.assertEqual(cmd[3], "/tmp/a.mkv")
                self.assertEqual(cmd[4],
                                 "/home/mkv-raw/y/a.mkv.partial")

    def test_byte_count_mismatch_fails(self):
        run, _ = self._calls(["-rw-r--r-- 1 a b 640 x y z\n"])
        with mock.patch.object(upload.subprocess, "run", run):
            with self.assertRaises(upload.UploadError):
                upload.put("/tmp/a.mkv", "/home/mkv-raw/y/a.mkv", 1000)


class TestDone(unittest.TestCase):
    """跳過ê判準：正名有佇咧就是做好矣。

    半截ê上傳叫做 .partial，永遠袂佔著正名，所以「有」就等於「全」。
    """

    def test_present_final_name_is_done(self):
        def run(cmd, **kwargs):
            return mock.Mock(returncode=0,
                             stdout="-rw-r--r-- 1 a b 2540000000 x y z\n")

        with mock.patch.object(upload.subprocess, "run", run):
            self.assertTrue(upload.already_there("/home/mkv-raw/y/a.mkv"))

    def test_absent_final_name_is_not_done(self):
        def run(cmd, **kwargs):
            return mock.Mock(returncode=1, stdout="not found\n")

        with mock.patch.object(upload.subprocess, "run", run):
            self.assertFalse(upload.already_there("/home/mkv-raw/y/a.mkv"))

    def test_a_zero_byte_final_name_is_not_done(self):
        """0 位元組ê正名毋是成品，是別項代誌留落來ê。"""
        def run(cmd, **kwargs):
            return mock.Mock(returncode=0,
                             stdout="-rw-r--r-- 1 a b 0 x y z\n")

        with mock.patch.object(upload.subprocess, "run", run):
            self.assertFalse(upload.already_there("/home/mkv-raw/y/a.mkv"))


class TestRemoteSizeLookup(unittest.TestCase):
    def test_absent_remote_reads_as_none(self):
        def run(cmd, **kwargs):
            return mock.Mock(returncode=1, stdout="not found\n")

        with mock.patch.object(upload.subprocess, "run", run):
            self.assertIsNone(upload.remote_size("/home/mkv-raw/y/a.mkv"))


if __name__ == "__main__":
    unittest.main()
