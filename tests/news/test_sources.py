"""sources: 一集配一支檔的規則，佮「揀袂出來就跳過」。

目錄的「影片檔案位置」欄是**候選清單**，毋是識別碼：仝一逝會使用分號
列幾若條（母帶佮轉檔、抑是編目時無把握的幾个檔名）。無政策就提第一條，
會用「午間」彼支影片去做「晚間」這集——整集字幕走位，而且無人會報錯。

fixture 攏是照真實目錄合成的，數字對會著 `ilrdf-corpus.csv`。
"""
import unittest

from scripts.news import sources

CORPUS = "ilrdf-corpus/族語新聞/110.1-110.10/"
CORPUS_111 = "ilrdf-corpus/族語新聞/111.1-111.5/"


def row(slot, paths, **over):
    entry = {"年度": "2021", "集數": "37", "播出日期": "2021-02-06",
             "播出時段": slot, "族語別(英)": "Paiwan", "族語別(中)": "排灣",
             "有無影片": "是" if paths else "否",
             "影片檔案位置": ";".join(paths)}
    entry.update(over)
    return entry


class TestCandidates(unittest.TestCase):
    """分號並列的來源，逐條都愛揣會著。

    這是回歸測試：舊的 `resolve_slug.load()` 對整串取 basename，一逝
    `a.mxf;b.mp4` 只索引著 `b.mp4`，全語料有 78 个檔名按呢查無——查無就
    退去檔名 stem，slug 佮 metadata 攏空，而且袂報錯。
    """

    def test_every_path_in_a_semicolon_list_is_a_candidate(self):
        paths = [CORPUS + "2月原始mxf檔/21NL004_37晚間族語新聞.mxf",
                 CORPUS + "7月/21NL004_37晚間族語新聞.mp4"]
        self.assertEqual(sources.candidates(row("晚間", paths)), paths)

    def test_a_four_way_list_keeps_all_four(self):
        paths = [CORPUS + "2月原始mxf檔/21NL004_37午間族語新聞.mxf",
                 CORPUS + "2月原始mxf檔/21NL004_37晚間族語新聞.mxf",
                 CORPUS + "7月/21NL004_37午間族語新聞.mp4",
                 CORPUS + "7月/21NL004_37晚間族語新聞.mp4"]
        self.assertEqual(sources.candidates(row("晚間", paths)), paths)

    def test_blank_and_whitespace_yield_nothing(self):
        self.assertEqual(sources.candidates(row("午間", [])), [])
        self.assertEqual(sources.candidates(row("午間", [" ", ""])), [])


class TestPick(unittest.TestCase):
    """逐集的規則：母帶優先 → 時段相符 → 同名不同資料夾算仝一份。"""

    def test_master_wins_over_the_transcode(self):
        mxf = CORPUS + "2月原始mxf檔/21NL004_37晚間族語新聞.mxf"
        mp4 = CORPUS + "7月/21NL004_37晚間族語新聞.mp4"
        path, problem = sources.pick(row("晚間", [mxf, mp4]))
        self.assertEqual(path, mxf)
        self.assertEqual(problem, "")

    def test_the_slot_in_the_file_name_breaks_the_tie(self):
        # 2021-02-06 晚間 排灣 佇目錄列四條，其中兩條檔名寫「午間」。
        # 提第一條就是用午間彼支影片做晚間這集。
        paths = [CORPUS + "2月原始mxf檔/21NL004_37午間族語新聞.mxf",
                 CORPUS + "2月原始mxf檔/21NL004_37晚間族語新聞.mxf",
                 CORPUS + "7月/21NL004_37午間族語新聞.mp4",
                 CORPUS + "7月/21NL004_37晚間族語新聞.mp4"]
        path, problem = sources.pick(row("晚間", paths))
        self.assertEqual(path, paths[1])
        self.assertEqual(problem, "")

    def test_an_unreadable_slot_word_is_not_read_as_another_slot(self):
        # 「五間」是「午間」拍毋著。若kā伊當做某一个時段，這集就會去
        # 配著別集的檔。無時段資訊就是無時段資訊。
        typo = CORPUS + "3月/21NL003_80五間族語新聞.mp4"
        self.assertIsNone(sources.slot_of(typo))
        path, problem = sources.pick(row("午間", [typo]))
        self.assertEqual(path, typo)
        self.assertEqual(problem, "")

    def test_the_same_name_in_two_folders_is_one_source(self):
        # 111 年彼批：仝一个檔名囥兩个資料夾，內容仝款，任揀一條。
        a = CORPUS_111 + "1月/22NL005_001晨間族語新聞.mp4"
        b = CORPUS_111 + "2月/22NL005_001晨間族語新聞.mp4"
        path, problem = sources.pick(row("晨間", [a, b]))
        self.assertIn(path, (a, b))
        self.assertEqual(problem, "")

    def test_no_source_at_all_is_not_a_thing_to_judge(self):
        path, problem = sources.pick(row("晚間", []))
        self.assertIsNone(path)
        self.assertIs(problem, sources.NO_SOURCE)


class TestUndecidable(unittest.TestCase):
    """賰兩條以上就是揀袂出來——毋通提第一條，嘛毋通擲例外。"""

    PATHS = ["ilrdf-corpus/族語新聞/110.1-110.10/6月/21NL003_167晚間族語新聞.mp4",
             "ilrdf-corpus/族語新聞/110.1-110.10/6月/21NL004_167晚間族語新聞.mp4"]

    def test_two_different_names_left_over_cannot_be_decided(self):
        path, problem = sources.pick(row("晚間", self.PATHS))
        self.assertIsNone(path)
        self.assertTrue(problem)
        self.assertIsNot(problem, sources.NO_SOURCE)

    def test_the_report_carries_the_candidates(self):
        _, problem = sources.pick(row("晚間", self.PATHS))
        for path in self.PATHS:
            self.assertIn(path, problem)

    def test_it_reports_rather_than_raising(self):
        try:
            sources.pick(row("晚間", self.PATHS))
        except Exception as exc:                       # noqa: BLE001
            self.fail("揀袂出來應該回報，毋是擲例外：%r" % exc)


class TestOneFileOneEpisode(unittest.TestCase):
    """一支檔干焦准一集用。

    目錄有三組兩集指著仝一支（攏佇 2021-03，編目拍毋著）。若逐集家己
    判，代先處理著彼集kā檔提去、後彼集才報錯——誰先誰後決定誰提著，
    這是重現袂出來的行為。所以撞檔愛看過歸批才判。
    """

    SHARED = CORPUS + "3月/21NL003_80五間族語新聞.mp4"

    def _rows(self):
        # 2021-03-21 午間 拉阿魯哇 佮 卡那卡那富，兩逝指著仝一支檔
        return [row("午間", [self.SHARED], 集數="80",
                    播出日期="2021-03-21"),
                row("午間", [self.SHARED], 集數="80",
                    播出日期="2021-03-21")]

    def test_neither_episode_gets_the_file(self):
        got = sources.resolve(self._rows())
        for path, problem in got:
            self.assertIsNone(path)
            self.assertIn("兩集以上", problem)

    def test_the_verdict_does_not_depend_on_order(self):
        rows = self._rows()
        for order in (rows, list(reversed(rows))):
            for path, _ in sources.resolve(order):
                self.assertIsNone(path)

    def test_results_line_up_with_the_rows_given(self):
        clean = row("晚間", [CORPUS + "7月/21NL004_44晚間族語新聞.mp4"],
                    集數="44", 播出日期="2021-02-13")
        rows = self._rows() + [clean]
        got = sources.resolve(rows)
        self.assertEqual(len(got), 3)
        self.assertIsNone(got[0][0])
        self.assertIsNone(got[1][0])
        self.assertEqual(got[2][0], CORPUS + "7月/21NL004_44晚間族語新聞.mp4")

    def test_an_episode_with_no_source_is_left_as_no_source(self):
        got = sources.resolve([row("晚間", [])])
        self.assertIs(got[0][1], sources.NO_SOURCE)


class TestReadingCopy(unittest.TestCase):
    """讀字幕愛用**壓縮過**ê彼份，毋是母帶。

    使用者裁定：來源順序對 `mxf => mp4` 改做 `mkv => mxf => mp4`。

    因為 pipeline 家己有kā母帶封存做 mkv（CRF 23、1920x1080、逐支驗過
    位元組數），一支才 2 GB，母帶 19 GB。欲讀ê若干焦是字幕帶ê像素，
    mkv 就有夠——實測 20210222_053 cue 201 彼句藏起來ê「保障孩子安全」，
    對 mkv 抽出來佮對 mxf 抽出來仝款清楚。

    差 10 倍：欲回頭補查 2 月 35 集，用母帶著 665 GB，用 mkv 是 0（已經
    佇本機）。

    這支函式**無 I/O**（sources.py 規矩）：有無 mkv 由呼叫端講。
    """

    def test_the_archived_mkv_wins_over_the_master(self):
        paths = [CORPUS + "2月原始mxf檔/21NL004_37晚間族語新聞.mxf",
                 CORPUS + "7月/21NL004_37晚間族語新聞.mp4"]
        got = sources.reading_copy(row("晚間", paths), "/mkv/037晚.mkv")
        self.assertEqual(got, "/mkv/037晚.mkv")

    def test_no_mkv_falls_back_to_the_master(self):
        paths = [CORPUS + "2月原始mxf檔/21NL004_37晚間族語新聞.mxf",
                 CORPUS + "7月/21NL004_37晚間族語新聞.mp4"]
        got = sources.reading_copy(row("晚間", paths), None)
        self.assertTrue(got.endswith(".mxf"), got)

    def test_no_mkv_no_master_falls_back_to_the_mp4(self):
        paths = [CORPUS + "7月/21NL004_37晚間族語新聞.mp4"]
        got = sources.reading_copy(row("晚間", paths), None)
        self.assertTrue(got.endswith(".mp4"), got)

    def test_the_slot_rules_still_apply_to_the_fallback(self):
        # mkv 無ê時，賰ê愛照原本四條規則揀，袂使提著午間彼支
        paths = [CORPUS + "2月原始mxf檔/21NL004_37午間族語新聞.mxf",
                 CORPUS + "2月原始mxf檔/21NL004_37晚間族語新聞.mxf"]
        got = sources.reading_copy(row("晚間", paths), None)
        self.assertIn("晚間", got)

    def test_an_episode_with_no_source_at_all_answers_like_pick(self):
        # 無來源ê時，照 `pick()` 本底ê講法（None），莫家己閣發明一種
        blank = row("晚間", [])
        self.assertEqual(sources.reading_copy(blank, None),
                         sources.pick(blank)[0])
        self.assertFalse(sources.reading_copy(blank, None))

    def test_an_empty_string_counts_as_no_mkv(self):
        paths = [CORPUS + "2月原始mxf檔/21NL004_37晚間族語新聞.mxf"]
        got = sources.reading_copy(row("晚間", paths), "")
        self.assertTrue(got.endswith(".mxf"), got)


if __name__ == "__main__":
    unittest.main()
