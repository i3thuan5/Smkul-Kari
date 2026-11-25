"""預覽檔ê ffmpeg 指令：三條路徑（全硬體、混合、軟體）逐个參數。

參數攏是《字幕編輯預覽檔規格》（kithann/字幕編輯預覽檔規格_20261027.md）
量過ê；漏一个，毋是慢，是錯：格數走精、起點偏、半截檔傳起去。
指令是 list，直接比對，免真ê ffmpeg。
"""
import subprocess
import unittest

from tools.mkv2mp4wav import encode

SRC = "/tmp/w/開會了_107_Hla'alua_拉阿魯哇.mkv"
DST = "/tmp/w/開會了_107_Hla'alua_拉阿魯哇.preview.mp4"


def text(path, track=0):
    return " ".join(encode.command(SRC, DST, track, path))


class TestHardware(unittest.TestCase):
    def test_spec_3_1_decode_on_the_gpu(self):
        got = text(encode.HARDWARE)
        self.assertIn("-hwaccel vaapi", got)
        self.assertIn("-hwaccel_output_format vaapi", got)
        self.assertIn("-c:v h264_vaapi", got)

    def test_threads_1_is_there(self):
        """無 -threads 1，軟解多執行緒佮 VAAPI surface pool 相拍，
        廣播素材頂懸噴 get_buffer() failed。"""
        cmd = encode.command(SRC, DST, 0, encode.HARDWARE)
        self.assertEqual(cmd[cmd.index("-threads") + 1], "1")
        self.assertLess(cmd.index("-threads"), cmd.index("-i"))

    def test_bob_deinterlace_frame_rate(self):
        """無寫 mode=bob 會用驅動預設：實測規集少 3 格、起點偏 0.066 秒。"""
        got = text(encode.HARDWARE)
        self.assertIn("deinterlace_vaapi=mode=bob:rate=frame", got)
        self.assertIn("scale_vaapi=w=1280:h=720:format=nv12", got)


class TestHybrid(unittest.TestCase):
    """開會了 mp4 是 H.264 High 4:2:2，硬體解袂來（實測全硬體指令直接
    Impossible to convert between the formats）：CPU 解碼、GPU 做其餘。"""

    def test_cpu_decode_then_upload(self):
        got = text(encode.HYBRID)
        self.assertIn("-vaapi_device /dev/dri/renderD128", got)
        self.assertIn(
            "format=nv12,hwupload,deinterlace_vaapi=mode=bob:rate=frame", got)
        self.assertIn("scale_vaapi=w=1280:h=720:format=nv12", got)
        self.assertIn("-c:v h264_vaapi", got)

    def test_single_thread_decode(self):
        """CPU 多執行緒解碼，檔尾 flush 一擺吐傷濟格，hwupload 就
        Cannot allocate memory、離開碼 244：合成 300 格干焦編出 285 格
        （2026-11-23 e2e 量著；頭前 079 干焦轉頭 60 秒，無行到檔尾）。
        -threads 1 了後 300／300。"""
        cmd = encode.command(SRC, DST, 0, encode.HYBRID)
        self.assertIn("-threads", cmd)
        self.assertEqual(cmd[cmd.index("-threads") + 1], "1")
        self.assertLess(cmd.index("-threads"), cmd.index("-i"))

    def test_no_hardware_decode(self):
        got = text(encode.HYBRID)
        self.assertNotIn("-hwaccel vaapi", got)
        self.assertNotIn("-hwaccel_output_format", got)


class TestSoftware(unittest.TestCase):
    def test_yadif_one_frame_per_frame_every_frame(self):
        """yadif=0:-1:0：一格出一格、每格攏處理。yadif=1 格數加倍；
        deint=1 會跳過標記 progressive ê格——開會了 mp4 就是標 progressive
        實際交錯。"""
        got = text(encode.SOFTWARE)
        self.assertIn("yadif=0:-1:0,scale=1280:-2,format=yuv420p", got)
        self.assertNotIn("yadif=1", got)
        self.assertNotIn("deint=1", got)
        self.assertIn("-c:v libx264", got)
        self.assertNotIn("vaapi", got)


class TestAllPaths(unittest.TestCase):
    PATHS = (encode.HARDWARE, encode.HYBRID, encode.SOFTWARE)

    def test_the_chosen_audio_track(self):
        """107 換音軌進前ê原檔第一條靜音：選第二條就愛 map 第二條。"""
        for path in self.PATHS:
            cmd = encode.command(SRC, DST, 1, path)
            self.assertIn("0:a:1", cmd)
            self.assertNotIn("0:a:0", cmd)
            self.assertIn("0:v:0", cmd)

    def test_frame_times_are_passed_through(self):
        """無 -fps_mode passthrough，寫 MP4 會補格抑丟格，逐擺 33 毫秒、
        閣會累積；嘛袂使出現 -r。"""
        for path in self.PATHS:
            cmd = encode.command(SRC, DST, 0, path)
            self.assertEqual(cmd[cmd.index("-fps_mode") + 1], "passthrough")
            self.assertNotIn("-r", cmd)

    def test_no_padding_or_shifting(self):
        """實測 tpad 補 0.033 秒烏畫面，頭一格對 0.033 推去 0.067，規集
        慢一格。"""
        for path in self.PATHS:
            got = text(path)
            self.assertNotIn("tpad", got)
            self.assertNotIn("setpts", got)

    def test_rate_and_gop(self):
        for path in self.PATHS:
            got = text(path)
            self.assertIn("-b:v 1200k -maxrate 1800k -bufsize 3600k", got)
            self.assertIn("-g 30 -bf 0", got)
            self.assertIn("-profile:v high", got)
            self.assertIn("-c:a aac -b:a 128k -ac 1", got)

    def test_no_keyboard_no_timecode_index_first(self):
        """-nostdin：終端機按著 q，ffmpeg 好好收尾出一支短檔（10-06 有 8 支
        半截 mkv 傳起去）。-write_tmcd 0：帶時間碼軌，剪輯軟體對
        01:00:00;00 起算、佮 SRT 對袂起來。+faststart：瀏覽器愛先讀著索引。"""
        for path in self.PATHS:
            cmd = encode.command(SRC, DST, 0, path)
            self.assertIn("-nostdin", cmd)
            self.assertEqual(cmd[cmd.index("-write_tmcd") + 1], "0")
            self.assertEqual(cmd[cmd.index("-movflags") + 1], "+faststart")
            self.assertEqual(cmd[-1], DST)

    def test_low_priority(self):
        """無 nice／ionice，軟體路徑食滿全部核心（2888 核心秒／集）。"""
        for path in self.PATHS:
            cmd = encode.command(SRC, DST, 0, path)
            self.assertEqual(cmd[:6],
                             ["nice", "-n", "15", "ionice", "-c", "3"])
            self.assertEqual(cmd[6], "ffmpeg")

    def test_input_is_the_source(self):
        for path in self.PATHS:
            cmd = encode.command(SRC, DST, 0, path)
            self.assertEqual(cmd[cmd.index("-i") + 1], SRC)


class TestEncodeRun(unittest.TestCase):
    """跑 ffmpeg ê薄層：逾時、喝停、一般失敗愛分清楚。"""

    def go(self, outcome, logged=None):
        def run(cmd, **kwargs):
            self.kwargs = kwargs
            if isinstance(outcome, Exception):
                raise outcome
            return subprocess.CompletedProcess(cmd, outcome, "", "ffmpeg 講ê話")

        return encode.encode(["ffmpeg"], 2880.0, logged.append
                             if logged is not None else (lambda t: None),
                             run=run)

    def test_timeout_is_the_source_duration(self):
        """正常 7–8 倍速；跑滿 1 倍速猶未煞就是卡死矣。"""
        self.go(0)
        self.assertEqual(self.kwargs["timeout"], 2880.0)

    def test_stuck_encode_is_an_ordinary_failure_not_an_interrupt(self):
        with self.assertRaises(encode.EncodeError) as caught:
            self.go(subprocess.TimeoutExpired(["ffmpeg"], 2880.0))
        self.assertIn("2880", str(caught.exception))

    def test_signal_exits_stop_the_whole_batch(self):
        """ffmpeg 收著 SIGINT 好好收尾離開碼 255；包佇 nice／ionice 內底
        回傳碼仝款（exec 落去，毋是子行程）。"""
        for code in (255, 130, -2, -15):
            with self.assertRaises(KeyboardInterrupt):
                self.go(code)

    def test_ordinary_failure(self):
        with self.assertRaises(encode.EncodeError):
            self.go(1)

    def test_stderr_goes_to_the_log(self):
        logged = []
        self.go(0, logged)
        self.assertIn("ffmpeg 講ê話", "".join(logged))


if __name__ == "__main__":
    unittest.main()
