"""音軌選用第一條有聲音的（整條平均高於 −80 dB）。

開會了 107 換音軌進前ê原檔：第一條 −91 dB（數位靜音）、第二條 −25 dB，
照「干焦取第一條」會產出規集靜音ê預覽檔佮音檔。有聲音ê落佇 −21～−27
dB，中央空真闊，所以門檻 −80。量音量是 measure，測試傳假ê。
"""
import unittest

from tools.mkv2mp4wav import tracks


def fake(levels):
    asked = []

    def measure(source, index):
        asked.append(index)
        return levels[index]

    return measure, asked


class TestPick(unittest.TestCase):
    def test_silent_first_track_picks_the_second(self):
        measure, _ = fake([-91.0, -25.0])
        got = tracks.pick("107.mkv", 2, measure)
        self.assertEqual(got.index, 1)
        self.assertEqual(got.mean_db, -25.0)
        self.assertIsNone(got.problem)

    def test_audible_first_track_is_used_without_measuring_the_rest(self):
        measure, asked = fake([-24.9, -91.0])
        got = tracks.pick("101.mkv", 2, measure)
        self.assertEqual(got.index, 0)
        self.assertEqual(asked, [0])

    def test_all_silent_uses_the_first_and_says_so(self):
        measure, _ = fake([-91.0, -91.0])
        got = tracks.pick("x.mkv", 2, measure)
        self.assertEqual(got.index, 0)
        self.assertEqual(got.problem, "全部音軌靜音")

    def test_minus_80_is_silence_minus_79_9_is_sound(self):
        measure, _ = fake([-80.0, -79.9])
        self.assertEqual(tracks.pick("x.mkv", 2, measure).index, 1)

    def test_no_audio_track_at_all(self):
        measure, asked = fake([])
        got = tracks.pick("x.mkv", 0, measure)
        self.assertEqual(asked, [])
        self.assertIsNotNone(got.problem)

    def test_a_track_that_cannot_be_measured_counts_as_silent(self):
        """volumedetect 讀無平均（例：整條空ê）回傳 None，當做無聲。"""
        measure, _ = fake([None, -30.0])
        self.assertEqual(tracks.pick("x.mkv", 2, measure).index, 1)


class TestParseVolume(unittest.TestCase):
    def test_reads_mean_volume_out_of_volumedetect(self):
        stderr = ("[Parsed_volumedetect_0 @ 0x55] n_samples: 138246912\n"
                  "[Parsed_volumedetect_0 @ 0x55] mean_volume: -25.9 dB\n"
                  "[Parsed_volumedetect_0 @ 0x55] max_volume: -3.1 dB\n")
        self.assertEqual(tracks.parse_mean_volume(stderr), -25.9)

    def test_digital_silence(self):
        stderr = "[Parsed_volumedetect_0 @ 0x5] mean_volume: -91.0 dB\n"
        self.assertEqual(tracks.parse_mean_volume(stderr), -91.0)

    def test_nothing_to_read(self):
        self.assertIsNone(tracks.parse_mean_volume("Output file is empty"))


class TestSampleCount(unittest.TestCase):
    """音檔驗收愛來源選用音軌解碼了ê樣本數。量音量彼趟 volumedetect 就
    印 n_samples，順紲記落來，免閣解一擺。實測頭前閣有一逝 n_samples: 0
    （另外一个 filter 實例），愛提有 mean_volume 彼个。"""

    STDERR = ("[Parsed_volumedetect_0 @ 0xa] n_samples: 0\n"
              "[Parsed_volumedetect_0 @ 0xb] n_samples: 143999856\n"
              "[Parsed_volumedetect_0 @ 0xb] mean_volume: -25.9 dB\n")

    def test_the_real_count_not_the_zero_line(self):
        self.assertEqual(tracks.parse_samples(self.STDERR), 143999856)

    def test_meter_remembers_each_measured_track(self):
        import subprocess

        def run(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 0, "", self.STDERR)

        meter = tracks.Meter(run=run)
        self.assertEqual(meter.mean("x.mkv", 0), -25.9)
        self.assertEqual(meter.samples[0], 143999856)


if __name__ == "__main__":
    unittest.main()
