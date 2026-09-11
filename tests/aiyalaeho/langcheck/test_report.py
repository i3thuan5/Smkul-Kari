"""兩張 CSV。

逐條表：非本集族語ê條目，一條一逝。逐集表：逐集ê計數，一集一逝。

會出代誌ê：五个計數欄相加無等於字幕條數（表家己講袂通）、
`smkul.csv` 有ê集佇分布表無出現（查袂動佮查過無代誌濫做伙）、
命中率去予當做會使跨集比（其實是方言別造成ê）。
"""
import csv
import io
import os
import tempfile
import textwrap
import unittest

from scripts.aiyalaeho.langcheck import report


AMIS = {"kako", "matini", "tangasa", "maafo", "patatiko", "kakialawan"}
BUNUN = {"halinga", "maitastutasa", "cina", "sain", "tupa"}
LEX = {"阿美": AMIS, "布農": BUNUN}


def srt(*blocks):
    return "\n\n".join(textwrap.dedent(b).strip() for b in blocks) + "\n"


EPISODE = srt("""
    1
    00:00:06,220 --> 00:00:09,560
    族語：
    華語：養蜂是另外一塊工作環境的
""", """
    2
    00:01:41,500 --> 00:01:45,020
    族語：Patatiko ho kita i kakialawan a 節目
    華語：我們再回到節目
""", """
    3
    00:03:10,000 --> 00:03:14,000
    族語：Tangasa to matini maafo to
    華語：直到到今天
""", """
    4
    00:04:00,000 --> 00:04:04,000
    族語：sain hai maitastutasa cina tupa
    華語：這是其中一個的
""")

OTHER = srt("""
    1
    00:00:01,000 --> 00:00:02,000
    族語：kako matini
    華語：我今天
""")


def episodes():
    return [
        report.Episode("開會了_082_Amis_阿美", "82", "阿美", "Amis", "",
                       "ami", EPISODE),
        report.Episode("開會了_068_Amis_阿美", "68", "阿美", "Amis", "秀姑巒",
                       "ami-x-skl", OTHER),
    ]


def cell(row, header, name):
    """一格：用**欄名**提，莫用位置——頭前加欄位就規組歪去。"""
    return row[header.index(name)]


def read(path):
    with open(path, encoding="utf-8", newline="") as handle:
        return list(csv.reader(handle))


class TestMarkTable(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="aiya-report-")
        self.path = os.path.join(self.folder, "逐條語言標記.csv")
        report.write_marks(self.path, episodes(), LEX)
        self.table = read(self.path)

    def at(self, row):
        """這一逝ê取格仔函式，用**欄名**提。"""
        return lambda name: cell(row, self.table[0], name)

    def test_the_fifteen_columns_in_order(self):
        """頭七欄佮其他五張表同名同序，任兩張都 join 會起來。

        `本集族語` 併入 `族語別(中)`——仝一件代誌兩个名，開兩張表
        對照ê時愛佇心內先翻一擺。
        """
        self.assertEqual(self.table[0], [
            "成果檔名", "節目名稱", "集數", "族語別(英)", "族語別(中)",
            "語言別", "語言別代號", "字幕編號", "開始時間", "結束時間",
            "這列的語言", "疑似語言", "疑似語言詞庫比對命中率",
            "族語列", "華語列"])
        self.assertNotIn("本集族語", self.table[0])

    def test_rows_sort_by_name_then_number(self):
        keys = []
        for row in self.table[1:]:
            keys.append((row[0], int(cell(row, self.table[0], "字幕編號"))))
        self.assertEqual(keys, sorted(keys))

    def test_every_entry_is_in_the_table(self):
        # 使用者裁定 2026-09-10：純族語嘛入表，一條都莫漏。
        self.assertEqual(len(self.table) - 1, 5)   # 4 條＋1 條

    def test_the_ordinary_case_is_there_too(self):
        labels = set()
        for row in self.table[1:]:
            labels.add(cell(row, self.table[0], "這列的語言"))
        self.assertIn("純族語", labels)

    def test_the_start_time_is_the_srt_stamp(self):
        for row in self.table[1:]:
            got = self.at(row)
            if not row[0].endswith("082_Amis_阿美"):
                continue
            if got("字幕編號") == "1":
                self.assertEqual(got("開始時間"), "00:00:06,220")
                self.assertEqual(got("結束時間"), "00:00:09,560")
                return
        self.fail("揣無彼逝")

    def test_the_formosan_row_is_copied_verbatim(self):
        for row in self.table[1:]:
            got = self.at(row)
            if got("字幕編號") == "2":
                self.assertEqual(got("族語列"),
                                 "Patatiko ho kita i kakialawan a 節目")
                return
        self.fail("揣無彼逝")

    def test_certain_labels_leave_the_guess_columns_empty(self):
        for row in self.table[1:]:
            got = self.at(row)
            label = got("這列的語言")
            if label != "無法確定":
                self.assertEqual(got("疑似語言"), "", label)
                self.assertEqual(got("疑似語言詞庫比對命中率"), "", label)

    def test_the_mixed_label_carries_no_tribe_name(self):
        for row in self.table[1:]:
            label = self.at(row)("這列的語言")
            if "夾" in label:
                self.assertEqual(label, "族語夾雜華語")

    def test_an_unsure_row_names_the_suspect_and_its_rate(self):
        for row in self.table[1:]:
            got = self.at(row)
            if got("這列的語言") == "無法確定":
                self.assertEqual(got("疑似語言"), "布農")
                rate = got("疑似語言詞庫比對命中率")
                self.assertTrue(rate.endswith("%"), rate)
                return
        self.fail("無半逝無法確定")

    def test_the_file_uses_unix_line_endings(self):
        with open(self.path, "rb") as handle:
            self.assertNotIn(b"\r", handle.read())


class TestDistributionTable(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="aiya-dist-")
        self.path = os.path.join(self.folder, "逐集語言分布.csv")
        report.write_distribution(self.path, episodes(), LEX)
        self.table = read(self.path)

    def test_the_twelve_columns_in_order(self):
        self.assertEqual(self.table[0], [
            "成果檔名", "節目名稱", "集數", "族語別(英)", "族語別(中)",
            "語言別", "語言別代號", "字幕條數", "純族語",
            "族語夾雜華語", "華語", "無法確定"])
        self.assertNotIn("本集族語", self.table[0])

    def test_every_episode_gets_a_row(self):
        names = []
        for row in self.table[1:]:
            names.append(row[0])
        self.assertEqual(sorted(names),
                         ["開會了_068_Amis_阿美", "開會了_082_Amis_阿美"])

    def test_the_four_counts_add_up_to_the_entry_count(self):
        for row in self.table[1:]:
            total = int(cell(row, self.table[0], "字幕條數"))
            counted = 0
            for name in ("純族語", "族語夾雜華語", "華語", "無法確定"):
                counted += int(cell(row, self.table[0], name))
            self.assertEqual(counted, total, row[0])

    def test_the_entry_count_matches_the_srt(self):
        for row in self.table[1:]:
            if row[0].endswith("082_Amis_阿美"):
                self.assertEqual(int(cell(row, self.table[0], "字幕條數")), 4)
                return
        self.fail("揣無彼逝")


class TestLoadingFromTheStore(unittest.TestCase):
    """對 smkul.csv 佮 3-srt/ 讀材料。單元測試若攏家己捏 Episode，
    這條路就一擺都無走過——伊斷去嘛無人知。"""

    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="aiya-load-")
        self.srt_dir = os.path.join(self.folder, "3-srt")
        os.makedirs(self.srt_dir)
        self.table = os.path.join(self.folder, "smkul.csv")
        with open(self.table, "w", encoding="utf-8-sig",
                  newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(["成果檔名", "節目名稱", "集數", "族語別(英)",
                             "族語別(中)", "語言別", "語言別代號",
                             "原始影片檔案位置", "備註"])
            writer.writerow(["開會了_082_Amis_阿美", "開會了", "82", "Amis",
                             "阿美", "", "ami", "x.mp4", ""])

    def write_srt(self, name, text):
        with open(os.path.join(self.srt_dir, name + ".srt"), "w",
                  encoding="utf-8") as handle:
            handle.write(text)

    def test_an_episode_comes_back_with_its_tribe_and_code(self):
        self.write_srt("開會了_082_Amis_阿美", EPISODE)
        got = report.load_episodes(self.table, self.srt_dir)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0].srt_name, "開會了_082_Amis_阿美")
        self.assertEqual(got[0].tribe, "阿美")
        self.assertEqual(got[0].english, "Amis")
        self.assertEqual(got[0].number, "82")
        self.assertEqual(got[0].code, "ami")
        self.assertIn("族語：", got[0].text)

    def test_a_missing_srt_is_named_not_skipped(self):
        with self.assertRaises(Exception) as caught:
            report.load_episodes(self.table, self.srt_dir)
        self.assertIn("開會了_082_Amis_阿美", str(caught.exception))


class TestLoadingLexicons(unittest.TestCase):
    def test_a_missing_lexicon_is_named(self):
        # 恬恬跳過ê話，彼一族ê集會規份判做「純族語」，看起來若無代誌。
        folder = tempfile.mkdtemp(prefix="aiya-lex-")
        with self.assertRaises(Exception) as caught:
            report.load_lexicons({"阿美"}, folder)
        self.assertIn("阿美", str(caught.exception))


class TestRateFormat(unittest.TestCase):
    def test_a_rate_reads_as_a_percentage(self):
        self.assertEqual(report.percent(0.8571), "86%")
        self.assertEqual(report.percent(1.0), "100%")
        self.assertEqual(report.percent(0.0), "0%")


class TestWritingIsStable(unittest.TestCase):
    def test_writing_twice_gives_the_same_bytes(self):
        folder = tempfile.mkdtemp(prefix="aiya-stable-")
        one = os.path.join(folder, "a.csv")
        two = os.path.join(folder, "b.csv")
        report.write_marks(one, episodes(), LEX)
        report.write_marks(two, episodes(), LEX)
        with open(one, "rb") as handle:
            first = handle.read()
        with open(two, "rb") as handle:
            second = handle.read()
        self.assertEqual(first, second)

    def test_the_body_is_what_the_writer_would_emit(self):
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(["a", "b"])
        self.assertEqual(buffer.getvalue(), "a,b\n")


if __name__ == "__main__":
    unittest.main()
