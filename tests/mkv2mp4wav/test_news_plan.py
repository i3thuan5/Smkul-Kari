"""新聞ê工作清單：照成果檔名排、來源揣三位、伺服器頂已有ê逐月列一擺。

3153 集照 srt_name 排，`--limit 200` 重跑愛是仝款 200 集，袂使照 csv 列序
抑伺服器 ls 順序。來源照定稿區 → 暫放區 → 原始影片檔案位置揣，干焦伺服器
明講「揣無」才換下一位；本機切 cue 留落來ê暫存封存檔袂使提來用。
"""
import os
import shutil
import tempfile
import unittest
from unittest import mock

from scripts.errors import PipelineError
from scripts.news import paths
from tools.mkv2mp4wav import news

HEADER = ("成果檔名,節目名稱,年度,集數,播出日期,族語別(英),族語別(中),語言別,"
          "語言別代號,原始影片檔案位置,備註\n")


def row(name, video):
    year = name[:4]
    date = "%s-%s-%s" % (name[:4], name[4:6], name[6:8])
    number = int(name.split("_")[1]) if name.split("_")[1].isdigit() else 1
    slot = name.split("_")[2]
    tribe = name.split("_")[3]
    return "%s,%s族語新聞,%s,%d,%s,%s,X,,ami,%s,\n" % (
        name, slot, year, number, date, tribe, video)


class FakeSftp:
    def __init__(self, files=None, folders=None, broken=()):
        self.files = files or {}
        self.folders = folders or {}
        self.broken = set(broken)
        self.scanned = []
        self.statted = []

    def stat(self, path):
        self.statted.append(path)
        if path in self.broken:
            raise PipelineError("sftp ls %s 失敗（1）：Connection timed out"
                                % path)
        return self.files.get(path)

    def scan(self, folder):
        self.scanned.append(folder)
        if folder not in self.folders:
            return None
        return self.folders[folder], []


class PlanCase(unittest.TestCase):
    NAMES = ("20210103_003_晨間_Hla'alua_拉阿魯哇",
             "20210101_001_午間_Rukai_魯凱",
             "20241001_275_晚間_Amis_阿美")

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.table = os.path.join(self.tmp, "smkul.csv")
        self.write(self.NAMES)

    def write(self, names):
        with open(self.table, "w", encoding="utf-8-sig") as handle:
            handle.write(HEADER)
            for name in names:
                handle.write(row(name, "home/mkv-raw/9月/%s.mkv"
                                 % name.split("_")[0]))

    def jobs(self, limit=0):
        return news.jobs(limit, table=self.table)


class TestOrder(PlanCase):
    def test_sorted_by_srt_name_not_row_order(self):
        names = []
        for job in self.jobs():
            names.append(job.label)
        self.assertEqual(names, sorted(self.NAMES))

    def test_limit_is_stable(self):
        first = []
        for job in self.jobs(2):
            first.append(job.label)
        self.assertEqual(first, ["20210101_001_午間_Rukai_魯凱",
                                 "20210103_003_晨間_Hla'alua_拉阿魯哇"])


class TestBadName(PlanCase):
    def test_two_digit_episode_number_is_a_failed_job(self):
        self.write(["20210103_03_晨間_Amis_阿美"])
        jobs = self.jobs()
        self.assertIn("20210103_03_晨間_Amis_阿美", jobs[0].error)
        self.assertIsNone(jobs[0].remote)


class TestPaths(PlanCase):
    def test_apostrophe_survives(self):
        job = self.jobs()[1]
        self.assertEqual(
            job.preview,
            "/home/news/mp4/2021-01/20210103_003_晨間_Hla'alua_拉阿魯哇.mp4")
        self.assertEqual(
            job.wav,
            "/home/news/wav/2021-01/20210103_003_晨間_Hla'alua_拉阿魯哇.wav")

    def test_month_comes_from_the_name_even_from_the_original_place(self):
        """原始位置佇 /home/mkv-raw/9月/，產出猶原囥 2024-10/。"""
        job = self.jobs()[2]
        sftp = FakeSftp(files={"/home/mkv-raw/9月/20241001.mkv": 2500})
        remote, where = news.locate(job, sftp, lambda text: None)
        self.assertEqual(remote, "/home/mkv-raw/9月/20241001.mkv")
        self.assertEqual(where, "原始")
        self.assertIn("/2024-10/", job.preview)
        self.assertIn("/2024-10/", job.wav)


class TestLocate(PlanCase):
    NAME = "20210101_001_午間_Rukai_魯凱"

    def job(self):
        return self.jobs()[0]

    def test_docker_first(self):
        docker = "/docker/news/mkv/2021-01/%s.mkv" % self.NAME
        home = "/home/news/mkv/2021-01/%s.mkv" % self.NAME
        sftp = FakeSftp(files={docker: 1, home: 1})
        self.assertEqual(news.locate(self.job(), sftp, print)[0], docker)

    def test_then_home(self):
        home = "/home/news/mkv/2021-01/%s.mkv" % self.NAME
        sftp = FakeSftp(files={home: 1})
        self.assertEqual(news.locate(self.job(), sftp, print)[0], home)

    def test_falling_back_says_which_path(self):
        said = []
        sftp = FakeSftp(files={"/home/mkv-raw/9月/20210101.mkv": 1})
        news.locate(self.job(), sftp, said.append)
        self.assertIn("/home/mkv-raw/9月/20210101.mkv", " ".join(said))

    def test_nowhere_names_all_three(self):
        with self.assertRaises(PipelineError) as caught:
            news.locate(self.job(), FakeSftp(), print)
        text = str(caught.exception)
        self.assertIn("/docker/news/mkv/2021-01/", text)
        self.assertIn("/home/news/mkv/2021-01/", text)
        self.assertIn("/home/mkv-raw/9月/20210101.mkv", text)

    def test_a_connection_error_does_not_move_on(self):
        docker = "/docker/news/mkv/2021-01/%s.mkv" % self.NAME
        sftp = FakeSftp(broken={docker})
        with self.assertRaises(PipelineError):
            news.locate(self.job(), sftp, print)
        self.assertEqual(sftp.statted, [docker])

    def test_the_local_cue_cutting_copy_is_not_used(self):
        """paths.mkv_path() ê暫存封存檔屬於切 cue 彼步，袂使提來做來源。"""
        local = os.path.join(self.tmp, "local.mkv")
        with open(local, "w") as handle:
            handle.write("old")
        docker = "/docker/news/mkv/2021-01/%s.mkv" % self.NAME
        with mock.patch.object(paths, "mkv_path", return_value=local):
            remote, _ = news.locate(self.job(), FakeSftp(files={docker: 1}),
                                    print)
        self.assertEqual(remote, docker)


class TestListing(PlanCase):
    def test_each_month_folder_once_per_root_and_nothing_downloaded(self):
        sftp = FakeSftp(folders={
            "/home/news/mp4/2021-01": {
                "20210101_001_午間_Rukai_魯凱.mp4": 600000000},
            "/home/news/wav/2021-01": {
                "20210101_001_午間_Rukai_魯凱.wav": 138000000,
                "empty.wav": 0}})
        got = news.listing(sftp, self.jobs())
        self.assertEqual(sorted(sftp.scanned), [
            "/home/news/mp4/2021-01", "/home/news/mp4/2024-10",
            "/home/news/wav/2021-01", "/home/news/wav/2024-10"])
        self.assertEqual(got, {
            "/home/news/mp4/2021-01/20210101_001_午間_Rukai_魯凱.mp4",
            "/home/news/wav/2021-01/20210101_001_午間_Rukai_魯凱.wav"})
        self.assertEqual(sftp.statted, [])


class TestProgramme(unittest.TestCase):
    def test_its_own_log_folder(self):
        self.assertEqual(news.NAME, "news")


if __name__ == "__main__":
    unittest.main()
