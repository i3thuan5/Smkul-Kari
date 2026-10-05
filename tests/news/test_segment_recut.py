"""segment_recut：段落表上帶外ê段，用伊家己ê區域重切，接轉去時間軸。

佇讀字**進前**做：猶無 TSV，重新編號無代價。讀了才重切是 `rescan_band`
ê路，範圍外ê TSV 攏愛徙號碼，是規條管線上危險ê一步。

重切佮精修攏予測試換做假ê（毋免影片）：假重切照段落寫幾條 cue，假精修
kā `refined` 設 True。
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

from scripts import datadirs
from scripts.errors import PipelineError
from scripts.news import paths
from scripts.news import segment_recut
from scripts.news import segments
from scripts.news import splice


def cue(index, start, end):
    name = "t%08d_han.png" % int(round(start * 1000))
    return {"index": index, "start": start, "end": end, "frames": 3,
            "images": {"han": datadirs.strip_ref(name)}}


def row(start, end, kind, language="布農", basis="自動"):
    top, bottom = segments.rows_of(kind, language, (722, 848))
    return {"起秒": start, "迄秒": end, "類型": kind, "單元語別": language,
            "字幕上緣y": top, "字幕下緣y": bottom, "依據": basis}


class Work(object):
    """一个切好、精修好、猶未讀字ê work dir。"""

    def __init__(self, test, cues, table):
        tmp = tempfile.TemporaryDirectory()
        test.addCleanup(tmp.cleanup)
        self.work = os.path.join(tmp.name, "x.work")
        os.makedirs(paths.strips_dir(self.work))
        self.timeline = paths.refined_cues(self.work)
        os.makedirs(os.path.dirname(self.timeline))
        self.book = {"cues": cues, "refined": True, "duration": 600.0,
                     "lines": [{"name": "han", "y": 0, "h": 126}],
                     "region": [0, 722, 1920, 126]}
        self.write(self.book)
        segments.write(paths.segments_file(self.work), table)
        self.calls = []

    def write(self, book):
        with open(self.timeline, "w", encoding="utf-8") as handle:
            json.dump(book, handle, ensure_ascii=False, indent=2,
                      sort_keys=True)

    def read(self):
        with open(self.timeline, encoding="utf-8") as handle:
            return json.load(handle)

    def raw(self):
        with open(self.timeline, "rb") as handle:
            return handle.read()

    def recut(self, video, start, duration, out, preset):
        """假重切：這段逐 10 秒一條，寫做粗切時間軸佮圖條。"""
        self.calls.append((start, duration, preset))
        made = []
        second = start
        while second + 10 <= start + duration + 1e-6:
            made.append(cue(len(made) + 1, second + 1, second + 9))
            second += 10
        os.makedirs(paths.strips_dir(out), exist_ok=True)
        for item in made:
            name = os.path.basename(item["images"]["han"])
            with open(os.path.join(paths.strips_dir(out), name), "wb") as fh:
                fh.write(b"png")
        target = datadirs.coarse_cues(out)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as handle:
            json.dump({"cues": made, "region": [0, 940, 1920, 120]}, handle)
        return target

    def refine(self, video, coarse, preset, refined=True):
        with open(coarse, encoding="utf-8") as handle:
            book = json.load(handle)
        book["refined"] = refined
        target = datadirs.refined_cues(os.path.dirname(os.path.dirname(
            coarse)))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as handle:
            json.dump(book, handle)
        return target

    def run(self, refine=None):
        return segment_recut.run(self.work, "v.mkv", recut=self.recut,
                                 refine=refine or self.refine)


def band(count, step=20.0):
    out = []
    for index in range(count):
        out.append(cue(index + 1, index * step + 1, index * step + 15))
    return out


class TestIslandTimeIsRecut(unittest.TestCase):
    """島語時間ê對白置中佇 y≈960–1050、x≈620–1300；字幕帶ê置右比對遮罩
    （x 1250–1790）看袂著，帶內干焦單字卡、花字，照遐切出來ê cue 攏無
    對白。
    """

    def setUp(self):
        table = [row("0", "200", "外景新聞"),
                 row("200", "400", "島語時間", basis=segments.PENDING),
                 row("400", "600.000", "外景新聞")]
        self.w = Work(self, band(30), table)

    def test_the_stretch_is_cut_again_with_the_island_preset(self):
        self.w.run()
        self.assertEqual(self.w.calls, [(200.0, 200.0, "titv-news-island")])

    def test_cues_outside_are_untouched_and_numbering_is_continuous(self):
        before = self.w.read()["cues"]
        self.w.run()
        after = self.w.read()["cues"]
        numbers = []
        for item in after:
            numbers.append(item["index"])
        self.assertEqual(numbers, list(range(1, len(after) + 1)))
        outside = []
        for item in before:
            if item["start"] < 200 or item["start"] >= 400:
                outside.append((item["start"], item["end"]))
        kept = []
        for item in after:
            if "area" not in item:
                kept.append((item["start"], item["end"]))
        self.assertEqual(kept, outside)

    def test_the_new_cues_say_which_area_cut_them(self):
        self.w.run()
        book = self.w.read()
        inside = []
        for item in book["cues"]:
            if 200 <= item["start"] < 400:
                inside.append(item)
        self.assertEqual(len(inside), 20)
        for item in inside:
            self.assertEqual(item["area"], "島語時間")
        self.assertEqual(sorted(book["areas"]), ["島語時間"])
        self.assertEqual(book["areas"]["島語時間"]["preset"],
                         "titv-news-island")

    def test_the_new_strips_are_in_the_work_dir(self):
        self.w.run()
        for item in self.w.read()["cues"]:
            if item.get("area"):
                name = os.path.basename(item["images"]["han"])
                self.assertTrue(os.path.exists(os.path.join(
                    paths.strips_dir(self.w.work), name)), name)


class TestOnlyBeforeReading(unittest.TestCase):
    """讀了字才重切，重新編號會予 TSV 對著別條 cue——愛行 rescan_band。"""

    def setUp(self):
        table = [row("0", "200", "外景新聞"),
                 row("200", "400", "島語時間"),
                 row("400", "600.000", "外景新聞")]
        self.w = Work(self, band(30), table)

    def test_a_read_episode_is_refused(self):
        target = paths.transcripts_file(self.w.work)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as handle:
            json.dump({"3": {"han": "字"}}, handle)
        with self.assertRaises(PipelineError) as caught:
            self.w.run()
        self.assertIn("rescan_band", str(caught.exception))
        self.assertEqual(self.w.calls, [])

    def test_an_empty_transcripts_file_is_not_reading(self):
        target = paths.transcripts_file(self.w.work)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as handle:
            json.dump({}, handle)
        self.w.run()
        self.assertEqual(len(self.w.calls), 1)


class TestNothingOffBand(unittest.TestCase):

    def test_the_timeline_is_byte_for_byte_the_same(self):
        table = [row("0", "300", "攝影棚"), row("300", "600.000", "外景新聞")]
        w = Work(self, band(30), table)
        before = w.raw()
        w.run()
        self.assertEqual(w.raw(), before)
        self.assertEqual(w.calls, [])


class TestOnlyRefinedStretchesGoIn(unittest.TestCase):
    """store 干焦收精修過ê時間軸；接一段粗切ê入去，publish 會擋。"""

    def test_an_unrefined_stretch_is_refused(self):
        table = [row("0", "200", "外景新聞"),
                 row("200", "400", "部落信箱"),
                 row("400", "600.000", "外景新聞")]
        w = Work(self, band(30), table)
        before = w.raw()

        def coarse_only(video, coarse, preset):
            return w.refine(video, coarse, preset, refined=False)

        with self.assertRaises(PipelineError):
            w.run(refine=coarse_only)
        self.assertEqual(w.raw(), before)


class TestRecutReadsTheCoarseStage(unittest.TestCase):
    """切 cue 寫 `1-cues/cues.json` 了後，重切閣咧讀 `<out>/cues.json`。

    `rescan_band` 本底ê寫法；分階段了後彼个檔永遠無，2021 年 15 集帶外
    專題欲重切ê時就會倒。
    """

    def test_the_cues_come_from_the_coarse_stage(self):
        with tempfile.TemporaryDirectory() as out:
            def runner(cmd, **kwargs):
                target = datadirs.coarse_cues(out)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with open(target, "w", encoding="utf-8") as handle:
                    json.dump({"cues": [cue(1, 5.0, 7.0)]}, handle)

                class Done(object):
                    returncode = 0
                    stderr = ""
                return Done()

            got = splice.recut("v.mkv", 0.0, 10.0, out,
                               region="0,940,1920,120", runner=runner,
                               keep=True)
        self.assertEqual(len(got), 1)

    def test_output_that_is_not_utf8_does_not_crash(self):
        # 2023-11 305 午鄒族紀錄片段試切：切 cue 子程序ê輸出有一个 0xe5
        # 後壁無接續位元組（UTF-8 中文字切一半），`text=True` 解碼就
        # UnicodeDecodeError，cue 已經切好也提袂著。輸出干焦是記錄，袂當
        # 為著一个字元倒規段。
        with tempfile.TemporaryDirectory() as out:
            target = datadirs.coarse_cues(out)
            script = (
                "import json, os, sys\n"
                "os.makedirs(os.path.dirname(%r), exist_ok=True)\n"
                "json.dump({'cues': [{'start': 5.0, 'end': 7.0}]},"
                " open(%r, 'w'))\n"
                "sys.stdout.buffer.write(b'\\xe5x')\n"
                "sys.stderr.buffer.write(b'\\xe5x')\n" % (target, target))

            def runner(cmd, **kwargs):
                return subprocess.run([sys.executable, "-c", script],
                                      **kwargs)

            got = splice.recut("v.mkv", 0.0, 10.0, out,
                               region="0,940,1920,120", runner=runner,
                               keep=True)
        self.assertEqual(len(got), 1)


class TestSpliceByTime(unittest.TestCase):

    def test_an_empty_recut_removes_the_stretch(self):
        # 帶外段落重切了一條都無：彼段本底照字幕帶切ê cue（單字卡、
        # 花字）嘛無愛，拿掉。
        got = splice.splice_time(band(5), 20, 60, [])
        starts = []
        for item in got:
            starts.append(item["start"])
        self.assertEqual(starts, [1, 61, 81])

    def test_the_replacement_lands_in_time_order(self):
        got = splice.splice_time(band(5), 20, 60, [cue(1, 30, 35)])
        starts = []
        for item in got:
            starts.append((item["index"], item["start"]))
        self.assertEqual(starts, [(1, 1), (2, 30), (3, 61), (4, 81)])


if __name__ == "__main__":
    unittest.main()


def sunken_work(test, name):
    table = [row("0", "200", "外景新聞"),
             row("200", "400", "文化小辭典"),
             row("400", "600.000", "外景新聞")]
    w = Work(test, band(30), table)
    renamed = os.path.join(os.path.dirname(w.work), name + ".work")
    os.rename(w.work, renamed)
    w.work = renamed
    w.timeline = paths.refined_cues(renamed)
    return w


class TestSunkenDictionary2021(unittest.TestCase):
    """2021 年「文化小辭典」規个節目縮做子母畫面，字幕沉到 y≈803–885，
    字幕帶（722–848）干焦切著頂懸一截：20211101_305 晚間 889–1107 秒
    讀者愛逐條抽原生格才讀會完整，cue 275（969.5–975.0）內底換三句字幕
    切袂開，干焦寫著頭一句。2022 起字幕轉去帶內（y 770–837），免重切；
    分界看播出年，毋是 preset——2021-11 佮 2022-01 仝款用 titv-news-848。
    """

    def work(self, name):
        return sunken_work(self, name)

    def test_a_2021_dictionary_is_recut_low(self):
        w = self.work("2021_305_2021-11-01_晚間_Amis_阿美")
        w.run()
        self.assertEqual(w.calls, [(200.0, 200.0, "titv-news-dict-2021")])
        areas = []
        for item in w.read()["cues"]:
            if item.get("area"):
                areas.append(item["area"])
        self.assertEqual(set(areas), {"文化小辭典"})

    def test_a_2022_dictionary_stays_in_the_band(self):
        w = self.work("2022_007_2022-01-07_午間_Rukai_魯凱")
        before = w.raw()
        w.run()
        self.assertEqual(w.calls, [])
        self.assertEqual(w.raw(), before)


class TestSunkenRowsFollowTheText(unittest.TestCase):
    """2021-11 文化小辭典ê字幕高低逐集無仝：20211101_305 晚間 y 815–870，
    20211124_328 晚間 780–825。比對列若照 305 定死（810–880），328
    干焦比著字ê下緣一屑仔，三句切做一條 31 秒ê cue。重切進前先量彼段
    ê字佇佗幾列：背景一直變、字ê位置無變，逐列白點取中位數就看會出。
    """

    def frames(self, top, bottom, count=9, seed=1):
        import numpy as np
        rng = np.random.default_rng(seed)
        out = []
        for index in range(count):
            frame = rng.integers(0, 150, size=(180, 300, 3), dtype=np.uint8)
            # 背景有時真光（白衫、天），但逐格位置無仝
            spot = rng.integers(0, 150)
            frame[spot:spot + 25, :] = 235
            left = 20 + 7 * index
            frame[top:bottom, left:left + 200:3] = 250
            out.append(frame)
        return out

    def test_the_text_rows_are_found_under_a_moving_background(self):
        top, bottom = segment_recut.text_rows(self.frames(70, 105))
        self.assertLessEqual(abs(top - 70), 2)
        self.assertLessEqual(abs(bottom - 105), 2)

    def test_a_steady_sunlit_background_is_not_text(self):
        # 20211124_328 晚間：日頭照ê樹葉逐格攏光，白點比例 0.04–0.06，
        # 字才 0.09–0.12；干焦算白點，規條帶攏予人當做字。字有烏框，
        # 光ê樹葉無。
        frames = self.frames(70, 105)
        for frame in frames:
            frame[120:170, :] = 240
        top, bottom = segment_recut.text_rows(frames)
        self.assertLessEqual(abs(top - 70), 2)
        self.assertLessEqual(abs(bottom - 105), 2)

    def test_no_steady_text_gives_nothing(self):
        import numpy as np
        rng = np.random.default_rng(3)
        frames = []
        for _ in range(9):
            frames.append(rng.integers(0, 150, size=(180, 300, 3),
                                       dtype=np.uint8))
        self.assertIsNone(segment_recut.text_rows(frames))

    def test_the_recut_region_is_moved_to_the_measured_rows(self):
        w = sunken_work(self, "2021_328_2021-11-24_晚間_Sakizaya_撒奇萊雅")
        seen = {}

        def recut(video, start, duration, out, preset, presets=None):
            with open(presets, encoding="utf-8") as handle:
                seen["layout"] = json.load(handle)[preset]
            return w.recut(video, start, duration, out, preset)

        def refine(video, coarse, preset, presets=None):
            return w.refine(video, coarse, preset)

        def probe(video, lo, hi):
            return self.frames(40, 90)

        segment_recut.run(w.work, "v.mkv", recut=recut, refine=refine,
                          probe=probe)
        region = seen["layout"]["region"]
        rows = seen["layout"]["mask"]["compare_rows"]
        top = region[1] + rows[0]
        bottom = region[1] + rows[1]
        self.assertLessEqual(abs(top - (segment_recut.PROBE_TOP + 40)), 3)
        self.assertLessEqual(abs(bottom - (segment_recut.PROBE_TOP + 90)), 3)
        self.assertLessEqual(region[1], top)
        self.assertGreaterEqual(region[1] + region[3], bottom)
