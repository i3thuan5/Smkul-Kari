"""walk.todo: 佗幾支猶欲做、佗幾支已經好矣。

跳過ê判準是「遠端敆本機成品ê位元組數仝款」，毋是「遠端有這个檔案」:
傳一半斷去會留一个短檔案，若干焦看有無，彼个短檔案就會讀做做好矣。
"""
import unittest

from tools.mxf2mkv import walk


class TestNeedsUpload(unittest.TestCase):
    def test_absent_remote_needs_upload(self):
        self.assertTrue(walk.needs_upload(1000, None))

    def test_same_size_is_done(self):
        self.assertFalse(walk.needs_upload(1000, 1000))

    def test_short_remote_needs_redo(self):
        """傳一半斷去ê短檔案愛重做，袂使算做好矣。"""
        self.assertTrue(walk.needs_upload(1000, 640))

    def test_longer_remote_also_needs_redo(self):
        self.assertTrue(walk.needs_upload(1000, 1200))


class TestPlan(unittest.TestCase):
    def test_limit_takes_the_first_n(self):
        rows = ["a.mxf", "b.mxf", "c.mxf"]
        self.assertEqual(walk.apply_limit(rows, 2), ["a.mxf", "b.mxf"])

    def test_zero_limit_means_everything(self):
        rows = ["a.mxf", "b.mxf", "c.mxf"]
        self.assertEqual(walk.apply_limit(rows, 0), rows)

    def test_limit_beyond_the_end_is_harmless(self):
        rows = ["a.mxf"]
        self.assertEqual(walk.apply_limit(rows, 9), rows)


if __name__ == "__main__":
    unittest.main()
