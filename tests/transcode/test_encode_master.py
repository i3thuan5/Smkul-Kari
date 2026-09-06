"""encode_master.sh: 一趟 ffmpeg 愛按怎兜參數。

這隻走 `ENCODE_DRY_RUN=1`，干焦共欲送出ê ffmpeg 指令印出來，無真正
編碼——所以佇 CI（無 ffmpeg）嘛走會過。`ffprobe` 用 PATH 頭前ê假
程式擋落來，按呢音軌數佮音訊編碼是測試家己決定ê，免真ê影片。

會遮爾細膩測參數ê理由：`-map` 若展開毋著，指紋就算著別軌ê聲音。
算毋著ê結果若是「對袂起來」，好ê檔案會失敗，彼真吵，人會發現；
若是「這兩軌相仝」，就恬恬擲掉一條無仝ê聲音，彼無聲無說。
"""
import os
import shutil
import stat
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SCRIPT = os.path.join(ROOT, "scripts", "transcode", "encode_master.sh")

# 假 ffprobe：看引數內底問ê是啥，才決定欲應啥。
FAKE_FFPROBE = """#!/bin/bash
for arg in "$@"; do
  case "$arg" in
    *codec_name*) echo "$FAKE_CODEC"; exit 0 ;;
  esac
done
# 賰ê是咧數音軌，一軌印一逝
i=0
while [ "$i" -lt "$FAKE_TRACKS" ]; do echo "$i"; i=$((i + 1)); done
"""


class EncodeMasterDryRun(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.bin = os.path.join(self.tmp, "bin")
        os.makedirs(self.bin)
        fake = os.path.join(self.bin, "ffprobe")
        with open(fake, "w", encoding="utf-8") as handle:
            handle.write(FAKE_FFPROBE)
        os.chmod(fake, os.stat(fake).st_mode | stat.S_IEXEC)
        self.work = os.path.join(self.tmp, "work")
        os.makedirs(self.work)
        self.src = os.path.join(self.tmp, "a.mxf")
        with open(self.src, "w", encoding="utf-8") as handle:
            handle.write("not really a video")

    def run_dry(self, tracks=2, codec="pcm_s24le", extra=()):
        env = dict(os.environ)
        env["PATH"] = self.bin + os.pathsep + env["PATH"]
        env["ENCODE_DRY_RUN"] = "1"
        env["FAKE_TRACKS"] = str(tracks)
        env["FAKE_CODEC"] = codec
        done = subprocess.run(
            ["bash", SCRIPT, self.src, self.work, "a"] + list(extra),
            capture_output=True, text=True, env=env)
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout


class TestOneFfmpegPass(EncodeMasterDryRun):
    def test_only_one_ffmpeg_invocation(self):
        """規个改動ê重點：來源干焦讀一擺。

        舊版讀三擺（比音軌、編碼、驗證），一支 19 GB ê母帶佇 USB
        碟就是 57 GB ê讀取。
        """
        out = self.run_dry(tracks=2)
        self.assertEqual(out.count("ffmpeg"), 1)

    def test_no_pre_pass_comparing_tracks(self):
        """袂當閣有彼逝「先共兩軌比較」ê預先讀取。"""
        out = self.run_dry(tracks=2)
        self.assertNotIn("checking whether", out)


class TestTrackMaps(EncodeMasterDryRun):
    def test_single_track(self):
        out = self.run_dry(tracks=1)
        self.assertIn("-map 0:v:0", out)
        self.assertIn("-map 0:a:0", out)
        self.assertNotIn("0:a:1", out)

    def test_two_tracks(self):
        out = self.run_dry(tracks=2)
        self.assertIn("-map 0:a:0", out)
        self.assertIn("-map 0:a:1", out)
        self.assertNotIn("0:a:2", out)

    def test_three_tracks_are_all_carried(self):
        """三軌以上袂使閣恬恬無去——舊版就是佇遮漏ê。"""
        out = self.run_dry(tracks=3)
        for index in range(3):
            self.assertIn("-map 0:a:%d" % index, out)


class TestMd5Outputs(EncodeMasterDryRun):
    def test_one_md5_output_per_track(self):
        out = self.run_dry(tracks=3)
        for index in range(3):
            self.assertIn("a.src-a%d.md5" % index, out)

    def test_md5_output_count_matches_tracks(self):
        out = self.run_dry(tracks=2)
        self.assertEqual(out.count("-f md5"), 2)
        self.assertNotIn("a.src-a2.md5", out)

    def test_md5_is_paired_with_its_own_track(self):
        """第 i 个 md5 輸出頭前愛是第 i 軌ê -map，順序袂使走精。"""
        out = self.run_dry(tracks=2)
        first = out.index("a.src-a0.md5")
        second = out.index("a.src-a1.md5")
        self.assertLess(out.index("-map 0:a:0", out.index("-f md5") - 200),
                        first)
        self.assertLess(first, second)


class TestAudioCodec(EncodeMasterDryRun):
    def test_integer_pcm_goes_to_flac(self):
        out = self.run_dry(codec="pcm_s24le")
        self.assertIn("-c:a flac", out)
        self.assertIn("-compression_level 8", out)

    def test_float_decoding_source_is_copied(self):
        """AAC 解出來是浮點，轉去 FLAC ê整數愛捨入——彼是真ê資料改變。

        2021-02-09 晚間 雅美彼支就是按呢予逐位元檢查擋落來ê。
        """
        out = self.run_dry(codec="aac")
        self.assertIn("-c:a copy", out)
        self.assertNotIn("-c:a flac", out)


class TestVideoParams(EncodeMasterDryRun):
    def test_defaults(self):
        out = self.run_dry()
        self.assertIn("-c:v libx264", out)
        self.assertIn("-crf 23", out)
        self.assertIn("-pix_fmt yuv420p", out)

    def test_caller_can_override(self):
        out = self.run_dry(extra=["18", "yuv422p"])
        self.assertIn("-crf 18", out)
        self.assertIn("-pix_fmt yuv422p", out)


class TestOutputPath(EncodeMasterDryRun):
    def test_archive_lands_in_the_work_dir_under_the_given_name(self):
        out = self.run_dry()
        self.assertIn(os.path.join(self.work, "a.all.mkv"), out)


if __name__ == "__main__":
    unittest.main()
