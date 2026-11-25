"""開會了ê工作清單：兩張表攏做、照成果檔名排、來源取原始影片檔案位置。

使用者裁定 2026-11-23：字幕版型異常表彼 5 集（083 僅華語字幕、088／090／
098／116 無字幕）嘛愛做——無雙語字幕，毋過預覽檔正好提去字幕編輯器補
字幕，音檔嘛會當做語料。干焦讀 smkul.csv 會漏掉這 5 集。
"""
import os
import shutil
import tempfile
import unittest

from tools.mkv2mp4wav import aiyalaeho

HEADER = ("成果檔名,節目名稱,集數,族語別(英),族語別(中),語言別,語言別代號,"
          "原始影片檔案位置,備註\n")
FOLDER = "docker/族語節目-aiyalaeho開會了/"


def write(path, rows):
    with open(path, "w", encoding="utf-8-sig") as handle:
        handle.write(HEADER)
        for name, video, note in rows:
            handle.write("%s,開會了,1,X,X,,sxr,%s%s,%s\n"
                         % (name, FOLDER, video, note))


class FakeSftp:
    def __init__(self, files=None, folders=None):
        self.files = files or {}
        self.folders = folders or {}
        self.scanned = []
        self.statted = []

    def stat(self, path):
        self.statted.append(path)
        return self.files.get(path)

    def scan(self, folder):
        self.scanned.append(folder)
        if folder not in self.folders:
            return None
        return self.folders[folder], []


class PlanCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.table = os.path.join(self.tmp, "smkul.csv")
        self.abnormal = os.path.join(self.tmp, "smkul-字幕版型異常.csv")
        write(self.table, [
            ("開會了_107_Hla'alua_拉阿魯哇", "107-拉阿魯哇語-雙語字幕.mkv", ""),
            ("開會了_079_SaiSiyat_賽夏", "079-賽夏語-雙語字幕.mp4", ""),
        ])
        write(self.abnormal, [
            ("開會了_116_Unknown_（未知）", "116ALL_無字.mkv", "無字幕"),
        ])

    def jobs(self, limit=0):
        return aiyalaeho.jobs(limit, table=self.table,
                              abnormal_table=self.abnormal)


class TestBothTables(PlanCase):
    def test_the_abnormal_table_is_in_the_list(self):
        names = []
        for job in self.jobs():
            names.append(job.label)
        self.assertIn("開會了_116_Unknown_（未知）", names)
        self.assertEqual(len(names), 3)


class TestOrder(PlanCase):
    def test_sorted_by_srt_name_not_row_order(self):
        names = []
        for job in self.jobs():
            names.append(job.label)
        self.assertEqual(names, ["開會了_079_SaiSiyat_賽夏",
                                 "開會了_107_Hla'alua_拉阿魯哇",
                                 "開會了_116_Unknown_（未知）"])

    def test_limit_takes_the_same_first_ones_every_time(self):
        first = []
        for job in self.jobs(2):
            first.append(job.label)
        again = []
        for job in self.jobs(2):
            again.append(job.label)
        self.assertEqual(first, again)
        self.assertEqual(len(first), 2)


class TestBadName(PlanCase):
    def test_a_bad_name_becomes_a_failed_job_without_paths(self):
        write(self.table, [("開會了_68_Amis_阿美", "068-阿美語.mp4", "")])
        write(self.abnormal, [])
        jobs = self.jobs()
        self.assertEqual(len(jobs), 1)
        self.assertIn("開會了_68_Amis_阿美", jobs[0].error)
        self.assertIsNone(jobs[0].remote)


class TestPaths(PlanCase):
    def test_outputs_have_no_sub_folder(self):
        job = self.jobs()[1]
        self.assertEqual(
            job.preview, "/home/aiyalaeho/mp4/開會了_107_Hla'alua_拉阿魯哇.mp4")
        self.assertEqual(
            job.wav, "/home/aiyalaeho/wav/開會了_107_Hla'alua_拉阿魯哇.wav")

    def test_source_is_the_catalogue_location_with_a_leading_slash(self):
        jobs = self.jobs()
        sftp = FakeSftp(files={
            "/" + FOLDER + "079-賽夏語-雙語字幕.mp4": 867017267,
            "/" + FOLDER + "107-拉阿魯哇語-雙語字幕.mkv": 1506779505})
        self.assertEqual(aiyalaeho.locate(jobs[0], sftp, print),
                         ("/" + FOLDER + "079-賽夏語-雙語字幕.mp4",
                          "原始影片檔案位置"))
        self.assertEqual(aiyalaeho.locate(jobs[1], sftp, print)[0],
                         "/" + FOLDER + "107-拉阿魯哇語-雙語字幕.mkv")

    def test_a_missing_source_fails_naming_the_path(self):
        with self.assertRaises(Exception) as caught:
            aiyalaeho.locate(self.jobs()[0], FakeSftp(), print)
        self.assertIn("079-賽夏語-雙語字幕.mp4", str(caught.exception))


class TestListing(PlanCase):
    def test_each_folder_listed_once_and_nothing_downloaded(self):
        sftp = FakeSftp(folders={
            "/home/aiyalaeho/mp4": {"開會了_079_SaiSiyat_賽夏.mp4": 600000000,
                                    "half.mp4": 0},
            "/home/aiyalaeho/wav": {"開會了_079_SaiSiyat_賽夏.wav": 80000000}})
        got = aiyalaeho.listing(sftp, self.jobs())
        self.assertEqual(sorted(sftp.scanned),
                         ["/home/aiyalaeho/mp4", "/home/aiyalaeho/wav"])
        self.assertEqual(got, {
            "/home/aiyalaeho/mp4/開會了_079_SaiSiyat_賽夏.mp4",
            "/home/aiyalaeho/wav/開會了_079_SaiSiyat_賽夏.wav"})
        self.assertEqual(sftp.statted, [])

    def test_folders_not_there_yet_mean_nothing_done(self):
        self.assertEqual(aiyalaeho.listing(FakeSftp(), self.jobs()), set())


class TestProgramme(unittest.TestCase):
    def test_its_own_log_folder(self):
        self.assertEqual(aiyalaeho.NAME, "aiyalaeho")


if __name__ == "__main__":
    unittest.main()
