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

    def test_apple_double_sidecars_are_skipped(self):
        """macOS 寫去 exFAT／FAT 隨身硬碟ê時，逐支檔案會伴生一个
        `._檔名` ê資源分支 metadata，副檔名照抄所以會通過 .mxf ê篩選，
        毋過內容毋是影片，送去 encode 一定編碼失敗（0925-2210 這批
        111.01-111.05 ê 232 支失敗攏是這款）。"""
        self.touch("a.mxf")
        self.touch("._a.mxf")
        self.touch("夜間/b.mxf")
        self.touch("夜間/._b.mxf")
        got = walk.scan(self.tmp)
        self.assertEqual(got, ["a.mxf", "夜間/b.mxf"])


if __name__ == "__main__":
    unittest.main()
