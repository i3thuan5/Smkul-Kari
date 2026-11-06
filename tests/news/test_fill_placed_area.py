"""fill_placed_area：補上既有 placed cue 缺的 area。

place_cue insert 原本不寫 area：286 晚 cue 846（島語時間金句卡）、210 晨
部落信箱 860／867／877 都是前後有 area、自己沒有；2026-11-03 全庫數到前後
（越過相連的 placed cue）同一個 area、自己卻沒有的 placed cue 有 1168 條
（93 集），補上的 area 和段落表該秒的類型全部一致。這支只補 placed 的——269 午
462 那種前後是島語時間、自己沒有 area 但不是插入的，是當初用頂層字幕帶
切出來的；area 說的是「用哪一個切法切的」，不可以跟著鄰居改。
"""
import fcntl
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

from scripts.news import fill_placed_area


def cue(index, area=None, placed=False, shift=0.0):
    item = {"index": index, "start": float(index) + shift,
            "end": index + 0.5 + shift}
    if area:
        item["area"] = area
    if placed:
        item["placed"] = True
    return item


class TestFill(unittest.TestCase):

    def test_a_placed_cue_between_one_area_gets_it(self):
        cues = [cue(1, "島語時間"), cue(2, placed=True), cue(3, "島語時間")]
        got, filled = fill_placed_area.fill(cues)
        self.assertEqual(filled, [(2, "島語時間")])
        self.assertEqual(got[1]["area"], "島語時間")
        self.assertNotIn("area", cues[1])          # 傳進來的那份不動

    def test_a_cut_cue_without_area_is_left_alone(self):
        # 269 午 462：前後是島語時間，但它是頂層字幕帶切的，不是插入的
        cues = [cue(1, "島語時間"), cue(2), cue(3, "島語時間")]
        self.assertEqual(fill_placed_area.fill(cues)[1], [])

    def test_a_placed_cue_on_an_area_boundary_is_left_alone(self):
        cues = [cue(1, "島語時間"), cue(2, placed=True), cue(3, "部落信箱")]
        self.assertEqual(fill_placed_area.fill(cues)[1], [])
        cues = [cue(1, "島語時間"), cue(2, placed=True), cue(3)]
        self.assertEqual(fill_placed_area.fill(cues)[1], [])

    def test_a_run_of_placed_cues_is_filled_together(self):
        cues = [cue(1, "部落信箱"), cue(2, placed=True), cue(3, placed=True),
                cue(4, "部落信箱")]
        self.assertEqual(fill_placed_area.fill(cues)[1],
                         [(2, "部落信箱"), (3, "部落信箱")])

    def test_first_and_last_cue_are_left_alone(self):
        cues = [cue(1, placed=True), cue(2, "島語時間"), cue(3, placed=True)]
        self.assertEqual(fill_placed_area.fill(cues)[1], [])


class TestPortedFromAPlacedCue(unittest.TestCase):
    """291 晚 1036、301 晚 1399 是移植工具從 286 晚 846（placed、沒有 area）
    照首播起迄搬過去的：重播那條沒有 placed，area 照首播的拿掉了，前後都是
    島語時間。只補 placed 的話這種全跳過（2026-11-03 全庫 45 條、28 集，
    292 午 875、320 晚 987、334 晚 880、360 晚 805、364 晚 715 都是）。
    認法：時間軸 `ported` 記了從哪一集、位移多少，扣掉位移後跟首播某條
    placed（或同樣是這樣搬來的）cue 起迄相同。範圍尾端重播自己的 cue
    （314 晚 872、364 晚 817、016 晚 645，frames 6、ink 340）起迄對不上
    首播，是重播用頂層字幕帶切的，照原則不動。"""

    def books(self):
        source = {"cues": [cue(1, "島語時間"), cue(2, placed=True),
                           cue(3, "島語時間")]}
        target = {"cues": [cue(1, "島語時間", shift=10.0),
                           cue(2, shift=10.0),
                           cue(3, "島語時間", shift=10.0),
                           cue(4, shift=10.2),
                           cue(5, "島語時間", shift=10.0)],
                  "ported": [{"from": "286", "offset": 10.0,
                              "range": [10.0, 15.0]}]}
        chained = {"cues": [cue(1, "島語時間", shift=30.0),
                            cue(2, shift=30.0),
                            cue(3, "島語時間", shift=30.0)],
                   "ported": [{"from": "291", "offset": 20.0,
                               "range": [30.0, 35.0]}]}
        return {"286": source, "291": target, "301": chained}

    def test_a_cue_ported_from_a_placed_cue_is_found(self):
        found = fill_placed_area.inherited(self.books())
        self.assertEqual(found["291"], {2})
        self.assertEqual(found["301"], {2})       # 從 291 再搬一次的也算
        self.assertEqual(found["286"], set())

    def test_it_is_filled_like_a_placed_cue(self):
        books = self.books()
        found = fill_placed_area.inherited(books)
        _got, filled = fill_placed_area.fill(books["291"]["cues"],
                                             inherited=found["291"])
        self.assertEqual(filled, [(2, "島語時間")])

    def test_the_replays_own_cue_at_the_edge_is_left_alone(self):
        # cue 4 起迄跟首播對不上（重播自己切的），前後雖然都是島語時間也不動
        books = self.books()
        found = fill_placed_area.inherited(books)
        self.assertNotIn(4, found["291"])
        _got, filled = fill_placed_area.fill(books["291"]["cues"],
                                             inherited=found["291"])
        self.assertNotIn(4, dict(filled))


def seg(start, end, kind):
    return {"起秒": str(start), "迄秒": str(end), "類型": kind}


class TestBoundaryBySegments(unittest.TestCase):
    """在區域邊上的 placed cue：一邊是島語時間、一邊是頂層字幕帶，只看鄰居
    判斷不出來，2026-11-03 全庫 83 條沒補（089 晚 68–70、171 晚 383–385、
    305 晚 375–381 開場歌詞、316 晨 363–364…）。段落表那一秒的類型就是
    鄰居那個 area、而且另一邊的鄰居在別的段落裡，才補（量到 76 條）；
    另一邊的鄰居也在同一段（364 晚 685、027 晨 1055、100 午 871）或段落
    表對不上（358 晨 1291–1292 段落表是「其他」）就不補，列出來要人看。"""

    def cues(self):
        return [cue(1), cue(2, placed=True), cue(3, placed=True),
                cue(4, "島語時間"), cue(5, "島語時間")]

    def test_the_segment_table_breaks_the_tie(self):
        rows = [seg(0, 1.9, "攝影棚"), seg(1.9, 10, "島語時間")]
        _got, filled = fill_placed_area.fill(self.cues(), rows=rows)
        self.assertEqual(filled, [(2, "島語時間"), (3, "島語時間")])

    def test_the_other_neighbour_in_the_same_segment_is_ambiguous(self):
        rows = [seg(0, 10, "島語時間")]
        self.assertEqual(fill_placed_area.fill(self.cues(), rows=rows)[1], [])

    def test_a_segment_of_another_kind_decides_nothing(self):
        rows = [seg(0, 1.9, "攝影棚"), seg(1.9, 10, "其他")]
        self.assertEqual(fill_placed_area.fill(self.cues(), rows=rows)[1], [])

    def test_what_is_left_is_listed(self):
        rows = [seg(0, 10, "島語時間")]
        self.assertEqual(fill_placed_area.left_out(self.cues(), rows=rows),
                         [(2, None, "島語時間"), (3, None, "島語時間")])


class TestMain(unittest.TestCase):
    """`--write` 同時寫 Kari-SRT 和 work dir 的時間軸，不拿 store.lock 會跟
    publish 撞在一起；寫完時間軸 sha 變了，還沒 apply 的 rebroadcast_port
    plan 都要重做 prepare，要講出來。"""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = os.path.join(tmp.name, "20231013_286_晚間_x.json")
        self.lock = os.path.join(tmp.name, "store.lock")
        book = {"cues": [cue(1, "島語時間"), cue(2, placed=True),
                         cue(3, "島語時間")]}
        with open(self.path, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(book, ensure_ascii=False, indent=2,
                                    sort_keys=True) + "\n")
        # 測試不讀真的 Kari-SRT（三千多份時間軸、段落表）
        for patch in (
                mock.patch.object(fill_placed_area, "_all_store_books",
                                  lambda: {}),
                mock.patch.object(fill_placed_area, "_segment_rows",
                                  lambda name: None)):
            patch.start()
            self.addCleanup(patch.stop)

    def run_main(self, argv):
        out = io.StringIO()
        with redirect_stdout(out):
            code = fill_placed_area.main(argv)
        return code, out.getvalue()

    def test_write_needs_the_lock(self):
        with self.assertRaises(SystemExit):
            with redirect_stdout(io.StringIO()):
                fill_placed_area.main(["--write", self.path])

    def test_write_holds_the_lock_and_says_what_it_invalidates(self):
        held = []
        real = fill_placed_area.fill_file

        def probe(*args, **kwargs):
            with open(self.lock, "a") as handle:
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    held.append(False)
                    fcntl.flock(handle, fcntl.LOCK_UN)
                except BlockingIOError:
                    held.append(True)
            return real(*args, **kwargs)

        with mock.patch.object(fill_placed_area, "fill_file", probe):
            code, text = self.run_main(["--write", "--lock", self.lock,
                                        self.path])
        self.assertEqual(code, 0)
        self.assertEqual(held, [True])
        self.assertIn("rebroadcast_port", text)
        self.assertIn("prepare", text)


class TestFillFile(unittest.TestCase):
    """寫回去要跟 Kari-SRT 的排版逐 byte 相同，只多出 area 那幾行。"""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = os.path.join(tmp.name, "x.json")
        self.book = {"cues": [cue(1, "島語時間"), cue(2, placed=True),
                              cue(3, "島語時間")], "duration": 9.0}

    def write(self, text):
        with open(self.path, "w", encoding="utf-8") as handle:
            handle.write(text)

    def read(self):
        with open(self.path, encoding="utf-8") as handle:
            return handle.read()

    def canonical(self, doc, newline):
        return json.dumps(doc, ensure_ascii=False, indent=2,
                          sort_keys=True) + ("\n" if newline else "")

    def test_dry_run_reports_and_writes_nothing(self):
        text = self.canonical(self.book, True)
        self.write(text)
        filled = fill_placed_area.fill_file(self.path, write=False)
        self.assertEqual(filled, [(2, "島語時間")])
        self.assertEqual(self.read(), text)

    def test_written_file_keeps_its_layout_and_trailing_newline(self):
        for newline in (True, False):
            self.write(self.canonical(self.book, newline))
            fill_placed_area.fill_file(self.path, write=True)
            want = json.loads(json.dumps(self.book))
            want["cues"][1]["area"] = "島語時間"
            self.assertEqual(self.read(), self.canonical(want, newline))

    def test_a_file_in_some_other_layout_is_not_rewritten(self):
        # 整份重排會改到別行，diff 看不出改了什麼；擋下來並指名是哪一份
        text = json.dumps(self.book)
        self.write(text)
        with self.assertRaises(fill_placed_area.PipelineError):
            fill_placed_area.fill_file(self.path, write=True)
        self.assertEqual(self.read(), text)


if __name__ == "__main__":
    unittest.main()
