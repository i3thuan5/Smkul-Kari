"""預覽檔驗收：規格書第四節逐項，加上起點跟來源、無時間碼軌。

逐項攏是純函式，食已經解析好ê ffprobe 結果（抑是檔頭位元組），免真ê
影片。任何一項無過就袂使上傳，而且愛列出**全部**無過ê項目。
"""
import struct
import unittest

from tools.mkv2mp4wav import verify

DURATION = 2880.144          # 2021-02-01 晚間 阿美，規格書實測彼支
FRAMES = 86318


def box(kind, payload_size):
    return struct.pack(">I", 8 + payload_size) + kind + b"\0" * payload_size


def good_head():
    return box(b"ftyp", 16) + box(b"moov", 64) + box(b"mdat", 32)


def source(**changes):
    facts = {"frames": FRAMES, "video_start": 0.0, "audio_start": 0.0,
             "duration": DURATION}
    facts.update(changes)
    return facts


def preview(**changes):
    video = {"codec_type": "video", "codec_name": "h264", "profile": "High",
             "pix_fmt": "yuv420p", "width": 1280, "height": 720,
             "r_frame_rate": "30000/1001", "field_order": "progressive"}
    audio = {"codec_type": "audio", "codec_name": "aac", "channels": 1,
             "sample_rate": "48000"}
    keyframes = []
    second = 0.0
    while second < DURATION:
        keyframes.append(round(second, 3))
        second += 1.001
    facts = {"frames": FRAMES, "video_start": 0.0, "audio_start": 0.0,
             "duration": DURATION + 0.02, "streams": [video, audio],
             "head": good_head(), "keyframes": keyframes,
             "size": 620 * 1000 * 1000}
    facts.update(changes)
    return facts


def failures(src, got):
    return verify.problems(verify.check_all(src, got))


class TestAllGood(unittest.TestCase):
    def test_a_good_preview_passes_everything(self):
        self.assertEqual(failures(source(), preview()), [])

    def test_every_item_is_reported(self):
        names = []
        for name, _ok, _note in verify.check_all(source(), preview()):
            names.append(name)
        for want in ("影格數", "起點", "時長", "影像規格", "聲音規格",
                     "時間碼軌", "索引在檔頭", "關鍵格間距", "大小"):
            self.assertIn(want, names)


class TestFrames(unittest.TestCase):
    def test_three_frames_short(self):
        """去交錯無逐格輸出ê實測值：少 3 格。說明愛寫出兩爿格數。"""
        got = failures(source(), preview(frames=FRAMES - 3))
        self.assertEqual(len(got), 1)
        self.assertIn(str(FRAMES), got[0])
        self.assertIn(str(FRAMES - 3), got[0])


class TestStart(unittest.TestCase):
    """20210101_001_午間_Rukai_魯凱：影像起點 0.033、聲音 0。"""

    def test_rukai_0_033_against_0_033_passes(self):
        self.assertEqual(
            failures(source(video_start=0.033), preview(video_start=0.033)),
            [])

    def test_rukai_moved_to_0_fails(self):
        got = failures(source(video_start=0.033), preview(video_start=0.0))
        self.assertEqual(len(got), 1)
        self.assertIn("起點", got[0])

    def test_audio_start_is_checked_too(self):
        got = failures(source(), preview(audio_start=0.021))
        self.assertEqual(len(got), 1)


class TestDuration(unittest.TestCase):
    def test_short_by_23_minutes(self):
        """予人停掉ê半截檔。"""
        got = failures(source(), preview(duration=DURATION - 23 * 60))
        joined = " ".join(got)
        self.assertIn("時長", joined)

    def test_within_a_tenth_passes(self):
        self.assertEqual(failures(source(), preview(duration=DURATION + 0.09)),
                         [])


class TestVideoSpec(unittest.TestCase):
    def _with(self, **video):
        got = preview()
        got["streams"][0].update(video)
        return failures(source(), got)

    def test_field_order_tt(self):
        got = self._with(field_order="tt")
        self.assertEqual(len(got), 1)
        self.assertIn("tt", got[0])

    def test_1080p(self):
        got = self._with(width=1920, height=1080)
        self.assertIn("1920", got[0])

    def test_422(self):
        got = self._with(pix_fmt="yuv422p")
        self.assertIn("yuv422p", got[0])


class TestAudioSpec(unittest.TestCase):
    def test_two_audio_tracks(self):
        got = preview()
        got["streams"].append(dict(got["streams"][1]))
        problems = failures(source(), got)
        self.assertEqual(len(problems), 1)
        self.assertIn("2", problems[0])

    def test_two_channels(self):
        got = preview()
        got["streams"][1]["channels"] = 2
        self.assertEqual(len(failures(source(), got)), 1)


class TestTimecode(unittest.TestCase):
    def test_a_tmcd_track_fails(self):
        """帶時間碼軌，剪輯軟體對 01:00:00;00 起算，佮 SRT 對袂起來。"""
        got = preview()
        got["streams"].append({"codec_type": "data",
                               "codec_tag_string": "tmcd"})
        problems = failures(source(), got)
        self.assertEqual(len(problems), 1)
        self.assertIn("tmcd", problems[0])


class TestMoovFirst(unittest.TestCase):
    def test_moov_after_mdat_fails(self):
        head = box(b"ftyp", 16) + box(b"mdat", 32) + box(b"moov", 64)
        problems = failures(source(), preview(head=head))
        self.assertEqual(len(problems), 1)
        self.assertIn("moov", problems[0])

    def test_a_64_bit_largesize_box_is_skipped_correctly(self):
        """頂層 box 長度寫 1 是講後壁 8 位元組才是真ê長度。"""
        large = (struct.pack(">I", 1) + b"free" + struct.pack(">Q", 16 + 40)
                 + b"\0" * 40)
        head = box(b"ftyp", 16) + large + box(b"moov", 64) + box(b"mdat", 8)
        self.assertTrue(verify.moov_before_mdat(head)[0])

    def test_neither_box_in_the_first_4_mb_fails(self):
        self.assertFalse(verify.moov_before_mdat(box(b"ftyp", 16))[0])


class TestKeyframes(unittest.TestCase):
    def test_eight_second_gaps_fail(self):
        """x264 預設 GOP 是 250 格（約 8 秒）：瀏覽器跳轉愛等。"""
        keys = []
        second = 0.0
        while second < DURATION:
            keys.append(second)
            second += 8.0
        problems = failures(source(), preview(keyframes=keys))
        self.assertEqual(len(problems), 1)
        self.assertIn("8.0", problems[0])

    def test_a_single_keyframe_in_a_long_file_fails(self):
        self.assertEqual(len(failures(source(), preview(keyframes=[0.0]))), 1)


class TestSize(unittest.TestCase):
    def test_limit_follows_duration(self):
        """24 分鐘 0.5 GB：超過 (1800+128) kbps × 1440 秒 ≈ 0.347 GB。
        干焦用固定 0.7 GB 會漏掉。"""
        short = 24 * 60.0
        src = source(duration=short)
        got = preview(duration=short, size=500 * 1000 * 1000,
                      keyframes=[0.0, 1.0])
        got["keyframes"] = []
        second = 0.0
        while second < short:
            got["keyframes"].append(second)
            second += 1.0
        problems = failures(src, got)
        self.assertEqual(len(problems), 1)
        self.assertIn("大小", problems[0])

    def test_48_minutes_at_0_69_gb_passes(self):
        self.assertEqual(
            failures(source(), preview(size=690 * 1000 * 1000)), [])


class TestSeveralAtOnce(unittest.TestCase):
    def test_all_three_are_listed_not_just_the_first(self):
        keys = [0.0, 8.0, 16.0]
        got = preview(frames=FRAMES - 3, video_start=0.0, keyframes=keys)
        problems = failures(source(video_start=0.033), got)
        self.assertEqual(len(problems), 3)


if __name__ == "__main__":
    unittest.main()
