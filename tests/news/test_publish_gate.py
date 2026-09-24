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
import json
import os
import tempfile
import unittest
from unittest import mock

from scripts.news import paths
from scripts.news import publish
from scripts.news import rebuild
from scripts.news import segments


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


DEC = "20241201_336_晨間_Thau_邵"


def segment_rows(basis="自動"):
    return [{"起秒": "0", "迄秒": "100", "類型": "攝影棚", "單元語別": "邵",
             "字幕上緣y": "722", "字幕下緣y": "848", "依據": "自動",
             segments.INTERVIEWEE: ""},
            {"起秒": "100", "迄秒": "600.000", "類型": "島語時間",
             "單元語別": "泰雅", "字幕上緣y": "940", "字幕下緣y": "1060",
             "依據": basis, segments.INTERVIEWEE: ""}]


class TestSegmentsGoWithTheTimeline(unittest.TestCase):
    """段落表確認了就綴時間軸入 `1-ocr/0-segments/<年-月>/`。"""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = tmp.name
        self.work = os.path.join(tmp.name, "x.work")
        timeline = paths.refined_cues(self.work)
        os.makedirs(os.path.dirname(timeline))
        with open(timeline, "w", encoding="utf-8") as handle:
            json.dump({"cues": [], "refined": True, "duration": 600.0},
                      handle)
        self.store = os.path.join(tmp.name, "0-segments")
        self.target = paths.stage_path(self.store, DEC, ".csv")

    def publish(self, rows):
        segments.write(paths.segments_file(self.work), rows)
        return publish.publish_segments(entry(DEC), self.work,
                                        folder=self.store)

    def test_a_confirmed_table_is_written_under_its_month(self):
        self.assertEqual(self.publish(segment_rows("Claude Vision 確認")),
                         "write")
        self.assertTrue(self.target.endswith(
            os.path.join("0-segments", "2024-12", DEC + ".csv")))
        self.assertEqual(segments.read(self.target),
                         segment_rows("Claude Vision 確認"))

    def test_the_same_content_is_not_rewritten(self):
        self.publish(segment_rows("Claude Vision 確認"))
        before = os.stat(self.target).st_mtime_ns
        self.assertEqual(self.publish(segment_rows("Claude Vision 確認")),
                         "same")
        self.assertEqual(os.stat(self.target).st_mtime_ns, before)

    def test_an_unconfirmed_table_waits(self):
        # 島語時間教佗一族猶未確認：無確認ê段落表入袂了 store。
        got = self.publish(segment_rows(segments.PENDING))
        self.assertTrue(got.startswith("wait"), got)
        self.assertFalse(os.path.exists(self.target))

    def test_an_episode_without_a_table_is_nothing_to_do(self):
        got = publish.publish_segments(entry(DEC), self.work,
                                       folder=self.store)
        self.assertEqual(got, "none")


class TestSegmentsInTheStoreAreChecked(unittest.TestCase):
    """`rebuild --verify` 也驗 store 內底ê段落表。"""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.segments = os.path.join(tmp.name, "0-segments")
        self.cues = os.path.join(tmp.name, "1-cues")

    def put(self, name, rows, duration=600.0):
        target = paths.stage_path(self.segments, name, ".csv")
        os.makedirs(os.path.dirname(target), exist_ok=True)
        segments.write(target, rows)
        timeline = paths.stage_path(self.cues, name, ".json")
        os.makedirs(os.path.dirname(timeline), exist_ok=True)
        with open(timeline, "w", encoding="utf-8") as handle:
            json.dump({"cues": [], "duration": duration}, handle)

    def problems(self, names):
        return rebuild.segment_problems(set(names), base=self.segments,
                                        cues_base=self.cues)

    def test_an_orphan_table_is_named(self):
        self.put(DEC, segment_rows("Claude Vision 確認"))
        got = self.problems([])
        self.assertEqual(len(got), 1)
        self.assertIn(DEC, got[0])

    def test_a_table_that_fails_the_check_is_named(self):
        self.put(DEC, segment_rows("Claude Vision 確認"), duration=700.0)
        got = self.problems([DEC])
        self.assertEqual(len(got), 1)
        self.assertIn("影片長度", got[0])

    def test_episodes_without_a_table_are_not_missing_anything(self):
        # 2021 年大部分集數無段落表，彼毋是缺件。
        self.assertEqual(self.problems([DEC, JAN, FEB]), [])

    def test_a_good_table_passes(self):
        self.put(DEC, segment_rows("Claude Vision 確認"))
        self.assertEqual(self.problems([DEC]), [])


DEC_SLUG = "2024_336_2024-12-01_晨間_Thau_邵"


class TestStaleWorkDir(unittest.TestCase):
    """帶外補切直接改 Kari-SRT，work dir 猶是補切進前ê舊時間軸。

    踏著ê坑（2026-09-24）：`20241209_344_晚間_Amis_阿美` 補切了後，對
    2024-12 規月跑 publish，work dir 彼份 575 條ê舊時間軸共 store 729
    條ê蓋掉，「帶外專題」彼逝段落表嘛無去；`rebuild --verify` 才抓著
    SRT 對袂齊。publish 無報任何錯。
    """

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = tmp.name
        self.entry = {"srt_name": DEC, "slug": DEC_SLUG, "pending": False}
        self.work = paths.work_dir(DEC_SLUG, tmp.name)
        self.cues = os.path.join(tmp.name, "1-cues")

    def timeline(self, path, areas=None):
        book = {"cues": [], "refined": True, "duration": 600.0}
        if areas is not None:
            book["areas"] = areas
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(book, handle)

    def judge(self):
        with mock.patch.object(publish, "WORK", self.root):
            return publish.publishable(self.entry, cues_dir=self.cues)

    def spliced_store(self):
        self.timeline(paths.stage_path(self.cues, DEC, ".json"),
                      {"帶外專題": {"preset": "titv-news-848",
                                "region": [0, 722, 1920, 126]}})

    def test_a_spliced_store_timeline_is_not_overwritten(self):
        self.timeline(paths.refined_cues(self.work))
        self.spliced_store()
        work, reason = self.judge()
        self.assertEqual(work, "")
        self.assertIn("帶外專題", reason)

    def test_a_work_dir_that_has_the_area_too_is_fine(self):
        # 島語時間、部落信箱是切 cue 時就佇 work dir 重切ê，兩爿攏有。
        self.timeline(paths.refined_cues(self.work),
                      {"帶外專題": {"preset": "titv-news-848",
                                "region": [0, 722, 1920, 126]}})
        self.spliced_store()
        work, reason = self.judge()
        self.assertEqual(reason, "")

    def test_the_segments_table_is_not_overwritten_either(self):
        # 仝一集又踏一擺（2026-09-24 深夜）：受訪者名條ê腳本直接叫
        # publish_segments，work dir 彼份補切進前ê段落表共「帶外專題」
        # 彼逝洗掉。publishable() 有把關，publish_segments 無。
        self.timeline(paths.refined_cues(self.work))
        self.spliced_store()
        segments.write(paths.segments_file(self.work),
                       segment_rows("Claude Vision 確認"))
        store = os.path.join(self.root, "0-segments")
        target = paths.stage_path(store, DEC, ".csv")
        got = publish.publish_segments(self.entry, self.work, folder=store,
                                       cues_dir=self.cues)
        self.assertTrue(got.startswith("wait"), got)
        self.assertIn("帶外專題", got)
        self.assertFalse(os.path.exists(target))

    def test_an_episode_not_yet_in_the_store_is_published(self):
        self.timeline(paths.refined_cues(self.work))
        work, reason = self.judge()
        self.assertEqual(reason, "")
        self.assertTrue(work)


if __name__ == "__main__":
    unittest.main()
