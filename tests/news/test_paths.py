"""paths: ROOT derivation, the --var CLI, and the argument guards."""
import os
import subprocess
import sys
import tempfile
import unittest

from scripts.news import paths


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

    def test_store_layout_is_corpus_technique_stage(self):
        # Kari-SRT is layered corpus -> technique -> numbered stage; the
        # numbers are the production order (srt-data-store spec).
        news = os.path.join(paths.KARI, "news")
        ocr = os.path.join(news, "1-ocr")
        self.assertEqual(paths.KARI_CUES, os.path.join(ocr, "1-cues"))
        self.assertEqual(paths.KARI_FROM_RTF,
                         os.path.join(ocr, "2-from_rtf"))
        self.assertEqual(paths.KARI_VISION, os.path.join(ocr, "3-vision"))
        self.assertEqual(paths.KARI_VISION_RTF,
                         os.path.join(ocr, "4-vision-rtf"))
        self.assertEqual(paths.SRT_DIR, os.path.join(ocr, "6-srt"))
        self.assertEqual(paths.INVENTORY,
                         os.path.join(news, "inventory.json"))
        self.assertEqual(paths.TRACKER_STORE,
                         os.path.join(news, "smkul.csv"))
        self.assertEqual(paths.ASR_DIR, os.path.join(news, "2-asr"))


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

    def test_separators_and_dots_are_refused(self):
        for bad in ("a/b", "a\\b", "..", "x/../y", "", "."):
            with self.assertRaises(SystemExit):
                paths.check_name(bad, "slug")

    def test_srt_name_needs_the_date_episode_prefix(self):
        for bad in ("evil", "2021_032_晚間", "20210201_32_晚間",
                    "20210201_032_晚間/../x", "/etc/passwd"):
            with self.assertRaises(SystemExit):
                paths.check_srt_name(bad)

    def test_only_ascii_digits_count_as_the_date(self):
        # Python 的 \d 預設連 Unicode 數字都吃（٢٠٢١、２０２１），那些
        # 不是集數命名用的字元；日期與集數只認 ASCII 0-9。
        for bad in ("٢٠٢١٠٢٠١_٠٣٢_晚間_Amis_阿美",
                    "２０２１０２０１_０３２_晚間_Amis_阿美"):
            with self.assertRaises(SystemExit):
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
            with self.assertRaises(SystemExit):
                paths.check_under(bad)

    def test_outside_the_repo_is_refused(self):
        for bad in ("/etc/passwd", os.path.expanduser("~/.ssh/id_rsa")):
            with self.assertRaises(SystemExit):
                paths.check_under(bad)

    def test_traversal_out_of_a_data_folder_is_refused(self):
        escape = os.path.join(paths.WORK, "..", "..", "..", "..", "etc")
        with self.assertRaises(SystemExit):
            paths.check_under(escape)

    def test_a_sibling_sharing_the_prefix_is_refused(self):
        # kithann-secret 並不在 kithann/ 底下——前綴比對一定要帶分隔符
        with self.assertRaises(SystemExit):
            paths.check_under(paths.KITHANN + "-secret")

    def test_a_call_site_may_name_its_own_roots(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(paths.check_under(tmp, roots=[tmp]), tmp)


if __name__ == "__main__":
    unittest.main()
