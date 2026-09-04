"""Re-running a step whose output already exists, on purpose.

Every step skips when its output is there -- a batch that dies halfway
picks up where it stopped instead of paying for the vosk decode again.
That is right nearly always, and wrong for the one operation the spec
names explicitly: **when the picture side's timeline changes, the speech
side has to be projected onto it again**. The old entries are exactly
what must not be kept.

沒這个開關ê時，欲重投影就愛家己去刣檔案，而彼是「刣毋著就愛重跑
vosk」ê動作——`1-words` 佮 `2-entries` 差一个數量級ê代價。
"""
import unittest

from scripts.news import asrmt_run


class TestRedo(unittest.TestCase):
    def setUp(self):
        self.addCleanup(asrmt_run.set_redo, False)

    def test_by_default_an_existing_output_is_left_alone(self):
        asrmt_run.set_redo(False)
        self.assertFalse(asrmt_run.step_needed(__file__))

    def test_a_missing_output_is_always_needed(self):
        asrmt_run.set_redo(False)
        self.assertTrue(asrmt_run.step_needed(__file__ + ".nope"))

    def test_redo_makes_an_existing_output_needed_again(self):
        asrmt_run.set_redo(True)
        self.assertTrue(asrmt_run.step_needed(__file__))

    def test_the_switch_goes_back(self):
        asrmt_run.set_redo(True)
        asrmt_run.set_redo(False)
        self.assertFalse(asrmt_run.step_needed(__file__))


if __name__ == "__main__":
    unittest.main()
