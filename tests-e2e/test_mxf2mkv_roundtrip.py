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
import math
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from tools.mxf2mkv import batch
from tools.mxf2mkv import run as runner
from tools.sftpbatch import upload


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


def write_s24le(path, low_byte_xor=0):
    """兩秒 440 Hz ê 24-bit 單聲道原始 PCM；`low_byte_xor` 改逐个取樣
    上低彼个位元組——干焦下跤 8 位元無仝，上懸 16 位元一模一樣。"""
    data = bytearray()
    for index in range(2 * 48000):
        value = int(math.sin(2 * math.pi * 440 * index / 48000)
                    * 0.5 * (2 ** 23 - 1))
        raw = bytearray(value.to_bytes(4, "little", signed=True)[:3])
        raw[0] ^= low_byte_xor
        data += raw
    with open(path, "wb") as handle:
        handle.write(bytes(data))


def make_mxf_low_bits_differ(path, work):
    """一支兩軌ê mxf：第二軌是第一軌干焦改下跤 8 位元。"""
    first = os.path.join(work, "a0.s24")
    second = os.path.join(work, "a1.s24")
    write_s24le(first)
    write_s24le(second, low_byte_xor=0x5A)
    cmd = ["ffmpeg", "-hide_banner", "-v", "error", "-y",
           "-f", "lavfi", "-i", "testsrc2=s=320x240:r=25:d=2"]
    for raw in (first, second):
        cmd += ["-f", "s24le", "-ar", "48000", "-ac", "1", "-i", raw]
    cmd += ["-map", "0:v", "-map", "1:a", "-map", "2:a",
            "-c:v", "mpeg2video", "-pix_fmt", "yuv420p", "-b:v", "500k",
            "-c:a", "pcm_s24le", "-ar", "48000", "-ac", "1", "-f", "mxf",
            path]
    done = subprocess.run(cmd, capture_output=True, text=True)
    os.remove(first)
    os.remove(second)
    if done.returncode:
        raise AssertionError("合成 mxf 失敗：%s" % done.stderr)


def audio_sha256s(path):
    """逐軌取樣ê SHA-256，以 32-bit 算——佮封存程式仝款涵蓋 24 位元。"""
    out = []
    index = 0
    while True:
        done = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", path, "-map", "0:a:%d" % index,
             "-c:a", "pcm_s32le", "-f", "hash", "-hash", "sha256", "-"],
            capture_output=True, text=True)
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
        self.assertEqual(len(audio_sha256s(archive)), 1)

    def test_two_differing_tracks_both_survive(self):
        source, entry, archive = self.one([440, 660])
        self.assertEqual(entry["audio_tracks_kept"], 2)
        self.assertEqual(entry["音軌"], "兩軌不同，兩條都留")
        self.assertEqual(len(audio_sha256s(archive)), 2)

    def test_three_tracks_with_a_duplicate_pair(self):
        """舊版干焦 map a:0 佮 a:1，第三軌會恬恬無去。"""
        source, entry, archive = self.one([440, 440, 660])
        self.assertEqual(entry["audio_tracks_src"], 3)
        self.assertEqual(entry["audio_tracks_kept"], 2)
        self.assertEqual(len(audio_sha256s(archive)), 2)

    def test_a_single_track_is_carried_through(self):
        source, entry, archive = self.one([440])
        self.assertEqual(entry["audio_tracks_kept"], 1)
        self.assertEqual(entry["音軌"], "一軌")

    def test_tracks_differing_only_in_the_low_8_bits_are_both_kept(self):
        """ffmpeg ê -f md5 預設先轉 16-bit 才算：兩條 24-bit 音軌干焦差佇
        下跤 8 位元，舊算法會講「兩軌相同」、擲掉一條真正無仝ê聲音。"""
        source = os.path.join(self.src_root, "low.mxf")
        make_mxf_low_bits_differ(source, self.tmp)
        job = batch.Job("low.mxf", source, "/home/mkv-raw/2月原始mxf檔/low.mkv")
        with self.fake_upload():
            entry = runner.one_file(job, self.work)
        archive = os.path.join(self.landed, "low.mkv")
        self.assertEqual(entry["audio_tracks_kept"], 2)
        self.assertEqual(entry["音軌"], "兩軌不同，兩條都留")
        self.assertEqual(audio_sha256s(source), audio_sha256s(archive))
        hashes = audio_sha256s(archive)
        self.assertNotEqual(hashes[0], hashes[1])
        self.assertEqual(len(hashes[0]), len("SHA256=") + 64)

    def test_the_audio_survives_bit_for_bit(self):
        """這篇上要緊ê一條：語料就是欲提去訓練聲學模型ê。"""
        source, entry, archive = self.one([440, 660])
        self.assertTrue(entry["音訊逐位元相符"])
        self.assertEqual(audio_sha256s(source), audio_sha256s(archive))

    def test_nothing_is_left_in_the_work_dir(self):
        """隨身硬碟本身欲滇矣，中間產物袂使留咧。"""
        self.one([440, 440])
        self.assertEqual(os.listdir(self.work), [])

    def test_the_source_is_untouched(self):
        source, _entry, _archive = self.one([440, 440])
        self.assertTrue(os.path.exists(source))


if __name__ == "__main__":
    unittest.main()
