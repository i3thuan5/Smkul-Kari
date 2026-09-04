"""paths: ROOT derivation, the --var CLI, and the argument guards."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

from scripts.news import paths
from scripts.errors import PipelineError


class TestConstants(unittest.TestCase):
    def test_root_is_the_repo_checkout(self):
        # derived from __file__, so it must hold this very package
        self.assertTrue(os.path.isdir(os.path.join(paths.ROOT, "scripts",
                                                   "news")))
        self.assertTrue(os.path.isfile(os.path.join(paths.ROOT, "tox.ini")))

    def test_every_path_lives_under_root(self):
        for value in (paths.WORK, paths.LOGS, paths.KARI, paths.SRT_DIR,
                      paths.ENGINE_PRESETS, paths.INVENTORY,
                      paths.CATALOGUE):
            self.assertTrue(value.startswith(paths.ROOT + os.sep), value)

    def test_srt_dir_is_inside_kari(self):
        self.assertTrue(paths.SRT_DIR.startswith(paths.KARI + os.sep))

    def test_the_catalogue_is_in_the_store_not_the_workspace(self):
        # 目錄是外部予的來源資料、重生袂出來（正本是伺服器頂彼支
        # xlsx），而且是規劃新月份的源頭。囥佇 gitignore 的 kithann/，
        # 換一台機器就無去；伊愛綴資料走。
        self.assertEqual(paths.CATALOGUE,
                         os.path.join(paths.KARI, "ilrdf-corpus.csv"))
        self.assertFalse(paths.CATALOGUE.startswith(paths.KITHANN + os.sep))

    def test_the_catalogue_covers_more_than_one_corpus_so_it_sits_on_top(self):
        # 內底有族語新聞（983 逝）嘛有開會了（46 逝），毋是 news/ 一个
        # 語料的物件，所以囥 Kari-SRT 的頂層。
        self.assertEqual(os.path.dirname(paths.CATALOGUE), paths.KARI)

    def test_store_layout_is_corpus_technique_stage(self):
        # Kari-SRT is layered corpus -> technique -> numbered stage; the
        # numbers are the production order (srt-data-store spec).
        news = os.path.join(paths.KARI, "news")
        ocr = os.path.join(news, "1-ocr")
        self.assertEqual(paths.KARI_CUES, os.path.join(ocr, "1-cues"))
        self.assertEqual(paths.KARI_VISION, os.path.join(ocr, "2-vision"))
        self.assertEqual(paths.SRT_DIR, os.path.join(ocr, "3-srt"))
        self.assertEqual(paths.INVENTORY,
                         os.path.join(news, "inventory.json"))
        self.assertEqual(paths.TRACKER_STORE,
                         os.path.join(news, "smkul.csv"))
        self.assertEqual(paths.ASR_DIR, os.path.join(news, "2-asr"))

    def test_the_catalogue_is_data_so_it_lives_in_the_store(self):
        # 目錄是跨語料的資料（毋是這批新聞專屬），所以khǹg佇 Kari-SRT
        # 頂層。伊本底佇 `kithann/`，毋過彼跡是 gitignore ê——換一台機器
        # 就無去矣，而且 `plan_month` 無伊就選袂出來源。
        self.assertEqual(paths.CATALOGUE,
                         os.path.join(paths.KARI, "ilrdf-corpus.csv"))
        self.assertFalse(paths.CATALOGUE.startswith(paths.KITHANN + os.sep))

    def test_stage_constants_are_base_folders_not_file_locations(self):
        # 逐集檔案住佇階段目錄下的月份一層，所以階段常數是「基底」，
        # 毋是「檔案囥的所在」——組路徑一律行 stage_path()。
        name = "20210201_032_午間_Atayal_泰雅"
        for base in (paths.KARI_CUES, paths.KARI_VISION, paths.SRT_DIR):
            self.assertEqual(paths.stage_path(base, name),
                             os.path.join(base, "2021-02", name))

    def test_the_retired_stages_are_gone(self):
        # 文稿供字彼條路線佮 align 延伸攏裁掉矣，常數留咧就是閣有人
        # 會去指——階段目錄本身嘛已經對 store 提掉。
        for name in ("KARI_FROM_RTF", "KARI_VISION_RTF", "KARI_REPORT",
                     "MT_CACHE"):
            self.assertFalse(hasattr(paths, name), name)


class TestStagePath(unittest.TestCase):
    """stage_path：階段目錄下的月份一層，是組路徑的唯一出口。

    月份鍵對 `srt_name` 家己推，無另外囥一份對照表——兩份真相愛同步
    的問題，inventory 已經踏過一擺矣。
    """

    NAME = "20210201_032_午間_Atayal_泰雅"

    def test_month_comes_from_the_name_itself(self):
        self.assertEqual(paths.month_of(self.NAME), "2021-02")
        self.assertEqual(paths.month_of("19990101_001_午間_Test_測試"),
                         "1999-01")

    def test_path_is_stage_then_month_then_name(self):
        got = paths.stage_path("/base", self.NAME)
        self.assertEqual(got, os.path.join("/base", "2021-02", self.NAME))

    def test_a_suffix_lands_on_the_file_not_the_folder(self):
        got = paths.stage_path("/base", self.NAME, ".json")
        self.assertEqual(got,
                         os.path.join("/base", "2021-02",
                                      self.NAME + ".json"))

    def test_the_name_is_checked_before_it_becomes_a_path(self):
        for bad in ("../../etc/passwd", "evil", "", None,
                    "20210201_032_晚間/../x"):
            with self.assertRaises(PipelineError):
                paths.stage_path("/base", bad)

    def test_an_impossible_month_stops_instead_of_making_a_junk_folder(self):
        # check_srt_name 只認「8 碼數字」，無認彼 8 碼是毋是真正的日期。
        # 若無擋，2021-99/ 這款資料夾會恬恬生出來、閣揣無人會發覺。
        for bad in ("20219901_001_午間_Test_測試",
                    "20210001_001_午間_Test_測試"):
            with self.assertRaisesRegex(PipelineError, "月份"):
                paths.month_of(bad)


class TestVarCli(unittest.TestCase):
    def _var(self, name, env_extra):
        env = dict(os.environ)
        env.update(env_extra)
        proc = subprocess.run(
            [sys.executable, "-m", "scripts.news.paths", "--var", name],
            capture_output=True, text=True, cwd=paths.ROOT, env=env)
        return proc

    def test_unknown_var_fails_and_lists_the_known_ones(self):
        proc = self._var("NO_SUCH_PATH", {})
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("WORK", proc.stderr)


class TestNameGuards(unittest.TestCase):
    """名字類 CLI 參數不得帶路徑成分逃出基底資料夾。

    工作目錄、store 檔案都是「基底資料夾＋名字」組出來的；名字帶
    分隔符或 .. 就會變成任意讀寫（agent 打錯或被誘導的參數）。
    """

    def test_good_names_pass_through(self):
        self.assertEqual(paths.check_name("abc.B", "slug"), "abc.B")
        name = "20210201_032_晚間_Amis_阿美"
        self.assertEqual(paths.check_srt_name(name), name)

    def test_hlaalua_apostrophe_is_a_legal_name_character(self):
        name = "20210304_063_晚間_Hla'alua_拉阿魯哇"
        self.assertEqual(paths.check_srt_name(name), name)

    def test_a_missing_name_says_so_instead_of_blaming_path_components(self):
        # None 是 inventory 寫成 "slug": null 時會拿到的；它並沒有「帶
        # 路徑成分」，訊息要講對事情才找得到問題。
        for empty in (None, ""):
            with self.assertRaisesRegex(PipelineError, "無值"):
                paths.check_name(empty, "slug")
        with self.assertRaisesRegex(PipelineError, "無值"):
            paths.check_srt_name(None)

    def test_a_name_is_never_silently_rewritten(self):
        # 清乾淨後若跟原本不同，就是中止而不是回傳清過的版本：
        # inventory 讀進來會被 publish／add_episodes 寫回去，靜默改寫
        # 等於改掉資料正本。
        with self.assertRaises(PipelineError):
            paths.check_name("2021_041_午間/../別集", "slug")

    def test_separators_and_dots_are_refused(self):
        for bad in ("a/b", "a\\b", "..", "x/../y", "", "."):
            with self.assertRaises(PipelineError):
                paths.check_name(bad, "slug")

    def test_srt_name_needs_the_date_episode_prefix(self):
        for bad in ("evil", "2021_032_晚間", "20210201_32_晚間",
                    "20210201_032_晚間/../x", "/etc/passwd"):
            with self.assertRaises(PipelineError):
                paths.check_srt_name(bad)

    def test_only_ascii_digits_count_as_the_date(self):
        # Python 的 \d 預設連 Unicode 數字都吃（٢٠٢١、２０２１），那些
        # 不是集數命名用的字元；日期與集數只認 ASCII 0-9。
        for bad in ("٢٠٢١٠٢٠١_٠٣٢_晚間_Amis_阿美",
                    "２０２１０２０１_０３２_晚間_Amis_阿美"):
            with self.assertRaises(PipelineError):
                paths.check_srt_name(bad)


class TestPathGuard(unittest.TestCase):
    """check_under：路徑類 CLI 參數只准落在資料資料夾裡。

    白名單是 kithann/（工作區與快取）、Kari-SRT/（資料正本）、系統暫存
    目錄（rebuild 與 asrmt 在那裡合成工作目錄）。repo 底下的其他地方
    ——程式碼、openspec——不是資料，不准當輸出入路徑。
    """

    def test_the_three_data_roots_pass(self):
        for good in (paths.WORK, paths.STAGE, paths.SRT_DIR, paths.ASR_DIR):
            self.assertEqual(paths.check_under(good), good)

    def test_tempdir_passes_because_rebuild_synthesises_work_dirs_there(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(paths.check_under(tmp), tmp)

    def test_elsewhere_in_the_repo_is_refused(self):
        # 「不是 repo 底下都可以讀寫」：程式碼與規格不是資料
        for bad in (os.path.join(paths.ROOT, "scripts"),
                    os.path.join(paths.ROOT, "openspec"),
                    paths.ROOT):
            with self.assertRaises(PipelineError):
                paths.check_under(bad)

    def test_outside_the_repo_is_refused(self):
        for bad in ("/etc/passwd", os.path.expanduser("~/.ssh/id_rsa")):
            with self.assertRaises(PipelineError):
                paths.check_under(bad)

    def test_traversal_out_of_a_data_folder_is_refused(self):
        escape = os.path.join(paths.WORK, "..", "..", "..", "..", "etc")
        with self.assertRaises(PipelineError):
            paths.check_under(escape)

    def test_a_sibling_sharing_the_prefix_is_refused(self):
        # kithann-secret 並不在 kithann/ 底下——前綴比對一定要帶分隔符
        with self.assertRaises(PipelineError):
            paths.check_under(paths.KITHANN + "-secret")

    def test_a_call_site_may_name_its_own_roots(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(paths.check_under(tmp, roots=[tmp]), tmp)


class TestLoadInventory(unittest.TestCase):
    """inventory 是名字進入程式的唯一入口，就在這裡檢查。

    11 支程式都拿 slug／srt_name 去組工作目錄與 store 檔名；檢查集中
    在讀出來的那一刻，下游才不必各自重複，而且「inventory 的名字是
    安全的」這個假設才變成明講的、擋得住的不變量。
    """

    def _write(self, entries):
        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False, encoding="utf-8")
        json.dump(entries, handle, ensure_ascii=False)
        handle.close()
        self.addCleanup(os.unlink, handle.name)
        return handle.name

    def _entry(self, **over):
        entry = {"slug": "2021_032_2021-02-01_午間_Atayal_泰雅",
                 "srt_name": "20210201_032_午間_Atayal_泰雅",
                 "video": "ilrdf-corpus/2月/x.mxf", "truncated": "",
                 "文稿位置": "", "節目名稱": "午間族語新聞", "年度": "2021",
                 "集數": "32", "播出日期": "2021-02-01",
                 "播出時段": "午間", "族語別(英)": "Atayal",
                 "族語別(中)": "泰雅"}
        entry.update(over)
        return entry

    def test_legal_entries_come_back_unchanged(self):
        entry = self._entry()
        got = paths.load_inventory(self._write([entry]))
        self.assertEqual(got, [entry])

    def test_a_slug_with_path_components_is_refused(self):
        path = self._write([self._entry(slug="../../etc/passwd")])
        with self.assertRaises(PipelineError):
            paths.load_inventory(path)

    def test_an_srt_name_with_path_components_is_refused(self):
        path = self._write([self._entry(srt_name="../../etc/passwd")])
        with self.assertRaises(PipelineError):
            paths.load_inventory(path)

    def test_a_missing_required_field_is_named(self):
        entry = self._entry()
        del entry["播出時段"]
        path = self._write([entry])
        with self.assertRaisesRegex(PipelineError, "播出時段"):
            paths.load_inventory(path)

    def test_optional_fields_survive(self):
        # pending 只在批次進行中存在、publish 完成時刪掉；partial 會併進
        # smkul.csv 的狀態欄。讀進來若把它們丟掉，寫回去就永久消失。
        entry = self._entry(pending="尚未切cue", partial="來源只有前半",
                            file="20NL003_32午間族語新聞.mxf")
        got = paths.load_inventory(self._write([entry]))
        self.assertEqual(got[0]["pending"], "尚未切cue")
        self.assertEqual(got[0]["partial"], "來源只有前半")
        self.assertEqual(got[0]["file"], "20NL003_32午間族語新聞.mxf")

    def test_an_undeclared_field_stops_rather_than_vanishing(self):
        # 條目是逐欄位重建的，沒宣告的欄位會在 publish 寫回 store 時
        # 消失。與其靜默掉資料，不如中止、要求先去宣告。
        entry = self._entry()
        entry["新欄位"] = "x"
        path = self._write([entry])
        with self.assertRaisesRegex(PipelineError, "新欄位"):
            paths.load_inventory(path)

    def test_field_order_follows_the_store_not_the_input(self):
        # publish／add_episodes 會把這些條目寫回 inventory.json；重建的
        # 順序若跟正本不同，一次寫回就是整份檔案的 diff。
        entry = self._entry(file="20NL003_32午間族語新聞.mxf",
                            partial="來源只有前半")
        got = paths.load_inventory(self._write([entry]))[0]
        self.assertEqual(list(got)[:4],
                         ["file", "video", "slug", "srt_name"])
        self.assertEqual(list(got)[-2:], ["truncated", "partial"])

    def test_every_entry_is_checked_not_just_the_first(self):
        path = self._write([self._entry(),
                            self._entry(slug="a/b")])
        with self.assertRaises(PipelineError):
            paths.load_inventory(path)


class TestStageLayout(unittest.TestCase):
    """work dir 的 cues.json 分階段：粗切一份、精修一份，不互相蓋。

    使用者裁定 2026-08-31：**refine 不可以原地改寫粗切那份。** 原本
    `refine_cues` 是讀進記憶體、改完整份寫回同一個檔，於是：

    - 精修跑到一半被砍，粗切那份就毀了（而且它是**重切才生得回來**的，
      要重新下載 2 GB 的影片）；
    - 兩個行程同時開同一份 manifest，後寫的贏，沒有一個地方會報錯
      （這是 aiyalaeho 那條線先踩到、回報過來的）。

    分開之後粗切變成唯讀，上面兩件都消掉了：精修失敗最多是沒有精修版。

    編號跟 store 的 `news/1-ocr/1-cues/` 是同一套意思——數字是產製順序。
    """

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.work = tmp.name

    def _write(self, rel, body="{}"):
        path = os.path.join(self.work, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(body)
        return path

    def test_the_two_stages_are_separate_files(self):
        self.assertNotEqual(paths.coarse_cues(self.work),
                            paths.refined_cues(self.work))

    def test_the_coarse_one_is_stage_one(self):
        self.assertEqual(paths.coarse_cues(self.work),
                         os.path.join(self.work, "1-cues", "cues.json"))

    def test_the_refined_one_is_stage_two(self):
        self.assertEqual(paths.refined_cues(self.work),
                         os.path.join(self.work, "2-refined", "cues.json"))

    def test_reading_prefers_the_refined_one(self):
        self._write("1-cues/cues.json")
        self._write("2-refined/cues.json")
        self.assertEqual(paths.cues_to_read(self.work),
                         paths.refined_cues(self.work))

    def test_reading_falls_back_to_the_coarse_one(self):
        # 精修猶未做（抑是做失敗），粗切彼份照常會使組 SRT，干焦邊界
        # 是 0.2 秒格ê。
        self._write("1-cues/cues.json")
        self.assertEqual(paths.cues_to_read(self.work),
                         paths.coarse_cues(self.work))

    def test_reading_nothing_is_none_not_a_guess(self):
        self.assertIsNone(paths.cues_to_read(self.work))

    def test_the_pre_split_layout_is_no_longer_read(self):
        """舊版面（平ê `<work>/cues.json`）已經無人捌矣。

        過渡期間伊排佇第三位讀會著，因為遷移袂當一睏做煞——換版面
        彼陣《開會了》彼條線咧走一批 7 點鐘ê切 cue，一直咧生舊版面ê
        work dir，讀ê程式若干焦捌新版面，彼批做到一半就斷去。

        `migrate_workdirs` 掃過矣（news 75 个、《開會了》40 个，兩爿
        攏賰 0 个平版面），所以這條路提掉。留咧ê代價是：有人手動
        khǹg一份平ê落去，程式會恬恬讀伊，而且無人知影彼份是佗位來ê。
        """
        self._write("cues.json")
        self.assertIsNone(paths.cues_to_read(self.work))

    def test_refined_asks_the_file_not_the_flag(self):
        # 「敢精修過矣」是問彼个檔案佇無，毋是去剖粗切彼份內底ê旗標
        self._write("1-cues/cues.json")
        self.assertFalse(paths.is_refined(self.work))
        self._write("2-refined/cues.json")
        self.assertTrue(paths.is_refined(self.work))


class TestHasCues(unittest.TestCase):
    """「這集切過矣未？」——兩个 work dir 隨一个有 cues.json 就算切過。

    通常兩个攏有（`cues` 寫 `.work`，`gap_sheets` 對伊生 `.B.work`），
    毋過 `fetch_sftp.sh` 是直接切入去 `.B.work`，054–059 彼批連 `.work`
    都無。干焦問 `.work` ê話，14 集已經做好ê會予人講「尚未切cue」。

    問題毋是干焦報告歹看：`fetch_sftp.sh` 用仝一句判斷來決定「愛閣切
    無」，判毋著就是kā已交付ê集數重切——cue 規排重編號，交付ê SRT
    時間就對袂起來矣。所以這句判斷愛干焦一份，佇遮。
    """

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.work = tmp.name

    def _cut(self, suffix, stage="1-cues"):
        folder = os.path.join(self.work, "ep" + suffix, stage)
        os.makedirs(folder)
        with open(os.path.join(folder, "cues.json"), "w") as handle:
            handle.write("{}")

    def test_nothing_on_disk_means_not_cut(self):
        self.assertFalse(paths.has_cues("ep", work=self.work))

    def test_the_plain_work_dir_counts(self):
        self._cut(".work")
        self.assertTrue(paths.has_cues("ep", work=self.work))

    def test_the_vision_work_dir_counts_on_its_own(self):
        self._cut(".B.work")
        self.assertTrue(paths.has_cues("ep", work=self.work))

    def test_an_empty_work_dir_is_not_cut(self):
        os.makedirs(os.path.join(self.work, "ep.work"))
        self.assertFalse(paths.has_cues("ep", work=self.work))

    def test_another_episodes_cues_do_not_count(self):
        self._cut(".work")
        self.assertFalse(paths.has_cues("other", work=self.work))


if __name__ == "__main__":
    unittest.main()
