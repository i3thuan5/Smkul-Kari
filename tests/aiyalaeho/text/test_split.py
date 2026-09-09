"""多重分隔符的切法：出工作表、收 Claude 的回覆、整批驗證後匯入。

照 `scripts/asrmt/judge.py` 立好的規矩：Claude 的產出以檔案交回、程式
驗證後匯入，整批接受或整批拒收，鍵是內容不是行號。
"""
import os
import tempfile
import unittest

from scripts.aiyalaeho.text import split
from scripts.errors import PipelineError


def _write_utf8(path, text):
    # decode.py 的規則：無 BOM 的 .txt 一律當 Big5——這批語料實測沒有
    # 無 BOM 的 UTF-8 檔。fixture 要照這個真實規則寫，不能圖方便寫純
    # UTF-8，不然會被 decode.py 正確地拒收。
    with open(path, "w", encoding="utf-8-sig") as f:
        f.write(text)


class TestFindProblemLines(unittest.TestCase):
    def test_finds_multi_separator_lines_across_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_utf8(os.path.join(tmp, "a.txt"),
                        "族語//華語\n族語A//族語B//華語A\n")
            problems = split.find_problem_lines(tmp)
        self.assertEqual(len(problems), 1)
        rel, line_no, content = problems[0]
        self.assertEqual(rel, "a.txt")
        self.assertEqual(line_no, 2)
        self.assertEqual(content, "族語A//族語B//華語A")

    def test_strips_timecode_prefix_before_checking_separators(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_utf8(os.path.join(tmp, "a.txt"),
                        "00:00:14;15 00:00:17;09 族語A\\\\族語B\\\\華語A\n")
            problems = split.find_problem_lines(tmp)
        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0][2], "族語A\\\\族語B\\\\華語A")

    def test_single_separator_lines_are_not_problems(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_utf8(os.path.join(tmp, "a.txt"), "族語//華語\n")
            problems = split.find_problem_lines(tmp)
        self.assertEqual(problems, [])


class TestWorksheet(unittest.TestCase):
    def test_worksheet_deduplicates_identical_content(self):
        problems = [
            ("a.txt", 1, "族語A//族語B//華語A"),
            ("b.txt", 5, "族語A//族語B//華語A"),
            ("c.txt", 9, "另一句//另一句//另一句華語"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "worksheet.tsv")
            split.write_worksheet(problems, path)
            with open(path, encoding="utf-8") as f:
                lines = [ln for ln in f if ln.strip()]
        self.assertEqual(len(lines), 2)


class TestIngestReply(unittest.TestCase):
    """整批接受或整批拒收：這是這一步唯一的把關，一步錯全部重來。"""

    def _worksheet(self, tmp, contents):
        path = os.path.join(tmp, "worksheet.tsv")
        problems = [("a.txt", i + 1, c) for i, c in enumerate(contents)]
        split.write_worksheet(problems, path)
        return path

    def test_a_single_pair_answer_reconstructs_the_original_line(self):
        content = "imi ni ga pagluw ta//kumaal ci yogi na alang//" \
                 '"聚在一起討論重要事務"的意思'
        with tempfile.TemporaryDirectory() as tmp:
            worksheet = self._worksheet(tmp, [content])
            reply = os.path.join(tmp, "reply.tsv")
            with open(reply, "w", encoding="utf-8") as f:
                f.write("1\timi ni ga pagluw ta//kumaal ci yogi na alang\t"
                        '"聚在一起討論重要事務"的意思\n')
            table = split.ingest_reply(worksheet, reply)
        self.assertEqual(
            table[content],
            [("imi ni ga pagluw ta//kumaal ci yogi na alang",
             '"聚在一起討論重要事務"的意思')])

    def test_a_two_pair_answer_for_a_genuinely_glued_line(self):
        content = ("na semalji a'en uta//我也很好奇uri 'ivadaq a'en ta "
                   "aicu ti ina audra ui//想問問秋梅長老")
        with tempfile.TemporaryDirectory() as tmp:
            worksheet = self._worksheet(tmp, [content])
            reply = os.path.join(tmp, "reply.tsv")
            with open(reply, "w", encoding="utf-8") as f:
                f.write("1\tna semalji a'en uta\t我也很好奇\n")
                f.write("1\turi 'ivadaq a'en ta aicu ti ina audra ui\t"
                        "想問問秋梅長老\n")
            table = split.ingest_reply(worksheet, reply)
        self.assertEqual(len(table[content]), 2)
        self.assertEqual(table[content][0],
                         ("na semalji a'en uta", "我也很好奇"))
        self.assertEqual(
            table[content][1],
            ("uri 'ivadaq a'en ta aicu ti ina audra ui", "想問問秋梅長老"))

    def test_answer_that_does_not_reconstruct_the_original_is_rejected(self):
        content = "族語A//族語B//華語A"
        with tempfile.TemporaryDirectory() as tmp:
            worksheet = self._worksheet(tmp, [content])
            reply = os.path.join(tmp, "reply.tsv")
            with open(reply, "w", encoding="utf-8") as f:
                # 漏了「族語B」——接回去不等於原句
                f.write("1\t族語A\t華語A\n")
            with self.assertRaises(PipelineError):
                split.ingest_reply(worksheet, reply)

    def test_a_missing_id_rejects_the_whole_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            worksheet = self._worksheet(tmp, ["族語A//族語B//華語A",
                                              "族語C//族語D//華語C"])
            reply = os.path.join(tmp, "reply.tsv")
            with open(reply, "w", encoding="utf-8") as f:
                f.write("1\t族語A//族語B\t華語A\n")
                # id 2 沒有回覆
            with self.assertRaises(PipelineError):
                split.ingest_reply(worksheet, reply)

    def test_an_id_not_in_the_worksheet_rejects_the_whole_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            worksheet = self._worksheet(tmp, ["族語A//族語B//華語A"])
            reply = os.path.join(tmp, "reply.tsv")
            with open(reply, "w", encoding="utf-8") as f:
                f.write("1\t族語A//族語B\t華語A\n")
                f.write("2\t亂入\t亂入\n")
            with self.assertRaises(PipelineError):
                split.ingest_reply(worksheet, reply)

    def test_whitespace_around_the_boundary_does_not_fail_reconstruction(self):
        # 切法要求邊界上的空白被 trim 掉，不能因為這樣就打回票——原句
        # 裡分隔符旁邊常常就有多餘空白。
        content = "族語A //族語B// 華語A "
        with tempfile.TemporaryDirectory() as tmp:
            worksheet = self._worksheet(tmp, [content])
            reply = os.path.join(tmp, "reply.tsv")
            with open(reply, "w", encoding="utf-8") as f:
                f.write("1\t族語A//族語B\t華語A\n")
            table = split.ingest_reply(worksheet, reply)
        self.assertEqual(table[content], [("族語A//族語B", "華語A")])

    def test_odd_length_separator_run_does_not_leave_a_false_mismatch(self):
        # 真實資料裡有幾行是「純分隔符占位」，長度是奇數（例如 11 個
        # `/`）——拿掉「成對」的分隔符會留一個殘餘字元，兩邊留的位置
        # 不一定一樣，會製造假的不符。整個拿掉組成分隔符的字元才對。
        content = "///////////"
        with tempfile.TemporaryDirectory() as tmp:
            worksheet = self._worksheet(tmp, [content])
            reply = os.path.join(tmp, "reply.tsv")
            with open(reply, "w", encoding="utf-8") as f:
                f.write("1\t\t\n")
            table = split.ingest_reply(worksheet, reply)
        self.assertEqual(table[content], [("", "")])

    def test_one_reply_row_is_rejected_when_a_partial_batch_exists(self):
        # 半批接受會把切法安到別的句子上——一步錯全部重來，不是「這條
        # 錯了就跳過這條」。
        with tempfile.TemporaryDirectory() as tmp:
            worksheet = self._worksheet(tmp, ["族語A//族語B//華語A",
                                              "族語C//族語D//華語C"])
            reply = os.path.join(tmp, "reply.tsv")
            with open(reply, "w", encoding="utf-8") as f:
                f.write("1\t族語A//族語B\t華語A\n")
                f.write("2\t錯誤答案\t錯誤答案\n")  # 接不回原句
            with self.assertRaises(PipelineError):
                split.ingest_reply(worksheet, reply)


class TestWriteSplitTableCsv(unittest.TestCase):
    def test_re_expands_deduplicated_content_back_to_every_occurrence(self):
        content = "族語A//族語B//華語A"
        problems = [("a.txt", 1, content), ("b.txt", 5, content)]
        table = {content: [("族語A//族語B", "華語A")]}
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "多重分隔符切法.csv")
            split.write_split_table_csv(problems, table, path)
            with open(path, encoding="utf-8") as f:
                lines = f.read().splitlines()
        self.assertEqual(lines[0], "來源檔,原句,族語,華語")
        self.assertEqual(len(lines), 3)  # header + 2 個來源檔各一列

    def test_a_two_pair_result_becomes_two_rows_for_that_source(self):
        content = ("na semalji a'en uta//我也很好奇uri 'ivadaq a'en ta "
                   "aicu ti ina audra ui//想問問秋梅長老")
        problems = [("a.txt", 8, content)]
        table = {
            content: [
                ("na semalji a'en uta", "我也很好奇"),
                ("uri 'ivadaq a'en ta aicu ti ina audra ui", "想問問秋梅長老"),
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "多重分隔符切法.csv")
            split.write_split_table_csv(problems, table, path)
            with open(path, encoding="utf-8") as f:
                lines = f.read().splitlines()
        self.assertEqual(len(lines), 3)  # header + 2 列
        self.assertNotIn("序", lines[0])


class TestReadSplitTableCsv(unittest.TestCase):
    """`pairs.py`要把這份 CSV 讀回 `{原句: [(族語,華語), ...]}`，餵給
    `parse.parse_lines()` 的 `split_table` 參數——寫出來再讀回去要
    一致，這樣 `多重分隔符切法.csv` 才是可信的正本。
    """

    def test_round_trips_through_write_and_read(self):
        content1 = "族語A//族語B//華語A"
        content2 = ("na semalji a'en uta//我也很好奇uri 'ivadaq a'en ta "
                    "aicu ti ina audra ui//想問問秋梅長老")
        problems = [("a.txt", 1, content1), ("b.txt", 5, content1),
                    ("c.txt", 8, content2)]
        table = {
            content1: [("族語A//族語B", "華語A")],
            content2: [
                ("na semalji a'en uta", "我也很好奇"),
                ("uri 'ivadaq a'en ta aicu ti ina audra ui", "想問問秋梅長老"),
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "多重分隔符切法.csv")
            split.write_split_table_csv(problems, table, path)
            loaded = split.read_split_table_csv(path)
        self.assertEqual(loaded[content1], [("族語A//族語B", "華語A")])
        self.assertEqual(loaded[content2], table[content2])


if __name__ == "__main__":
    unittest.main()
