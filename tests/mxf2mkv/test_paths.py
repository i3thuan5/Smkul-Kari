"""walk: 來源資料夾底ê .mxf 對應到遠端佗一位。

「照著放」ê意思是：遠端根 ＋ --src 上尾彼層資料夾名 ＋ 檔案佇 --src
底下ê相對路徑，副檔名換 .mkv，其他一字無改。
"""
import os
import shutil
import tempfile
import unittest

from tools.mxf2mkv import walk


class TestRemotePath(unittest.TestCase):
    def test_file_at_the_root(self):
        got = walk.remote_path("/media/hong/USB/2月原始mxf檔", "a.mxf",
                               "/home/mkv-raw")
        self.assertEqual(got, "/home/mkv-raw/2月原始mxf檔/a.mkv")

    def test_file_in_a_subfolder(self):
        got = walk.remote_path("/media/hong/USB/2月原始mxf檔", "夜間/b.mxf",
                               "/home/mkv-raw")
        self.assertEqual(got, "/home/mkv-raw/2月原始mxf檔/夜間/b.mkv")

    def test_trailing_slash_on_src_does_not_change_the_answer(self):
        """`--src .../2月原始mxf檔/` 佮無煞尾斜線ê結果愛仝款。

        Tab 補完真自然就加一个斜線，若無處理，basename 會變空字串,
        規个遠端路徑就少一層。
        """
        got = walk.remote_path("/media/hong/USB/2月原始mxf檔/", "a.mxf",
                               "/home/mkv-raw")
        self.assertEqual(got, "/home/mkv-raw/2月原始mxf檔/a.mkv")

    def test_extension_case_is_normalised(self):
        got = walk.remote_path("/x/y", "A.MXF", "/home/mkv-raw")
        self.assertEqual(got, "/home/mkv-raw/y/A.mkv")

    def test_dst_root_trailing_slash(self):
        got = walk.remote_path("/x/y", "a.mxf", "/home/mkv-raw/")
        self.assertEqual(got, "/home/mkv-raw/y/a.mkv")


class TestDangerousPaths(unittest.TestCase):
    """sftp -b 會共批次檔逐逝重讀，所以路徑內底ê引號會共引數煞尾，
    換逝會開一條新ê指令。sftp.sh 家己嘛擋，毋過佇遮就擋起來，
    失敗ê時陣講會出是佗一支檔案。
    """

    def test_quote_is_rejected(self):
        self.assertFalse(walk.is_safe('a"b.mxf'))

    def test_backslash_is_rejected(self):
        self.assertFalse(walk.is_safe("a\\b.mxf"))

    def test_newline_is_rejected(self):
        self.assertFalse(walk.is_safe("a\nb.mxf"))

    def test_tab_and_carriage_return_are_rejected(self):
        self.assertFalse(walk.is_safe("a\tb.mxf"))
        self.assertFalse(walk.is_safe("a\rb.mxf"))

    def test_ordinary_names_pass(self):
        self.assertTrue(walk.is_safe("21NL004_41晚間族語新聞.mxf"))
        self.assertTrue(walk.is_safe("夜間/a b-c_d.mxf"))


class TestScan(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def touch(self, rel):
        path = os.path.join(self.tmp, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("x")

    def test_only_mxf_is_picked_up(self):
        self.touch("a.mxf")
        self.touch("b.mp4")
        self.touch("readme.txt")
        got = walk.scan(self.tmp)
        self.assertEqual(got, ["a.mxf"])

    def test_extension_match_is_case_insensitive(self):
        self.touch("a.MXF")
        got = walk.scan(self.tmp)
        self.assertEqual(got, ["a.MXF"])

    def test_subfolders_are_included(self):
        self.touch("a.mxf")
        self.touch("夜間/b.mxf")
        self.touch("夜間/深/c.mxf")
        got = walk.scan(self.tmp)
        self.assertEqual(got, ["a.mxf", "夜間/b.mxf", "夜間/深/c.mxf"])

    def test_order_is_stable(self):
        """順序愛會當重現——按呢 --limit 2 兩擺走著ê是仝兩支。"""
        for name in ["c.mxf", "a.mxf", "b.mxf"]:
            self.touch(name)
        self.assertEqual(walk.scan(self.tmp), walk.scan(self.tmp))
        self.assertEqual(walk.scan(self.tmp), ["a.mxf", "b.mxf", "c.mxf"])

    def test_empty_folder(self):
        self.assertEqual(walk.scan(self.tmp), [])


if __name__ == "__main__":
    unittest.main()
