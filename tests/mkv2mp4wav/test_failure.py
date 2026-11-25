"""一集ê流程：各自跳過、各自上傳、一種失敗袂牽連另一種、做煞本機清空。

磁碟捌塞滿兩擺（讀者抓ê影片一個月 25–40 GB 留咧），所以毋管成功、編碼
失敗、驗收無過、上傳失敗，來源佮兩種產出攏愛刣。伺服器頂懸兩種攏已經
有，就連下載都免——新聞一集 2.5 GB。
"""
import os
import shutil
import subprocess
import tempfile
import unittest

from tools.sftpbatch import batch
from tools.sftpbatch import report
from tools.mkv2mp4wav import encode
from tools.mkv2mp4wav import run

from tests.mkv2mp4wav import fakes

NAME = "開會了_107_Hla'alua_拉阿魯哇"
PREVIEW = "/home/aiyalaeho/mp4/%s.mp4" % NAME
WAV = "/home/aiyalaeho/wav/%s.wav" % NAME


class EpisodeCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.work = os.path.join(self.tmp, "work")
        os.makedirs(self.work)
        self.logged = []

    def go(self, tools, program=None, software=False, name=NAME):
        program = program or fakes.FakeProgram([name])
        return run.one_episode(fakes.make_job(name), program, self.work,
                               software, self.logged.append, tools)


class TestSkipping(EpisodeCase):
    def test_both_there_means_no_download(self):
        tools = fakes.FakeTools(existing={PREVIEW, WAV})
        entry = self.go(tools)
        self.assertEqual(entry["結果"], "已存在")
        self.assertEqual(tools.fetched, [])

    def test_only_the_wav_missing_makes_only_the_wav(self):
        tools = fakes.FakeTools(existing={PREVIEW})
        entry = self.go(tools)
        self.assertEqual(len(tools.fetched), 1)
        self.assertEqual(tools.encoded, [])
        self.assertEqual(len(tools.converted), 1)
        self.assertEqual(entry["預覽檔"]["結果"], "已存在")
        self.assertEqual(entry["音檔"]["結果"], "成功")
        self.assertEqual(entry["結果"], "成功")

    def test_only_the_preview_missing_makes_only_the_preview(self):
        tools = fakes.FakeTools(existing={WAV})
        self.go(tools)
        self.assertEqual(len(tools.encoded), 1)
        self.assertEqual(tools.converted, [])


class TestOneFailsTheOtherStillGoes(EpisodeCase):
    def test_wav_rejected_preview_still_uploaded(self):
        tools = fakes.FakeTools()
        tools.wav_changes = {"sample_rate": "16000"}
        entry = self.go(tools)
        uploaded = []
        for _local, remote in tools.uploaded:
            uploaded.append(remote)
        self.assertEqual(uploaded, [PREVIEW])
        self.assertEqual(entry["結果"], "失敗")
        self.assertIn("音檔", entry["原因"])
        self.assertEqual(entry["預覽檔"]["結果"], "成功")

    def test_preview_rejected_wav_still_uploaded(self):
        tools = fakes.FakeTools()
        tools.preview_changes = {"frames": fakes.FRAMES - 3}
        entry = self.go(tools)
        uploaded = []
        for _local, remote in tools.uploaded:
            uploaded.append(remote)
        self.assertEqual(uploaded, [WAV])
        self.assertIn("預覽檔", entry["原因"])
        self.assertIn(str(fakes.FRAMES - 3), entry["原因"])

    def test_all_silent_fails_the_wav_but_makes_the_preview_from_track_1(self):
        tools = fakes.FakeTools(levels=[-91.0, -91.0])
        entry = self.go(tools)
        self.assertIn("0:a:0", tools.encoded[0])
        self.assertEqual(tools.converted, [])
        self.assertIn("全部音軌靜音", entry["原因"])

    def test_aac_in_mkv_fails_the_wav_only(self):
        tools = fakes.FakeTools(audio_codec="aac", container="mkv")
        entry = self.go(tools)
        self.assertEqual(tools.converted, [])
        self.assertEqual(entry["預覽檔"]["結果"], "成功")
        self.assertIn("aac", entry["原因"])


class TestTrackChoice(EpisodeCase):
    def test_second_track_feeds_both_outputs(self):
        """107 換音軌進前ê原檔：第一條 −91 dB、第二條 −25 dB。"""
        tools = fakes.FakeTools(levels=[-91.0, -25.0])
        entry = self.go(tools)
        self.assertIn("0:a:1", tools.encoded[0])
        self.assertEqual(tools.converted[0][2], 1)
        self.assertEqual(entry["音軌"]["第幾條"], 2)
        self.assertEqual(entry["音軌"]["平均音量"], -25.0)


class TestMp4Source(EpisodeCase):
    def test_mp4_source_keeps_its_extension_and_does_not_clash(self):
        """開會了 mp4 下載落來愛保留 .mp4，而且袂使佮預覽檔仝名互蓋。"""
        program = fakes.FakeProgram([NAME], source_ext=".mp4")
        tools = fakes.FakeTools(container="mp4", audio_codec="aac",
                                pix_fmt="yuv422p")
        self.go(tools, program=program)
        local_src = tools.fetched[0][1]
        self.assertTrue(local_src.endswith(".mp4"))
        cmd = tools.encoded[0]
        self.assertEqual(cmd[cmd.index("-i") + 1], local_src)
        self.assertNotEqual(cmd[-1], local_src)
        self.assertEqual(fakes.path_of(cmd), encode.HYBRID)


class TestCleanup(EpisodeCase):
    def assert_empty(self):
        self.assertEqual(os.listdir(self.work), [])

    def test_after_success(self):
        self.go(fakes.FakeTools())
        self.assert_empty()

    def test_after_an_encode_failure(self):
        tools = fakes.FakeTools()
        tools.encode_error = encode.EncodeError("編碼失敗")
        self.go(tools)
        self.assert_empty()

    def test_after_a_rejected_preview(self):
        tools = fakes.FakeTools()
        tools.preview_changes = {"size": 9 * 10 ** 9}
        self.go(tools)
        self.assert_empty()

    def test_after_an_upload_failure(self):
        tools = fakes.FakeTools()
        tools.put_error = (".wav", RuntimeError("上傳了後位元組數無仝"))
        entry = self.go(tools)
        self.assertEqual(entry["結果"], "失敗")
        self.assert_empty()

    def test_after_an_interrupt(self):
        tools = fakes.FakeTools()
        tools.encode_error = KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            self.go(tools)
        self.assert_empty()


class TestBatchLevel(unittest.TestCase):
    """經過 sftpbatch 迴圈：揣無來源記失敗、編碼卡死毋是中斷、喝停規批停。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.work = os.path.join(self.tmp, "work")
        os.makedirs(self.work)

    def go(self, program, tools):
        def one_file(job, log):
            return run.one_episode(job, program, self.work, False, log, tools)

        def open_report():
            return report.open_run(os.path.join(self.tmp, "r"), "1123-1200",
                                   {})

        return batch.run(program.jobs(), open_report, one_file,
                         work_dir=self.work, key_field="srt_name")

    def test_missing_source_fails_with_the_paths_and_the_next_goes_on(self):
        program = fakes.FakeProgram(["開會了_101_a", "開會了_102_b"],
                                    missing={"開會了_101_a"})
        tools = fakes.FakeTools()
        result = self.go(program, tools)
        self.assertEqual(result.failed, ["開會了_101_a"])
        self.assertIn("/docker/a/開會了_101_a.mkv", result.entries[0]["原因"])
        self.assertEqual(result.entries[1]["結果"], "成功")

    def test_a_stuck_encode_is_a_failure_not_an_interrupt(self):
        program = fakes.FakeProgram(["開會了_101_a", "開會了_102_b"])
        tools = fakes.FakeTools()
        tools.encode_error = encode.EncodeError("編碼超過來源時長 2880 秒")
        result = self.go(program, tools)
        self.assertEqual(len(result.entries), 2)
        self.assertEqual(result.exit_code, 1)

    def test_hardware_failure_does_not_fall_back_to_software(self):
        """驅動出問題時若家己改軟體，規批會恬恬食滿 CPU。"""
        program = fakes.FakeProgram(["開會了_101_a", "開會了_102_b"])
        tools = fakes.FakeTools()
        tools.encode_error = encode.EncodeError("h264_vaapi 失敗")
        self.go(program, tools)
        self.assertEqual(len(tools.encoded), 2)
        for cmd in tools.encoded:
            self.assertEqual(fakes.path_of(cmd), encode.HARDWARE)

    def test_interrupt_stops_the_batch(self):
        program = fakes.FakeProgram(["開會了_101_a", "開會了_102_b"])
        tools = fakes.FakeTools()
        tools.encode_error = KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            self.go(program, tools)
        self.assertEqual(len(tools.encoded), 1)


class TestInterruptCodes(unittest.TestCase):
    """ffmpeg 離開碼 255／130／-SIGINT：包佇 nice／ionice 內底嘛認會出。"""

    def test_each_code_becomes_an_interrupt(self):
        for code in (255, 130, -2):
            def fake_run(cmd, **kwargs):
                return subprocess.CompletedProcess(cmd, code, "", "")

            with self.assertRaises(KeyboardInterrupt):
                encode.encode(encode.command("a", "b", 0, encode.HARDWARE),
                              10.0, lambda text: None, run=fake_run)


if __name__ == "__main__":
    unittest.main()
