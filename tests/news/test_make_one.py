"""make_all.make_one: which source an episode's status is decided from.

The order the sources are asked about is the whole point. A finished vision
pass supersedes everything, so it must be asked FIRST. It was not: a
"has anything been recognised yet?" guard sat above it, looking for the
tesseract draft in <slug>.work. The February batch had one in every work dir,
so the guard never misfired -- and then thirteen episodes read by vision
alone, which never run tesseract, were all reported as 尚未辨識 with their
finished transcripts sitting in <slug>.B.work.
"""
import json
import os
import tempfile
import unittest
from unittest import mock

from scripts.news import make_all


# Deliberately not a real episode. make_one writes the SRT itself, so a test
# that names a delivered episode overwrites it -- which this test did, and
# `rebuild --verify` caught. SRT_DIR is redirected below as well; the fake
# name is the second lock on the door.
ENTRY = {"slug": "9999_001_1999-01-01_午間_Test_測試",
         "srt_name": "19990101_001_午間_Test_測試",
         "文稿位置": "", "truncated": ""}


class TestMakeOne(unittest.TestCase):
    def _work(self, cues=True, tesseract=False, vision=False):
        """A WORK dir holding one episode in the requested state."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        plain = os.path.join(tmp.name, ENTRY["slug"] + ".work")
        os.makedirs(plain)
        if cues:
            self._cues(plain)
        if tesseract:
            self._write(plain, "transcripts.json", {"1": {"han": "ocr"}})
        if vision:
            done = os.path.join(tmp.name, ENTRY["slug"] + ".B.work")
            os.makedirs(done)
            self._cues(done)
            self._write(done, "verified.json", {"1": {"han": True}})
        return tmp.name

    def _cues(self, work):
        self._write(work, "cues.json",
                    {"cues": [{"index": 1, "start": 1.0, "end": 2.0}]})

    def _write(self, work, name, value):
        with open(os.path.join(work, name), "w", encoding="utf-8") as handle:
            json.dump(value, handle)

    def _status(self, **state):
        root = self._work(**state)
        out = os.path.join(root, "srt")
        os.makedirs(out)
        with mock.patch.object(make_all, "WORK", root), \
             mock.patch.object(make_all, "SRT_DIR", out):
            return make_all.make_one(dict(ENTRY))

    def test_cut_straight_into_the_B_work_dir_is_not_called_uncut(self):
        """判「切了未」愛看伊實在**組裝ê彼跡**，毋是邊仔彼跡。

        本底是看 `<slug>.work/cues.json`，毋過 SRT 是對
        `<slug>.B.work` 組ê。054–059 這批是直接切入去 `.B.work`
        （`fetch_sftp.sh` 是按呢做ê），無 `.work`，所以 `make_all`
        講「尚未切cue」——實際上圖條、strips、TSV 攏好勢矣。
        """
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        done = os.path.join(tmp.name, ENTRY["slug"] + ".B.work")
        os.makedirs(done)
        self._cues(done)
        self._write(done, "verified.json", {"1": {"han": True}})
        self._write(done, "transcripts.json", {"1": {"han": "有字"}})
        out = os.path.join(tmp.name, "srt")
        os.makedirs(out)
        with mock.patch.object(make_all, "WORK", tmp.name), \
                mock.patch.object(make_all, "SRT_DIR", out):
            got = make_all.make_one(dict(ENTRY))
        self.assertNotIn("尚未切cue", got)

    def test_uncut_episode_says_so(self):
        self.assertIn("尚未切cue", self._status(cues=False))

    def test_cut_but_unread_episode_says_so(self):
        self.assertIn("尚未校讀完", self._status())

    def test_a_finished_vision_pass_is_not_reported_as_unread(self):
        # No tesseract draft anywhere -- which is the normal state for an
        # episode read by vision alone, and used to be enough to hide it.
        status = self._status(vision=True)
        self.assertNotIn("待處理", status)

    def test_vision_wins_over_a_tesseract_draft(self):
        status = self._status(tesseract=True, vision=True)
        self.assertNotIn("待處理", status)


if __name__ == "__main__":
    unittest.main()
