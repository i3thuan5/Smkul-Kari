"""編碼路徑按怎揀：預設只用硬體，依來源自動揀全硬體抑混合；
加 --software 才規批改軟體。

單集硬體失敗袂使家己改軟體重做（驅動出問題時規批會恬恬食滿 CPU）——
彼條佇 test_failure.py；開跑前無硬體就停、一支都無下載，佇 test_preflight.py。
"""
import subprocess
import unittest

from tools.mkv2mp4wav import encode


class TestChoosePath(unittest.TestCase):
    def test_420_goes_all_hardware(self):
        """新聞、開會了 mkv：規格書 3.1。"""
        self.assertEqual(encode.choose_path("yuv420p", False), encode.HARDWARE)

    def test_422_goes_hybrid(self):
        """開會了 mp4（079 實測 H.264 High 4:2:2）：全硬體指令直接失敗。"""
        self.assertEqual(encode.choose_path("yuv422p", False), encode.HYBRID)

    def test_anything_else_not_420_goes_hybrid(self):
        for fmt in ("yuv422p10le", "yuvj422p", "yuv444p"):
            self.assertEqual(encode.choose_path(fmt, False), encode.HYBRID)

    def test_software_flag_wins_for_every_source(self):
        for fmt in ("yuv420p", "yuv422p"):
            self.assertEqual(encode.choose_path(fmt, True), encode.SOFTWARE)


class TestProbeVaapi(unittest.TestCase):
    def test_no_device_is_not_usable_and_says_so(self):
        ran = []
        ok, reason = encode.probe_vaapi(
            device="/nonexistent/renderD128",
            run=lambda *a, **k: ran.append(a))
        self.assertFalse(ok)
        self.assertIn("/nonexistent/renderD128", reason)
        self.assertEqual(ran, [])

    def test_device_present_but_encoder_fails(self):
        def run(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 1, "", "No VA display")

        ok, reason = encode.probe_vaapi(device="/dev/null", run=run)
        self.assertFalse(ok)
        self.assertIn("No VA display", reason)

    def test_one_synthetic_frame_through_h264_vaapi(self):
        seen = []

        def run(cmd, **kwargs):
            seen.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, "", "")

        ok, _ = encode.probe_vaapi(device="/dev/null", run=run)
        self.assertTrue(ok)
        got = " ".join(seen[0])
        self.assertIn("h264_vaapi", got)
        self.assertIn("lavfi", got)
        self.assertIn("-frames:v 1", got)


if __name__ == "__main__":
    unittest.main()
