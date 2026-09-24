"""segment_recut：段落表上帶外ê段，用伊家己ê區域重切，接轉去時間軸。

佇讀字**進前**做：猶無 TSV，重新編號無代價。讀了才重切是 `rescan_band`
ê路，範圍外ê TSV 攏愛徙號碼，是規條管線上危險ê一步。

重切佮精修攏予測試換做假ê（毋免影片）：假重切照段落寫幾條 cue，假精修
kā `refined` 設 True。
"""
import json
import os
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
