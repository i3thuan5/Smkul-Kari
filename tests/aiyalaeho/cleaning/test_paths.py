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


def _entry(name, tribe, pending=False, abnormal=False):
    return {"srt_name": name, "族語別(中)": tribe, "pending": pending,
            "abnormal": abnormal}


class TestTargets(unittest.TestCase):
    """清洗範圍＝節目目錄已交付的集，不寫死清單。"""

    def test_only_delivered_episodes_sorted_by_name(self):
        # 第2-1期寫死 10 集：目錄長到 39 集，程式仍只跑 10 集，報告寫
        # 39 集、清洗版只有 10 個檔。版型異常（083 只有華語字幕、088
        # 無字幕）沒有 SRT，算進來會中途找不到檔倒掉；pending 也一樣。
        catalogue = [
            _entry("開會了_092_SaySiyat_賽夏", "賽夏"),
            _entry("開會了_068_Amis_阿美", "阿美"),
            _entry("開會了_083_Rukai_魯凱", "魯凱", abnormal=True),
            _entry("開會了_088_Atayal_泰雅", "泰雅", abnormal=True,
                   pending=True),
            _entry("開會了_200_Amis_阿美", "阿美", pending=True),
        ]
        self.assertEqual(paths.targets(catalogue),
                         ["開會了_068_Amis_阿美", "開會了_092_SaySiyat_賽夏"])

    def test_accepts_the_name_keyed_catalogue(self):
        # __main__ 手上的目錄是 {成果檔名: 條目}，兩種都要吃。
        name = "開會了_068_Amis_阿美"
        catalogue = {name: _entry(name, "阿美")}
        self.assertEqual(paths.targets(catalogue), ["開會了_068_Amis_阿美"])


class TestDictionaryVariety(unittest.TestCase):
    def test_measured_varieties(self):
        # 2026-11-23 量官方辭典 xlsx「語別」欄。
        self.assertEqual(paths.dictionary_variety("阿美"), "秀姑巒")
        self.assertEqual(paths.dictionary_variety("布農"), "郡群")
        self.assertEqual(paths.dictionary_variety("排灣"), "北排灣")
        self.assertEqual(paths.dictionary_variety("雅美"), "")
        self.assertEqual(paths.dictionary_variety("賽夏"), "")

    def test_unmeasured_language_stops_and_names_it(self):
        # 用 .get(族, "") 的話，沒量過的族語被當成不分語別，辭典永遠
        # 不當權威，錯得悄悄的。
        with self.assertRaises(PipelineError) as caught:
            paths.dictionary_variety("鄒")
        self.assertIn("鄒", str(caught.exception))


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
