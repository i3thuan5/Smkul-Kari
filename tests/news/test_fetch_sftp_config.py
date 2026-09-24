"""fetch_sftp.sh 的並行集數與 ffmpeg 執行緒數：可調，預設照本機量測。

量到的（2026-09-17 機器閒置時，同一段 120 秒）：ffmpeg 2 緒每核效率
0.88，預設（約 11 核）只有 0.68，同一份工多燒約 30% CPU；實際切 cue 一集
約用 2.4 核，16 核同時跑 6 集。換機器要能改，而且
改錯（0、非數字）要當場擋下，不可以靜靜退回預設值或變成不限並行。

離線：`--print-config` 印出生效值就結束，不連線、不讀清單。
"""
import os
import subprocess
import sys
import tempfile
import time
import unittest

from scripts.news import paths

FETCH = os.path.join(paths.ROOT, "scripts", "news", "fetch_sftp.sh")
POOL = os.path.join(paths.ROOT, "scripts", "news", "jobpool.sh")
CHECK = os.path.join(paths.ROOT, "scripts", "news", "videocheck.sh")


def config(*args, month="2021-10", **env):
    full = dict(os.environ)
    full.pop("FETCH_JOBS", None)
    full.pop("FFMPEG_THREADS", None)
    full.update(env)
    proc = subprocess.run(["bash", FETCH, month, "--print-config"]
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


class TestRemoteListingTakesMkv(unittest.TestCase):
    """2022–2024 新母帶佇 `/home/mkv-raw/`，全部是 .mkv。

    列伺服器檔案彼段本底干焦收 .mp4／.mxf，.mkv 拄著就講「伺服器頂懸
    無」、跳過——24 集試做是用另外一支腳本繞過去才做會落去。
    """

    def listing(self, *names):
        lines = []
        for name in names:
            lines.append("-rw-r--r--    1 u g  2863094396 Jun 25 2023 "
                         + name)
        script = open(FETCH, encoding="utf-8").read()
        start = script.index("import sys\nfolder = sys.argv[1]")
        body = script[start:script.index("' \"$folder\"", start)]
        proc = subprocess.run(
            [sys.executable, "-c", body, "/home/mkv-raw/113/12月"],
            input="\n".join(lines) + "\n", capture_output=True, text=True,
            cwd=paths.ROOT)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout

    def test_an_mkv_gets_its_size(self):
        out = self.listing("20241201S0800.mkv")
        self.assertIn("/home/mkv-raw/113/12月/20241201S0800.mkv\t2863094396",
                      out)

    def test_the_old_formats_still_count(self):
        out = self.listing("a.mp4", "b.MXF")
        self.assertIn("a.mp4", out)
        self.assertIn("b.MXF", out)

    def test_other_files_are_left_out(self):
        self.assertEqual(self.listing("清單.xlsx"), "")


class TestPresetFollowsTheMonth(unittest.TestCase):
    """無指定 `--preset` 就照月份：2021-11 起ê母帶紅條上緣 852，用 848。

    本底預設 `titv-news`（844）；2024 年照預設切，羅馬字ê下伸筆畫攏
    切去 1–5 px，閣無一个所在會報。
    """

    def test_2021_october_takes_844(self):
        _, values = config()
        self.assertEqual(values["preset"], "titv-news")

    def test_2024_july_takes_848(self):
        _, values = config(month="2024-07")
        self.assertEqual(values["preset"], "titv-news-848")

    def test_2024_december_takes_the_centred_layout(self):
        # 2024-08 起字幕置中、落到 y 860–925（2026-09-24 逐月量過）。
        _, values = config(month="2024-12")
        self.assertEqual(values["preset"], "titv-news-2024-08")

    def test_an_explicit_preset_still_wins(self):
        _, values = config("--preset", "titv-news", month="2024-12")
        self.assertEqual(values["preset"], "titv-news")


class TestNameBarsWhileTheVideoIsHere(unittest.TestCase):
    """受訪者名條愛佇影片刣掉進前截：2024-12 事後補，69 集攏愛重抓母帶。"""

    def after_cut(self):
        script = open(FETCH, encoding="utf-8").read()
        start = script.index("after_cut() {")
        return script[start:script.index("\n}\n", start)]

    def test_name_bars_are_grabbed_after_the_shot_features(self):
        block = self.after_cut()
        self.assertIn("scripts.news.namebars grab", block)
        self.assertIn('--preset "$PRESET"', block[block.index("namebars"):])
        self.assertLess(block.index("scripts.news.shots extract"),
                        block.index("scripts.news.namebars grab"))


class TestOpeningOnly(unittest.TestCase):
    """`--opening-only`：已經入庫ê集數補截片頭，毋切 cue。"""

    def test_the_mode_is_reported(self):
        _, values = config("--opening-only")
        self.assertEqual(values["mode"], "opening")

    def test_the_default_mode_cuts(self):
        _, values = config()
        self.assertEqual(values["mode"], "cut")

    def test_opening_mode_never_calls_the_cutter(self):
        script = open(FETCH, encoding="utf-8").read()
        start = script.index("if [[ -n \"$OPENING_ONLY\" ]]; then\n")
        end = script.index("\nfi\n", start)
        block = script[start:end]
        self.assertNotIn("scripts.ocr.cli", block)
        self.assertIn("grab-remote", block)
        self.assertIn("exit", block)


if __name__ == "__main__":
    unittest.main()
