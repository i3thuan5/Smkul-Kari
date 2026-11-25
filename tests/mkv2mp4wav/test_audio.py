"""訓練用 WAV：24 kHz、16-bit、單聲道，同一个來源逐擺逐位元相仝。

聲音規則依容器：mkv 愛是 FLAC（mkv 無記 AAC 開頭愛略過ê樣本數，解碼
規段偏移）；mp4 ê AAC 照 mp4 記ê時間解碼就好（開會了 20 集 mp4 攏是
AAC，照「毋是 FLAC 就失敗」會規批做袂出來）。毋是單聲道、起點毋是 0
攏失敗，袂混音、袂平移。
"""
import unittest

from tools.mkv2mp4wav import audio

SRC = "/tmp/w/開會了_079_SaiSiyat_賽夏.mp4"
DST = "/tmp/w/開會了_079_SaiSiyat_賽夏.wav"


class TestCommand(unittest.TestCase):
    def cmd(self, track=0):
        return audio.command(SRC, DST, track)

    def test_the_chosen_track(self):
        self.assertIn("0:a:1", self.cmd(1))
        self.assertNotIn("0:a:0", self.cmd(1))

    def test_soxr_24k_16_bit(self):
        got = " ".join(self.cmd())
        self.assertIn("aresample=24000:resampler=soxr:precision=28", got)
        self.assertIn("-sample_fmt s16", got)
        self.assertIn("-c:a pcm_s16le", got)

    def test_no_dither(self):
        """降位元無加抖動——加ê話逐擺轉出來無仝。"""
        got = " ".join(self.cmd())
        self.assertNotIn("dither", got)

    def test_bitexact_header(self):
        """無 bitexact，WAV 檔頭濟 54 位元組 ffmpeg 版本資訊，換版本轉出來
        就無仝（實測 98 對 44 位元組）。"""
        cmd = self.cmd()
        self.assertEqual(cmd[cmd.index("-map_metadata") + 1], "-1")
        self.assertEqual(cmd[cmd.index("-fflags") + 1], "+bitexact")
        self.assertEqual(cmd[cmd.index("-flags:a") + 1], "+bitexact")

    def test_low_priority_no_keyboard(self):
        cmd = self.cmd()
        self.assertEqual(cmd[:6], ["nice", "-n", "15", "ionice", "-c", "3"])
        self.assertIn("-nostdin", cmd)
        self.assertEqual(cmd[-1], DST)


def stream(**changes):
    got = {"codec_name": "flac", "channels": 1, "start_time": "0.000000"}
    got.update(changes)
    return got


class TestPrecheck(unittest.TestCase):
    def test_flac_in_mkv_passes(self):
        self.assertIsNone(audio.precheck("mkv", stream()))

    def test_aac_in_mkv_fails_and_says_why(self):
        reason = audio.precheck("mkv", stream(codec_name="aac"))
        self.assertIn("aac", reason)
        self.assertIn("mkv", reason)

    def test_aac_in_mp4_passes(self):
        self.assertIsNone(audio.precheck("mp4", stream(codec_name="aac")))

    def test_flac_in_mp4_passes(self):
        self.assertIsNone(audio.precheck("mp4", stream()))

    def test_something_else_in_mp4_fails(self):
        self.assertIsNotNone(audio.precheck("mp4", stream(codec_name="mp3")))

    def test_two_channels_fail(self):
        reason = audio.precheck("mkv", stream(channels=2))
        self.assertIn("2", reason)

    def test_start_0_021_fails(self):
        """WAV 無記起點：照轉會規段提早 0.021 秒，對袂起 SRT。"""
        reason = audio.precheck("mkv", stream(start_time="0.021000"))
        self.assertIn("0.021", reason)


def wav_info(**changes):
    got = {"codec_type": "audio", "codec_name": "pcm_s16le",
           "sample_rate": "24000", "channels": 1, "duration_ts": 71999928}
    got.update(changes)
    return {"streams": [got]}


class TestVerify(unittest.TestCase):
    SOURCE_SAMPLES = 143999856      # 107 第一條解碼後（volumedetect n_samples）

    def test_exactly_half_passes(self):
        self.assertEqual(audio.verify(wav_info(), self.SOURCE_SAMPLES), [])

    def test_off_by_one_passes(self):
        info = wav_info(duration_ts=71999929)
        self.assertEqual(audio.verify(info, self.SOURCE_SAMPLES), [])

    def test_off_by_two_fails(self):
        info = wav_info(duration_ts=71999926)
        self.assertEqual(len(audio.verify(info, self.SOURCE_SAMPLES)), 1)

    def test_a_short_wav_says_both_counts(self):
        """來源 138,246,912 個樣本，音檔干焦 60,000,000 個。"""
        problems = audio.verify(wav_info(duration_ts=60000000), 138246912)
        self.assertIn("60000000", problems[0])

    def test_16000_hz_fails(self):
        self.assertEqual(
            len(audio.verify(wav_info(sample_rate="16000"),
                             self.SOURCE_SAMPLES)), 1)

    def test_two_channels_fail(self):
        self.assertEqual(
            len(audio.verify(wav_info(channels=2), self.SOURCE_SAMPLES)), 1)

    def test_24_bit_fails(self):
        self.assertEqual(
            len(audio.verify(wav_info(codec_name="pcm_s24le"),
                             self.SOURCE_SAMPLES)), 1)

    def test_two_tracks_fail(self):
        info = wav_info()
        info["streams"].append(dict(info["streams"][0]))
        self.assertTrue(audio.verify(info, self.SOURCE_SAMPLES))

    def test_unknown_source_count_fails(self):
        """來源樣本數量無著，就無法度驗——袂使當做通過。"""
        self.assertTrue(audio.verify(wav_info(), None))


class TestContainer(unittest.TestCase):
    def test_matroska_and_mp4_names(self):
        self.assertEqual(audio.container_of("matroska,webm"), "mkv")
        self.assertEqual(audio.container_of("mov,mp4,m4a,3gp,3g2,mj2"), "mp4")
        self.assertIsNone(audio.container_of("mxf"))


if __name__ == "__main__":
    unittest.main()
