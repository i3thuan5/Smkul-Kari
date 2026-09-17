"""ffmpeg 讀取層：原生格率串流、select 視窗、showinfo 時間戳。

一律用假的子程序餵位元組與 stderr，不跑 ffmpeg、不讀影片。
"""
import os
import unittest
from unittest import mock

import numpy as np

from scripts.ocr import decode

W, H = 4, 2
NBYTES = W * H * 3
REGION = (0, 0, W, H)


def frame_bytes(value):
    return bytes([value]) * NBYTES


CONFIG = ("[Parsed_showinfo_1 @ 0x55d] config in time_base: 1/30000, "
          "frame_rate: 30000/1001\n"
          "[Parsed_showinfo_1 @ 0x55d] config out time_base: 0/0, "
          "frame_rate: 0/0\n")


def showinfo(n, pts, base=30000):
    # showinfo 的 pts_time 是 %g：只有 6 位有效數字
    return ("[Parsed_showinfo_1 @ 0x55d] n:%4d pts:%7d pts_time:%-7g "
            "duration:   1001 duration_time:0.0333667 fmt:yuv420p\n"
            % (n, round(pts * base), pts))


def parse(text):
    return decode.ShowinfoParser().feed(text)


class FakeProc:
    """假的 Popen：stdout 給畫面位元組，stderr 給 showinfo 文字。"""

    def __init__(self, frames, stderr, returncode=0):
        import io
        self.stdout = io.BytesIO(b"".join(frames))
        self.stderr = io.BytesIO(stderr.encode("utf-8"))
        self.returncode = None
        self._code = returncode
        self.args = None

    def wait(self):
        self.returncode = self._code
        return self._code

    def kill(self):
        pass


def times(pairs):
    out = []
    for pts, _ in pairs:
        out.append(pts)
    return out


def run(frames, stderr, returncode=0, **kwargs):
    proc = FakeProc(frames, CONFIG + stderr, returncode)
    seen = {}

    def spawn(args, **popen_kwargs):
        seen["args"] = args
        return proc

    with mock.patch.object(decode.subprocess, "Popen", side_effect=spawn):
        out = list(decode.stream_frames("ep.mp4", REGION, **kwargs))
    return out, seen["args"]


class TestFrameTimestampPairing(unittest.TestCase):

    def test_frames_carry_showinfo_pts_not_index_over_fps(self):
        # select 之後畫面之間有跳號，時間不可用「第幾格 ÷ fps」推算
        err = showinfo(0, 10.01) + showinfo(1, 10.0434) + showinfo(2, 55.5)
        out, _ = run([frame_bytes(1), frame_bytes(2), frame_bytes(3)], err)
        self.assertEqual(times(out), [10.01, 10.0434, 55.5])
        self.assertEqual(out[2][1].shape, (H, W, 3))
        self.assertEqual(int(out[2][1][0, 0, 0]), 3)

    def test_more_frames_than_timestamps_fails(self):
        # 實驗踩過：rawvideo 預設補重複格，畫面 832、時間戳 166
        err = showinfo(0, 1.0) + showinfo(1, 1.2)
        with self.assertRaisesRegex(RuntimeError, "時間戳"):
            run([frame_bytes(1)] * 5, err)

    def test_more_timestamps_than_frames_fails(self):
        err = showinfo(0, 1.0) + showinfo(1, 1.2) + showinfo(2, 1.4)
        with self.assertRaisesRegex(RuntimeError, "時間戳"):
            run([frame_bytes(1)] * 2, err)

    def test_passthrough_and_nostats_are_always_requested(self):
        _, args = run([frame_bytes(1)], showinfo(0, 0.0))
        self.assertIn("-nostats", args)
        self.assertEqual(args[args.index("-fps_mode") + 1], "passthrough")

    def test_thread_count_is_passed_before_input(self):
        _, args = run([frame_bytes(1)], showinfo(0, 0.0), threads=2)
        self.assertLess(args.index("-threads"), args.index("-i"))
        self.assertEqual(args[args.index("-threads") + 1], "2")

    def test_start_seeks_on_input_and_pts_are_shifted_back(self):
        # 輸入端 -ss 之後 pts 從 0 起算；實測 pts＋start＝真實時間
        err = showinfo(0, 802 / 30000) + showinfo(1, 1802 / 30000)
        out, args = run([frame_bytes(1), frame_bytes(2)], err,
                        start=10.05, duration=0.1)
        self.assertLess(args.index("-ss"), args.index("-i"))
        self.assertEqual(args[args.index("-ss") + 1], "10.050")
        self.assertLess(args.index("-t"), args.index("-i"))
        self.assertEqual(args[args.index("-t") + 1], "0.100")
        self.assertAlmostEqual(out[0][0], 10.05 + 802 / 30000, places=9)
        self.assertAlmostEqual(out[1][0], 10.05 + 1802 / 30000, places=9)

    def test_no_seek_when_starting_at_zero(self):
        _, args = run([frame_bytes(1)], showinfo(0, 0.0))
        self.assertNotIn("-ss", args)
        self.assertNotIn("-t", args)

    def test_trailing_partial_frame_fails(self):
        with self.assertRaisesRegex(RuntimeError, "trailing"):
            run([frame_bytes(1), b"\x00" * 5], showinfo(0, 0.0))


class TestParsePts(unittest.TestCase):

    def test_progress_line_sharing_a_line_with_showinfo(self):
        # 實驗踩過：沒關進度列時，進度與 showinfo 印在同一行，時間戳漏抓
        line = ("frame=  12 fps=0.0 q=-0.0 size=N/A time=00:00:00.40 "
                "bitrate=N/A speed=0.8x    \r"
                + showinfo(0, 0.4).rstrip("\n")
                + showinfo(1, 0.4334).rstrip("\n"))
        self.assertEqual(parse(CONFIG + line), [0.4, 0.4334])

    def test_duration_time_is_not_a_timestamp(self):
        self.assertEqual(parse(CONFIG + showinfo(3, 7.0)), [7.0])

    def test_non_showinfo_lines_give_nothing(self):
        self.assertEqual(parse("Stream #0:0: Video: h264\n"), [])

    def test_time_comes_from_integer_pts_not_the_rounded_pts_time(self):
        # 實測：1000 秒以後 pts_time 只印到小數兩位（1082.983 印成
        # 1082.98），相鄰兩格看起來一樣近，挑到的格就不對了
        text = ("[Parsed_showinfo_2 @ 0x5f] config in time_base: 1/1000, "
                "frame_rate: 30000/1001\n"
                "[Parsed_showinfo_2 @ 0x5f] n: 7 pts:1082983 "
                "pts_time:1082.98 duration: 33 duration_time:0.033\n")
        self.assertEqual(parse(text), [1082.983])

    def test_output_time_base_line_does_not_replace_the_input_one(self):
        text = CONFIG + showinfo(0, 2.0)
        self.assertEqual(parse(text), [2.0])

    def test_a_frame_before_any_time_base_fails(self):
        with self.assertRaisesRegex(RuntimeError, "time_base"):
            parse(showinfo(0, 2.0))

    def test_frame_without_pts_fails(self):
        text = CONFIG + ("[Parsed_showinfo_1 @ 0x55d] n:   0 pts:NOPTS "
                         "pts_time:NOPTS duration: 1001\n")
        with self.assertRaisesRegex(RuntimeError, "NOPTS"):
            parse(text)

    def test_split_across_reads_still_found(self):
        err = showinfo(0, 1.5) + showinfo(1, 1.7)
        out, _ = run([frame_bytes(1), frame_bytes(2)], err)
        self.assertEqual(times(out), [1.5, 1.7])


class TestSelectWindows(unittest.TestCase):

    def test_overlapping_windows_merge_into_one_select_term(self):
        # 同一格 select 只輸出一次：重疊的視窗在濾鏡裡併成一段
        expr = decode.select_expr([(1.0, 1.48), (1.3, 1.78), (5.0, 5.48)])
        self.assertEqual(expr, "between(t,1.000,1.780)+between(t,5.000,5.480)")

    def test_windows_are_clamped_at_zero(self):
        self.assertEqual(decode.select_expr([(-0.14, 0.34)]),
                         "between(t,0.000,0.340)")

    def test_shared_frames_go_to_both_windows(self):
        # 兩個邊界不到 0.48 秒，中間的格要分給兩個邊界，不可只算一次
        windows = [(1.0, 1.4), (1.2, 1.6)]
        frames = []
        for pts in (1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6):
            frames.append((pts, np.full((H, W, 3), int(pts * 10), np.uint8)))
        got = dict(decode.window_frames(iter(frames), windows))
        self.assertEqual(times(got[0]), [1.0, 1.1, 1.2, 1.3, 1.4])
        self.assertEqual(times(got[1]), [1.2, 1.3, 1.4, 1.5, 1.6])
        self.assertIs(got[0][2][1], got[1][0][1])

    def test_windows_are_released_as_soon_as_they_close(self):
        # 一集約一萬兩千格，不可全部留在記憶體；視窗關了就交出去
        windows = [(0.0, 0.2), (5.0, 5.2)]
        order = []

        def frames():
            for pts in (0.0, 0.1, 0.2, 5.0, 5.1, 5.2):
                order.append(pts)
                yield (pts, None)

        gen = decode.window_frames(frames(), windows)
        index, got = next(gen)
        self.assertEqual(index, 0)
        self.assertEqual(len(got), 3)
        self.assertLessEqual(max(order), 5.0)
        self.assertEqual(times(gen), [1])

    def test_window_cut_short_by_end_of_file_is_still_returned(self):
        windows = [(9.8, 10.28), (20.0, 20.48)]
        frames = iter([(9.8, None), (9.9, None)])
        got = list(decode.window_frames(frames, windows))
        self.assertEqual(got[0][0], 0)
        self.assertEqual(len(got[0][1]), 2)
        self.assertEqual(got[1], (1, []))

    def test_short_filter_stays_on_command_line(self):
        _, args = run([frame_bytes(1)], showinfo(0, 1.0),
                      windows=[(1.0, 1.48)])
        self.assertIn("-vf", args)
        chain = args[args.index("-vf") + 1]
        self.assertIn("select='between(t,1.000,1.480)'", chain)
        self.assertLess(chain.index("select"), chain.index("showinfo"))
        self.assertTrue(chain.startswith("crop="))

    def test_long_filter_goes_to_filter_script(self):
        # 819 個視窗約 25 KB，不可塞命令列
        windows = []
        for k in range(819):
            windows.append((k * 3.0, k * 3.0 + 0.48))
        captured = {}

        def spawn_check(args):
            path = args[args.index("-filter_script:v") + 1]
            with open(path, encoding="utf-8") as f:
                captured["script"] = f.read()
            captured["path"] = path

        proc = FakeProc([frame_bytes(1)], CONFIG + showinfo(0, 0.0))

        def spawn(args, **kwargs):
            spawn_check(args)
            captured["args"] = args
            return proc

        with mock.patch.object(decode.subprocess, "Popen",
                               side_effect=spawn):
            list(decode.stream_frames("ep.mp4", REGION, windows=windows))
        self.assertNotIn("-vf", captured["args"])
        self.assertIn("between(t,2454.000,2454.480)", captured["script"])
        for arg in captured["args"]:
            self.assertLess(len(arg), 1000)
        self.assertFalse(os.path.exists(captured["path"]))


class TestNearestGridFilter(unittest.TestCase):
    """ffmpeg 先丟掉用不到的格：逐格轉 RGB 再經管線，多燒約 20% CPU。"""

    def test_only_frames_within_half_a_frame_of_the_grid_pass(self):
        _, args = run([frame_bytes(1)], showinfo(0, 0.0),
                      grid=(0.2, 30000 / 1001))
        chain = args[args.index("-vf") + 1]
        # 半格 0.01668 加 1 毫秒：mkv 的 pts 捨入到毫秒，只給半格時一集
        # 14,400 個格點掉了 158 個
        self.assertIn("select='lte(abs(t-0.2*floor(t/0.2+0.5)),0.017700)'",
                      chain)
        self.assertLess(chain.index("select"), chain.index("showinfo"))
        self.assertLess(chain.index("select"), chain.index("format=rgb24"))

    def test_25_fps_passes_exactly_the_grid_frames(self):
        _, args = run([frame_bytes(1)], showinfo(0, 0.0), grid=(0.2, 25.0))
        chain = args[args.index("-vf") + 1]
        # 格線剛好落在兩格正中間（起點偏 0.02 秒）時，恰好半格寬會被
        # 浮點誤差擋掉兩格；要留一點餘裕
        self.assertIn(",0.021000)'", chain)

    def test_unknown_rate_keeps_every_frame(self):
        # 格率 0/0：半格寬算不出來，全部交給 Python 挑
        _, args = run([frame_bytes(1)], showinfo(0, 0.0), grid=(0.2, 0.0))
        chain = args[args.index("-vf") + 1]
        self.assertNotIn("select", chain)

    def test_grid_and_windows_do_not_mix(self):
        with self.assertRaises(ValueError):
            run([frame_bytes(1)], showinfo(0, 0.0), grid=(0.2, 25.0),
                windows=[(1.0, 1.5)])


class TestFailure(unittest.TestCase):

    def test_unparseable_timestamps_name_the_cause(self):
        # 時間戳讀不出來時，要說是 NOPTS，不是含糊的「畫面比時間戳多」
        err = ("[Parsed_showinfo_1 @ 0x55d] n:   0 pts:NOPTS "
               "pts_time:NOPTS duration: 1001\n")
        with self.assertRaisesRegex(RuntimeError, "NOPTS"):
            run([frame_bytes(1)], err)

    def test_nonzero_exit_raises_and_names_the_video(self):
        err = showinfo(0, 0.0) + "ep.mp4: Invalid data found\n"
        with self.assertRaisesRegex(RuntimeError, "ep.mp4"):
            run([frame_bytes(1)], err, returncode=1)

    def test_nonzero_exit_hands_out_nothing_after_failure(self):
        # 不可回傳半套畫面卻不報錯：呼叫端拿 list() 就要拋出
        err = showinfo(0, 0.0) + showinfo(1, 0.2) + "Error while decoding\n"
        with self.assertRaisesRegex(RuntimeError, "Error while decoding"):
            run([frame_bytes(1), frame_bytes(2)], err, returncode=183)


if __name__ == "__main__":
    unittest.main()
