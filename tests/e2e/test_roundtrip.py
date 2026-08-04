"""Full round trip: burn a known SRT in, pull it back out, compare.

Needs ffmpeg (with libass), tesseract + chi_tra, and a CJK font -- run via
`tox -e subtitle-e2e`. The unit envs never touch this directory.
"""
import os
import shutil
import tempfile
import unittest

import numpy as np

from tests.e2e import fixture


class TestRoundTrip(unittest.TestCase):
    KEEP = os.environ.get("E2E_KEEP", "")

    @classmethod
    def setUpClass(cls):
        fixture.require_fixture_tools()
        cls.tmpdir = cls.KEEP or tempfile.mkdtemp(prefix="subs2srt-e2e-")
        os.makedirs(cls.tmpdir, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        if not cls.KEEP:
            shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def _assert_timing(self, result):
        self.assertEqual(result["missed"], 0,
                         "%(label)s missed %(missed)d cue(s)" % result)
        self.assertEqual(result["extra"], 0,
                         "%(label)s found %(extra)d spurious cue(s)" % result)
        self.assertEqual(result["matched"], result["truth"])
        self.assertTrue(result["start_errs"], "no cue matched at all")
        worst = float(np.max(np.abs(result["start_errs"])))
        self.assertLessEqual(worst, 0.30,
                             "worst start error %.3fs > 0.30s" % worst)

    def test_plain_latin_roundtrip(self):
        result = fixture.run_end_to_end(self.tmpdir, False,
                                        fixture.GROUND_TRUTH, "eng",
                                        "plain-latin")
        self._assert_timing(result)

    def test_band_chinese_roundtrip(self):
        result = fixture.run_end_to_end(self.tmpdir, True,
                                        fixture.GROUND_TRUTH_HAN, "chi_tra",
                                        "band-chinese")
        self._assert_timing(result)
        # the odd-region crop check reuses this fixture's video
        video = os.path.join(self.tmpdir, "fixture_band-chinese.mp4")
        frames = fixture.check_odd_region(video)
        self.assertGreater(frames, 0)


if __name__ == "__main__":
    unittest.main()
