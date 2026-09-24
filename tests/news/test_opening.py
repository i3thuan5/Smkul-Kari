"""opening：片頭 20／30／40 秒截圖，讀者讀語別牌佮主播，寫 `片頭辨識.csv`。

2026-09-23 核對新母帶 24 逝無合輪值規律ê，6 逝ê語別是標毋著ê，攏是
看片頭語別牌才揣著——檔名、清單攏袂講。所以逐集切 cue ê時就截片頭，
語別佮目錄無仝就停，毋等整集讀了才發現。
"""
import csv
import os
import subprocess
import tempfile
import unittest

from scripts.errors import PipelineError
from scripts.news import opening
from scripts.news import paths


def catalogue(path, rows):
    head = ["成果檔名", "節目名稱", "年度", "集數", "播出日期",
            "族語別(英)", "族語別(中)", "語言別", "語言別代號",
            "原始影片檔案位置", "備註"]
    with open(path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, head, lineterminator="\r\n")
        writer.writeheader()
        for name, chinese in rows:
            writer.writerow({"成果檔名": name, "族語別(中)": chinese})


def anchors(path, names):
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["族語別(中)", "主播族語名", "主播漢名", "語言別",
                         "語言別代號", "抽聽的集", "語別依據"])
        for chinese, name in names:
            writer.writerow([chinese, name, "", "", "", "", ""])


class Store(object):
    """合成ê目錄、主播表、片頭辨識表。"""

    SEDIQ = "20240608_160_午間_Paiwan_排灣"
    SAISIYAT = "20230628_179_晚間_SaySiyat_賽夏"
    THAU = "20241201_336_晨間_Thau_邵"

    def __init__(self, test):
        tmp = tempfile.TemporaryDirectory()
        test.addCleanup(tmp.cleanup)
        self.dir = tmp.name
        self.catalogue = os.path.join(tmp.name, "smkul.csv")
        self.anchors = os.path.join(tmp.name, "主播.csv")
        self.table = os.path.join(tmp.name, "片頭辨識.csv")
        catalogue(self.catalogue, [(self.SEDIQ, "排灣"),
                                   (self.SAISIYAT, "賽夏"),
                                   (self.THAU, "邵")])
        anchors(self.anchors, [("賽德克", "Awe Nawi"), ("邵", "Tanngi")])

    def tsv(self, lines):
        path = os.path.join(self.dir, "opening.tsv")
        with open(path, "w", encoding="utf-8") as handle:
            for line in lines:
                handle.write("\t".join(line) + "\n")
        return path

    def ingest(self, lines):
        return opening.ingest(self.tsv(lines), table=self.table,
                              catalogue=self.catalogue, anchors=self.anchors)

    def rows(self):
        with open(self.table, encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))


class TestGrab(unittest.TestCase):

    def test_three_frames_land_in_the_work_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            video = os.path.join(tmp, "v.mp4")
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
                            "-i", "testsrc=s=320x180:r=5:d=45",
                            "-c:v", "libx264", "-pix_fmt", "yuv420p", video],
                           check=True)
            work = os.path.join(tmp, "x.work")
            made = opening.grab(video, work)
            names = []
            for path in made:
                names.append(os.path.basename(path))
                self.assertTrue(os.path.getsize(path) > 0)
            self.assertEqual(names, ["20.png", "30.png", "40.png"])
            self.assertEqual(os.path.dirname(made[0]),
                             paths.opening_dir(work))


class TestSparseFetch(unittest.TestCase):
    """2021 年ê集數已經入庫，影片毋佇本機；整支抓（約 2.2 GB）干焦為三
    格傷了。mp4 ê索引（moov）佇檔尾，干焦抓頭前解袂開——頭 60 MB 佮
    尾 16 MB 寫入仝大細ê稀疏檔，20／30／40 秒就解會出來。
    """

    REMOTE = "/docker/ilrdf-corpus/族語新聞/110.1-110.10/3月/21NL003_80.mp4"

    def test_the_two_ranges_are_head_and_tail(self):
        size = 2200000000
        head, tail = opening.curl_commands(self.REMOTE, size)
        self.assertIn("0-62914559", head)
        self.assertIn("%d-" % (size - 16777216), tail)

    def test_the_password_comes_from_netrc(self):
        for cmd in opening.curl_commands(self.REMOTE, 2200000000):
            self.assertIn("--netrc", cmd)
            url = cmd[-1]
            self.assertTrue(url.startswith("sftp://"), url)
            self.assertNotIn("@", url.split("/")[2])

    def test_a_short_file_is_fetched_whole(self):
        head, tail = opening.curl_commands(self.REMOTE, 50000000)
        self.assertIn("0-49999999", head)
        self.assertIsNone(tail)

    def test_bytes_that_do_not_add_up_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "v.mp4")

            def fetch(cmd):
                return b"x" * 1000          # 伺服器干焦予 1000 byte

            with self.assertRaises(PipelineError) as caught:
                opening.sparse_copy(self.REMOTE, 80000000, target,
                                    fetch=fetch)
            self.assertIn("21NL003_80", str(caught.exception))

    def test_the_sparse_file_is_the_server_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "v.mp4")
            size = 80000000

            def fetch(cmd):
                span = cmd[cmd.index("-r") + 1]
                lo, _, hi = span.partition("-")
                hi = int(hi) if hi else size - 1
                return b"x" * (hi - int(lo) + 1)

            opening.sparse_copy(self.REMOTE, size, target, fetch=fetch)
            self.assertEqual(os.path.getsize(target), size)


class TestSheetCrop(unittest.TestCase):
    """組合圖逐格對 CROP_TOP 裁起，愛包著棚內主播名條。

    2021 棚內「主播 ○○」名條佇 y≈660–720。裁 700 起，名條賰下緣一截：
    邵語晨間 2021-06、08、09 十集 kurali Lhkashnawanan 讀袂出、主播欄留空，
    賽德克 Awe Nawi 勉強讀出。語別牌（y≈900）無受影響。
    """

    def test_the_anchor_name_bar_is_inside_the_crop(self):
        self.assertLessEqual(opening.CROP_TOP, 650)

    def test_the_sheet_is_still_a_crop_not_the_whole_frame(self):
        # 名條以上是主播半身佮棚景，讀者用袂著；提傷懸組合圖就變大。
        self.assertGreaterEqual(opening.CROP_TOP, 600)


class TestIngest(unittest.TestCase):

    def test_a_badge_that_disagrees_with_the_catalogue_stops(self):
        # `24NL003_160_Paiwan`：片頭是賽德克主播 Awe Nawi。
        store = Store(self)
        report = store.ingest([
            (Store.SEDIQ, "20", "賽德克", "Awe Nawi"),
            (Store.SEDIQ, "30", "賽德克", ""),
            (Store.SEDIQ, "40", "判不準", "")])
        self.assertEqual(len(report.mismatched), 1)
        name, listed, seen = report.mismatched[0]
        self.assertEqual((name, listed, seen), (Store.SEDIQ, "排灣", "賽德克"))
        row = store.rows()[0]
        self.assertEqual(row["與目錄相符"], "否")
        self.assertEqual(row["截圖秒數"], "20/30")
        self.assertEqual(opening.exit_code(report), 1)

    def test_three_unreadable_frames_are_not_a_match(self):
        store = Store(self)
        report = store.ingest([
            (Store.THAU, "20", "判不準", ""),
            (Store.THAU, "30", "判不準", ""),
            (Store.THAU, "40", "判不準", "")])
        row = store.rows()[0]
        self.assertEqual(row["畫面語別牌"], "判不準")
        self.assertEqual(row["與目錄相符"], "判不準")
        self.assertEqual(report.unreadable, [Store.THAU])
        self.assertEqual(opening.exit_code(report), 1)

    def test_a_new_anchor_is_reported_but_does_not_stop(self):
        store = Store(self)
        report = store.ingest([
            (Store.SAISIYAT, "20", "賽夏", "'okay a 'ataw hayawan"),
            (Store.SAISIYAT, "30", "賽夏", ""),
            (Store.SAISIYAT, "40", "賽夏", "")])
        self.assertEqual(report.new_anchors,
                         [(Store.SAISIYAT, "'okay a 'ataw hayawan")])
        self.assertEqual(report.mismatched, [])
        self.assertEqual(opening.exit_code(report), 0)
        self.assertEqual(store.rows()[0]["與目錄相符"], "是")

    def test_the_same_anchor_spelt_differently_is_not_new(self):
        # 2021-01 讀著ê：`Xuzi·Hakaw`（表上 `Xuzi Hakaw`）、`Ava'e`
        # （表上 `Ava’e`）、華語字幕「我是倫敦」（表上漢名
        # `倫敦．伊斯瑪哈善`）。點、撇、空白無仝，毋是新主播。
        anchors(self.store_anchors(), [("泰雅", "Xuzi Hakaw"),
                                       ("鄒", "Ava’e Poiconʉ"),
                                       ("布農", "倫敦．伊斯瑪哈善")])
        for who in ("Xuzi·Hakaw", "Ava'e Poiconʉ", "倫敦"):
            self.assertTrue(opening.known_anchor(
                who, opening._known_anchors(self.store_anchors())), who)
        self.assertFalse(opening.known_anchor(
            "Canglah Kapelo'", opening._known_anchors(self.store_anchors())))

    def store_anchors(self):
        if not hasattr(self, "_anchors"):
            tmp = tempfile.TemporaryDirectory()
            self.addCleanup(tmp.cleanup)
            self._anchors = os.path.join(tmp.name, "主播.csv")
        return self._anchors

    def test_running_it_again_replaces_the_row_and_keeps_the_order(self):
        store = Store(self)
        store.ingest([(Store.THAU, "20", "判不準", "")])
        store.ingest([(Store.SAISIYAT, "20", "賽夏", "")])
        store.ingest([(Store.THAU, "30", "邵", "Tanngi")])
        rows = store.rows()
        names = []
        for row in rows:
            names.append(row["成果檔名"])
        self.assertEqual(names, [Store.SAISIYAT, Store.THAU])
        self.assertEqual(rows[1]["畫面語別牌"], "邵")
        self.assertEqual(rows[1]["主播"], "Tanngi")

    def test_an_episode_not_in_the_catalogue_is_refused(self):
        store = Store(self)
        with self.assertRaises(PipelineError) as caught:
            store.ingest([("20991231_365_晚間_Amis_阿美", "20", "阿美", "")])
        self.assertIn("20991231_365", str(caught.exception))

    def test_the_columns_are_the_ones_the_spec_names(self):
        self.assertEqual(opening.COLUMNS,
                         ("成果檔名", "畫面語別牌", "主播", "與目錄相符",
                          "截圖秒數", "依據"))


if __name__ == "__main__":
    unittest.main()
