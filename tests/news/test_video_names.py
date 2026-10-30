"""video_names：伺服器上ê新聞影片搬去 `/home/news/mkv/<年-月>/<成果檔名>.mkv`。

搬移是 rename（移動），毋是複製：全部約 7 TB，伺服器干焦賰 5.3 TB。
所以逐支ê安全愛靠規劃、清單、續跑——一支搬毋著，無法度重來。

怎麼對伺服器下指令由外面傳入來，這爿測試攏傳假ê，離線。
"""
import csv
import io
import os
import posixpath
import tempfile
import unittest

from scripts.errors import PipelineError
from scripts.news import paths
from scripts.news import video_names

RUKAI = "20210101_001_午間_Rukai_魯凱"
AMIS = "20241001_275_晚間_Amis_阿美"
HLAALUA = "20210103_003_晨間_Hla'alua_拉阿魯哇"


class FakeSftp(object):
    """假ê伺服器：一个 {路徑: 大小} ê檔案表，逐項照真ê規矩。

    - mkdir 一改干焦一層，上層無就失敗（真ê sftp 嘛按呢）；已經有袂算錯
    - rename 目標已經有就失敗（sftp ê rename 袂覆寫）、上層資料夾愛先有
    - stat 揣無回 None；`broken` 內底ê路徑回別款失敗（逾時、權限）
    - `cross_device` 是 True ê時，跨 /home/news 佮 /home/mkv-raw 兩爿ê
      rename 失敗（模擬跨子卷）
    """

    def __init__(self, files, cross_device=False):
        self.files = dict(files)
        self.dirs = set(["/"])
        for path in self.files:
            self._add_parents(path)
        self.broken = set()
        self.fail_rename = set()
        self.fail_rmdir = set()
        self.cross_device = cross_device
        self.calls = []

    def _add_parents(self, path):
        parent = posixpath.dirname(path)
        while parent and parent not in self.dirs:
            self.dirs.add(parent)
            parent = posixpath.dirname(parent)

    def stat(self, path):
        self.calls.append(("stat", path))
        if path in self.broken:
            raise PipelineError("sftp ls 失敗：Connection timed out")
        return self.files.get(path)

    def listdir(self, folder):
        self.calls.append(("listdir", folder))
        if folder not in self.dirs:
            return None
        out = {}
        for path, size in self.files.items():
            if posixpath.dirname(path) == folder:
                out[posixpath.basename(path)] = size
        return out

    def scan(self, folder):
        self.calls.append(("scan", folder))
        if folder not in self.dirs:
            return None
        files = {}
        for path, size in self.files.items():
            if posixpath.dirname(path) == folder:
                files[posixpath.basename(path)] = size
        subdirs = []
        for path in sorted(self.dirs):
            if path != folder and posixpath.dirname(path) == folder:
                subdirs.append(posixpath.basename(path))
        return files, subdirs

    def rmdir(self, path):
        self.calls.append(("rmdir", path))
        if path in self.fail_rmdir:
            raise PipelineError("rmdir 失敗：%s 伺服器拒絕" % path)
        found = self.scan(path)
        self.calls.pop()
        if found is None:
            raise PipelineError("rmdir 失敗：%s 無佇咧" % path)
        if found[0] or found[1]:
            raise PipelineError("rmdir 失敗：%s 毋是空ê" % path)
        self.dirs.discard(path)

    def mkdir(self, path):
        self.calls.append(("mkdir", path))
        parent = posixpath.dirname(path)
        if parent not in self.dirs:
            raise PipelineError("mkdir 失敗：上層 %s 無佇咧" % parent)
        self.dirs.add(path)

    def rename(self, old, new):
        self.calls.append(("rename", old, new))
        if old in self.fail_rename:
            raise PipelineError("rename 失敗：伺服器拒絕 %s" % old)
        if old not in self.files:
            raise PipelineError("rename 失敗：%s 無佇咧" % old)
        if new in self.files:
            raise PipelineError("rename 失敗：%s 已經有" % new)
        if posixpath.dirname(new) not in self.dirs:
            raise PipelineError("rename 失敗：上層無佇咧")
        if self.cross_device and (old.startswith("/home/mkv-raw/") !=
                                  new.startswith("/home/mkv-raw/")):
            raise PipelineError("rename 失敗：Invalid cross-device link")
        self.files[new] = self.files.pop(old)

    def verbs(self):
        out = []
        for call in self.calls:
            out.append(call[0])
        return out


def entry(name, original, programme="午間族語新聞"):
    """`episodes.load` 出來ê一集，揣影片用得著ê欄。"""
    return {"srt_name": name, "video": original, "原始影片檔案位置": original,
            "節目名稱": programme}


def row(name, original):
    return {"成果檔名": name, "原始影片檔案位置": original}


def rows():
    return [
        row(RUKAI,
            "home/mkv-raw/110.01-110.10/1月原始mxf檔/20210101S1100.mkv"),
        row(HLAALUA,
            "home/mkv-raw/110.01-110.10/1月原始mxf檔/20210103s0800.mkv"),
        row(AMIS, "home/mkv-raw/113/9月/20241001S2000.mkv"),
    ]


class TestPlan(unittest.TestCase):

    def test_one_move_per_row_old_from_the_column_new_from_the_name(self):
        # 使用者舉ê例：.../1月原始mxf檔/20210101S1100.mkv
        #           → /home/news/mkv/2021-01/20210101_001_午間_Rukai_魯凱.mkv
        got = video_names.plan(rows(), [])
        self.assertEqual(len(got), 3)
        first = got[0]
        self.assertEqual(first.name, RUKAI)
        self.assertEqual(
            first.old,
            "/home/mkv-raw/110.01-110.10/1月原始mxf檔/20210101S1100.mkv")
        self.assertEqual(
            first.new,
            "/home/news/mkv/2021-01/20210101_001_午間_Rukai_魯凱.mkv")

    def test_the_order_is_the_catalogue_order(self):
        names = []
        for move in video_names.plan(rows(), []):
            names.append(move.name)
        self.assertEqual(names, [RUKAI, HLAALUA, AMIS])

    def test_the_month_comes_from_the_name_not_the_old_folder(self):
        # 20241001_275 本底囥佇「9月」資料夾——48 逝ê資料夾月份佮播出月份無仝。
        move = video_names.plan(rows(), [])[2]
        self.assertIn("/2024-10/", move.new)
        self.assertIn("/113/9月/", move.old)

    def test_the_apostrophe_name_is_kept_whole(self):
        move = video_names.plan(rows(), [])[1]
        self.assertTrue(move.new.endswith("Hla'alua_拉阿魯哇.mkv"))

    def test_an_excluded_path_is_never_a_move(self):
        # 20241002S2000.mkv 佮目錄用ê 20241001S2000.mkv 串流相仝，排除ê。
        excluded = ["/home/mkv-raw/113/10月/20241002S2000.mkv"]
        for move in video_names.plan(rows(), excluded):
            self.assertNotIn("20241002S2000", move.old)
            self.assertNotIn("20241002S2000", move.new)

    def test_a_row_whose_source_is_excluded_stops_the_whole_plan(self):
        excluded = ["/home/mkv-raw/113/9月/20241001S2000.mkv"]
        with self.assertRaises(PipelineError) as caught:
            video_names.plan(rows(), excluded)
        self.assertIn(AMIS, str(caught.exception))

    def test_the_excluded_list_may_spell_the_path_differently(self):
        # 目錄寫 `home/…`，排除清單寫 `/home/…`；字串直接比會漏。
        excluded = ["home/mkv-raw/113/9月/20241001S2000.mkv"]
        with self.assertRaises(PipelineError):
            video_names.plan(rows(), excluded)

    def test_two_rows_with_one_old_file_refuse_the_whole_plan(self):
        # 搬一半ê話，第二逝ê檔已經毋佇原位矣。
        twin = rows() + [row("20241002_276_晚間_Amis_阿美",
                             "home/mkv-raw/113/9月/20241001S2000.mkv")]
        with self.assertRaises(PipelineError) as caught:
            video_names.plan(twin, [])
        self.assertIn(AMIS, str(caught.exception))
        self.assertIn("20241002_276_晚間_Amis_阿美", str(caught.exception))

    def test_two_rows_with_one_new_path_refuse_the_whole_plan(self):
        twin = rows() + [row(AMIS, "home/mkv-raw/113/10月/別支.mkv")]
        with self.assertRaises(PipelineError) as caught:
            video_names.plan(twin, [])
        self.assertIn(AMIS, str(caught.exception))

    def test_a_source_outside_mkv_raw_is_refused_by_name(self):
        # 開會了佇 /docker/…，其他人唯讀，嘛毋是 mkv。
        bad = rows() + [row("20240101_001_午間_Atayal_泰雅",
                            "docker/族語節目-aiyalaeho開會了/068.mp4")]
        with self.assertRaises(PipelineError) as caught:
            video_names.plan(bad, [])
        self.assertIn("20240101_001_午間_Atayal_泰雅", str(caught.exception))

    def test_a_semicolon_list_is_refused_not_guessed(self):
        # 規劃愛一條確定ê舊位置；候選清單愛先決定是佗一支。
        bad = [row(RUKAI, "home/mkv-raw/a/1.mkv;home/mkv-raw/a/2.mkv")]
        with self.assertRaises(PipelineError):
            video_names.plan(bad, [])

    def test_a_blank_source_is_refused_by_name(self):
        with self.assertRaises(PipelineError) as caught:
            video_names.plan([row(RUKAI, "")], [])
        self.assertIn(RUKAI, str(caught.exception))

    def test_the_new_path_is_the_shared_one(self):
        # 位置ê算法干焦一份（paths.video_path）。
        move = video_names.plan(rows(), [])[0]
        self.assertEqual(move.new, paths.video_path(RUKAI))


CANON = "/home/news/mkv/2021-01/20210101_001_午間_Rukai_魯凱.mkv"
ORIG = "/home/mkv-raw/110.01-110.10/1月原始mxf檔/20210101S1100.mkv"
ORIG_CELL = "home/mkv-raw/110.01-110.10/1月原始mxf檔/20210101S1100.mkv"


class TestLocate(unittest.TestCase):
    """新位置揣無才退回 `原始影片檔案位置`；退ê時愛大聲講。"""

    def setUp(self):
        self.said = []

    def say(self, line):
        self.said.append(line)

    def test_the_canonical_place_wins_and_the_original_is_not_read(self):
        # 原始欄空白抑是亂寫攏無影響；只問新位置一擺。
        for cell in ("", "ilrdf-corpus/亂寫/無這檔.mkv"):
            fake = FakeSftp({CANON: 123})
            got = video_names.locate(entry(RUKAI, cell), fake, say=self.say)
            self.assertEqual(got.path, CANON)
            self.assertEqual(got.size, 123)
            self.assertEqual(got.source, "正規")
            self.assertEqual(fake.calls, [("stat", CANON)])
        self.assertEqual(self.said, [])

    def test_missing_canonical_falls_back_and_says_so(self):
        fake = FakeSftp({ORIG: 456})
        got = video_names.locate(entry(RUKAI, ORIG_CELL), fake, say=self.say)
        self.assertEqual((got.path, got.size, got.source), (ORIG, 456, "原始"))
        self.assertEqual(len(self.said), 1)
        self.assertIn("退回原始位置", self.said[0])
        self.assertIn(ORIG, self.said[0])

    def test_neither_place_names_both_paths(self):
        with self.assertRaises(PipelineError) as caught:
            video_names.locate(entry(RUKAI, ORIG_CELL), FakeSftp({}),
                               say=self.say)
        self.assertIn(CANON, str(caught.exception))
        self.assertIn(ORIG, str(caught.exception))

    def test_a_blank_original_column_is_said_not_guessed(self):
        with self.assertRaises(PipelineError) as caught:
            video_names.locate(entry(RUKAI, ""), FakeSftp({}), say=self.say)
        self.assertIn(CANON, str(caught.exception))
        self.assertIn("空", str(caught.exception))

    def test_a_failure_that_is_not_not_found_does_not_fall_back(self):
        # 連線逾時、權限錯誤：網路一抖就去讀原始位置，可能讀著過時ê檔。
        fake = FakeSftp({ORIG: 456})
        fake.broken.add(CANON)
        with self.assertRaises(PipelineError) as caught:
            video_names.locate(entry(RUKAI, ORIG_CELL), fake, say=self.say)
        self.assertIn("timed out", str(caught.exception))
        self.assertNotIn(("stat", ORIG), fake.calls)
        self.assertEqual(self.said, [])

    def test_a_candidate_list_picks_by_the_sourcing_rules_not_the_first(self):
        # 母帶優先（`sources.pick` ê頭一條規矩），毋是提第一條。
        cell = "home/mkv-raw/a/x.mp4;home/mkv-raw/a/x.mxf"
        fake = FakeSftp({"/home/mkv-raw/a/x.mxf": 9})
        got = video_names.locate(entry(RUKAI, cell), fake, say=self.say)
        self.assertEqual(got.path, "/home/mkv-raw/a/x.mxf")
        self.assertEqual(got.source, "原始")


class Result(object):
    def __init__(self, returncode, out="", err=""):
        self.returncode = returncode
        self.stdout = out.encode("utf-8")
        self.stderr = err.encode("utf-8")


class TestRealSftpTellsNotFoundFromOtherFailures(unittest.TestCase):
    """`sftp.sh ls` 一律 exit 1，愛看訊息才分會出「揣無」佮「連袂著」。

    本底 `audio._remote_size` 干焦看標準輸出，兩種失敗攏當做「無這个檔」，
    網路一抖就誤判做缺檔。
    """

    LONG = ("-rwxrwxrwx    1 ilrdf-corpus users    1672396330 Sep 17 19:59 "
            "20241201S0800.mkv")

    def sftp(self, result):
        calls = []

        def run(cmd, **kw):
            calls.append(cmd)
            return result
        return video_names.Sftp(run=run), calls

    def test_a_found_file_gives_its_size(self):
        client, _calls = self.sftp(Result(0, "sftp> ls -l \"/x\"\n" +
                                          self.LONG + "\n"))
        self.assertEqual(client.stat("/x"), 1672396330)

    def test_not_found_gives_none(self):
        client, _calls = self.sftp(Result(
            1, "sftp> ls -l \"/x\"\nCan't ls: \"/x\" not found\n"))
        self.assertIsNone(client.stat("/x"))

    def test_any_other_failure_raises(self):
        for text in ("Connection timed out", "Permission denied",
                     "Received disconnect"):
            client, _calls = self.sftp(Result(255, "", text))
            with self.assertRaises(PipelineError) as caught:
                client.stat("/x")
            self.assertIn(text, str(caught.exception))

    def test_the_path_goes_through_sftp_sh_as_its_own_argument(self):
        client, calls = self.sftp(Result(0, self.LONG + "\n"))
        path = "/home/news/mkv/2021-01/20210103_003_晨間_Hla'alua.mkv"
        client.stat(path)
        self.assertEqual(calls[0][-1], path)
        self.assertEqual(calls[0][-2], "ls")


SIZES = {RUKAI: 111, HLAALUA: 222, AMIS: 333}


class ApplyFixture(unittest.TestCase):
    """三支影片佇舊位置，伺服器頂猶無 /home/news。"""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.manifest_dir = os.path.join(tmp.name, "video-rename")
        self.said = []
        self.moves = video_names.plan(rows(), [])
        files = {}
        for move in self.moves:
            files[move.old] = SIZES[move.name]
        self.fake = FakeSftp(files)

    def say(self, line):
        self.said.append(line)

    def apply(self, fake=None, now="20261030-170000"):
        return video_names.apply(self.moves, fake or self.fake,
                                 self.manifest_dir, now=now, say=self.say)

    def manifest_rows(self, now="20261030-170000"):
        path = os.path.join(self.manifest_dir, now + ".csv")
        with open(path, encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))


class TestApply(ApplyFixture):

    def test_every_file_moves_and_keeps_its_size(self):
        result = self.apply()
        self.assertEqual(len(result.moved), 3)
        for move in self.moves:
            self.assertEqual(self.fake.files[move.new], SIZES[move.name])
            self.assertNotIn(move.old, self.fake.files)

    def test_the_manifest_lists_old_new_and_size(self):
        self.apply()
        got = self.manifest_rows()
        self.assertEqual(len(got), 3)
        self.assertEqual(sorted(got[0].keys()),
                         sorted(["成果檔名", "舊位置", "新位置", "大小"]))
        self.assertEqual(got[0]["成果檔名"], RUKAI)
        self.assertEqual(got[0]["新位置"], self.moves[0].new)
        self.assertEqual(got[0]["大小"], "111")

    def test_the_manifest_is_complete_when_the_third_move_fails(self):
        # 先寫清單、才搬第一支：搬到一半斷掉，清單已經完整佇咧。
        self.fake.fail_rename.add(self.moves[2].old)
        with self.assertRaises(PipelineError):
            self.apply()
        self.assertEqual(len(self.manifest_rows()), 3)
        self.assertIn(self.moves[0].new, self.fake.files)
        self.assertIn(self.moves[1].new, self.fake.files)
        self.assertIn(self.moves[2].old, self.fake.files)
        self.assertNotIn(self.moves[2].new, self.fake.files)

    def test_the_manifest_exists_before_the_first_rename(self):
        seen = []
        original = self.fake.rename

        def watching(old, new):
            seen.append(os.path.exists(os.path.join(self.manifest_dir,
                                                    "20261030-170000.csv")))
            original(old, new)
        self.fake.rename = watching
        self.apply()
        self.assertEqual(seen, [True, True, True])

    def test_folders_are_made_level_by_level_and_only_once(self):
        # /home/news 伺服器頂猶無；mkdir 毋是遞迴ê，愛一層一層。
        self.apply()
        made = []
        for call in self.fake.calls:
            if call[0] == "mkdir":
                made.append(call[1])
        self.assertEqual(sorted(made), sorted(set(made)))
        self.assertEqual(
            made, ["/home", "/home/news", "/home/news/mkv",
                   "/home/news/mkv/2021-01", "/home/news/mkv/2024-10"])

    def test_an_existing_month_folder_is_not_an_error(self):
        self.fake.dirs.update(["/home/news", "/home/news/mkv",
                               "/home/news/mkv/2021-01"])
        self.assertEqual(len(self.apply().moved), 3)

    def test_the_run_after_an_interruption_finishes_the_rest(self):
        self.fake.fail_rename.add(self.moves[1].old)
        with self.assertRaises(PipelineError):
            self.apply()
        self.fake.fail_rename.clear()
        result = self.apply(now="20261030-170500")
        self.assertEqual(result.skipped, [RUKAI])
        self.assertEqual(sorted(result.moved), sorted([HLAALUA, AMIS]))
        for move in self.moves:
            self.assertEqual(self.fake.files[move.new], SIZES[move.name])

    def test_a_finished_move_is_skipped_without_touching_the_server(self):
        self.apply()
        before = len(self.fake.calls)
        result = self.apply(now="20261030-171000")
        self.assertEqual(result.moved, [])
        self.assertEqual(len(result.skipped), 3)
        for call in self.fake.calls[before:]:
            self.assertNotIn(call[0], ("rename", "mkdir"))

    def test_both_places_occupied_stops_and_overwrites_nothing(self):
        clash = self.moves[1]
        self.fake.files[clash.new] = 999
        self.fake._add_parents(clash.new)
        with self.assertRaises(PipelineError) as caught:
            self.apply()
        self.assertIn(HLAALUA, str(caught.exception))
        self.assertEqual(self.fake.files[clash.new], 999)
        self.assertIn(clash.old, self.fake.files)
        self.assertNotIn("rename", self.fake.verbs())

    def test_a_move_with_neither_place_is_named_and_the_rest_go_on(self):
        gone = self.moves[0]
        del self.fake.files[gone.old]
        result = self.apply()
        self.assertEqual([name for name, _why in result.problems], [RUKAI])
        self.assertEqual(sorted(result.moved), sorted([HLAALUA, AMIS]))

    def test_the_listings_are_per_folder_not_per_file(self):
        # 3,153 支若逐支問，光是問就愛個外鐘頭。
        self.apply()
        listed = []
        for call in self.fake.calls:
            if call[0] == "listdir":
                listed.append(call[1])
        self.assertEqual(sorted(listed), sorted(set(listed)))


class TestRealSftpActions(unittest.TestCase):
    """listdir／mkdir／rename 對真ê `sftp.sh`：路徑攏是獨立引數。"""

    def client(self, result):
        calls = []

        def run(cmd, **kw):
            calls.append(cmd)
            return result
        return video_names.Sftp(run=run), calls

    def test_listdir_gives_names_and_sizes(self):
        out = ("sftp> ls -l \"/x\"\n"
               "-rwxrwxrwx 1 ilrdf-corpus users 10 Sep 17 19:59 a.mkv\n"
               "drwxrwxrwx 1 ilrdf-corpus users 0 Sep 17 19:59 sub\n"
               "-rwxrwxrwx 1 ilrdf-corpus users 20 Sep 17 19:59 b c.mkv\n")
        client, _calls = self.client(Result(0, out))
        self.assertEqual(client.listdir("/x"), {"a.mkv": 10, "b c.mkv": 20})

    def test_listdir_of_a_missing_folder_is_none(self):
        client, _calls = self.client(Result(
            1, "Can't ls: \"/x\" not found\n"))
        self.assertIsNone(client.listdir("/x"))

    def test_listdir_failing_otherwise_raises(self):
        client, _calls = self.client(Result(255, "", "Permission denied"))
        with self.assertRaises(PipelineError):
            client.listdir("/x")

    def test_mkdir_and_rename_pass_each_path_as_its_own_argument(self):
        client, calls = self.client(Result(0, ""))
        client.mkdir("/home/news")
        client.rename("/a/舊.mkv", "/b/Hla'alua_拉阿魯哇.mkv")
        self.assertEqual(calls[0][-2:], ["mkdir", "/home/news"])
        self.assertEqual(calls[1][-3:],
                         ["rename", "/a/舊.mkv", "/b/Hla'alua_拉阿魯哇.mkv"])

    def test_a_failed_rename_raises_with_the_server_words(self):
        client, _calls = self.client(Result(1, "", "Couldn't rename file"))
        with self.assertRaises(PipelineError) as caught:
            client.rename("/a", "/b")
        self.assertIn("Couldn't rename", str(caught.exception))


class TestProbe(ApplyFixture):
    """搬一支過去再搬回來——驗證跨資料夾 rename 會使，才做全部。"""

    def probe_move(self):
        return self.moves[1]          # 拉阿魯哇：名內底有撇號

    def test_it_goes_over_and_comes_back_leaving_nothing_changed(self):
        before = dict(self.fake.files)
        move = self.probe_move()
        video_names.probe(move, self.fake, say=self.say)
        self.assertEqual(self.fake.files, before)
        renames = [call for call in self.fake.calls if call[0] == "rename"]
        self.assertEqual(renames, [("rename", move.old, move.new),
                                   ("rename", move.new, move.old)])
        self.assertTrue(move.new.endswith("Hla'alua_拉阿魯哇.mkv"))

    def test_the_folders_are_made_level_by_level_first(self):
        video_names.probe(self.probe_move(), self.fake, say=self.say)
        made = []
        for call in self.fake.calls:
            if call[0] == "mkdir":
                made.append(call[1])
        self.assertEqual(made, ["/home", "/home/news", "/home/news/mkv",
                                "/home/news/mkv/2021-01"])

    def test_a_refused_trip_over_stops_and_names_the_fallback(self):
        # 跨子卷：mkv-raw 若是獨立子卷，rename 會失敗，頂懸 sftp 看袂出來。
        self.fake.cross_device = True
        before = dict(self.fake.files)
        with self.assertRaises(PipelineError) as caught:
            video_names.probe(self.probe_move(), self.fake, say=self.say)
        self.assertIn("跨子卷", str(caught.exception))
        self.assertIn("/home/mkv-raw/news/mkv", str(caught.exception))
        self.assertEqual(self.fake.files, before)
        renames = [c for c in self.fake.calls if c[0] == "rename"]
        self.assertEqual(len(renames), 1)

    def test_a_failed_trip_back_says_where_the_file_is_now(self):
        move = self.probe_move()
        self.fake.fail_rename.add(move.new)
        with self.assertRaises(PipelineError) as caught:
            video_names.probe(move, self.fake, say=self.say)
        self.assertIn(move.new, str(caught.exception))
        self.assertIn("現在", str(caught.exception))
        self.assertIn(move.new, self.fake.files)

    def test_a_missing_source_is_named_and_nothing_is_made(self):
        move = self.probe_move()
        del self.fake.files[move.old]
        with self.assertRaises(PipelineError) as caught:
            video_names.probe(move, self.fake, say=self.say)
        self.assertIn(move.old, str(caught.exception))
        self.assertNotIn("mkdir", self.fake.verbs())

    def test_an_occupied_target_is_refused_before_anything_moves(self):
        move = self.probe_move()
        self.fake.files[move.new] = 1
        self.fake._add_parents(move.new)
        with self.assertRaises(PipelineError) as caught:
            video_names.probe(move, self.fake, say=self.say)
        self.assertIn(move.new, str(caught.exception))
        self.assertNotIn("rename", self.fake.verbs())


EXCLUDED_NEAR = "/home/mkv-raw/113/9月/20241002S2000.mkv"
EXCLUDED_FAR = "/home/mkv-raw/族語新聞/別的節目.mkv"


class CheckFixture(ApplyFixture):
    """搬煞了後ê伺服器：三支佇新位置，排除ê兩支原地。"""

    def setUp(self):
        ApplyFixture.setUp(self)
        self.excluded = [EXCLUDED_NEAR, EXCLUDED_FAR]
        for path in self.excluded:
            self.fake.files[path] = 777
            self.fake._add_parents(path)
        self.apply()

    def check(self):
        return video_names.check(self.moves, self.excluded, self.fake,
                                 sizes=SIZES)


class TestCheck(CheckFixture):

    def test_everything_in_place_reports_nothing(self):
        self.assertEqual(self.check(), [])

    def test_a_missing_file_is_named_with_its_expected_place(self):
        del self.fake.files[self.moves[0].new]
        problems = self.check()
        self.assertEqual(len(problems), 1)
        self.assertIn(RUKAI, problems[0])
        self.assertIn(self.moves[0].new, problems[0])

    def test_a_size_that_differs_from_the_manifest_is_named(self):
        self.fake.files[self.moves[2].new] = 1
        problems = self.check()
        self.assertEqual(len(problems), 1)
        self.assertIn(AMIS, problems[0])
        self.assertIn("333", problems[0])

    def test_a_stray_file_among_the_new_ones_is_named(self):
        stray = "/home/news/mkv/2021-01/亂入.mkv"
        self.fake.files[stray] = 5
        problems = self.check()
        self.assertEqual(len(problems), 1)
        self.assertIn(stray, problems[0])

    def test_a_file_that_never_moved_is_named(self):
        move = self.moves[1]
        self.fake.files[move.old] = SIZES[move.name]
        del self.fake.files[move.new]
        joined = "\n".join(self.check())
        self.assertIn(HLAALUA, joined)
        self.assertIn(move.old, joined)

    def test_the_old_folders_may_hold_only_the_excluded_files(self):
        stray = "/home/mkv-raw/113/9月/不知道哪來ê.mkv"
        self.fake.files[stray] = 5
        problems = self.check()
        self.assertEqual(len(problems), 1)
        self.assertIn(stray, problems[0])

    def test_an_excluded_file_already_gone_is_not_a_problem(self):
        # 排除清單記ê是「曾經有、後來予人取代」ê重複檔、分段檔，22 列內底
        # 有 4 列搬進前伺服器頂就無矣。搬移本底就毋碰排除ê檔，所以袂是
        # 搬移害ê，毋算問題。
        del self.fake.files[EXCLUDED_FAR]
        self.assertEqual(self.check(), [])

    def test_an_excluded_path_outside_mkv_raw_is_not_looked_at(self):
        # 排除清單有一列佇 /docker/ilrdf-corpus/…/10月/，彼个資料夾有幾百个
        # 別ê檔（mp3、wav、mp4）——本底攏當做「舊位置多出」，202 逝雜訊。
        outside = "/docker/ilrdf-corpus/族語新聞/110.1-110.10/10月/286.mp4"
        self.excluded.append(outside)
        for index in range(3):
            self.fake.files[posixpath.dirname(outside) + "/別ê%d.mp3"
                            % index] = 1
        self.fake.files[outside] = 1
        self.fake._add_parents(outside)
        self.assertEqual(self.check(), [])
        for call in self.fake.calls:
            self.assertNotEqual(call[1:], (posixpath.dirname(outside),))

    def test_the_excluded_file_beside_a_moved_one_is_not_a_problem(self):
        # 20241002S2000.mkv 佮 20241001S2000.mkv 本底囥仝一个資料夾。
        self.assertIn(EXCLUDED_NEAR, self.fake.files)
        self.assertEqual(self.check(), [])

    def test_without_sizes_only_presence_is_checked(self):
        self.fake.files[self.moves[2].new] = 1
        got = video_names.check(self.moves, self.excluded, self.fake)
        self.assertEqual(got, [])


class TestUndo(ApplyFixture):
    """依清單反向搬；舊位置被佔用就拒絕，毋覆寫。"""

    def setUp(self):
        ApplyFixture.setUp(self)
        self.original = dict(self.fake.files)
        self.result = self.apply()

    def undo(self):
        return video_names.undo(self.result.manifest, self.fake,
                                say=self.say)

    def test_every_file_goes_back_where_it_was(self):
        got = self.undo()
        self.assertEqual(len(got.moved), 3)
        self.assertEqual(self.fake.files, self.original)

    def test_a_second_undo_has_nothing_to_do(self):
        self.undo()
        before = len(self.fake.calls)
        got = self.undo()
        self.assertEqual(got.moved, [])
        self.assertEqual(len(got.skipped), 3)
        for call in self.fake.calls[before:]:
            self.assertNotIn(call[0], ("rename", "mkdir"))

    def test_an_occupied_old_place_is_refused_and_not_overwritten(self):
        taken = self.moves[1]
        self.fake.files[taken.old] = 999
        got = self.undo()
        self.assertEqual([name for name, _why in got.problems], [HLAALUA])
        self.assertEqual(self.fake.files[taken.old], 999)
        self.assertIn(taken.new, self.fake.files)
        self.assertEqual(sorted(got.moved), sorted([RUKAI, AMIS]))

    def test_an_old_folder_that_was_pruned_is_made_again(self):
        # 清空資料夾那步做了才還原：舊資料夾愛重建，一層一層。
        old_folder = posixpath.dirname(self.moves[2].old)
        self.fake.dirs.discard(old_folder)
        got = self.undo()
        self.assertIn(AMIS, got.moved)
        self.assertEqual(self.fake.files[self.moves[2].old], SIZES[AMIS])

    def test_a_file_missing_from_both_places_is_named(self):
        gone = self.moves[0]
        del self.fake.files[gone.new]
        got = self.undo()
        self.assertEqual([name for name, _why in got.problems], [RUKAI])


OLD_NAME = "20240930_274_晚間_Amis_阿美"
NEW_NAME = "20241001_275_晚間_Amis_阿美"
OLD_CANON = "/home/news/mkv/2024-09/20240930_274_晚間_Amis_阿美.mkv"
NEW_CANON = "/home/news/mkv/2024-10/20241001_275_晚間_Amis_阿美.mkv"
OLD_ORIG = "/home/mkv-raw/113/10月/20241001S2000.mkv"
OLD_ORIG_CELL = "home/mkv-raw/113/10月/20241001S2000.mkv"


class TestRenameEpisode(unittest.TestCase):
    """改成果檔名（改語別、改日期）：伺服器頂ê影片綴咧搬去新名稱ê位置。"""

    def setUp(self):
        self.said = []

    def say(self, line):
        self.said.append(line)

    def rename(self, fake, cell=OLD_ORIG_CELL, new=NEW_NAME):
        return video_names.rename_episode(entry(OLD_NAME, cell), new, fake,
                                          say=self.say)

    def test_from_the_canonical_place_to_the_new_names_place(self):
        fake = FakeSftp({OLD_CANON: 5})
        got = self.rename(fake)
        self.assertEqual((got.old, got.new, got.source),
                         (OLD_CANON, NEW_CANON, "正規"))
        self.assertEqual(fake.files, {NEW_CANON: 5})
        self.assertNotIn("退回原始位置", "\n".join(self.said))

    def test_a_date_change_across_months_makes_the_month_folder(self):
        fake = FakeSftp({OLD_CANON: 5})
        self.rename(fake)
        self.assertIn("/home/news/mkv/2024-10", fake.dirs)

    def test_a_never_moved_episode_is_moved_from_the_original_place(self):
        # 還無搬進正式位置ê集數（新批次剛匯入）：改名順紲搬入去。
        fake = FakeSftp({OLD_ORIG: 7})
        got = self.rename(fake)
        self.assertEqual((got.old, got.new, got.source),
                         (OLD_ORIG, NEW_CANON, "原始"))
        self.assertEqual(fake.files, {NEW_CANON: 7})
        self.assertIn("退回原始位置", "\n".join(self.said))

    def test_neither_place_refuses_and_names_both(self):
        fake = FakeSftp({})
        with self.assertRaises(PipelineError) as caught:
            self.rename(fake)
        self.assertIn(OLD_CANON, str(caught.exception))
        self.assertIn(OLD_ORIG, str(caught.exception))
        self.assertNotIn("rename", fake.verbs())
        self.assertNotIn("mkdir", fake.verbs())

    def test_an_occupied_new_place_is_refused_and_nothing_moves(self):
        fake = FakeSftp({OLD_CANON: 5, NEW_CANON: 9})
        with self.assertRaises(PipelineError) as caught:
            self.rename(fake)
        self.assertIn(NEW_CANON, str(caught.exception))
        self.assertEqual(fake.files, {OLD_CANON: 5, NEW_CANON: 9})

    def test_a_failure_that_is_not_not_found_is_not_papered_over(self):
        fake = FakeSftp({OLD_ORIG: 7})
        fake.broken.add(OLD_CANON)
        with self.assertRaises(PipelineError):
            self.rename(fake)
        self.assertEqual(fake.files, {OLD_ORIG: 7})

    def test_the_same_name_moves_nothing(self):
        # 名無變（抑是 relabel／redate 算出仝一个名）：毋是「新位置已經有
        # 檔」ê錯誤，是無代誌愛做。
        fake = FakeSftp({OLD_CANON: 5})
        got = video_names.rename_episode(entry(OLD_NAME, OLD_ORIG_CELL),
                                         OLD_NAME, fake, say=self.say)
        self.assertEqual(got.old, got.new)
        self.assertEqual(fake.files, {OLD_CANON: 5})
        self.assertNotIn("rename", fake.verbs())

    def test_rename_back_returns_the_file_to_where_it_was(self):
        for files in ({OLD_CANON: 5}, {OLD_ORIG: 7}):
            fake = FakeSftp(files)
            before = dict(fake.files)
            got = self.rename(fake)
            video_names.rename_back(got, fake)
            self.assertEqual(fake.files, before)

    def test_the_apostrophe_name_renames_whole(self):
        old = "20210103_003_晨間_Hla'alua_拉阿魯哇"
        new = "20210103_003_晨間_Hla'alua_拉阿魯哇改"
        fake = FakeSftp({paths.video_path(old): 3})
        video_names.rename_episode(entry(old, ""), new, fake, say=self.say)
        self.assertEqual(list(fake.files), [paths.video_path(new)])


RAW = "/home/mkv-raw"
SUB_A = RAW + "/110.01-110.10/1月原始mxf檔"
TOP_A = RAW + "/110.01-110.10"
SUB_B = RAW + "/113/9月"
TOP_B = RAW + "/113"


class TestPrune(CheckFixture):
    """搬完了、驗收了，最後才清掉搬空ê舊資料夾；干焦刪空ê。"""

    def prune(self, execute=False):
        return video_names.prune(self.moves, self.fake, execute=execute,
                                 say=self.say)

    def rmdirs(self):
        out = []
        for call in self.fake.calls:
            if call[0] == "rmdir":
                out.append(call[1])
        return out

    def test_only_empty_folders_are_listed_deepest_first(self):
        # 9月 猶有排除ê 20241002S2000.mkv，所以 9月 佮伊ê上層 113 攏袂刪。
        self.assertEqual(self.prune(), [SUB_A, TOP_A])

    def test_the_default_only_lists_and_sends_no_rmdir(self):
        self.prune()
        self.assertEqual(self.rmdirs(), [])
        self.assertIn(SUB_A, self.fake.dirs)

    def test_executing_removes_exactly_those_folders(self):
        got = self.prune(execute=True)
        self.assertEqual(got, [SUB_A, TOP_A])
        self.assertEqual(self.rmdirs(), [SUB_A, TOP_A])
        self.assertNotIn(SUB_A, self.fake.dirs)
        self.assertNotIn(TOP_A, self.fake.dirs)
        self.assertIn(SUB_B, self.fake.dirs)
        self.assertIn(EXCLUDED_NEAR, self.fake.files)

    def test_the_root_of_mkv_raw_is_never_listed(self):
        # 排除ê檔攏無去，規棵樹都空：猶是毋刪 /home/mkv-raw 本身。
        del self.fake.files[EXCLUDED_NEAR]
        got = self.prune(execute=True)
        self.assertEqual(got, [SUB_A, SUB_B, TOP_A, TOP_B])
        self.assertNotIn(RAW, got)
        self.assertIn(RAW, self.fake.dirs)

    def test_a_parent_whose_only_child_goes_in_the_same_run_goes_too(self):
        # 子資料夾刪了，上層才有可能空——dry-run 嘛愛算會出來。
        self.assertIn(TOP_A, self.prune())

    def test_a_refused_rmdir_stops_everything_and_names_the_folder(self):
        # 列出ê時看起來是空ê，後來有人囥檔入去——伺服器會拒絕，這爿毋吞。
        self.fake.fail_rmdir.add(SUB_A)
        with self.assertRaises(PipelineError) as caught:
            self.prune(execute=True)
        self.assertIn(SUB_A, str(caught.exception))
        self.assertEqual(self.rmdirs(), [SUB_A])
        self.assertIn(TOP_A, self.fake.dirs)

    def test_a_folder_that_is_already_gone_is_skipped(self):
        self.prune(execute=True)
        before = len(self.rmdirs())
        self.assertEqual(self.prune(execute=True), [])
        self.assertEqual(len(self.rmdirs()), before)


CATALOGUE_HEAD = ["成果檔名", "節目名稱", "年度", "集數", "播出日期",
                  "族語別(英)", "族語別(中)", "語言別", "語言別代號",
                  "原始影片檔案位置", "備註"]


def catalogue_rows():
    out = []
    for name, programme, year, episode, date, english, chinese, cell in (
            (RUKAI, "午間族語新聞", "2021", "1", "2021-01-01", "Rukai", "魯凱",
             rows()[0]["原始影片檔案位置"]),
            (HLAALUA, "晨間族語新聞", "2021", "3", "2021-01-03", "Hla'alua",
             "拉阿魯哇", rows()[1]["原始影片檔案位置"]),
            (AMIS, "看見族語（晚間）", "2024", "275", "2024-10-01", "Amis",
             "阿美", rows()[2]["原始影片檔案位置"])):
        out.append({"成果檔名": name, "節目名稱": programme, "年度": year,
                    "集數": episode, "播出日期": date, "族語別(英)": english,
                    "族語別(中)": chinese, "語言別": "", "語言別代號": "x",
                    "原始影片檔案位置": cell, "備註": ""})
    return out


class CliFixture(ApplyFixture):
    """目錄、排除清單、清單資料夾攏佇暫存目錄；伺服器是假ê。"""

    def setUp(self):
        ApplyFixture.setUp(self)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.catalogue = os.path.join(tmp.name, "smkul.csv")
        with open(self.catalogue, "w", encoding="utf-8-sig",
                  newline="") as handle:
            writer = csv.DictWriter(handle, CATALOGUE_HEAD)
            writer.writeheader()
            for one in catalogue_rows():
                writer.writerow(one)
        self.excluded_csv = os.path.join(tmp.name, "排除影片.csv")
        with open(self.excluded_csv, "w", encoding="utf-8-sig",
                  newline="") as handle:
            handle.write("伺服器路徑,排除原因,同一支的保留檔,判定依據,判定日期\n"
                         "%s,重複檔,x,y,2026-10-05\n" % EXCLUDED_NEAR)
        self.fake.files[EXCLUDED_NEAR] = 777
        self.fake._add_parents(EXCLUDED_NEAR)
        self.made = []

    def factory(self):
        self.made.append(True)
        return self.fake

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        code = video_names.main(
            list(argv), sftp_factory=self.factory, catalogue=self.catalogue,
            excluded_path=self.excluded_csv,
            manifest_dir=self.manifest_dir, out=out, err=err)
        return code, out.getvalue(), err.getvalue()


class TestCli(CliFixture):

    def test_no_subcommand_is_plan_and_never_touches_the_server(self):
        code, out, _err = self.run_cli()
        self.assertEqual(code, 0)
        self.assertEqual(self.made, [])
        self.assertIn("3 組", out)
        self.assertIn("2 個月份資料夾", out)
        self.assertEqual(self.fake.calls, [])

    def test_plan_is_the_same_thing_said_out_loud(self):
        code, out, _err = self.run_cli("plan")
        self.assertEqual(code, 0)
        self.assertEqual(self.made, [])
        self.assertIn(RUKAI, out)

    def test_apply_must_be_asked_for_and_then_moves_everything(self):
        code, _out, _err = self.run_cli("apply")
        self.assertEqual(code, 0)
        self.assertEqual(self.made, [True])
        for move in self.moves:
            self.assertIn(move.new, self.fake.files)
        self.assertIn(EXCLUDED_NEAR, self.fake.files)

    def test_apply_with_a_missing_file_exits_nonzero_and_names_it(self):
        del self.fake.files[self.moves[0].old]
        code, out, err = self.run_cli("apply")
        self.assertEqual(code, 1)
        self.assertIn(RUKAI, out + err)

    def test_probe_takes_one_name(self):
        code, out, _err = self.run_cli("probe", HLAALUA)
        self.assertEqual(code, 0)
        self.assertEqual(self.fake.files[self.moves[1].old], SIZES[HLAALUA])
        self.assertIn("探針", out)

    def test_probe_of_an_unknown_name_says_so(self):
        code, _out, err = self.run_cli("probe", "20990101_001_午間_Rukai_魯凱")
        self.assertEqual(code, 2)
        self.assertIn("20990101_001_午間_Rukai_魯凱", err)
        self.assertEqual(self.made, [])

    def test_check_passes_after_apply_and_fails_when_a_file_is_missing(self):
        self.run_cli("apply")
        code, _out, _err = self.run_cli("check")
        self.assertEqual(code, 0)
        del self.fake.files[self.moves[2].new]
        code, out, err = self.run_cli("check")
        self.assertEqual(code, 1)
        self.assertIn(AMIS, out + err)

    def test_check_reads_the_sizes_from_the_newest_manifest(self):
        self.run_cli("apply")
        self.fake.files[self.moves[0].new] = 1
        code, out, err = self.run_cli("check")
        self.assertEqual(code, 1)
        self.assertIn("111", out + err)

    def test_undo_takes_the_manifest(self):
        self.run_cli("apply")
        manifest = os.path.join(self.manifest_dir, sorted(
            os.listdir(self.manifest_dir))[-1])
        code, _out, _err = self.run_cli("undo", manifest)
        self.assertEqual(code, 0)
        for move in self.moves:
            self.assertIn(move.old, self.fake.files)

    def test_prune_lists_by_default_and_removes_only_when_told(self):
        self.run_cli("apply")
        code, out, _err = self.run_cli("prune")
        self.assertEqual(code, 0)
        self.assertIn(SUB_A, out)
        self.assertIn(SUB_A, self.fake.dirs)
        code, _out, _err = self.run_cli("prune", "--execute")
        self.assertEqual(code, 0)
        self.assertNotIn(SUB_A, self.fake.dirs)

    def test_locate_prints_path_size_and_source_for_the_shell(self):
        # fetch_sftp.sh 用 `cut -f` 切；退回ê提示愛去 stderr，stdout 干焦
        # 一逝「路徑<TAB>大小<TAB>來源」。
        self.fake.files[paths.video_path(RUKAI)] = 42
        self.fake._add_parents(paths.video_path(RUKAI))
        code, out, _err = self.run_cli("locate", RUKAI)
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines(),
                         ["%s\t42\t正規" % paths.video_path(RUKAI)])

    def test_locate_falling_back_says_so_on_stderr_only(self):
        code, out, err = self.run_cli("locate", RUKAI)
        self.assertEqual(code, 0)
        self.assertEqual(len(out.splitlines()), 1)
        self.assertTrue(out.rstrip().endswith("\t111\t原始"))
        self.assertIn("退回原始位置", err)
        self.assertNotIn("退回", out)

    def test_locate_with_nothing_found_exits_nonzero_and_names_both(self):
        del self.fake.files[self.moves[0].old]
        code, out, err = self.run_cli("locate", RUKAI)
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn(paths.video_path(RUKAI), err)


if __name__ == "__main__":
    unittest.main()
