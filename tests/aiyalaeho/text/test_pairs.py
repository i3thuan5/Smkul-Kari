"""掃過暫存目錄，組出 `Kari-SRT/aiyalaeho/text/1-句對.csv`。

集‧來源檔‧語言別代號的邏輯已經各自有測試（`test_lang.py`、
`test_decode.py`、`test_parse.py`），這裡只測 `pairs.py` 自己的事：
怎麼把它們串起來成一份 CSV，逐檔照收、順序固定、CSV 本身的格式安全。
"""
import csv
import os
import tempfile
import unittest

from scripts.aiyalaeho.text import pairs
from scripts.errors import PipelineError


def _write_big5(root, folder, name, text):
    path = os.path.join(root, folder, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(text.encode("cp950"))
    return path


class TestColumnsAndOrder(unittest.TestCase):
    def test_fifteen_columns_in_order(self):
        """頭七欄佮其他五張表同名同序，任兩張都 join 會起來。"""
        with tempfile.TemporaryDirectory() as tmp:
            _write_big5(tmp, "開會001_賽夏族", "a.txt", "族語//華語\n")
            rows = pairs.build_rows(tmp, split_table={})
        self.assertEqual(
            list(rows[0].keys()),
            ["成果檔名", "節目名稱", "集數", "族語別(英)", "族語別(中)",
             "語言別", "語言別代號", "來源文字檔檔案位置",
             "來源文字檔編碼格式", "行號", "類型", "族語", "華語",
             "開始時間", "結束時間"])

    def test_the_episode_string_is_split_into_a_number(self):
        """`集` 彼欄本底囥規串，拆做 `集數`。

        兩款分隔符攏愛食：`開會001_賽夏族`（下橫）佮
        `開會041-旅北阿美`（連字號）。
        """
        with tempfile.TemporaryDirectory() as tmp:
            _write_big5(tmp, "開會041-旅北阿美", "a.txt", "族語//華語\n")
            rows = pairs.build_rows(tmp, split_table={})
        self.assertEqual(rows[0]["集數"], "41")
        self.assertEqual(rows[0]["成果檔名"], "開會了_041_Amis_阿美")

    def test_the_tail_survives_in_the_source_path(self):
        """尾溜彼段（主題字樣）無另外囥欄位——路徑前綴本底就有。

        驗過 55785 逝：`來源文字檔檔案位置` ê前綴等於本底ê `集`，
        零例外。所以拆做 `集數` 無漏掉物件。
        """
        with tempfile.TemporaryDirectory() as tmp:
            _write_big5(tmp, "開會045-布農族挖礦", "a.txt", "族語//華語\n")
            rows = pairs.build_rows(tmp, split_table={})
        self.assertTrue(
            rows[0]["來源文字檔檔案位置"].startswith("開會045-布農族挖礦/"))

    def test_language_code_is_resolved_once_per_episode(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_big5(tmp, "開會002_布農族", "a.txt", "族語//華語\n")
            rows = pairs.build_rows(tmp, split_table={})
        self.assertEqual(rows[0]["語言別代號"], "bnn")
        self.assertEqual(rows[0]["集數"], "2")


class TestNoDeduplication(unittest.TestCase):
    def test_identical_content_in_two_files_both_appear(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_big5(tmp, "開會001_賽夏族", "a.txt", "族語//華語\n")
            _write_big5(tmp, "開會001_賽夏族", "b.txt", "族語//華語\n")
            rows = pairs.build_rows(tmp, split_table={})
        self.assertEqual(len(rows), 2)
        sources = {r["來源文字檔檔案位置"] for r in rows}
        self.assertEqual(sources,
                         {os.path.join("開會001_賽夏族", "a.txt"),
                          os.path.join("開會001_賽夏族", "b.txt")})


class TestTraceability(unittest.TestCase):
    def test_source_file_is_relative_to_the_corpus_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_big5(tmp, "開會001_賽夏族", "a.txt", "族語//華語\n")
            rows = pairs.build_rows(tmp, split_table={})
        self.assertEqual(rows[0]["來源文字檔檔案位置"],
                         os.path.join("開會001_賽夏族", "a.txt"))

    def test_line_number_matches_the_source_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_big5(tmp, "開會001_賽夏族", "a.txt",
                        "第一句//第一句華語\n\n第三句//第三句華語\n")
            rows = pairs.build_rows(tmp, split_table={})
        self.assertEqual(rows[0]["行號"], 1)
        self.assertEqual(rows[1]["行號"], 3)


class TestOrdering(unittest.TestCase):
    def test_sorted_by_episode_then_file_then_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_big5(tmp, "開會002_布農族", "b.txt", "b1//b1華\nb2//b2華\n")
            _write_big5(tmp, "開會001_賽夏族", "a.txt", "a1//a1華\n")
            rows = pairs.build_rows(tmp, split_table={})
        got = [(r["成果檔名"], r["來源文字檔檔案位置"], r["行號"]) for r in rows]
        self.assertEqual(got, sorted(got))

    def test_rerunning_on_the_same_source_is_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_big5(tmp, "開會001_賽夏族", "a.txt", "族語//華語\n")
            with tempfile.TemporaryDirectory() as outdir:
                path1 = os.path.join(outdir, "1.csv")
                path2 = os.path.join(outdir, "2.csv")
                pairs.write_csv(pairs.build_rows(tmp, split_table={}), path1)
                pairs.write_csv(pairs.build_rows(tmp, split_table={}), path2)
                with open(path1, "rb") as f1, open(path2, "rb") as f2:
                    self.assertEqual(f1.read(), f2.read())


class TestCsvSafety(unittest.TestCase):
    def test_tabs_become_spaces(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_big5(tmp, "開會001_賽夏族", "a.txt", "族語\t尾//華語\n")
            rows = pairs.build_rows(tmp, split_table={})
        self.assertNotIn("\t", rows[0]["族語"])
        self.assertIn(" ", rows[0]["族語"])

    def test_commas_and_quotes_survive_a_write_read_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_big5(tmp, "開會001_賽夏族", "a.txt",
                        '有,逗號和"引號"的句子//對應的華語,也有,逗號\n')
            rows = pairs.build_rows(tmp, split_table={})
            with tempfile.TemporaryDirectory() as outdir:
                path = os.path.join(outdir, "out.csv")
                pairs.write_csv(rows, path)
                with open(path, encoding="utf-8", newline="") as handle:
                    back = list(csv.DictReader(handle))
        self.assertEqual(back[0]["族語"], '有,逗號和"引號"的句子')
        self.assertEqual(back[0]["華語"], "對應的華語,也有,逗號")


class TestTypeEnumeration(unittest.TestCase):
    LEGAL_TYPES = {
        "雙語", "雙語（多重分隔符，AI切割）", "雙語（多重分隔符，規則切割）",
        "隔行配對", "僅族語", "僅華語", "混合", "註記",
    }

    def test_only_legal_type_values_appear(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_big5(tmp, "開會001_賽夏族", "a.txt",
                        "OS1\n族語//華語\n羅馬字行\n漢字行\n")
            rows = pairs.build_rows(tmp, split_table={})
        for row in rows:
            self.assertIn(row["類型"], self.LEGAL_TYPES)


class TestFailsWhole(unittest.TestCase):
    def test_one_undecodable_file_aborts_the_whole_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_big5(tmp, "開會001_賽夏族", "good.txt", "族語//華語\n")
            path = os.path.join(tmp, "開會001_賽夏族", "bad.docx")
            with open(path, "wb") as handle:
                handle.write(b"not a docx at all")
            with self.assertRaises(PipelineError):
                pairs.build_rows(tmp, split_table={})


if __name__ == "__main__":
    unittest.main()
