"""vision_complete: has every cue of this episode actually been read?

Getting this wrong in the permissive direction is expensive and invisible:
the episode is assembled, published and marked delivered while some of its
subtitles are simply absent from the SRT.

Counting is not the same as checking. A verified.json can hold entries for
cue numbers that no longer exist -- rebuilding the contact sheets renumbers
them -- and then the count reaches the total while real cues sit unread.
"""
import json
import os
import tempfile
import unittest

from scripts.news import make_all


class TestVisionComplete(unittest.TestCase):
    def _work(self, cues, verified):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        listed = []
        for index in cues:
            listed.append({"index": index, "start": 1.0, "end": 2.0})
        os.makedirs(os.path.join(tmp.name, "1-cues"), exist_ok=True)
        self._write(tmp.name, os.path.join("1-cues", "cues.json"),
                    {"cues": listed})
        marked = {}
        for index in verified:
            marked[str(index)] = {"han": True}
        self._write(tmp.name, "verified.json", marked)
        return tmp.name

    def _write(self, work, name, value):
        with open(os.path.join(work, name), "w", encoding="utf-8") as handle:
            json.dump(value, handle)

    def test_every_cue_read(self):
        self.assertTrue(make_all.vision_complete(self._work([1, 2, 3],
                                                            [1, 2, 3])))

    def test_one_cue_unread(self):
        self.assertFalse(make_all.vision_complete(self._work([1, 2, 3],
                                                             [1, 2])))

    def test_enough_rows_but_the_wrong_ones(self):
        # Three cues, three verified rows, and cue 3 was never read: 99 is a
        # number left over from an earlier numbering. A count says finished.
        self.assertFalse(make_all.vision_complete(self._work([1, 2, 3],
                                                             [1, 2, 99])))

    def test_a_work_dir_with_nothing_in_it(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.assertFalse(make_all.vision_complete(tmp.name))

    def test_no_cues_at_all_is_not_finished(self):
        self.assertFalse(make_all.vision_complete(self._work([], [])))


if __name__ == "__main__":
    unittest.main()
