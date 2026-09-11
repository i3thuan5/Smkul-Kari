"""publish: 把關的單位是**一集**，毋是一批。

歷史：本底 `gate()` 行過規本 inventory，任何一筆 pending 無做完規批
就擋牢；2026-08-31 縮做照播出月份分開把關。這馬（2026-09-09）閣縮做
**逐集**——一集家己有影切好、精修好、讀煞，就家己會使定版，仝一批
內底無做煞ê別集擋伊袂牢。

實際踏著ê坑：2021-01 有 58 集連 cue 都猶未切，共 006午 彼集擋牢。
彼集ê時間軸干焦踮佇工作目錄，母帶已經刣掉、`out/mkv/` 嘛無伊——
工作目錄若清掉就永遠生袂轉來。

為啥拆到單集猶原自洽：`publishable()` 本底就是逐集ê檢查（切過、
精修過、讀煞）；`smkul.csv` 干焦列無 pending ê集；`rebuild --verify`
嘛干焦行無 pending ê集。**無一集是替別集背書ê**。

`gate()` 佮 `months_of()` 留咧，做「這幾集是按怎猶未會使發」ê查詢
介面，毋過無閣決定寫抑無寫。
"""
import unittest
from unittest import mock

from scripts.news import publish


def entry(name, pending=False):
    return {"srt_name": name, "slug": name,
            "pending": pending}


FEB = "20210223_054_午間_Test_測試"
FEB2 = "20210224_055_午間_Test_測試"
JAN = "20210105_005_午間_Test_測試"
JAN2 = "20210106_006_午間_Test_測試"


class TestGateQuery(unittest.TestCase):
    """`gate(entries, month)` 是查詢介面，毋是寫入ê閘門。

    伊ê行為無變——照舊回「這幾集猶未做煞」——干焦 `main()` 無閣
    提伊來擋寫入。
    """

    def blocked(self, entries, month, unfinished=()):
        def fake(one):
            if one["srt_name"] in unfinished:
                return "", "視覺辨識尚未讀完"
            return "work", ""
        with mock.patch.object(publish, "publishable", fake):
            return publish.gate(entries, month)

    def test_other_months_pending_does_not_block(self):
        rows = [entry(FEB, pending=True), entry(JAN, pending=True)]
        got = self.blocked(rows, "2021-02", unfinished=[JAN])
        self.assertEqual(got, [])

    def test_this_months_pending_still_blocks(self):
        rows = [entry(FEB, pending=True), entry(JAN, pending=True)]
        got = self.blocked(rows, "2021-02", unfinished=[FEB])
        self.assertEqual([name for name, _ in got], [FEB])

    def test_delivered_episodes_are_never_a_reason(self):
        rows = [entry(FEB, pending=False)]
        got = self.blocked(rows, "2021-02", unfinished=[FEB])
        self.assertEqual(got, [])

    def test_reports_only_the_unfinished_ones(self):
        """仝一个月內底，`gate()` 干焦報無做煞ê彼幾集。

        （本底這條號做 all_or_nothing，講ê是「一集無好勢規個月擋牢」。
        彼是舊ê寫入規矩，2026-09-09 改做逐集了後就無彼款代誌矣；
        `gate()` 本身回啥物並無變。）
        """
        rows = [entry(FEB, pending=True), entry(FEB2, pending=True)]
        got = self.blocked(rows, "2021-02", unfinished=[FEB2])
        self.assertEqual([name for name, _ in got], [FEB2])

    def test_no_month_given_means_the_whole_inventory(self):
        """無講月份ê時，照原本ê款行過規本——予別ê呼叫者袂著。"""
        rows = [entry(FEB, pending=True), entry(JAN, pending=True)]
        got = self.blocked(rows, None, unfinished=[JAN])
        self.assertEqual([name for name, _ in got], [JAN])


class TestPublishPerEpisode(unittest.TestCase):
    """`main()` 逐集決定，無做煞ê集擋袂牢做煞ê。"""

    def run_main(self, rows, unfinished=(), argv=None):
        written = []

        def fake_publishable(one):
            if one["srt_name"] in unfinished:
                return "", "待處理（尚未切cue）"
            return "work/" + one["srt_name"], ""

        def fake_publish_one(one, work):
            written.append(one["srt_name"])
            return ["cues.json"]

        with mock.patch.object(publish.episodes, "load", lambda: rows), \
                mock.patch.object(publish, "publishable",
                                  fake_publishable), \
                mock.patch.object(publish, "publish_one",
                                  fake_publish_one):
            code = publish.main(argv or [])
        return code, written, set(written)

    def test_unfinished_episode_does_not_hold_a_finished_one(self):
        """踏著ê坑：2021-01 有 58 集猶未切 cue，共做煞ê 006午 擋牢。

        彼集ê時間軸干焦踮工作目錄，母帶已經刣掉，工作目錄若清掉
        就生袂轉來——所以「規批做煞才會使寫」這條害伊一直無法度
        入 store。
        """
        rows = [entry(JAN, pending=True), entry(JAN2, pending=True)]
        code, written, cleared = self.run_main(rows, unfinished=[JAN2])
        self.assertEqual(code, 0)
        self.assertEqual(written, [JAN])
        self.assertEqual(cleared, {JAN})

    def test_unfinished_episode_is_not_written_and_is_named(self):
        """無做煞ê集袂使綴咧寫出去，而且愛講伊敢在佗一步。"""
        rows = [entry(JAN, pending=True), entry(JAN2, pending=True)]
        code, written, cleared = self.run_main(rows, unfinished=[JAN2])
        self.assertEqual(code, 0)
        self.assertNotIn(JAN2, written)
        self.assertNotIn(JAN2, cleared)

    def test_nothing_finished_is_not_a_failure(self):
        """一集都猶未做煞ê時陣回 0，毋是回非零。

        回非零會予批次ê script 共「猶未輪著」讀做「失敗」。
        """
        rows = [entry(JAN, pending=True), entry(FEB, pending=True)]
        code, written, cleared = self.run_main(rows,
                                               unfinished=[JAN, FEB])  # noqa
        self.assertEqual(code, 0)
        self.assertEqual(written, [])

    def test_check_writes_nothing(self):
        rows = [entry(JAN, pending=True)]
        code, written, cleared = self.run_main(rows, argv=["--check"])
        self.assertEqual(code, 0)
        self.assertEqual(written, [])


class TestMonthsOf(unittest.TestCase):
    def test_groups_entries_by_broadcast_month(self):
        rows = [entry(FEB), entry(FEB2), entry(JAN)]
        self.assertEqual(publish.months_of(rows), ["2021-01", "2021-02"])

    def test_each_month_appears_once(self):
        rows = [entry(FEB), entry(FEB2)]
        self.assertEqual(publish.months_of(rows), ["2021-02"])


if __name__ == "__main__":
    unittest.main()
