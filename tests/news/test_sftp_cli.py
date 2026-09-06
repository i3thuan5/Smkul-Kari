"""sftp.sh 的介面：動詞＋各自獨立的參數，路徑不進指令字串。

`sftp -b` 是逐行剖析批次檔的，所以路徑若被拼進一行指令裡，引號會斷、
換行會多出一行指令。改成由 sftp.sh 自己組批次行，並且拒收帶引號、
反斜線、換行的路徑——母帶檔名不會有這些字元。

離線測試：`SFTP_DRY_RUN=1` 只印出要送的批次內容就結束，不連線。
"""
import os
import subprocess
import unittest

from scripts.news import paths

SFTP = os.path.join(paths.ROOT, "scripts", "news", "sftp.sh")


def run(*args):
    env = dict(os.environ)
    env["SFTP_DRY_RUN"] = "1"
    return subprocess.run(["bash", SFTP] + list(args),
                          capture_output=True, text=True, env=env)


class TestBatchBuilding(unittest.TestCase):
    def test_get_builds_one_quoted_line(self):
        proc = run("get", "/docker/一月/影片.mxf", "/stage/影片.mxf")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout,
                         'get "/docker/一月/影片.mxf" "/stage/影片.mxf"\n')

    def test_ls_is_the_long_form_the_callers_parse(self):
        # 呼叫端都在讀第 5 欄的位元組數，所以 ls 一定要是 -l
        proc = run("ls", "/docker/ilrdf-corpus/2月")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, 'ls -l "/docker/ilrdf-corpus/2月"\n')

    def test_stdin_batches_still_work_for_ad_hoc_use(self):
        env = dict(os.environ)
        env["SFTP_DRY_RUN"] = "1"
        proc = subprocess.run(["bash", SFTP, "-"], input="ls /docker\n",
                              capture_output=True, text=True, env=env)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, "ls /docker\n")


class TestPut(unittest.TestCase):
    """put：封存 mkv 送轉去伺服器。

    佮 get 的方向倒反——本機 → 遠端——所以兩爿的路徑攏愛檢查，而且順序
    愛照 sftp 的：`put LOCAL REMOTE`。
    """

    def test_put_builds_one_quoted_line(self):
        proc = run("put", "/kithann/out/mkv/影片.mkv",
                   "/home/news/mkv/2021-02/影片.mkv")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(
            proc.stdout,
            'put "/kithann/out/mkv/影片.mkv" '
            '"/home/news/mkv/2021-02/影片.mkv"\n')

    def test_both_sides_are_checked(self):
        bad = '/home/news/a".mkv'
        self.assertEqual(run("put", "/local/ok.mkv", bad).returncode, 2)
        self.assertEqual(run("put", bad, "/home/news/ok.mkv").returncode, 2)

    def test_put_needs_both_sides(self):
        self.assertEqual(run("put", "/only-local").returncode, 2)


class TestMkdir(unittest.TestCase):
    """mkdir：上傳進前愛先有資料夾。

    sftp 的 mkdir 拄著「已經有矣」會回非零，佇 batch 內底就會kā整批
    做煞。頭前彼个 `-` 是 sftp 的「這逝失敗嘛繼續」記號，是刁工的。
    """

    def test_mkdir_tolerates_an_existing_folder(self):
        proc = run("mkdir", "/home/news/mkv/2021-02")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, '-mkdir "/home/news/mkv/2021-02"\n')

    def test_mkdir_checks_its_path(self):
        self.assertEqual(run("mkdir", '/home/a".mkv').returncode, 2)
        self.assertEqual(run("mkdir", "").returncode, 2)

    def test_mkdir_takes_exactly_one_path(self):
        self.assertEqual(run("mkdir", "/a", "/b").returncode, 2)


class TestUnsafePathsRefused(unittest.TestCase):
    def test_a_quote_would_break_out_of_the_batch_line(self):
        proc = run("get", '/docker/a".mxf', "/stage/x.mxf")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("拒絕", proc.stderr)

    def test_a_newline_would_inject_a_second_command(self):
        proc = run("get", "/docker/a\nput /etc/passwd /x", "/stage/x.mxf")
        self.assertEqual(proc.returncode, 2)

    def test_a_backslash_is_refused_too(self):
        proc = run("ls", "/docker/a\\b")
        self.assertEqual(proc.returncode, 2)

    def test_the_local_side_is_checked_as_well(self):
        proc = run("get", "/docker/ok.mxf", '/stage/a".mxf')
        self.assertEqual(proc.returncode, 2)

    def test_an_empty_path_is_refused(self):
        self.assertEqual(run("ls", "").returncode, 2)


class TestUsageErrors(unittest.TestCase):
    def test_no_arguments_is_a_usage_error(self):
        self.assertEqual(run().returncode, 2)

    def test_unknown_verb_is_refused(self):
        # `rename` 本底佇這口灶，後來 mxf2mkv 需要伊（傳暫名才換正名）
        # 才加入去，所以這位換做別个無支援ê動詞。
        self.assertEqual(run("rm", "/a").returncode, 2)
        self.assertEqual(run("chmod", "/a", "/b").returncode, 2)

    def test_get_needs_both_sides(self):
        self.assertEqual(run("get", "/only-remote").returncode, 2)

    def test_ls_takes_exactly_one_path(self):
        self.assertEqual(run("ls", "/a", "/b").returncode, 2)


if __name__ == "__main__":
    unittest.main()


class TestRename(unittest.TestCase):
    """rename：傳煞才共暫名換做正名。

    為著「已經做好ê就跳過」這條判準。成品幾若个位元組愛轉煞才知,
    所以袂當提位元組數去問「遠端彼份完整無」——彼愛先花二十分鐘
    轉一支才比得。改做傳去 <名>.mkv.partial，位元組數對了才 rename
    做 <名>.mkv：按呢「正名有佇咧」本身就是「完整」ê證據，因為斷
    去ê彼份叫做別个名。

    佮 archive_batch.py 佇本機做ê代誌仝款（.partial.mkv → os.rename）。
    """

    def test_rename_builds_one_quoted_line(self):
        proc = run("rename", "/home/mkv-raw/2月/a.mkv.partial",
                   "/home/mkv-raw/2月/a.mkv")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(
            proc.stdout,
            'rename "/home/mkv-raw/2月/a.mkv.partial" '
            '"/home/mkv-raw/2月/a.mkv"\n')

    def test_rename_checks_both_paths(self):
        proc = run("rename", '/home/a"b.partial', "/home/a.mkv")
        self.assertNotEqual(proc.returncode, 0)
        proc = run("rename", "/home/a.partial", "/home/a\nb.mkv")
        self.assertNotEqual(proc.returncode, 0)

    def test_rename_takes_exactly_two_paths(self):
        self.assertNotEqual(run("rename", "/home/a").returncode, 0)
        self.assertNotEqual(
            run("rename", "/a", "/b", "/c").returncode, 0)

    def test_rename_does_not_tolerate_failure(self):
        """袂使加頭前彼个 "-"。

        mkdir 用 "-" 是因為「已經有矣」是正常狀況。rename 倒反：
        伊若失敗，就是正名無出現，彼支片實際上無傳成功——彼陣袂當
        恬恬過去，若無下一擺會共伊當做做好矣。
        """
        proc = run("rename", "/home/a.partial", "/home/a.mkv")
        self.assertFalse(proc.stdout.startswith("-"))
