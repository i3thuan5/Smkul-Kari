"""fetch_sftp.sh 的並行集數與 ffmpeg 執行緒數：可調，預設照本機量測。

量到的（2026-09-17 機器閒置時，同一段 120 秒）：ffmpeg 2 緒每核效率
0.88，預設（約 11 核）只有 0.68，同一份工多燒約 30% CPU；實際切 cue 一集
約用 2.4 核，16 核同時跑 6 集。換機器要能改，而且
改錯（0、非數字）要當場擋下，不可以靜靜退回預設值或變成不限並行。

離線：`--print-config` 印出生效值就結束，不連線、不讀清單。
"""
import os
import subprocess
import tempfile
import time
import unittest

from scripts.news import paths

FETCH = os.path.join(paths.ROOT, "scripts", "news", "fetch_sftp.sh")
POOL = os.path.join(paths.ROOT, "scripts", "news", "jobpool.sh")
CHECK = os.path.join(paths.ROOT, "scripts", "news", "videocheck.sh")


def config(*args, **env):
    full = dict(os.environ)
    full.pop("FETCH_JOBS", None)
    full.pop("FFMPEG_THREADS", None)
    full.update(env)
    proc = subprocess.run(["bash", FETCH, "2021-10", "--print-config"]
                          + list(args),
                          capture_output=True, text=True, env=full)
    values = {}
    for line in proc.stdout.splitlines():
        key, _, value = line.partition("=")
        values[key] = value
    return proc, values


class TestDefaults(unittest.TestCase):

    def test_six_episodes_two_threads(self):
        proc, values = config()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(values["jobs"], "6")
        self.assertEqual(values["threads"], "2")


class TestOverrides(unittest.TestCase):

    def test_environment_changes_them(self):
        _, values = config(FETCH_JOBS="4", FFMPEG_THREADS="3")
        self.assertEqual(values["jobs"], "4")
        self.assertEqual(values["threads"], "3")

    def test_flags_beat_the_environment(self):
        _, values = config("--jobs", "2", "--threads", "1",
                           FETCH_JOBS="4", FFMPEG_THREADS="3")
        self.assertEqual(values["jobs"], "2")
        self.assertEqual(values["threads"], "1")

    def test_zero_or_text_is_refused(self):
        # 0 個並行會讓迴圈永遠等不到空位；非數字會讓 bash 算術出錯後
        # 當成 0——兩種都要在開工前擋下
        for bad in ("0", "abc", "-1", ""):
            proc, _ = config("--jobs", bad)
            self.assertEqual(proc.returncode, 2, bad)
            proc, _ = config(FFMPEG_THREADS=bad or "x")
            self.assertEqual(proc.returncode, 2, bad)


class TestJobPool(unittest.TestCase):

    def test_never_more_than_the_limit_at_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = os.path.join(tmp, "events")
            script = (
                'source "%s"\n'
                'for i in 1 2 3 4 5 6 7; do\n'
                '  pool_wait_slot 3\n'
                '  ( echo + >> "%s"; sleep 0.3; echo - >> "%s" ) &\n'
                'done\n'
                'wait\n' % (POOL, log, log))
            started = time.monotonic()
            proc = subprocess.run(["bash", "-c", script],
                                  capture_output=True, text=True)
            elapsed = time.monotonic() - started
            self.assertEqual(proc.returncode, 0, proc.stderr)
            with open(log, encoding="utf-8") as f:
                events = f.read().split()
        running = 0
        peak = 0
        for event in events:
            running += 1 if event == "+" else -1
            peak = max(peak, running)
        self.assertEqual(events.count("+"), 7)
        self.assertEqual(events.count("-"), 7)
        self.assertEqual(peak, 3)
        # 真的有並行：7 個 0.3 秒的工作，一個接一個要 2.1 秒
        self.assertLess(elapsed, 1.8)

    def test_a_failed_job_does_not_stop_the_pool(self):
        script = (
            'source "%s"\n'
            'n=0\n'
            'for i in 1 2 3 4; do\n'
            '  pool_wait_slot 2\n'
            '  ( [ $i -ne 2 ] ) &\n'
            'done\n'
            'wait\n'
            'echo finished\n' % POOL)
        proc = subprocess.run(["bash", "-c", script],
                              capture_output=True, text=True)
        self.assertIn("finished", proc.stdout)


class TestUnreadableVideo(unittest.TestCase):
    """伺服器上的檔本身壞了，不可以被當成「字幕帶不合」而中止整個月。

    2021-10 第一支（21NL003_274午間）位元組數和遠端一致，卻是
    `moov atom not found`：上傳就不完整。當時 `verify_band` 解不出畫面，
    `fetch_sftp.sh` 報「band does not match preset」，一個月 67 集全停。
    """

    def _readable(self, path):
        proc = subprocess.run(
            ["bash", "-c", 'source "%s"; video_readable "$1"' % CHECK,
             "_", path], capture_output=True, text=True)
        return proc.returncode

    def _clip(self, folder):
        path = os.path.join(folder, "ok.mp4")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
                        "-i", "testsrc2=size=64x36:rate=30000/1001",
                        "-t", "2", "-pix_fmt", "yuv420p", path],
                       check=True)
        return path

    def test_a_whole_file_is_readable(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(self._readable(self._clip(tmp)), 0)

    def test_a_file_cut_short_before_its_index_is_not(self):
        # mp4 的 moov 在檔尾：截掉尾巴就整支打不開
        with tempfile.TemporaryDirectory() as tmp:
            path = self._clip(tmp)
            with open(path, "rb") as handle:
                data = handle.read()
            with open(path, "wb") as handle:
                handle.write(data[:len(data) // 2])
            self.assertNotEqual(self._readable(path), 0)

    def test_a_missing_file_is_not(self):
        self.assertNotEqual(self._readable("/nonexistent/x.mp4"), 0)

    def test_fetch_checks_readability_before_the_band(self):
        with open(FETCH, encoding="utf-8") as handle:
            text = handle.read()
        self.assertIn("videocheck.sh", text)
        self.assertLess(text.index("video_readable \"$local_file\""),
                        text.index("scripts.news.verify_band"))


if __name__ == "__main__":
    unittest.main()
