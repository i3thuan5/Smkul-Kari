"""audio: where the audio to recognise comes from, shared by kaldi and whisper.

Pins the asr-bilingual-srt spec's 音檔由該集影片抽出 requirement as
amended 2026-09-18: mkv first, else SFTP -- the staged original that
cue-cutting may have left behind is never read, and whatever is fetched
from SFTP is deleted once its audio track is out.
"""
import os
import subprocess
import tempfile
import unittest
from unittest import mock

from scripts.news import audio
from scripts.news import paths
from scripts.errors import PipelineError


def _entry(**over):
    one = {
        "srt_name": "20210201_032_午間_Atayal_泰雅",
        "節目名稱": "午間族語新聞", "播出日期": "2021-02-01",
        "集數": "32", "族語別(英)": "Atayal", "族語別(中)": "泰雅",
        "file": "20NL003_32午間族語新聞.mxf",
        "原始影片檔案位置":
            "ilrdf-corpus/族語新聞/110.1-110.10/2月原始mxf檔/"
            "20NL003_32午間族語新聞.mxf",
    }
    one.update(over)
    return one


class TestVideoSource(unittest.TestCase):
    def test_the_archived_mkv_is_used_first(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, tmp, True)
        os.makedirs(os.path.join(tmp, "2021-02"))
        mkv = os.path.join(tmp, "2021-02", "20210201_032_午間_Atayal_泰雅.mkv")
        open(mkv, "w").close()
        with mock.patch.object(audio.paths, "MKV_ARCHIVE", tmp):
            local, remote = audio.video_source(_entry())
        self.assertEqual(local, mkv)
        self.assertEqual(remote, "")

    def test_a_staged_original_left_by_cue_cutting_is_not_read(self):
        # 2026-09-18 使用者裁定：暫存區既有的原檔不算捷徑，一律走
        # 封存 mkv → SFTP。
        stage_tmp = tempfile.mkdtemp()
        mkv_tmp = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, stage_tmp, True)
        self.addCleanup(__import__("shutil").rmtree, mkv_tmp, True)
        os.makedirs(os.path.join(stage_tmp, "2021-02"))
        staged = os.path.join(stage_tmp, "2021-02",
                              "20NL003_32午間族語新聞.mxf")
        open(staged, "w").close()
        with mock.patch.object(audio.paths, "STAGE", stage_tmp), \
                mock.patch.object(audio.paths, "MKV_ARCHIVE", mkv_tmp):
            local, remote = audio.video_source(_entry())
        self.assertEqual(local, "")
        self.assertTrue(remote.startswith("/docker/ilrdf-corpus/"), remote)

    def test_no_mkv_falls_back_to_the_remote_video(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, tmp, True)
        with mock.patch.object(audio.paths, "MKV_ARCHIVE", tmp):
            local, remote = audio.video_source(_entry())
        self.assertEqual(local, "")
        self.assertEqual(
            remote,
            "/docker/ilrdf-corpus/族語新聞/110.1-110.10/2月原始mxf檔/"
            "20NL003_32午間族語新聞.mxf")

    def test_a_mkv_raw_source_is_fetched_from_its_own_root(self):
        # 2026-09-23 新母帶佇 /home/mkv-raw，毋是 /docker 底下
        raw = "home/mkv-raw/112/7月/23NL003_183_族語午間新聞_Kanakanavu.mkv"
        tmp = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, tmp, True)
        with mock.patch.object(audio.paths, "MKV_ARCHIVE", tmp):
            local, remote = audio.video_source(_entry(原始影片檔案位置=raw))
        self.assertEqual(remote, "/" + raw)

    def test_no_source_anywhere_is_named(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, tmp, True)
        with mock.patch.object(audio.paths, "MKV_ARCHIVE", tmp):
            with self.assertRaises(PipelineError) as caught:
                audio.video_source(_entry(原始影片檔案位置=""))
        self.assertIn("20210201_032", str(caught.exception))

    def test_kaldis_extracted_mp3_is_never_consulted(self):
        # whisper 不看 kaldi 工作目錄裡已抽好的 audio.mp3——
        # video_source 根本不查 ASRMT_WORK／asrmt_dir。
        mkv_tmp = tempfile.mkdtemp()
        kaldi_work = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, mkv_tmp, True)
        self.addCleanup(__import__("shutil").rmtree, kaldi_work, True)
        bogus_mp3 = os.path.join(
            paths.stage_path(kaldi_work, _entry()["srt_name"]),
            "audio.mp3")
        os.makedirs(os.path.dirname(bogus_mp3))
        open(bogus_mp3, "w").close()
        with mock.patch.object(audio.paths, "MKV_ARCHIVE", mkv_tmp), \
                mock.patch.object(audio.paths, "ASRMT_WORK", kaldi_work):
            local, remote = audio.video_source(_entry())
        self.assertNotEqual(local, bogus_mp3)
        self.assertEqual(local, "")
        self.assertTrue(remote)


class TestFetchVideo(unittest.TestCase):
    REMOTE = "/docker/x/video.mp4"

    def _ls_reply(self, size):
        return subprocess.CompletedProcess(
            [], 0, stdout="-rw-r--r-- 1 a a %d Jan 1 00:00 video.mp4\n"
                          % size, stderr="")

    def test_a_matching_local_file_is_reused_without_a_get_call(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, tmp, True)
        local = os.path.join(tmp, "video.mp4")
        with open(local, "wb") as handle:
            handle.write(b"x" * 10)
        calls = []

        def fake_run(cmd, **kw):
            calls.append(cmd)
            if cmd[2] == "ls":
                return self._ls_reply(10)
            raise AssertionError("get should not be called: %r" % cmd)

        with mock.patch.object(audio.subprocess, "run", fake_run):
            audio.fetch_video(self.REMOTE, local)
        kinds = []
        for call in calls:
            kinds.append(call[2])
        self.assertEqual(kinds, ["ls"])

    def test_missing_bytes_trigger_a_get(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, tmp, True)
        local = os.path.join(tmp, "video.mp4")
        calls = []

        def fake_run(cmd, **kw):
            calls.append(cmd)
            if cmd[2] == "ls":
                return self._ls_reply(10)
            with open(local, "wb") as handle:
                handle.write(b"y" * 10)
            return subprocess.CompletedProcess(cmd, 0)

        with mock.patch.object(audio.subprocess, "run", fake_run):
            audio.fetch_video(self.REMOTE, local)
        kinds = []
        for call in calls:
            kinds.append(call[2])
        self.assertEqual(kinds, ["ls", "get"])

    def test_a_short_download_is_removed_and_named_in_the_error(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, tmp, True)
        local = os.path.join(tmp, "video.mp4")

        def fake_run(cmd, **kw):
            if cmd[2] == "ls":
                return self._ls_reply(2_200_000_000)
            with open(local, "wb") as handle:
                handle.write(b"y" * 100)  # 抓袂完整
            return subprocess.CompletedProcess(cmd, 0)

        with mock.patch.object(audio.subprocess, "run", fake_run):
            with self.assertRaises(PipelineError) as caught:
                audio.fetch_video(self.REMOTE, local)
        self.assertIn(self.REMOTE, str(caught.exception))
        self.assertFalse(os.path.exists(local))

    def test_remote_missing_is_named(self):
        def fake_run(cmd, **kw):
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with mock.patch.object(audio.subprocess, "run", fake_run):
            with self.assertRaises(PipelineError) as caught:
                audio.fetch_video(self.REMOTE, "/tmp/wont-be-written")
        self.assertIn(self.REMOTE, str(caught.exception))


class TestGetAudio(unittest.TestCase):
    def test_video_fetched_from_sftp_is_deleted_after_extraction(self):
        mkv_tmp = tempfile.mkdtemp()
        stage_tmp = tempfile.mkdtemp()
        out_tmp = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, mkv_tmp, True)
        self.addCleanup(__import__("shutil").rmtree, stage_tmp, True)
        self.addCleanup(__import__("shutil").rmtree, out_tmp, True)
        out = os.path.join(out_tmp, "audio.mp3")

        written_video_path = {}

        def fake_fetch(remote, local):
            written_video_path["path"] = local
            os.makedirs(os.path.dirname(local), exist_ok=True)
            with open(local, "wb") as handle:
                handle.write(b"fake-video")

        def fake_extract(local_video, dest):
            self.assertTrue(os.path.exists(local_video))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as handle:
                handle.write(b"fake-audio")
            return dest

        with mock.patch.object(audio.paths, "MKV_ARCHIVE", mkv_tmp), \
                mock.patch.object(audio.paths, "STAGE", stage_tmp), \
                mock.patch.object(audio, "fetch_video", fake_fetch), \
                mock.patch.object(audio, "extract_audio", fake_extract):
            audio.get_audio(_entry(), out)

        self.assertTrue(os.path.exists(out))
        self.assertFalse(os.path.exists(written_video_path["path"]))

    def test_the_archived_mkv_is_never_deleted(self):
        mkv_tmp = tempfile.mkdtemp()
        out_tmp = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, mkv_tmp, True)
        self.addCleanup(__import__("shutil").rmtree, out_tmp, True)
        os.makedirs(os.path.join(mkv_tmp, "2021-02"))
        mkv = os.path.join(mkv_tmp, "2021-02", "20210201_032_午間_Atayal_泰雅.mkv")
        open(mkv, "w").close()
        out = os.path.join(out_tmp, "audio.mp3")

        def fake_extract(local_video, dest):
            with open(dest, "wb") as handle:
                handle.write(b"fake-audio")
            return dest

        with mock.patch.object(audio.paths, "MKV_ARCHIVE", mkv_tmp), \
                mock.patch.object(audio, "extract_audio", fake_extract):
            audio.get_audio(_entry(), out)
        self.assertTrue(os.path.exists(mkv))


if __name__ == "__main__":
    unittest.main()
