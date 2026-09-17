"""`cues` 以原生格率解碼、每 0.2 秒取最接近的一格，時間記真實 pts。

解碼與遮罩都換成假的：畫面左上角那一格的值就是「第幾句」（0＝空白），
這樣只測 `stage_cues` 怎麼接 decode 與 sampling，不跑 ffmpeg。
"""
import argparse
import json
import tempfile
import unittest
from unittest import mock

import numpy as np

from scripts import datadirs
from scripts.ocr import cli
from scripts.ocr import sampling

real_nearest = sampling.nearest_samples

FPS = 30000 / 1001
REGION = "0,0,40,4"


def native(start, seconds, script):
    """(pts, rgb)：`script(t)` 回傳該時刻是第幾句。"""
    frames = []
    for index in range(int(seconds * FPS)):
        pts = round(index / FPS, 6)
        rgb = np.zeros((4, 40, 3), dtype=np.uint8)
        rgb[0, 0, 0] = script(pts)
        frames.append((round(start + pts, 6), rgb))
    return frames


def fake_mask(rgb, spec):
    mask = np.zeros((4, 40), dtype=bool)
    slot = int(rgb[0, 0, 0])
    if slot:
        mask[:, slot * 5:slot * 5 + 5] = True
    return mask


def two_sentences(t):
    if 1.0 <= t < 3.0:
        return 1
    if 3.0 <= t < 5.0:
        return 3
    return 0


class TestCuesOnNativeFrames(unittest.TestCase):

    def _run(self, start=0.0, duration=None, **extra):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return self._cut(tmp.name, start, duration, **extra)

    def run_into(self, work):
        """Cut the synthetic episode into `work`; return the manifest."""
        manifest, _ = self._cut(work, 0.0, None)
        return manifest

    def _cut(self, work, start, duration, **extra):
        args = argparse.Namespace(
            video="ep.mp4", out=work, region=REGION, presets=None,
            preset=None, autodetect=False, fps=5.0, start=start,
            duration=duration, min_ink=10, change=0.35, min_stable=2,
            min_duration=0.30, samples=60, lang="chi_tra", sheets=False,
            progress=False, threads=2)
        for name in extra:
            setattr(args, name, extra[name])
        calls = []

        def frames(video, region, **kwargs):
            calls.append((video, list(region), kwargs))
            return iter(native(start, duration or 6.0, two_sentences))

        self.tolerances = []

        def picks(stream, interval, start, tolerance):
            self.tolerances.append(tolerance)
            return real_nearest(stream, interval=interval, start=start,
                                tolerance=tolerance)

        info = {"width": 40, "height": 4, "duration": 6.0, "fps": FPS}
        with mock.patch.object(cli.decode, "stream_frames",
                               side_effect=frames), \
             mock.patch.object(cli.decode, "stream_region",
                               side_effect=AssertionError("fps 濾鏡")), \
             mock.patch.object(cli.detector, "probe_or_die",
                               return_value=info), \
             mock.patch.object(cli.detector, "split_lines",
                               return_value=([], None)), \
             mock.patch.object(cli.sampling, "nearest_samples",
                               side_effect=picks), \
             mock.patch.object(cli.cuelib, "frame_mask", fake_mask):
            cli.stage_cues(args)
        with open(datadirs.coarse_cues(work), encoding="utf-8") as f:
            return json.load(f), calls

    def test_decodes_natively_with_the_thread_count(self):
        _, calls = self._run()
        self.assertEqual(len(calls), 1)
        video, region, kwargs = calls[0]
        self.assertEqual(kwargs.get("threads"), 2)
        self.assertIsNone(kwargs.get("windows"))
        interval, fps = kwargs.get("grid")
        self.assertAlmostEqual(interval, 0.2)
        self.assertAlmostEqual(fps, FPS)

    def test_edge_tolerance_is_ffmpegs_pass_width(self):
        # 片頭片尾規則要和 ffmpeg 端的篩法一致，容許值用同一個數字
        self._run()
        self.assertEqual(len(self.tolerances), 1)
        self.assertEqual(self.tolerances[0], cli.decode.grid_half(FPS))

    def test_sample_ts_is_a_real_frame_time(self):
        # 以 0.2 秒格點回填，照 sample_ts 抽格會抽到相鄰的另一格
        manifest, _ = self._run()
        self.assertEqual(len(manifest["cues"]), 2)
        for cue in manifest["cues"]:
            index = round(cue["sample_ts"] * FPS)
            self.assertAlmostEqual(cue["sample_ts"], index / FPS, places=3)
        starts = []
        for cue in manifest["cues"]:
            starts.append(cue["start"])
        self.assertAlmostEqual(starts[0], 1.0, delta=1 / FPS)
        self.assertAlmostEqual(starts[1], 3.0, delta=1 / FPS)
        self.assertNotAlmostEqual(starts[1] / 0.2, round(starts[1] / 0.2),
                                  places=3)

    def test_manifest_says_how_it_was_sampled(self):
        # 新切法與舊切法（fps=5 濾鏡）並存，時間軸要分得出來
        manifest, _ = self._run()
        self.assertEqual(manifest["sample_fps"], 5.0)
        self.assertEqual(manifest["sampling"], "nearest-native")
        self.assertAlmostEqual(manifest["source_fps"], FPS, places=3)

    def test_start_and_duration_reach_the_decoder(self):
        # rescan_band 會用 --start／--duration 重切一段，時間要是真的秒數
        manifest, calls = self._run(start=100.0, duration=6.0)
        kwargs = calls[0][2]
        self.assertEqual(kwargs.get("start"), 100.0)
        self.assertEqual(kwargs.get("duration"), 6.0)
        self.assertAlmostEqual(manifest["cues"][0]["start"], 101.0,
                               delta=1 / FPS)

    def test_threads_option_is_accepted(self):
        args = cli.build_parser().parse_args(
            ["cues", "v.mp4", "-o", "w", "--threads", "3"])
        self.assertEqual(args.threads, 3)
        args = cli.build_parser().parse_args(["cues", "v.mp4", "-o", "w"])
        self.assertEqual(args.threads, 2)


if __name__ == "__main__":
    unittest.main()
