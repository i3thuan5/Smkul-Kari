"""move_outdirs：kithann/out 一次性搬成「語料 → 月份 → 集」。

舊的樣子：`out/mxf/<slug>.work`（裡面 strips/、2-refined/、sheets/、
sheets.json、transcripts.json、verified.json 平鋪）、`out/mxf-logs/`、
`out/mkv/`、`out/asrmt/`、`out/stage*/`。400 多個 work dir 和一千多個
log，搬錯或漏搬都不會有人當場發現，所以搬完一定要自檢。
"""
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout

from scripts.news import move_outdirs as mover

SLUG = "2021_060_2021-03-01_晚間_Amis_阿美"
NAME = "20210301_060_晚間_Amis_阿美"
CATALOGUE = [{"slug": SLUG, "srt_name": NAME,
              "file": "21NL004_60晚間族語新聞.mp4",
              "原始影片檔案位置": "族語新聞/3月/21NL004_60晚間族語新聞.mp4"}]
TIMELINE = {"cues": [{"index": 1, "start": 1.0, "end": 2.0,
                      "images": {"han": "strips/t00001000_han.png"}}]}


class Tree(unittest.TestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.out = tmp.name

    def put(self, rel, body=""):
        path = os.path.join(self.out, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            if isinstance(body, dict):
                json.dump(body, handle, ensure_ascii=False)
            else:
                handle.write(body)
        return path

    def exists(self, rel):
        return os.path.exists(os.path.join(self.out, rel))

    def read(self, rel):
        with open(os.path.join(self.out, rel), encoding="utf-8") as handle:
            return json.load(handle)

    def old_work(self):
        work = os.path.join("mxf", SLUG + ".work")
        self.put(os.path.join(work, "1-cues", "cues.json"), TIMELINE)
        self.put(os.path.join(work, "2-refined", "cues.json"), TIMELINE)
        self.put(os.path.join(work, "strips", "t00001000_han.png"), "png")
        self.put(os.path.join(work, "sheets", "sheet_001.png"), "png")
        self.put(os.path.join(work, "sheets.json"),
                 {"sheet_001.png": [1]})
        self.put(os.path.join(work, "transcripts.json"), {"1": {"han": "字"}})
        self.put(os.path.join(work, "verified.json"), {"1": {"han": True}})
        return work

    def run_mover(self, *extra):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = mover.main(["--out", self.out] + list(extra),
                              catalogue=CATALOGUE)
        return code, buf.getvalue()


class TestWorkDirs(Tree):

    NEW = os.path.join("news", "1-ocr", "2021-03", SLUG + ".work")

    def test_a_work_dir_lands_in_its_month_with_numbered_stages(self):
        self.old_work()
        code, _ = self.run_mover()
        self.assertEqual(code, 0)
        for rel in ("1-cues/cues.json", "2-strips/t00001000_han.png",
                    "3-refined/cues.json", "4-sheets/sheet_001.png",
                    "4-sheets/sheets.json",
                    "5-transcripts/transcripts.json",
                    "5-transcripts/verified.json"):
            self.assertTrue(self.exists(os.path.join(self.NEW, rel)), rel)
        self.assertFalse(self.exists(os.path.join("mxf", SLUG + ".work")))

    def test_recorded_strip_paths_follow_the_folder(self):
        # 圖條搬進 2-strips/，時間軸還記 strips/，組合圖就抓不到圖
        self.old_work()
        self.run_mover()
        for stage in ("1-cues", "3-refined"):
            doc = self.read(os.path.join(self.NEW, stage, "cues.json"))
            ref = doc["cues"][0]["images"]["han"]
            self.assertEqual(ref, "2-strips/t00001000_han.png")
            self.assertTrue(self.exists(os.path.join(self.NEW, ref)))

    def test_dry_run_touches_nothing(self):
        work = self.old_work()
        code, printed = self.run_mover("--dry-run")
        self.assertEqual(code, 0)
        self.assertIn(SLUG, printed)
        self.assertTrue(self.exists(work))
        self.assertFalse(self.exists("news"))

    def test_running_twice_is_harmless(self):
        self.old_work()
        self.run_mover()
        code, _ = self.run_mover()
        self.assertEqual(code, 0)
        self.assertTrue(self.exists(os.path.join(self.NEW, "2-strips")))

    def test_an_aiyalaeho_work_dir_is_restaged_in_place(self):
        # 開會了共用引擎的階段名，資料夾本身不動位置
        work = os.path.join("aiyalaeho", "開會了_068_Amis_阿美.work")
        self.put(os.path.join(work, "2-refined", "cues.json"), TIMELINE)
        self.put(os.path.join(work, "strips", "t00001000_han.png"), "png")
        self.put(os.path.join(work, "sheets.json"), {})
        self.put(os.path.join(work, "transcripts.json"), {})
        self.put(os.path.join(work, "band.json"), {})
        code, _ = self.run_mover()
        self.assertEqual(code, 0)
        for rel in ("3-refined/cues.json", "2-strips/t00001000_han.png",
                    "4-sheets/sheets.json", "5-transcripts/transcripts.json",
                    "band.json"):
            self.assertTrue(self.exists(os.path.join(work, rel)), rel)


class TestOnlyWhatIsListed(Tree):

    def test_staging_is_never_taken_for_a_product(self):
        # stage-read/ 是讀者抓來看的 mp4，不是 1-ocr 的產物
        self.put("stage-read/21NL004_60晚間族語新聞.mp4", "mp4")
        code, _ = self.run_mover()
        self.assertEqual(code, 0)
        self.assertTrue(self.exists(
            "news/stage-read/2021-03/21NL004_60晚間族語新聞.mp4"))
        for root, _dirs, files in os.walk(os.path.join(self.out, "news",
                                                       "1-ocr")):
            self.assertEqual(files, [], root)

    def test_a_video_the_catalogue_does_not_know_is_left_and_named(self):
        self.put("stage-exp/不知道哪一集.mp4", "mp4")
        code, printed = self.run_mover()
        self.assertEqual(code, 0)
        self.assertTrue(self.exists("stage-exp/不知道哪一集.mp4"))
        self.assertIn("不知道哪一集.mp4", printed)

    def test_loose_files_in_out_are_not_moved(self):
        self.put("cues-sep.log", "x")
        self.put("smkul.csv", "x")
        self.run_mover()
        self.assertTrue(self.exists("cues-sep.log"))
        self.assertTrue(self.exists("smkul.csv"))

    def test_archive_and_speech_side_go_to_their_months(self):
        self.put("mkv/%s.mkv" % NAME, "mkv")
        self.put("asrmt/%s/audio.mp3" % NAME, "mp3")
        code, _ = self.run_mover()
        self.assertEqual(code, 0)
        self.assertTrue(self.exists("news/mkv/2021-03/%s.mkv" % NAME))
        self.assertTrue(self.exists(
            "news/2-asr/2021-03/%s/audio.mp3" % NAME))


class TestLogs(Tree):

    def test_every_episode_log_moves_to_its_month(self):
        for step in ("get", "cues", "refine"):
            self.put("mxf-logs/%s.%s.log" % (SLUG, step), step)
        code, _ = self.run_mover()
        self.assertEqual(code, 0)
        for step in ("get", "cues", "refine"):
            self.assertTrue(self.exists(
                "news/logs/2021-03/%s.%s.log" % (SLUG, step)), step)
        self.assertFalse(self.exists("mxf-logs/%s.get.log" % SLUG))

    def test_logs_never_land_inside_a_work_dir(self):
        # log 要比 work dir 活得久：work dir 驗收後就刪了
        self.old_work()
        self.put("mxf-logs/%s.cues.log" % SLUG, "x")
        self.run_mover()
        for root, _dirs, files in os.walk(os.path.join(self.out, "news",
                                                       "1-ocr")):
            for name in files:
                self.assertFalse(name.endswith(".log"), root)

    def test_a_log_without_a_slug_is_left_and_named(self):
        self.put("mxf-logs/隨手記.log", "x")
        code, printed = self.run_mover()
        self.assertEqual(code, 0)
        self.assertTrue(self.exists("mxf-logs/隨手記.log"))
        self.assertIn("隨手記.log", printed)


class TestSelfCheck(Tree):

    def test_a_move_that_did_not_happen_fails_the_run(self):
        # 自檢：舊路徑不該再有、新路徑數量要對，不對就非零結束
        self.put("mxf-logs/%s.cues.log" % SLUG, "x")
        real = mover.move

        def half(src, dst):
            if src.endswith(".log"):
                return
            real(src, dst)

        mover.move = half
        try:
            code, printed = self.run_mover()
        finally:
            mover.move = real
        self.assertNotEqual(code, 0)
        self.assertIn(".cues.log", printed)

    def test_an_existing_destination_is_not_overwritten(self):
        self.put("mkv/%s.mkv" % NAME, "old")
        self.put("news/mkv/2021-03/%s.mkv" % NAME, "already there")
        code, printed = self.run_mover()
        self.assertNotEqual(code, 0)
        with open(os.path.join(self.out, "news/mkv/2021-03/%s.mkv" % NAME),
                  encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "already there")
        self.assertTrue(self.exists("mkv/%s.mkv" % NAME))


if __name__ == "__main__":
    unittest.main()
