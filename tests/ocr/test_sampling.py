"""粗切取樣：每 0.2 秒取最接近的來源格，時間記該格的真實 pts。"""
import unittest

from scripts.ocr import sampling


def source(fps, seconds, offset=0.0):
    """合成來源格：(pts, 第幾格)，pts 照 ffmpeg 印的精度取到毫秒以下。"""
    count = int(round(seconds * fps))
    for index in range(count):
        yield (round(offset + index / fps, 6), index)


def picked(frames, **kwargs):
    out = []
    for pts, index in sampling.nearest_samples(frames, **kwargs):
        out.append((pts, index))
    return out


class TestNearestSamples(unittest.TestCase):

    def test_no_drift_over_a_48_minute_episode_at_29_97(self):
        # 固定每 6 格取一格每步偏 0.0002 秒，48 分鐘尾端累積約 0.6 秒
        fps = 30000 / 1001
        got = picked(source(fps, 48 * 60))
        self.assertEqual(len(got), 48 * 60 * 5)
        last_pts, _ = got[-1]
        target = (len(got) - 1) * 0.2
        self.assertLess(abs(last_pts - target), 1 / fps)
        worst = 0.0
        for k, (pts, _) in enumerate(got):
            worst = max(worst, abs(pts - k * 0.2))
        self.assertLessEqual(worst, 0.5 / fps + 1e-6)

    def test_reported_time_is_the_frame_pts_not_the_grid_point(self):
        # 以格點回填時間，照 sample_ts 回頭抽格會抽到相鄰的另一格
        fps = 30000 / 1001
        got = picked(source(fps, 10))
        off_grid = 0
        for pts, index in got:
            self.assertAlmostEqual(pts, round(index / fps, 6), places=6)
            if abs(pts / 0.2 - round(pts / 0.2)) > 1e-6:
                off_grid += 1
        self.assertGreater(off_grid, len(got) // 2)

    def test_25_fps_is_still_one_frame_every_0_2_s(self):
        got = picked(source(25.0, 60))
        self.assertEqual(len(got), 300)
        indices = []
        for _, index in got:
            indices.append(index)
        self.assertEqual(indices, list(range(0, 1500, 5)))

    def test_one_frame_nearest_to_two_targets_is_handed_out_once(self):
        # 可變格率掉格：1.0 之後直接跳到 1.9，1.2 與 1.4 都最接近 f、
        # 1.6 與 1.8 都最接近 g，同一格只能判斷一次
        frames = [(0.0, "a"), (0.2, "b"), (0.4, "c"), (0.6, "d"),
                  (0.8, "e"), (1.0, "f"), (1.9, "g"), (2.0, "h")]
        got = picked(iter(frames))
        names = []
        for _, name in got:
            names.append(name)
        self.assertEqual(names, ["a", "b", "c", "d", "e", "f", "g", "h"])

    def test_gap_nearer_the_earlier_frame_keeps_it_once(self):
        frames = [(0.0, "a"), (0.2, "b"), (0.9, "c"), (1.0, "d")]
        names = []
        for _, name in picked(iter(frames)):
            names.append(name)
        # 0.4 仍是 b（不重交）；0.6 與 0.8 → c（只交一次）；1.0 → d
        self.assertEqual(names, ["a", "b", "c", "d"])

    def test_start_offset_moves_the_grid(self):
        got = picked(source(25.0, 2, offset=100.0), start=100.0)
        self.assertEqual(got[0][0], 100.0)
        self.assertAlmostEqual(got[1][0], 100.2, places=6)

    def test_last_target_filled_only_when_the_last_frame_is_close(self):
        # 片尾沒有「下一格」可以觸發比較；最後一格離目標不到容許值才補，
        # 否則片尾會多出一格（逐格解碼）或少一格（ffmpeg 先篩過）
        got = picked(iter([(0.0, "a"), (0.1, "b"), (0.19, "c")]),
                     tolerance=0.0167)
        self.assertEqual(got, [(0.0, "a"), (0.19, "c")])
        got = picked(iter([(0.0, "a"), (0.1, "b"), (0.15, "c")]),
                     tolerance=0.0167)
        self.assertEqual(got, [(0.0, "a")])
        got = picked(iter([(0.0, "a"), (0.1, "b"), (0.2, "c")]),
                     tolerance=0.0167)
        self.assertEqual(got, [(0.0, "a"), (0.2, "c")])

    def test_first_target_skipped_when_the_first_frame_is_far(self):
        # --start 7.02 在 29.97 fps 上，seek 後第一格在 7.0404，離目標
        # 0.0204 秒、超過半格；ffmpeg 端會丟掉它，這裡也要一樣
        frames = [(7.0404, "a"), (7.0738, "b"), (7.2072, "c")]
        got = picked(iter(frames), start=7.02, tolerance=0.0167)
        self.assertEqual(got, [(7.2072, "c")])
        got = picked(iter(frames), start=7.03, tolerance=0.0167)
        self.assertEqual(got, [(7.0404, "a")])

    def test_thinned_stream_picks_the_same_frames(self):
        # ffmpeg 端先丟掉非最近格，挑出來的要和逐格挑的一模一樣
        fps = 30000 / 1001
        frames = []
        for pts, index in source(fps, 20):
            # mkv 的 pts 捨入到毫秒
            frames.append((round(pts, 3), index))
        half = 0.5 / fps + 0.001
        full = picked(iter(frames), tolerance=half)
        thin = []
        for pts, index in frames:
            k = round(pts / 0.2)
            if abs(pts - k * 0.2) <= half:
                thin.append((pts, index))
        self.assertEqual(picked(iter(thin), tolerance=half), full)
        self.assertEqual(len(full), 100)
        for start in (3.3, 7.02, 7.03):
            later = []
            for pts, index in frames:
                if pts >= start:
                    later.append((pts, index))
            thin = []
            for pts, index in later:
                k = round((pts - start) / 0.2)
                if abs(pts - start - k * 0.2) <= half:
                    thin.append((pts, index))
            self.assertEqual(
                picked(iter(thin), start=start, tolerance=half),
                picked(iter(later), start=start, tolerance=half), start)

    def test_empty_stream_gives_nothing(self):
        self.assertEqual(picked(iter([])), [])


class TestSourceFps(unittest.TestCase):

    def test_undeclared_rate_falls_back_to_29_97(self):
        # ffprobe 對可變格率給 0/0，probe 回 0.0
        self.assertAlmostEqual(sampling.source_fps(0.0), 30000 / 1001)
        self.assertAlmostEqual(sampling.source_fps(None), 30000 / 1001)

    def test_declared_rate_is_kept(self):
        self.assertEqual(sampling.source_fps(25.0), 25.0)

    def test_fallback_rate_does_not_touch_timestamps(self):
        # 既定值只拿來估算，取樣時間仍是真實 pts
        frames = [(0.0, 0), (0.21, 1), (0.43, 2)]
        got = picked(iter(frames))
        self.assertEqual(got, [(0.0, 0), (0.21, 1), (0.43, 2)])


if __name__ == "__main__":
    unittest.main()
