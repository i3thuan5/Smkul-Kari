"""audio_tracks: 用音軌指紋決定「封存對不對」與「該留哪幾軌」。

純函式，零 I/O——指紋怎麼算是 encode_master.sh 的事，這裡只吃算好的
字串。之所以要獨立成一支，是因為 N 軌的去留判斷在 bash 裡是巢狀陣列
迴圈，寫得出來但測不動；而判斷錯了的下場是靜靜丟掉一條真正不同的
音軌，那正是最需要被測到的事。
"""
import unittest

from scripts.transcode import audio_tracks

A = "957e0a09f97871af8c611d306aad8ab5"
B = "0be1ea57970f2418d0262c49824f0077"
C = "3c1f8d2e4b7a6905fe1d8c3b2a4e7f90"


class TestVerify(unittest.TestCase):
    def test_all_tracks_match(self):
        got = audio_tracks.decide([A, B], [A, B])
        self.assertTrue(got.bit_exact)
        self.assertEqual(got.mismatched, [])

    def test_one_track_differs_names_which(self):
        """毋是干焦講「無仝」，愛講是佗一軌。

        一支片有 N 軌，訊息若干焦講「音訊無仝」，人愛家己去一軌一軌
        比才知影是佗一條，彼是這隻程式已經知影ê代誌。
        """
        got = audio_tracks.decide([A, B], [A, C])
        self.assertFalse(got.bit_exact)
        self.assertEqual(got.mismatched, [1])

    def test_track_count_must_agree(self):
        """來源 N 軌、封存 M 軌，本身就是編碼那步做毋著矣。"""
        got = audio_tracks.decide([A, B], [A])
        self.assertFalse(got.bit_exact)


class TestKeep(unittest.TestCase):
    def test_single_track_is_kept_as_is(self):
        got = audio_tracks.decide([A], [A])
        self.assertEqual(got.keep, [0])

    def test_two_identical_tracks_keep_one(self):
        got = audio_tracks.decide([A, A], [A, A])
        self.assertEqual(got.keep, [0])

    def test_two_differing_tracks_keep_both(self):
        """實測 63 支封存有 28 支是這款，差佇上尾彼幾个位元。

        差是真ê，恬恬擲掉一軌袂使得——雙軌囥無仝物件（主聲道／國際聲、
        族語／華語）佇廣播是標準做法之一。
        """
        got = audio_tracks.decide([A, B], [A, B])
        self.assertEqual(got.keep, [0, 1])

    def test_three_tracks_two_identical(self):
        got = audio_tracks.decide([A, A, B], [A, A, B])
        self.assertEqual(got.keep, [0, 2])

    def test_three_tracks_all_different(self):
        got = audio_tracks.decide([A, B, C], [A, B, C])
        self.assertEqual(got.keep, [0, 1, 2])

    def test_duplicates_keep_the_first_of_each_group(self):
        """留頭一條，毋是留上尾條——按呢軌ê順序才袂顛倒。"""
        got = audio_tracks.decide([B, A, B], [B, A, B])
        self.assertEqual(got.keep, [0, 1])

    def test_no_keep_decision_when_verification_failed(self):
        """驗無過ê時陣，「留佗幾軌」這个問題無意義。

        指紋若對袂起來，代表封存內底ê聲音毋是來源彼份，這時陣去
        判斷佗兩軌相仝，是提無效ê資料咧做決定。
        """
        got = audio_tracks.decide([A, B], [A, C])
        self.assertEqual(got.keep, [])


class TestSummary(unittest.TestCase):
    def test_two_identical(self):
        got = audio_tracks.decide([A, A], [A, A])
        self.assertEqual(got.summary, "兩軌相同，留一軌")

    def test_two_differing(self):
        got = audio_tracks.decide([A, B], [A, B])
        self.assertEqual(got.summary, "兩軌不同，兩條都留")

    def test_single_track(self):
        got = audio_tracks.decide([A], [A])
        self.assertEqual(got.summary, "一軌")

    def test_three_tracks_say_the_count(self):
        """三軌以上愛共軌數寫出來——按呢人才看會出來有無漏掉。

        舊版 encode_master.sh 干焦 map a:0 佮 a:1，第三軌恬恬無去，
        連一句話都無。
        """
        got = audio_tracks.decide([A, A, B], [A, A, B])
        self.assertEqual(got.summary, "3 軌，其中 2 軌相同，留 2 軌")

    def test_mismatch_summary_names_the_track(self):
        got = audio_tracks.decide([A, B], [A, C])
        self.assertEqual(got.summary, "音訊對袂起來：第 2 軌")


if __name__ == "__main__":
    unittest.main()
