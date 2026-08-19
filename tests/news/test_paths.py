"""paths: ROOT derivation, the --var CLI, and the argument guards."""
import json
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

    def test_a_missing_name_says_so_instead_of_blaming_path_components(self):
        # None 是 inventory 寫成 "slug": null 時會拿到的；它並沒有「帶
        # 路徑成分」，訊息要講對事情才找得到問題。
        for empty in (None, ""):
            with self.assertRaisesRegex(SystemExit, "無值"):
                paths.check_name(empty, "slug")
        with self.assertRaisesRegex(SystemExit, "無值"):
            paths.check_srt_name(None)

    def test_a_name_is_never_silently_rewritten(self):
        # 清乾淨後若跟原本不同，就是中止而不是回傳清過的版本：
        # inventory 讀進來會被 publish／add_episodes 寫回去，靜默改寫
        # 等於改掉資料正本。
        with self.assertRaises(SystemExit):
            paths.check_name("2021_041_午間/../別集", "slug")

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
        with self.assertRaises(SystemExit):
            paths.load_inventory(path)

    def test_an_srt_name_with_path_components_is_refused(self):
        path = self._write([self._entry(srt_name="../../etc/passwd")])
        with self.assertRaises(SystemExit):
            paths.load_inventory(path)

    def test_a_missing_required_field_is_named(self):
        entry = self._entry()
        del entry["播出時段"]
        with self.assertRaisesRegex(SystemExit, "播出時段"):
            paths.load_inventory(self._write([entry]))

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
        with self.assertRaisesRegex(SystemExit, "新欄位"):
            paths.load_inventory(self._write([entry]))

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
        with self.assertRaises(SystemExit):
            paths.load_inventory(path)


if __name__ == "__main__":
    unittest.main()
