"""tools/mxf2mkv 規條线走一擺，用真ê ffmpeg。

佮 tests/mxf2mkv/ 無仝：遐是純邏輯，CI 走會著；遮愛真ê編碼器，所以
排佇 tox -e e2etest。

Fixture 是走測試ê時陣才用 ffmpeg 家己ê lavfi 合成ê，走煞就刣掉，git
內底一支 mxf 都無。MXF ê muxer 真厚工，三个條件缺一不可：音訊 48 kHz
（sine 預設 44100，寫袂出 header，錯誤訊息看起來若像是權限問題）、
視訊 yuv420p、影格率愛是廣播標準值。

SFTP 彼爿用假ê替代——網路毋是這篇欲測ê物件，這篇欲測ê是「聲音有無
逐位元活過來」佮「軌留了著無」。
"""
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from tools.mxf2mkv import batch
from tools.mxf2mkv import run as runner
from tools.mxf2mkv import upload


def have_ffmpeg():
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            return False
    return True


def make_mxf(path, tones):
    """一支細細ê mxf，音軌照 `tones` 排（仝一个數字＝仝一份訊號）。"""
    cmd = ["ffmpeg", "-hide_banner", "-v", "error", "-y",
           "-f", "lavfi", "-i", "testsrc2=s=320x240:r=25:d=2"]
    unique = sorted(set(tones))
    for tone in unique:
        cmd += ["-f", "lavfi", "-i",
                "sine=f=%d:d=2:r=48000" % tone]
    cmd += ["-map", "0:v"]
    for tone in tones:
        cmd += ["-map", "%d:a" % (unique.index(tone) + 1)]
    cmd += ["-c:v", "mpeg2video", "-pix_fmt", "yuv420p", "-b:v", "500k",
            "-c:a", "pcm_s24le", "-ar", "48000", "-ac", "1", "-f", "mxf",
            path]
    done = subprocess.run(cmd, capture_output=True, text=True)
    if done.returncode:
        raise AssertionError("合成 mxf 失敗：%s" % done.stderr)


def audio_md5s(path):
    out = []
    index = 0
    while True:
        done = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", path, "-map", "0:a:%d" % index,
             "-f", "md5", "-"], capture_output=True, text=True)
        if done.returncode:
            return out
        out.append(done.stdout.strip())
        index += 1


@unittest.skipUnless(have_ffmpeg(), "需要 ffmpeg 佮 ffprobe")
class RoundTrip(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.src_root = os.path.join(self.tmp, "2月原始mxf檔")
        os.makedirs(self.src_root)
        self.work = os.path.join(self.tmp, "work")
        os.makedirs(self.work)
        self.landed = os.path.join(self.tmp, "server")
        os.makedirs(self.landed)

    def fake_upload(self):
        """假ê SFTP：共檔案抄去 self.landed，回傳位元組數。"""
        def put(local, remote, local_size):
            dst = os.path.join(self.landed, os.path.basename(remote))
            shutil.copy(local, dst)
            return os.path.getsize(dst)

        return mock.patch.object(upload, "put", put)

    def one(self, tones, name="a.mxf"):
        source = os.path.join(self.src_root, name)
        make_mxf(source, tones)
        job = batch.Job(name, source,
                        "/home/mkv-raw/2月原始mxf檔/" + name[:-4] + ".mkv")
        with self.fake_upload():
            entry = runner.one_file(job, self.work)
        return source, entry, os.path.join(self.landed, name[:-4] + ".mkv")

    def test_two_identical_tracks_land_as_one(self):
        source, entry, archive = self.one([440, 440])
        self.assertEqual(entry["audio_tracks_src"], 2)
        self.assertEqual(entry["audio_tracks_kept"], 1)
        self.assertEqual(entry["音軌"], "兩軌相同，留一軌")
        self.assertEqual(len(audio_md5s(archive)), 1)

    def test_two_differing_tracks_both_survive(self):
        source, entry, archive = self.one([440, 660])
        self.assertEqual(entry["audio_tracks_kept"], 2)
        self.assertEqual(entry["音軌"], "兩軌不同，兩條都留")
        self.assertEqual(len(audio_md5s(archive)), 2)

    def test_three_tracks_with_a_duplicate_pair(self):
        """舊版干焦 map a:0 佮 a:1，第三軌會恬恬無去。"""
        source, entry, archive = self.one([440, 440, 660])
        self.assertEqual(entry["audio_tracks_src"], 3)
        self.assertEqual(entry["audio_tracks_kept"], 2)
        self.assertEqual(len(audio_md5s(archive)), 2)

    def test_a_single_track_is_carried_through(self):
        source, entry, archive = self.one([440])
        self.assertEqual(entry["audio_tracks_kept"], 1)
        self.assertEqual(entry["音軌"], "一軌")

    def test_the_audio_survives_bit_for_bit(self):
        """這篇上要緊ê一條：語料就是欲提去訓練聲學模型ê。"""
        source, entry, archive = self.one([440, 660])
        self.assertTrue(entry["音訊逐位元相符"])
        self.assertEqual(audio_md5s(source), audio_md5s(archive))

    def test_nothing_is_left_in_the_work_dir(self):
        """隨身硬碟本身欲滇矣，中間產物袂使留咧。"""
        self.one([440, 440])
        self.assertEqual(os.listdir(self.work), [])

    def test_the_source_is_untouched(self):
        source, _entry, _archive = self.one([440, 440])
        self.assertTrue(os.path.exists(source))


if __name__ == "__main__":
    unittest.main()
