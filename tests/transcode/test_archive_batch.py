"""archive_batch: resolve each episode's master path, name its staged
download and archival mkv, and know when it is already done -- pure logic,
mirrors news/test_asrmt_run.py's TestMp3Resolution. Fetching over SFTP and
running ffmpeg are I/O and are not unit tested (same reasoning as the vosk
call layer: real-transfer smoke test guards them instead).
"""
import os
import tempfile
import unittest

from scripts.transcode import archive_batch


class TestVideoRemote(unittest.TestCase):
    def test_remote_path_from_smkul_row(self):
        rows = [{"播出日期": "2021-02-06", "播出時段": "晚間",
                 "影片檔案位置":
                 "ilrdf-corpus/族語新聞/110.1-110.10/7月/"
                 "21NL004_37晚間族語新聞.mp4"}]
        got = archive_batch.video_remote(
            "20210206_037_晚間_Paiwan_排灣", rows)
        self.assertEqual(
            got, "/docker/ilrdf-corpus/族語新聞/110.1-110.10/7月/"
                 "21NL004_37晚間族語新聞.mp4")

    def test_missing_row_fails_loud(self):
        with self.assertRaises(SystemExit):
            archive_batch.video_remote("20210301_060_午間_Cou_鄒", [])

    def test_semicolon_cell_picks_the_matching_slot(self):
        rows = [{"播出日期": "2021-02-06", "播出時段": "晚間",
                 "影片檔案位置":
                 "ilrdf-corpus/7月/21NL004_37午間族語新聞.mp4;"
                 "ilrdf-corpus/7月/21NL004_37晚間族語新聞.mp4"}]
        got = archive_batch.video_remote(
            "20210206_037_晚間_Paiwan_排灣", rows)
        self.assertEqual(
            got, "/docker/ilrdf-corpus/7月/21NL004_37晚間族語新聞.mp4")

    def test_feb_mxf_shorthand_expands_to_the_real_sftp_directory(self):
        # smkul.csv 對 2 月 mxf 批次記的是舊本機掛載遺留下來的簡寫
        # "ilrdf-corpus/2月/<檔名>"；SFTP 上真正的路徑多一層
        # "族語新聞/110.1-110.10/2月原始mxf檔/"（見 refine_fetch.sh 的
        # 同一個註記），簡寫路徑在 SFTP 上找不到檔案。
        rows = [{"播出日期": "2021-02-01", "播出時段": "晚間",
                 "影片檔案位置":
                 "ilrdf-corpus/2月/20NL004_32晚間族語新聞.mxf"}]
        got = archive_batch.video_remote(
            "20210201_032_晚間_Amis_阿美", rows)
        self.assertEqual(
            got, "/docker/ilrdf-corpus/族語新聞/110.1-110.10/"
                 "2月原始mxf檔/20NL004_32晚間族語新聞.mxf")


class TestStageName(unittest.TestCase):
    def test_keeps_the_source_extension(self):
        self.assertEqual(
            archive_batch.stage_name(
                "20210201_032_晚間_Amis_阿美",
                "/docker/ilrdf-corpus/2月/x.mxf"),
            "20210201_032_晚間_Amis_阿美.mxf")
        self.assertEqual(
            archive_batch.stage_name(
                "20210206_037_晚間_Paiwan_排灣",
                "/docker/ilrdf-corpus/7月/x.mp4"),
            "20210206_037_晚間_Paiwan_排灣.mp4")


class TestOutputPath(unittest.TestCase):
    def test_output_is_srt_name_dot_mkv(self):
        out = archive_batch.output_path(
            "20210201_032_晚間_Amis_阿美", archive_dir="/tmp/mkv")
        self.assertEqual(
            out, "/tmp/mkv/20210201_032_晚間_Amis_阿美.mkv")


class TestAlreadyDone(unittest.TestCase):
    def test_true_once_the_mkv_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            name = "20210201_032_晚間_Amis_阿美"
            self.assertFalse(archive_batch.already_done(name, tmp))
            open(os.path.join(tmp, name + ".mkv"), "w").close()
            self.assertTrue(archive_batch.already_done(name, tmp))


if __name__ == "__main__":
    unittest.main()
