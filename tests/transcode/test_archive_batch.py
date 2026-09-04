"""archive_batch: resolve each episode's master path, name its staged
download and archival mkv, and know when it is already done -- pure logic,
mirrors news/test_asrmt_run.py's TestMp3Resolution. Fetching over SFTP and
running ffmpeg are I/O and are not unit tested (same reasoning as the vosk
call layer: real-transfer smoke test guards them instead).
"""
import os
import tempfile
import unittest
from unittest import mock

from scripts.news import paths
from scripts.transcode import archive_batch
from scripts.errors import PipelineError


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
        with self.assertRaises(PipelineError):
            archive_batch.video_remote("20210301_060_午間_Cou_鄒", [])

    def test_a_pending_episode_resolves_from_the_inventory(self):
        """猶咧做ê彼集，smkul.csv 內底猶未有，毋過封存愛佇彼陣做。

        交付版ê `smkul.csv` 刁工無列 pending ê集數（見 news/README），
        毋過母帶是 `fetch_sftp.sh` 抓落來、切完 cue 就留咧等封存ê——
        彼个時陣這集**一定**是 pending。若干焦看 smkul.csv，逐集ê流程
        就會佇遮斷去，而且錯誤講「no video in smkul.csv」，看無是按怎。
        Inventory 是登記簿，pending 佮已交付攏有，所以退去問伊。
        """
        inventory = [{"srt_name": "20210215_046_晚間_Amis_阿美",
                      "pending": True,
                      "video": "ilrdf-corpus/族語新聞/110.1-110.10/"
                               "2月原始mxf檔/21NL004_46晚間族語新聞.mxf"}]
        got = archive_batch.video_remote(
            "20210215_046_晚間_Amis_阿美", [], inventory=inventory)
        self.assertEqual(
            got, "/docker/ilrdf-corpus/族語新聞/110.1-110.10/"
                 "2月原始mxf檔/21NL004_46晚間族語新聞.mxf")

    def test_the_inventory_shorthand_is_expanded_too(self):
        # inventory 早期彼幾筆記ê嘛是 "ilrdf-corpus/2月/" 簡寫
        inventory = [{"srt_name": "20210215_046_午間_Atayal_泰雅",
                      "video": "ilrdf-corpus/2月/21NL003_46午間族語新聞.mxf"}]
        got = archive_batch.video_remote(
            "20210215_046_午間_Atayal_泰雅", [], inventory=inventory)
        self.assertEqual(
            got, "/docker/ilrdf-corpus/族語新聞/110.1-110.10/"
                 "2月原始mxf檔/21NL003_46午間族語新聞.mxf")

    def test_smkul_wins_when_both_know_the_episode(self):
        # 交付版是正本；inventory 干焦是 pending 彼站ê退路。
        rows = [{"播出日期": "2021-02-06", "播出時段": "晚間",
                 "影片檔案位置": "ilrdf-corpus/7月/對ê.mp4"}]
        inventory = [{"srt_name": "20210206_037_晚間_Paiwan_排灣",
                      "video": "ilrdf-corpus/7月/毋著ê.mp4"}]
        got = archive_batch.video_remote(
            "20210206_037_晚間_Paiwan_排灣", rows, inventory=inventory)
        self.assertTrue(got.endswith("對ê.mp4"))

    def test_neither_source_knows_it_still_fails_loud(self):
        with self.assertRaises(PipelineError):
            archive_batch.video_remote("20210301_060_午間_Cou_鄒", [],
                                       inventory=[])

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
        # "族語新聞/110.1-110.10/2月原始mxf檔/"（見 fetch_sftp.sh 的
        # 同一個註記），簡寫路徑在 SFTP 上找不到檔案。
        rows = [{"播出日期": "2021-02-01", "播出時段": "晚間",
                 "影片檔案位置":
                 "ilrdf-corpus/2月/20NL004_32晚間族語新聞.mxf"}]
        got = archive_batch.video_remote(
            "20210201_032_晚間_Amis_阿美", rows)
        self.assertEqual(
            got, "/docker/ilrdf-corpus/族語新聞/110.1-110.10/"
                 "2月原始mxf檔/20NL004_32晚間族語新聞.mxf")


class TestMasterRemote(unittest.TestCase):
    """封存愛問**目錄**，毋是問 smkul.csv。

    兩份資料咧回答無仝ê問題：

    - `smkul.csv` ê「影片檔案位置」記ê是**這支 SRT 是對佗一个檔做ê**，
      是交付紀錄，一集干焦一條，定版了就袂振動。
    - 目錄（`ilrdf-corpus.csv`）ê彼欄是**候選清單**，一集會使列幾若條，
      `sources.pick()` 照「mxf 母帶優先」ê規則揀。

    2 月頭一批 13 集是佇 `sources.py` 這套規則寫出來進前就交付ê，當時
    揀著 `7月/` 彼份 mp4。in ê母帶佇伺服器頂猶原佇咧，欲補封存ê時，
    問 smkul.csv 只會提著彼个 mp4，`is_master()` 就kā規 13 集攏跳過。
    所以封存這爿愛家己問目錄。
    """

    CAT = [{"srt_name": "20210206_037_晚間_Paiwan_排灣",
            "播出日期": "2021-02-06", "播出時段": "晚間",
            "影片檔案位置":
            "ilrdf-corpus/族語新聞/110.1-110.10/2月原始mxf檔/"
            "21NL004_37午間族語新聞.mxf;"
            "ilrdf-corpus/族語新聞/110.1-110.10/2月原始mxf檔/"
            "21NL004_37晚間族語新聞.mxf;"
            "ilrdf-corpus/族語新聞/110.1-110.10/7月/"
            "21NL004_37午間族語新聞.mp4;"
            "ilrdf-corpus/族語新聞/110.1-110.10/7月/"
            "21NL004_37晚間族語新聞.mp4"}]

    # 交付紀錄講ê是 mp4 -- 這條愛保留，毋是欲改ê
    SMKUL = [{"播出日期": "2021-02-06", "播出時段": "晚間",
              "影片檔案位置":
              "ilrdf-corpus/族語新聞/110.1-110.10/7月/"
              "21NL004_37晚間族語新聞.mp4"}]

    def test_it_finds_the_master_even_when_smkul_says_mp4(self):
        got = archive_batch.master_remote(
            "20210206_037_晚間_Paiwan_排灣", self.CAT, self.SMKUL, [])
        self.assertTrue(got.endswith("21NL004_37晚間族語新聞.mxf"), got)
        self.assertTrue(archive_batch.is_master(got))

    def test_the_slot_still_decides_which_master(self):
        # 仝一逝內底午間ê母帶排頭前，毋通提著彼支
        got = archive_batch.master_remote(
            "20210206_037_晚間_Paiwan_排灣", self.CAT, self.SMKUL, [])
        self.assertNotIn("午間", got)

    def test_no_master_in_the_catalogue_stays_an_mp4(self):
        # 目錄若干焦有 mp4，就是 mp4；`is_master()` 後壁會kā伊跳過
        cat = [{"srt_name": "20210206_037_晚間_Paiwan_排灣",
                "播出日期": "2021-02-06", "播出時段": "晚間",
                "影片檔案位置":
                "ilrdf-corpus/族語新聞/110.1-110.10/7月/"
                "21NL004_37晚間族語新聞.mp4"}]
        got = archive_batch.master_remote(
            "20210206_037_晚間_Paiwan_排灣", cat, self.SMKUL, [])
        self.assertFalse(archive_batch.is_master(got))

    def test_an_episode_the_catalogue_does_not_know_falls_back(self):
        got = archive_batch.master_remote(
            "20210206_037_晚間_Paiwan_排灣", [], self.SMKUL, [])
        self.assertTrue(got.endswith("21NL004_37晚間族語新聞.mp4"), got)

    def test_it_falls_all_the_way_to_the_inventory(self):
        inventory = [{"srt_name": "20210215_046_晚間_Amis_阿美",
                      "pending": True,
                      "video": "ilrdf-corpus/族語新聞/110.1-110.10/"
                               "2月原始mxf檔/21NL004_46晚間族語新聞.mxf"}]
        got = archive_batch.master_remote(
            "20210215_046_晚間_Amis_阿美", [], [], inventory)
        self.assertTrue(got.endswith("21NL004_46晚間族語新聞.mxf"), got)

    def test_the_feb_shorthand_is_expanded_from_the_catalogue_too(self):
        cat = [{"srt_name": "20210201_032_晚間_Amis_阿美",
                "播出日期": "2021-02-01", "播出時段": "晚間",
                "影片檔案位置":
                "ilrdf-corpus/2月/20NL004_32晚間族語新聞.mxf"}]
        got = archive_batch.master_remote(
            "20210201_032_晚間_Amis_阿美", cat, [], [])
        self.assertEqual(
            got, "/docker/ilrdf-corpus/族語新聞/110.1-110.10/"
                 "2月原始mxf檔/20NL004_32晚間族語新聞.mxf")

    def test_nothing_anywhere_still_fails_loud(self):
        with self.assertRaises(PipelineError):
            archive_batch.master_remote("20210301_060_午間_Cou_鄒",
                                        [], [], [])


class TestStageName(unittest.TestCase):
    """暫存的檔名愛佮 `fetch_sftp.sh` 囥的仝款。

    切 cue 的時陣母帶已經下載過一擺，`fetch_sftp.sh` 刁工kā伊留咧予這爿
    編 mkv。兩爿若各號各的名，這爿就揣無，19 GB 的母帶會閣抓一擺。
    """

    def test_it_is_the_source_file_own_name(self):
        self.assertEqual(
            archive_batch.stage_name(
                "20210201_032_晚間_Amis_阿美",
                "/docker/ilrdf-corpus/2月原始mxf檔/20NL004_32晚間族語新聞.mxf"),
            "20NL004_32晚間族語新聞.mxf")


class TestMastersOnly(unittest.TestCase):
    """干焦母帶封存。

    mp4 家己就是壓好的交付版，閣編一擺 mkv 是重壓，無意義；而且
    `fetch_sftp.sh` 切完 cue 就kā mp4 刣掉矣，這爿嘛無物通編。
    """

    def test_mxf_is_a_master(self):
        self.assertTrue(archive_batch.is_master("/docker/x/y.mxf"))
        self.assertTrue(archive_batch.is_master("/docker/x/y.MXF"))

    def test_mp4_is_not(self):
        self.assertFalse(archive_batch.is_master("/docker/x/y.mp4"))


class TestRemoteArchivePath(unittest.TestCase):
    """封存嘛送一份轉去伺服器，照播出月份分資料夾。"""

    NAME = "20210201_032_晚間_Amis_阿美"

    def test_path_is_root_month_name(self):
        self.assertEqual(
            archive_batch.remote_archive_path(self.NAME),
            "/home/news/mkv/2021-02/20210201_032_晚間_Amis_阿美.mkv")

    def test_the_folder_is_what_gets_made_first(self):
        self.assertEqual(
            archive_batch.remote_archive_dir(self.NAME),
            "/home/news/mkv/2021-02")

    def test_every_level_is_made_because_sftp_mkdir_is_not_recursive(self):
        # sftp ê mkdir 一改干焦一層，中間彼層無ê時就規句失敗。
        self.assertEqual(
            archive_batch.remote_dirs_to_make(self.NAME),
            ["/home", "/home/news", "/home/news/mkv",
             "/home/news/mkv/2021-02"])

    def test_the_month_comes_from_the_name(self):
        self.assertIn("/1999-01/",
                      archive_batch.remote_archive_path(
                          "19990101_001_午間_Test_測試"))

    def test_a_bad_name_cannot_become_a_remote_path(self):
        for bad in ("../../etc/passwd", "evil", ""):
            with self.assertRaises(PipelineError):
                archive_batch.remote_archive_path(bad)


class TestOutputPath(unittest.TestCase):
    def test_the_archive_dir_is_read_when_called_not_when_imported(self):
        # 預設值若佇 import 的時陣就綁死，換掉 paths.MKV_ARCHIVE 這爿
        # 完全無感覺——測試改了無效，是彼種恬恬失效ê陷阱。
        with mock.patch.object(paths, "MKV_ARCHIVE", "/tmp/somewhere-else"):
            out = archive_batch.output_path("20210201_032_晚間_Amis_阿美")
        self.assertTrue(out.startswith("/tmp/somewhere-else/"), out)

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


class TestNeedsUpload(unittest.TestCase):
    """補傳既有的封存：已經有的莫閣送，位元組數無仝的愛重送。

    22 支母帶轉的 mkv 是這條規矩訂出來進前就編好的，本機有、伺服器無。
    重編一擺是白了 20 分鐘一集，所以愛有一條干焦上傳的路。
    """

    def test_absent_on_the_server_needs_uploading(self):
        self.assertTrue(archive_batch.needs_upload(1000, None))

    def test_the_same_byte_count_is_already_there(self):
        self.assertFalse(archive_batch.needs_upload(1000, 1000))

    def test_a_different_byte_count_is_a_half_sent_file(self):
        self.assertTrue(archive_batch.needs_upload(1000, 640))


class TestMasterEpisodes(unittest.TestCase):
    """「賰的 mxf 攏轉做 mkv」彼條清單，對**目錄**提，毋是對 smkul.csv。

    smkul.csv 干焦列已經交付的集數，母帶封存佮 OCR 做到佗位無關係——
    影片佇伺服器頂懸，猶未讀字幕的集數嘛封存會得。
    """

    HEAD = ("節目名稱,年度,集數,播出日期,播出時段,族語別(英),族語別(中),"
            "有無影片,影片檔案位置,音檔位置(mp3),音檔位置(wav),文稿位置,備註")
    MXF = ("ilrdf-corpus/族語新聞/110.1-110.10/2月原始mxf檔/"
           "20NL003_32午間族語新聞.mxf")
    MP4 = ("ilrdf-corpus/族語新聞/110.1-110.10/7月/"
           "21NL003_41午間族語新聞.mp4")

    def _catalogue(self, rows):
        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".csv", delete=False, encoding="utf-8-sig")
        handle.write(self.HEAD + "\n")
        for row in rows:
            handle.write(row + "\n")
        handle.close()
        self.addCleanup(os.unlink, handle.name)
        from scripts.news import resolve_slug
        return resolve_slug.load(handle.name)

    def _row(self, episode, date, slot, en, zh, path):
        return ",".join(["%s族語新聞" % slot, "2021", episode, date, slot,
                         en, zh, "是", path, "", "", "", ""])

    def test_only_master_sourced_episodes_are_listed(self):
        cat = self._catalogue([
            self._row("32", "2021-02-01", "午間", "Atayal", "泰雅", self.MXF),
            self._row("41", "2021-02-10", "午間", "Cou", "鄒", self.MP4)])
        got = archive_batch.master_episodes(cat)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0][0], "20210201_032_午間_Atayal_泰雅")
        self.assertTrue(got[0][1].endswith(".mxf"))

    def test_the_remote_path_is_absolute_on_the_server(self):
        cat = self._catalogue([
            self._row("32", "2021-02-01", "午間", "Atayal", "泰雅", self.MXF)])
        self.assertTrue(archive_batch.master_episodes(cat)[0][1]
                        .startswith("/docker/ilrdf-corpus/"))

    def test_broadcast_order(self):
        other = self.MXF.replace("20NL003_32午間", "20NL003_33午間")
        cat = self._catalogue([
            self._row("33", "2021-02-02", "午間", "Kavalan", "噶瑪蘭", other),
            self._row("32", "2021-02-01", "午間", "Atayal", "泰雅", self.MXF)])
        names = []
        for name, _remote in archive_batch.master_episodes(cat):
            names.append(name)
        self.assertEqual(names, sorted(names))

    def test_the_list_is_pairs_of_name_and_remote(self):
        # `--list` 就是印這份清單，人看過才決定欲毋欲開始
        cat = self._catalogue([
            self._row("32", "2021-02-01", "午間", "Atayal", "泰雅", self.MXF)])
        name, remote = archive_batch.master_episodes(cat)[0]
        self.assertEqual(name, "20210201_032_午間_Atayal_泰雅")
        self.assertTrue(remote.endswith("20NL003_32午間族語新聞.mxf"))

    def test_rows_without_a_broadcast_date_are_ignored(self):
        # 《開會了》彼 46 逝無播出日期，命名袂出來
        cat = self._catalogue([
            ",".join(["開會了", "", "1", "", "", "", "", "是",
                      self.MXF, "", "", "", ""])])
        self.assertEqual(archive_batch.master_episodes(cat), [])


class TestDurationMatches(unittest.TestCase):
    """封存了後對時長——這是「敢有對半截的母帶轉落去」唯一掠會著的所在。

    2 月 24 支母帶有 2 支上傳無齊，而且 `ffprobe` 對母帶讀出來的時長照常
    宣稱完整；毋過轉出來的 mkv 是實際解碼出來的，短就是短，佮 store 內底
    彼條時間軸一比就現形。
    """

    def test_the_same_length_passes(self):
        self.assertTrue(archive_batch.duration_matches(2880.0, 2880.0))

    def test_a_small_wobble_is_fine(self):
        self.assertTrue(archive_batch.duration_matches(2880.4, 2880.0))

    def test_a_truncated_encode_is_caught(self):
        # 55% 彼支：解碼出來才 1584 秒，時間軸講 2880
        self.assertFalse(archive_batch.duration_matches(1584.0, 2880.0))

    def test_no_timeline_to_compare_against_is_not_a_failure(self):
        # 猶未切 cue 的集數照常封存，無物通比就莫假做有比
        self.assertTrue(archive_batch.duration_matches(2880.0, None))


class TestListRespectsLimit(unittest.TestCase):
    """`--list --limit 3` 愛列 3 逝，毋是規份。

    `--list` 是「敢是我想ê彼幾支？」ê問題；限額若無算入去，人看著ê佮
    提掉 --list 了後真正會做ê無仝款，彼是上僫掠ê彼種文件錯誤。
    """

    def test_limit_is_applied_before_listing(self):
        rows = [("a", "/x/a.mxf"), ("b", "/x/b.mxf"), ("c", "/x/c.mxf")]
        self.assertEqual(archive_batch.apply_limit(rows, 2), rows[:2])

    def test_zero_means_everything(self):
        rows = [("a", "/x/a.mxf")]
        self.assertEqual(archive_batch.apply_limit(rows, 0), rows)


class TestEncodeLock(unittest.TestCase):
    """一集干焦准一个行程轉。

    舊寫法是「partial 若佇咧就 `os.remove`」——彼是先看才做，中間有縫：
    A 看無 partial（B 猶未開始）、B 開始、A 才開始，A 頭一句就kā B 轉半條
    ê物件刣掉。兩爿攏照規矩，猶原相撞。所以改用**原子占位**：`O_EXCL` 建
    鎖，建會起才是你ê。
    """

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dst = os.path.join(tmp.name, "x.mkv")

    def test_the_first_caller_takes_it(self):
        with archive_batch.encode_lock(self.dst):
            self.assertTrue(archive_batch.is_locked(self.dst))

    def test_the_lock_is_released_afterwards(self):
        with archive_batch.encode_lock(self.dst):
            pass
        self.assertFalse(archive_batch.is_locked(self.dst))

    def test_released_even_when_the_encode_blows_up(self):
        try:
            with archive_batch.encode_lock(self.dst):
                raise ValueError("ffmpeg 死去")
        except ValueError:
            pass
        self.assertFalse(archive_batch.is_locked(self.dst))

    def test_a_second_caller_is_told_it_is_taken(self):
        with archive_batch.encode_lock(self.dst):
            with self.assertRaises(archive_batch.Busy):
                with archive_batch.encode_lock(self.dst):
                    self.fail("袂使兩个同時提著")

    def test_the_lock_names_the_process_holding_it(self):
        with archive_batch.encode_lock(self.dst):
            with open(self.dst + ".lock", encoding="utf-8") as handle:
                self.assertEqual(handle.read().strip(), str(os.getpid()))

    def test_busy_is_not_a_failure(self):
        # 呼叫端愛分會出「別人咧做」佮「轉檔失敗」，一个是跳過、一个是報錯
        self.assertTrue(issubclass(archive_batch.Busy, PipelineError))


if __name__ == "__main__":
    unittest.main()
