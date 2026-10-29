"""modeleval.pairs：開會了 OCR 字幕當標準答案，讀成評測用的句對。

全部合成 fixture；只有語別碼保底表讀 repo 內底的
`scripts/news/新聞語言別代號.csv`（綴 repo 走，毋是大檔）。
"""
import csv
import os
import tempfile
import unittest

from scripts.modeleval import pairs
from scripts.errors import PipelineError

FIELDS = [
    "成果檔名", "節目名稱", "集數", "族語別(英)", "族語別(中)", "語言別",
    "語言別代號", "字幕編號", "開始時間", "結束時間", "這列的語言",
    "疑似語言", "疑似語言詞庫比對命中率", "族語列", "華語列"]


def row(name, family, code, index, start, end, label, formosan, han):
    return {
        "成果檔名": name, "節目名稱": "開會了", "集數": "1",
        "族語別(英)": "Amis" if family == "阿美" else "Atayal",
        "族語別(中)": family, "語言別": "", "語言別代號": code,
        "字幕編號": str(index), "開始時間": start, "結束時間": end,
        "這列的語言": label, "疑似語言": "", "疑似語言詞庫比對命中率": "",
        "族語列": formosan, "華語列": han}


class TestLoad(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self._tmp.name, "labels.csv")
        rows = [
            row("開會了_068_Amis_阿美", "阿美", "ami-x-skl", 1,
                "00:00:13,960", "00:00:20,200", "純族語",
                "Nga'ay ho^", "大家好"),
            row("開會了_068_Amis_阿美", "阿美", "ami-x-skl", 2,
                "00:01:02,050", "00:01:04,000", "華語", "", "我是主持人"),
            row("開會了_085_Atayal_泰雅", "泰雅", "tay", 1,
                "00:00:01,000", "00:00:02,000", "純族語", "lokah su", "你好"),
        ]
        with open(self.path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, FIELDS)
            writer.writeheader()
            for item in rows:
                writer.writerow(item)

    def tearDown(self):
        self._tmp.cleanup()

    def test_only_the_asked_family_and_srt_comma_times_become_seconds(self):
        """SRT 時間用逗號分毫秒（00:01:02,050），當做小數點會差 1000 倍。"""
        got = pairs.load(self.path, family="阿美")
        self.assertEqual(len(got), 2)
        self.assertEqual(got[0]["srt_name"], "開會了_068_Amis_阿美")
        self.assertAlmostEqual(got[0]["start"], 13.96)
        self.assertAlmostEqual(got[1]["start"], 62.05)
        self.assertEqual(got[0]["formosan"], "Nga'ay ho^")
        self.assertEqual(got[1]["label"], "華語")

    def test_bom_header_still_reads(self):
        """正本 CSV 開頭有 BOM，第一欄名變做 '\\ufeff成果檔名' 就讀無。"""
        got = pairs.load(self.path, family="阿美")
        self.assertEqual(got[0]["srt_name"], "開會了_068_Amis_阿美")


class TestCodes(unittest.TestCase):
    def test_family_only_code_falls_back_to_the_news_default_variety(self):
        """smkul 只寫 `ami` 的集，sapolita 毋收 `ami`（選單只有五个
        語言別），愛照新聞線保底送海岸 `ami-x-pswl`。"""
        self.assertEqual(pairs.sapolita_code("開會了_082_Amis_阿美", "ami"),
                         "ami-x-pswl")

    def test_known_variety_is_sent_as_is(self):
        self.assertEqual(
            pairs.sapolita_code("開會了_068_Amis_阿美", "ami-x-skl"),
            "ami-x-skl")
        self.assertEqual(
            pairs.sapolita_code("開會了_112_Amis_阿美", "ami-x-iams"),
            "ami-x-iams")

    def test_mt_code_matches_the_same_variety_on_the_other_service(self):
        """兩个服務的語別碼無仝套：南勢在 sapolita 是 `ami-x-iams`，
        在翻譯服務是 `ami_Sout`（Sout 毋是「南部」，南部是恆春 ami_Heng）。
        2026-10-28 對兩爿下拉選單的標籤讀落來。"""
        self.assertEqual(pairs.mt_code("ami-x-iams"), "ami_Sout")
        self.assertEqual(pairs.mt_code("ami-x-skl"), "ami_Xiug")
        self.assertEqual(pairs.mt_code("ami-x-pswl"), "ami_Coas")
        self.assertEqual(pairs.mt_code("ami-x-frng"), "ami_Mala")
        self.assertEqual(pairs.mt_code("ami-x-pld"), "ami_Heng")

    def test_unknown_code_is_refused_not_guessed(self):
        """翻譯服務收著毋捌的碼袂報錯，會靜靜改用預設海岸翻——所以
        表內無的碼愛擋落來。"""
        with self.assertRaises(PipelineError):
            pairs.mt_code("ami")


class TestMTItems(unittest.TestCase):
    def test_both_rows_needed_and_repeats_sent_once(self):
        """一集內「Nga'ay ho^／大家好」出現好幾擺，服務只問一擺；
        族語列空的（受訪者講華語）毋送。"""
        rows = [
            {"srt_name": "a", "label": "純族語", "formosan": "Nga'ay ho^",
             "han": "大家好", "mt_code": "ami_Coas"},
            {"srt_name": "a", "label": "純族語", "formosan": "Nga'ay ho^",
             "han": "大家好", "mt_code": "ami_Coas"},
            {"srt_name": "a", "label": "華語", "formosan": "",
             "han": "我是主持人", "mt_code": "ami_Coas"},
        ]
        got = pairs.mt_items(rows)
        self.assertEqual(got, [
            ("f2z", "ami_Coas", "Nga'ay ho^"),
            ("z2f", "ami_Coas", "大家好"),
        ])


if __name__ == "__main__":
    unittest.main()
