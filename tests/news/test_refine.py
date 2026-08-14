"""refine_cues: transition rules, the ±0.2s safety net, atomic write-back.

All offline: the video-facing part (label_frames over real pixels) is
exercised in the field; here the pure logic is pinned -- run confirmation,
midpoint rule, boundary bookkeeping, and the all-or-nothing episode write.
"""
import json
import os
import tempfile
import unittest
from unittest import mock

from scripts.news import refine_cues


class TestTransitionTime(unittest.TestCase):
    TIMES = [10.00, 10.04, 10.08, 10.12, 10.16, 10.20, 10.24]

    def test_adjacent_switch_takes_the_first_right_frame(self):
        labels = ["L", "L", "L", "R", "R", "R", "R"]
        got = refine_cues.transition_time(self.TIMES, labels)
        self.assertAlmostEqual(got, 10.12)

    def test_unknown_stretch_takes_its_midpoint(self):
        # interlaced transition frames sit between the two runs
        labels = ["L", "L", "?", "?", "R", "R", "R"]
        got = refine_cues.transition_time(self.TIMES, labels)
        self.assertAlmostEqual(got, (10.04 + 10.16) / 2.0)

    def test_single_stray_frame_is_not_believed(self):
        # one stray R amid L must not end the cue early (CONFIRM=2)
        labels = ["L", "L", "R", "L", "L", "R", "R"]
        got = refine_cues.transition_time(self.TIMES, labels)
        self.assertAlmostEqual(got, 10.20)

    def test_window_not_opening_on_left_side_is_refused(self):
        labels = ["R", "R", "L", "L", "R", "R", "R"]
        self.assertIsNone(refine_cues.transition_time(self.TIMES, labels))

    def test_window_not_closing_on_right_side_is_refused(self):
        labels = ["L", "L", "R", "R", "R", "L", "L"]
        self.assertIsNone(refine_cues.transition_time(self.TIMES, labels))

    def test_all_unknown_is_refused(self):
        labels = ["?", "?", "?", "?", "?", "?", "?"]
        self.assertIsNone(refine_cues.transition_time(self.TIMES, labels))


class TestBoundariesOf(unittest.TestCase):
    def test_touching_cues_share_one_joint_boundary(self):
        cues = [{"index": 1, "start": 1.0, "end": 2.0},
                {"index": 2, "start": 2.0, "end": 3.0}]
        got = refine_cues.boundaries_of(cues)
        kinds = []
        for _positions, kind, _t in got:
            kinds.append(kind)
        self.assertEqual(kinds, ["start", "joint", "end"])
        self.assertEqual(got[1][0], (0, 1))

    def test_separated_cues_get_plain_edges(self):
        cues = [{"index": 1, "start": 1.0, "end": 2.0},
                {"index": 2, "start": 4.0, "end": 5.0}]
        kinds = []
        for _positions, kind, _t in refine_cues.boundaries_of(cues):
            kinds.append(kind)
        self.assertEqual(kinds, ["start", "end", "start", "end"])


class TestRefineEpisode(unittest.TestCase):
    def _cues_file(self, cues):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = os.path.join(tmp.name, "ep.json")
        manifest = {"region": [0, 722, 1920, 122], "mask": {},
                    "segmenter": {"min_ink": 120, "change": 0.35},
                    "cues": cues}
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(manifest, handle)
        return path

    CUES = [{"index": 1, "start": 10.0, "end": 12.0},
            {"index": 2, "start": 14.0, "end": 16.0}]

    def _run(self, boundary_times, dry_run=False, cues=None):
        """Run refine_episode with refine_boundary stubbed per boundary."""
        path = self._cues_file(cues or [dict(c) for c in self.CUES])
        results = list(boundary_times)

        def fake_boundary(video, region, spec, min_ink, change, t0, kind,
                          duration):
            return results.pop(0)

        with mock.patch.object(refine_cues, "probe_duration",
                               return_value=1800.0), \
                mock.patch.object(refine_cues, "refine_boundary",
                                  side_effect=fake_boundary):
            stats = refine_cues.refine_episode("fake.mxf", path,
                                               dry_run=dry_run)
        with open(path, encoding="utf-8") as handle:
            return stats, json.load(handle)

    def test_refined_times_are_written_with_flag_and_duration(self):
        stats, manifest = self._run([9.92, 12.08, 13.88, 16.12])
        self.assertTrue(manifest["refined"])
        self.assertEqual(manifest["duration"], 1800.0)
        self.assertEqual(manifest["cues"][0]["start"], 9.92)
        self.assertEqual(manifest["cues"][1]["end"], 16.12)
        self.assertEqual(stats["refined"], 4)
        self.assertEqual(stats["kept_coarse"], 0)

    def test_unclassifiable_boundary_keeps_coarse_value(self):
        stats, manifest = self._run([None, 12.08, None, None])
        self.assertEqual(manifest["cues"][0]["start"], 10.0)
        self.assertEqual(manifest["cues"][0]["end"], 12.08)
        self.assertEqual(stats["kept_coarse"], 3)

    def test_shift_beyond_limit_fails_the_whole_episode(self):
        # one bad boundary: nothing at all may be written
        with self.assertRaises(SystemExit):
            self._run([9.92, 12.5, 13.88, 16.12])
        # and the file is untouched
        path = self._cues_file([dict(c) for c in self.CUES])
        with open(path, encoding="utf-8") as handle:
            manifest = json.load(handle)
        self.assertEqual(manifest["cues"][0]["start"], 10.0)
        self.assertNotIn("refined", manifest)

    def test_dry_run_writes_nothing(self):
        stats, manifest = self._run([9.92, 12.08, 13.88, 16.12],
                                    dry_run=True)
        self.assertNotIn("refined", manifest)
        self.assertEqual(manifest["cues"][0]["start"], 10.0)
        self.assertEqual(stats["refined"], 4)

    def test_joint_boundary_moves_both_sides_together(self):
        cues = [{"index": 1, "start": 1.0, "end": 5.0},
                {"index": 2, "start": 5.0, "end": 8.0}]
        stats, manifest = self._run([0.96, 5.08, 8.04], cues=cues)
        self.assertEqual(manifest["cues"][0]["end"], 5.08)
        self.assertEqual(manifest["cues"][1]["start"], 5.08)


if __name__ == "__main__":
    unittest.main()
