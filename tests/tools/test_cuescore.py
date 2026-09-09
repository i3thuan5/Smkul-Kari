"""cuescore: the three numbers that say whether a cut got better or worse.

Everything here is synthetic. The tool itself reads a real timeline and the
real vision TSVs, which is why it lives in `tools/` and not in the pipeline
-- but its arithmetic has to be pinned somewhere offline, and this is it.
"""
import json
import os
import tempfile
import unittest

from tools.cuescore import score


class ScoreCase(unittest.TestCase):
    def _store(self, cues, texts, lines=("han",)):
        """A timeline plus the vision TSVs that go with it."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        timeline = os.path.join(tmp.name, "ep.json")
        with open(timeline, "w", encoding="utf-8") as handle:
            json.dump({"region": [0, 722, 1920, 122], "cues": cues}, handle)
        vision = os.path.join(tmp.name, "vision")
        os.makedirs(vision)
        with open(os.path.join(vision, "b01.tsv"), "w",
                  encoding="utf-8") as handle:
            for index, text in texts.items():
                if isinstance(text, dict):
                    for name in lines:
                        handle.write("%d\t%s\t%s\n"
                                     % (index, name, text.get(name, "")))
                else:
                    handle.write("%d\t%s\t%s\n" % (index, lines[0], text))
        return timeline, vision


class TestRepeatedPairs(ScoreCase):
    """Adjacent cues that touch and say the same thing: work read twice.

    24.9% of the whole store, measured. Only touching pairs count -- a line
    that leaves the screen and comes back later is two real subtitles.
    """

    def test_touching_pair_with_the_same_text_counts(self):
        cues = [{"index": 1, "start": 1.0, "end": 2.0},
                {"index": 2, "start": 2.0, "end": 3.0}]
        timeline, vision = self._store(cues, {1: "同一句", 2: "同一句"})
        self.assertEqual(score.score(timeline, vision)["repeated"], 1)

    def test_a_gap_between_them_is_not_a_repeat(self):
        cues = [{"index": 1, "start": 1.0, "end": 2.0},
                {"index": 2, "start": 2.5, "end": 3.0}]
        timeline, vision = self._store(cues, {1: "同一句", 2: "同一句"})
        self.assertEqual(score.score(timeline, vision)["repeated"], 0)

    def test_different_text_is_not_a_repeat(self):
        cues = [{"index": 1, "start": 1.0, "end": 2.0},
                {"index": 2, "start": 2.0, "end": 3.0}]
        timeline, vision = self._store(cues, {1: "頭一句", 2: "第二句"})
        self.assertEqual(score.score(timeline, vision)["repeated"], 0)

    def test_blank_cues_are_left_out_of_it(self):
        cues = [{"index": 1, "start": 1.0, "end": 2.0},
                {"index": 2, "start": 2.0, "end": 3.0}]
        timeline, vision = self._store(cues, {1: "", 2: ""})
        self.assertEqual(score.score(timeline, vision)["repeated"], 0)


class TestAgainstAnotherCut(ScoreCase):
    """Swallowed and dropped, judged against the delivered timeline.

    Both cost a subtitle, and this change trades one for the other: on one
    episode swallowed went 87 -> 43 while dropped went 0 -> 3. Counting only
    one of the two would have made a losing change look like a win.
    """

    TRUTH = [{"index": 1, "start": 1.0, "end": 2.0},
             {"index": 2, "start": 2.0, "end": 3.0},
             {"index": 3, "start": 3.0, "end": 4.0}]
    TEXTS = {1: "第一句", 2: "第二句", 3: "第三句"}

    def test_one_cue_covering_a_real_change_is_swallowed(self):
        timeline, vision = self._store(self.TRUTH, self.TEXTS)
        got = score.score(timeline, vision,
                          cut=[{"index": 1, "start": 1.0, "end": 4.0}])
        self.assertEqual(got["swallowed"], 2)

    def test_a_subtitle_no_cue_covers_is_dropped(self):
        timeline, vision = self._store(self.TRUTH, self.TEXTS)
        got = score.score(timeline, vision,
                          cut=[{"index": 1, "start": 1.0, "end": 2.0},
                               {"index": 2, "start": 3.0, "end": 4.0}])
        self.assertEqual(got["dropped"], 1)

    def test_the_same_cut_scores_clean(self):
        timeline, vision = self._store(self.TRUTH, self.TEXTS)
        got = score.score(timeline, vision, cut=self.TRUTH)
        self.assertEqual(got["swallowed"], 0)
        self.assertEqual(got["dropped"], 0)


class TestTwoRowCorpus(ScoreCase):
    """開會了 has two rows a cue; both together are the text.

    Comparing one row alone calls two cues identical when only the Chinese
    matched, which is exactly the pair a bilingual corpus must keep apart.
    """

    def test_rows_are_joined_before_comparing(self):
        cues = [{"index": 1, "start": 1.0, "end": 2.0},
                {"index": 2, "start": 2.0, "end": 3.0}]
        texts = {1: {"formosan": "aaa", "han": "仝款"},
                 2: {"formosan": "bbb", "han": "仝款"}}
        timeline, vision = self._store(cues, texts,
                                       lines=("formosan", "han"))
        self.assertEqual(score.score(timeline, vision)["repeated"], 0)


class TestRepeatsOfAnotherCut(ScoreCase):
    """Scoring a different cut has to find its text by time, not by index.

    Re-cutting renumbers every cue, so the numbers in a fresh timeline mean
    nothing to the TSVs that were read off the delivered one. Looking text
    up by index there quietly scores zero repeats for every cut, which would
    make any change look like a total success.
    """

    TRUTH = [{"index": 1, "start": 1.0, "end": 3.0},
             {"index": 2, "start": 3.0, "end": 5.0}]
    TEXTS = {1: "一句話", 2: "另外一句"}

    def test_a_cut_that_splits_one_line_shows_the_repeat(self):
        timeline, vision = self._store(self.TRUTH, self.TEXTS)
        got = score.score(timeline, vision,
                          cut=[{"index": 1, "start": 1.0, "end": 2.0},
                               {"index": 2, "start": 2.0, "end": 3.0},
                               {"index": 3, "start": 3.0, "end": 5.0}])
        self.assertEqual(got["repeated"], 1)

    def test_a_cut_matching_the_delivered_one_shows_none(self):
        timeline, vision = self._store(self.TRUTH, self.TEXTS)
        got = score.score(timeline, vision, cut=self.TRUTH)
        self.assertEqual(got["repeated"], 0)
