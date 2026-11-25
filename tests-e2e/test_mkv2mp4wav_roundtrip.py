"""tools/mkv2mp4wav 一集走規條，用真ê ffmpeg：編碼、驗收、音軌選擇、WAV。

佮 tests/mkv2mp4wav/ 無仝：遐是純邏輯；遮愛真ê編碼器，排佇 tox -e
e2etest。Fixture 走測試ê時才用 lavfi 合成，走煞就刣。SFTP 用假ê替代
（抄去一个本機資料夾）——網路毋是這篇欲測ê物件。

軟體路徑一定走；全硬體佮混合路徑愛 /dev/dri/renderD128，無就 skip
（CI 永遠 skip，本機愛過）。
"""
import filecmp
import os
import shutil
import subprocess
import tempfile
import unittest

from tools.sftpbatch import batch
from tools.mkv2mp4wav import audio
from tools.mkv2mp4wav import encode
from tools.mkv2mp4wav import run
from tools.mkv2mp4wav import verify

DEVICE = "/dev/dri/renderD128"


def have_ffmpeg():
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            return False
    return True


def have_vaapi():
    return have_ffmpeg() and encode.probe_vaapi()[0]


def ffmpeg(args):
    done = subprocess.run(["ffmpeg", "-hide_banner", "-v", "error", "-y"]
                          + args, capture_output=True, text=True)
    if done.returncode:
        raise AssertionError("合成失敗：%s" % done.stderr)


def make_interlaced_mkv(path):
    """開會了 mkv／新聞封存檔ê款：1080i 4:2:0、兩條 FLAC 24-bit、第一條靜音。"""
    args = ["-f", "lavfi", "-i",
            "testsrc2=s=1920x1080:r=30000/1001:d=3",
            "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono",
            "-f", "lavfi", "-i", "sine=f=440:r=48000:d=3"]
    args += ["-map", "0:v", "-map", "1:a", "-map", "2:a", "-t", "3",
             "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
             "-flags", "+ildct+ilme", "-top", "1",
             "-c:a", "flac", "-sample_fmt", "s32", "-bits_per_raw_sample",
             "24", "-ac", "1", path]
    ffmpeg(args)


def make_late_video_mkv(path):
    """新聞 20210101_001_午間_Rukai_魯凱 ê款：影像對 0.033 秒開始、聲音 0。"""
    ffmpeg(["-itsoffset", "0.0333667",
            "-f", "lavfi", "-i", "testsrc2=s=1920x1080:r=30000/1001:d=3",
            "-f", "lavfi", "-i", "sine=f=440:r=48000:d=3.1",
            "-map", "0:v", "-map", "1:a",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-flags", "+ildct+ilme", "-top", "1",
            "-c:a", "flac", "-sample_fmt", "s32", "-bits_per_raw_sample",
            "24", "-ac", "1", path])


def make_422_mp4(path):
    """開會了 mp4 ê款：H.264 High 4:2:2、標 progressive、AAC 單聲道。"""
    ffmpeg(["-f", "lavfi", "-i", "testsrc2=s=1920x1080:r=30000/1001:d=3",
            "-f", "lavfi", "-i", "sine=f=660:r=48000:d=3",
            "-map", "0:v", "-map", "1:a", "-t", "3",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv422p",
            "-c:a", "aac", "-b:a", "128k", "-ac", "1", path])


@unittest.skipUnless(have_ffmpeg(), "需要 ffmpeg 佮 ffprobe")
class EpisodeCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.work = os.path.join(self.tmp, "work")
        self.landed = os.path.join(self.tmp, "server")
        self.sources = os.path.join(self.tmp, "sources")
        for folder in (self.work, self.landed, self.sources):
            os.makedirs(folder)

    def tools(self):
        """The real encoders and probes; a local folder for the server."""
        tools = run.Tools()
        landed = self.landed

        def put(local, remote, size):
            shutil.copy(local, os.path.join(landed, os.path.basename(remote)))
            return size

        tools.sftp = None
        tools.already_there = lambda remote: False
        tools.put = put
        tools.fetch = lambda remote, local: shutil.copy(remote, local)
        return tools

    def one(self, source, software, name="開會了_101_Amis_阿美"):
        class Program:
            @staticmethod
            def locate(job, sftp, log):
                return source, "測試"

        job = batch.Job(name, None, preview="/x/mp4/%s.mp4" % name,
                        wav="/x/wav/%s.wav" % name)
        logged = []
        entry = run.one_episode(job, Program, self.work, software,
                                logged.append, self.tools())
        self.assertEqual(entry["結果"], "成功",
                         "%s\n%s" % (entry, "".join(logged)))
        return (entry, os.path.join(self.landed, name + ".mp4"),
                os.path.join(self.landed, name + ".wav"))

    def assert_landed_good(self, source, preview, wav, track):
        facts = run.probe_source(source)
        wanted = {"frames": facts["frames"],
                  "video_start": facts["video_start"],
                  "audio_start": run._start(facts["audio"][track]),
                  "duration": facts["duration"]}
        self.assertEqual(
            verify.problems(verify.check_all(wanted, verify.probe(preview))),
            [])
        info = audio.probe(wav)
        stream = info["streams"][0]
        self.assertEqual(stream["codec_name"], "pcm_s16le")
        self.assertEqual(stream["sample_rate"], "24000")
        self.assertEqual(os.listdir(self.work), [])


class TestSoftware(EpisodeCase):
    def test_interlaced_mkv_with_a_silent_first_track(self):
        source = os.path.join(self.sources, "a.mkv")
        make_interlaced_mkv(source)
        entry, preview, wav = self.one(source, software=True)
        self.assertEqual(entry["音軌"]["第幾條"], 2)
        self.assertEqual(entry["預覽檔"]["編碼路徑"], encode.SOFTWARE)
        self.assert_landed_good(source, preview, wav, 1)

    def test_422_mp4_flagged_progressive(self):
        source = os.path.join(self.sources, "b.mp4")
        make_422_mp4(source)
        entry, preview, wav = self.one(source, software=True)
        self.assertEqual(entry["音軌"]["第幾條"], 1)
        self.assert_landed_good(source, preview, wav, 0)

    def test_news_video_starting_at_0_033_keeps_its_start(self):
        """起點照來源，袂補烏畫面（實測 tpad 會共規集推慢一格）。"""
        source = os.path.join(self.sources, "rukai.mkv")
        make_late_video_mkv(source)
        facts = run.probe_source(source)
        self.assertGreater(facts["video_start"], 0.03)
        _entry, preview, wav = self.one(
            source, software=True, name="20210101_001_午間_Rukai_魯凱")
        got = verify.probe(preview)
        self.assertAlmostEqual(got["video_start"], facts["video_start"],
                               places=3)
        self.assert_landed_good(source, preview, wav, 0)

    def test_the_same_source_gives_the_same_wav_twice(self):
        source = os.path.join(self.sources, "a.mkv")
        make_interlaced_mkv(source)
        first = os.path.join(self.tmp, "1.wav")
        second = os.path.join(self.tmp, "2.wav")
        audio.convert(source, first, 1, lambda text: None)
        audio.convert(source, second, 1, lambda text: None)
        self.assertTrue(filecmp.cmp(first, second, shallow=False))
        with open(first, "rb") as handle:
            head = handle.read(64)
        self.assertNotIn(b"Lavf", head)


@unittest.skipUnless(have_vaapi(),
                     "需要 %s 而且 h264_vaapi 編會出來（CI 無 GPU）" % DEVICE)
class TestGpu(EpisodeCase):
    def test_420_mkv_goes_all_hardware(self):
        source = os.path.join(self.sources, "a.mkv")
        make_interlaced_mkv(source)
        entry, preview, wav = self.one(source, software=False)
        self.assertEqual(entry["預覽檔"]["編碼路徑"], encode.HARDWARE)
        self.assert_landed_good(source, preview, wav, 1)

    def test_news_video_starting_at_0_033_all_hardware(self):
        source = os.path.join(self.sources, "rukai.mkv")
        make_late_video_mkv(source)
        entry, preview, wav = self.one(
            source, software=False, name="20210101_001_午間_Rukai_魯凱")
        self.assertEqual(entry["預覽檔"]["編碼路徑"], encode.HARDWARE)
        self.assert_landed_good(source, preview, wav, 0)

    def test_422_mp4_goes_hybrid(self):
        source = os.path.join(self.sources, "b.mp4")
        make_422_mp4(source)
        entry, preview, wav = self.one(source, software=False)
        self.assertEqual(entry["預覽檔"]["編碼路徑"], encode.HYBRID)
        self.assert_landed_good(source, preview, wav, 0)


if __name__ == "__main__":
    unittest.main()
