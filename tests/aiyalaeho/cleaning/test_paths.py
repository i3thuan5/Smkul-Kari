"""清洗的輸出位置：各層照產出順序編號，而且絕對不寫進 Kari-SRT。"""
import os
import tempfile
import unittest

from scripts.aiyalaeho.cleaning import paths
from scripts.datadirs import KARI
from scripts.datadirs import KITHANN
from scripts.errors import PipelineError


class TestLayout(unittest.TestCase):
    def test_default_root_is_under_kithann_out(self):
        self.assertEqual(paths.OUT,
                         os.path.join(KITHANN, "out", "aiyalaeho-清洗"))

    def test_stages_are_numbered_in_production_order(self):
        root = tempfile.mkdtemp()
        layout = paths.Layout(root)
        self.assertEqual(layout.klokah, os.path.join(root, "1-詞庫", "E樂園"))
        self.assertEqual(layout.kaldi,
                         os.path.join(root, "1-詞庫", "Kaldi詞表"))
        self.assertEqual(layout.candidates, os.path.join(root, "2-候選"))
        self.assertEqual(layout.text_verdicts,
                         os.path.join(root, "3-判定", "文字分類"))
        self.assertEqual(layout.image_verdicts,
                         os.path.join(root, "3-判定", "看圖"))
        self.assertEqual(layout.overrides,
                         os.path.join(root, "3-判定", "人工改判.csv"))
        self.assertEqual(layout.cleaned, os.path.join(root, "4-清洗版"))
        self.assertEqual(layout.deliver, os.path.join(root, "5-交付"))

    def test_targets_are_the_ten_delivered_episodes(self):
        # 承辦講的 10 則＝第1期 4 集＋第2-1期新增 6 集。
        self.assertEqual(len(paths.TARGETS), 10)
        for name in paths.TARGETS:
            self.assertTrue(name.startswith("開會了_"))


class TestNeverWritesKari(unittest.TestCase):
    def test_root_under_kari_is_refused_before_anything_is_made(self):
        # 輸出目錄被設到 Kari-SRT 底下：交付資料會被改掉。要當場擋，
        # 而且擋的時候還沒建任何目錄。
        target = os.path.join(KARI, "aiyalaeho", "1-ocr", "清洗試做")
        with self.assertRaises(PipelineError) as caught:
            paths.Layout(target)
        self.assertIn(target, str(caught.exception))
        self.assertFalse(os.path.exists(target))

    def test_kari_itself_is_refused(self):
        with self.assertRaises(PipelineError):
            paths.Layout(KARI)

    def test_guard_refuses_a_single_file_under_kari(self):
        with self.assertRaises(PipelineError):
            paths.guard(os.path.join(KARI, "aiyalaeho", "smkul.csv"))

    def test_a_sibling_whose_name_starts_with_kari_is_fine(self):
        # 只比字串開頭的話，Kari-SRT-copy 也會被擋——要比路徑成分。
        sibling = KARI + "-copy"
        self.assertEqual(paths.guard(os.path.join(sibling, "a.csv")),
                         os.path.join(sibling, "a.csv"))


if __name__ == "__main__":
    unittest.main()
