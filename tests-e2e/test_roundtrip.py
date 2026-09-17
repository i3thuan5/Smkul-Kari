"""Full round trip: burn a known SRT in, pull it back out, compare.

Needs ffmpeg (with libass), tesseract + chi_tra, and a CJK font -- run via
`tox -e e2etest`. The unit envs never touch this directory.
"""
import os
import shutil
import tempfile
import unittest

import numpy as np

import fixture


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

    def test_band_chinese_at_29_97(self):
        # 語料全是 30000/1001：取樣格線永遠對不齊來源格
        fps = 30000 / 1001
        result = fixture.run_end_to_end(self.tmpdir, True,
                                        fixture.GROUND_TRUTH_HAN, "chi_tra",
                                        "band-chinese-2997",
                                        rate="30000/1001")
        self._assert_timing(result)
        # sample_ts 是真實畫面時間，照它抽格抽得回判斷用的那一格
        for cue in result["manifest"]["cues"]:
            index = round(cue["sample_ts"] * fps)
            self.assertAlmostEqual(cue["sample_ts"], index / fps, delta=0.001)
        self.assertEqual(result["manifest"]["sampling"], "nearest-native")

        refined = fixture.refine_pairs(result)
        self.assertEqual(len(refined), 2 * len(fixture.GROUND_TRUTH_HAN) - 1)
        moved = 0
        for truth, got, reason in refined:
            if got is None:
                continue
            moved += 1
            self.assertLessEqual(abs(got - truth), 0.05,
                                 "boundary %.3f refined to %.3f"
                                 % (truth, got))
        print("  refined %d/%d boundaries within 0.05s"
              % (moved, len(refined)))
        self.assertGreaterEqual(moved, len(refined) - 1)


if __name__ == "__main__":
    unittest.main()
