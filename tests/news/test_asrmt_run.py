"""asrmt_run: the per-episode orchestration guards.

Pins the asr-bilingual-srt spec's 音檔時長不符 scenario -- fail loud,
naming the episode and both durations, producing nothing -- and the
resume rule: a step whose output already exists is skipped, so an
interrupted run continues instead of redoing paid work.
"""
import os
import tempfile
import unittest

from scripts.news import asrmt_run


class TestVerifyAudio(unittest.TestCase):
    def test_within_tolerance_passes(self):
        asrmt_run.verify_audio("試集", 2880.168, 2880.144)

    def test_mismatch_names_the_episode_and_both_numbers(self):
        with self.assertRaises(SystemExit) as caught:
            asrmt_run.verify_audio("試集", 2760.0, 2880.144)
        message = str(caught.exception)
        self.assertIn("試集", message)
        self.assertIn("2760", message)
        self.assertIn("2880.144", message)

    def test_tolerance_is_one_second_by_default(self):
        with self.assertRaises(SystemExit):
            asrmt_run.verify_audio("試集", 2881.5, 2880.0)
        asrmt_run.verify_audio("試集", 2880.9, 2880.0)


class TestResume(unittest.TestCase):
    def test_existing_output_skips_the_step(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "done.json")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("{}")
            self.assertFalse(asrmt_run.step_needed(path))
            self.assertTrue(asrmt_run.step_needed(
                os.path.join(tmp, "not-there.json")))


class TestModelMapping(unittest.TestCase):
    def test_inventory_ethnicity_maps_to_hf_repo_name(self):
        # inventory 的族語別(英) 與 HF 模型 repo 名有五處不同拼法
        self.assertEqual(asrmt_run.model_id_of("Amis"),
                         "ILRDF/kaldi_formosan_250514_Amis")
        self.assertEqual(asrmt_run.model_id_of("SaySiyat"),
                         "ILRDF/kaldi_formosan_250514_Saisiyat")
        self.assertEqual(asrmt_run.model_id_of("Pinuyumayan"),
                         "ILRDF/kaldi_formosan_250514_Puyuma")
        self.assertEqual(asrmt_run.model_id_of("Hla'alua"),
                         "ILRDF/kaldi_formosan_250514_Saaroa")
        self.assertEqual(asrmt_run.model_id_of("Cou"),
                         "ILRDF/kaldi_formosan_250514_Tsou")
        self.assertEqual(asrmt_run.model_id_of("Thau"),
                         "ILRDF/kaldi_formosan_250514_Thao")

    def test_unknown_ethnicity_fails_loud(self):
        with self.assertRaises(SystemExit):
            asrmt_run.model_id_of("Klingon")


class TestMp3Resolution(unittest.TestCase):
    def test_remote_path_from_catalogue_row(self):
        rows = [{"播出日期": "2021-02-01", "播出時段": "晚間",
                 "音檔位置(mp3)": "ilrdf-corpus/族語新聞/7月/x.mp3"}]
        got = asrmt_run.mp3_remote("20210201_032_晚間_Amis_阿美", rows)
        self.assertEqual(got, "/docker/ilrdf-corpus/族語新聞/7月/x.mp3")

    def test_missing_row_fails_loud(self):
        with self.assertRaises(SystemExit):
            asrmt_run.mp3_remote("20210301_060_午間_Cou_鄒", [])

    def test_semicolon_cell_picks_the_matching_slot(self):
        # 型錄的 mp3 欄有同格塞多路徑的情況（037 晚間實例）
        rows = [{"播出日期": "2021-02-06", "播出時段": "晚間",
                 "音檔位置(mp3)":
                 "ilrdf-corpus/7月/21NL004_37午間族語新聞.mp3;"
                 "ilrdf-corpus/7月/21NL004_37晚間族語新聞.mp3"}]
        got = asrmt_run.mp3_remote("20210206_037_晚間_Paiwan_排灣", rows)
        self.assertEqual(got,
                         "/docker/ilrdf-corpus/7月/21NL004_37晚間族語新聞.mp3")

    def test_semicolon_cell_without_slot_match_takes_the_first(self):
        rows = [{"播出日期": "2021-02-06", "播出時段": "晚間",
                 "音檔位置(mp3)": "ilrdf-corpus/a.mp3;ilrdf-corpus/b.mp3"}]
        got = asrmt_run.mp3_remote("20210206_037_晚間_Paiwan_排灣", rows)
        self.assertEqual(got, "/docker/ilrdf-corpus/a.mp3")


if __name__ == "__main__":
    unittest.main()


class TestNameGuardWiring(unittest.TestCase):
    def test_path_escaping_srt_name_dies_before_touching_anything(self):
        # 帶路徑成分的參數要在格式驗證就擋下，
        # 不是走到 inventory 查無此集才失敗
        with self.assertRaisesRegex(SystemExit, "格式"):
            asrmt_run.main(["../../home/somebody/.sftp-pass"])
