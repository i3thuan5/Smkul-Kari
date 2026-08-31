"""lowpri：kā長時間ê重工降優先權，莫kā別人ê機器食牢去。

`encode_master.sh` 本底就有 `nice -n 15 ionice -c 3`（使用者裁定），
按呢彼支 ffmpeg 燒幾點鐘嘛袂影響著別項工課。仝一套愛套佇其他仝款重ê
步數：vosk 解碼、切 cue、邊界精修、出 contact sheet。

shell 彼爿直接寫 `nice -n 15 ionice -c 3`；Python 這爿走 `os.nice()`,
而且**子行程會 kè-sîng 老爸ê nice 值**，所以佇入口叫一擺，內底彼隻
ffmpeg 嘛就綴咧降落去。
"""
import unittest
from unittest import mock

from scripts import lowpri


class TestLevel(unittest.TestCase):
    def test_the_same_level_as_the_mkv_transcode(self):
        # 兩爿愛仝一个數字，若無「跟轉 mkv 一樣」這句話就無意義矣
        self.assertEqual(lowpri.NICE, 15)


class TestBeNice(unittest.TestCase):
    def setUp(self):
        lowpri._applied = False
        self.addCleanup(setattr, lowpri, "_applied", False)

    def test_it_drops_the_priority(self):
        with mock.patch("os.nice", return_value=15) as niced:
            self.assertEqual(lowpri.be_nice(), 15)
        niced.assert_called_once_with(15)

    def test_calling_it_twice_does_not_stack(self):
        # os.nice 是**累加**ê：叫兩擺就變 30，比想欲ê閣較低。入口若
        # 有兩个（asrmt_batch 呼叫 asrmt_run），這條就會拄著。
        with mock.patch("os.nice", return_value=15) as niced:
            lowpri.be_nice()
            lowpri.be_nice()
        self.assertEqual(niced.call_count, 1)

    def test_a_platform_without_nice_is_not_a_crash(self):
        # Windows 無 os.nice。降袂落去就照常做，莫kā規條 pipeline 擋牢。
        with mock.patch("os.nice", side_effect=AttributeError):
            self.assertIsNone(lowpri.be_nice())

    def test_no_permission_is_not_a_crash_either(self):
        with mock.patch("os.nice", side_effect=OSError(1, "denied")):
            self.assertIsNone(lowpri.be_nice())


if __name__ == "__main__":
    unittest.main()
