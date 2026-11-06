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
import contextlib
import io
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


class TestWorkDirChangedAfterTheDecision(unittest.TestCase):
    """main() 先逐集判斷、才逐集寫：這中間 work dir 被人改掉的情形。

    發生過的事（2026-10-28，第三批搬到重播）：全庫 publish 在 store.lock
    裡跑到一半當掉，traceback 停在 `refined_timeline`，看不出是哪一集；
    排在後面的集數全部沒入庫。鎖外重跑 334 集都正常——是別的 agent
    沒拿鎖就換名、或還在精修自己的 work dir，剛好落在判斷和寫入之間。

    是不是「被人改了」要看證據（判斷那時記下的檔案大小、修改時間），
    不是看例外的種類：段落表起秒手打錯成 x 的 ValueError、磁碟滿的
    OSError 都不是別人改的，叫人「等對方做完再 publish」只會一直重複失敗。
    """

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = tmp.name
        self.store = os.path.join(tmp.name, "1-cues")
        self.tables = os.path.join(tmp.name, "0-segments")

    def work_of(self, name, body, table=None):
        work = os.path.join(self.root, name + ".work")
        path = paths.refined_cues(work)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(body)
        if table is not None:
            with open(paths.segments_file(work), "w", encoding="utf-8") \
                    as handle:
                handle.write(table)
        return work

    def run_main(self, rows, works, meddle=None):
        """works：{集名: work dir}；publishable 一律放行（判斷那時還好好的）。
        meddle：{集名: fn(work)}，寫這一集之前先做（別人沒拿鎖改 work dir）。"""
        real = publish.publish_one
        real_table = publish.publish_segments
        meddle = meddle or {}

        def fake_publishable(one):
            return works[one["srt_name"]], ""

        def into_tmp_store(one, work):
            if one["srt_name"] in meddle:
                meddle[one["srt_name"]](work)
            return real(one, work, cues_dir=self.store)

        def table_into_tmp(one, work):
            return real_table(one, work, folder=self.tables,
                              cues_dir=self.store)

        out = io.StringIO()
        with mock.patch.object(publish.episodes, "load", lambda: rows), \
                mock.patch.object(publish, "publishable",
                                  fake_publishable), \
                mock.patch.object(publish, "publish_one", into_tmp_store), \
                mock.patch.object(publish, "publish_segments",
                                  table_into_tmp), \
                contextlib.redirect_stdout(out):
            code = publish.main([])
        return code, out.getvalue()

    def stored(self, name):
        return os.path.exists(paths.stage_path(self.store, name, ".json"))

    GOOD = json.dumps({"cues": [], "refined": True, "duration": 10.0})
    TABLE = ("起秒,迄秒,類型,單元語別,字幕上緣y,字幕下緣y\n"
             "0,10,攝影棚,阿美,722,844\n")

    def test_work_dir_renamed_away_names_the_episode_and_goes_on(self):
        # 判斷時有精修時間軸，寫之前 work dir 被改名成 .stale：要講是哪一
        # 集、後面的集照樣入庫、最後回非零
        works = {JAN: self.work_of(JAN, self.GOOD),
                 JAN2: self.work_of(JAN2, self.GOOD)}

        def rename(work):
            os.rename(work, work + ".stale-1")

        code, said = self.run_main([entry(JAN), entry(JAN2)], works,
                                   {JAN: rename})
        self.assertNotEqual(code, 0)
        self.assertIn("fail  " + JAN, said)
        self.assertIn("store.lock", said)
        self.assertTrue(self.stored(JAN2))
        self.assertFalse(self.stored(JAN))

    def test_half_written_timeline_names_the_episode_and_goes_on(self):
        # 沒拿鎖的人正在寫自己的時間軸：讀到一半的 JSON。以前是沒有
        # 集名的 JSONDecodeError，整輪停掉
        works = {JAN: self.work_of(JAN, self.GOOD),
                 JAN2: self.work_of(JAN2, self.GOOD)}

        def half(work):
            with open(paths.refined_cues(work), "w",
                      encoding="utf-8") as handle:
                handle.write('{"cu')

        code, said = self.run_main([entry(JAN), entry(JAN2)], works,
                                   {JAN: half})
        self.assertNotEqual(code, 0)
        self.assertIn("fail  " + JAN, said)
        self.assertIn("store.lock", said)
        self.assertTrue(self.stored(JAN2))

    def test_table_changed_after_the_timeline_was_written(self):
        # 寫一半：時間軸已經寫進 1-cues，才在讀段落表時發現別人正在改。
        # 不可以說「沒有入庫」——時間軸其實已經進去了
        works = {JAN: self.work_of(JAN, self.GOOD, self.TABLE)}
        real_table = publish.segments.read

        def half_table(path):
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("起秒,迄秒,類型\n0,")
            return real_table(path)

        with mock.patch.object(publish.segments, "read", half_table):
            code, said = self.run_main([entry(JAN)], works)
        self.assertNotEqual(code, 0)
        self.assertTrue(self.stored(JAN))
        self.assertIn("時間軸已經入庫、段落表沒有", said)
        self.assertIn("store.lock", said)

    def test_changed_without_an_error_is_still_reported(self):
        # 別人沒拿鎖、正在一步一步改 work dir（split_cue 先改 TSV 號碼、
        # 再寫時間軸）：publish 讀得進去、沒有出錯，可是抄進去的可能是改到
        # 一半的版本。不能默默算成「入庫」
        works = {JAN: self.work_of(JAN, self.GOOD)}

        def rewrite(work):
            with open(paths.refined_cues(work), "w",
                      encoding="utf-8") as handle:
                handle.write(json.dumps({"cues": [{"index": 1}],
                                         "refined": True}))

        code, said = self.run_main([entry(JAN)], works, {JAN: rewrite})
        self.assertNotEqual(code, 0)
        self.assertIn("fail  " + JAN, said)
        self.assertIn("時間軸被改寫", said)

    def test_typo_in_the_table_is_not_blamed_on_a_lock(self):
        # 審查重現：0-segments.csv 起秒手打錯成 x。work dir 從判斷到現在
        # 都沒變，不是別人改的；以前印「是不是有人沒拿 store.lock」、還說
        # 「沒有入庫」，時間軸其實已經寫進 1-cues。照舊停下來，講是哪一
        # 集、時間軸已經寫了、work dir 沒被改過
        table = self.TABLE.replace("\n0,10,", "\nx,10,")
        works = {JAN: self.work_of(JAN, self.GOOD, table)}
        with self.assertRaises(ValueError) as caught:
            self.run_main([entry(JAN)], works)
        notes = "".join(getattr(caught.exception, "__notes__", []))
        self.assertIn(JAN, notes)
        self.assertIn("時間軸已經入庫、段落表沒有", notes)
        self.assertIn("沒有變", notes)
        self.assertNotIn("store.lock", notes)
        self.assertTrue(self.stored(JAN))

    def test_disk_full_is_not_blamed_on_a_lock(self):
        # 磁碟滿（ENOSPC，stage-read 塞滿過兩次）：不是別人改的，照舊停
        # 下來給人看，講是哪一集、還沒寫進去
        works = {JAN: self.work_of(JAN, self.GOOD),
                 JAN2: self.work_of(JAN2, self.GOOD)}

        def full(manifest):
            raise OSError(28, "No space left on device")

        with mock.patch.object(publish.redump_store, "dump", full):
            with self.assertRaises(OSError) as caught:
                self.run_main([entry(JAN), entry(JAN2)], works)
        notes = "".join(getattr(caught.exception, "__notes__", []))
        self.assertIn(JAN, notes)
        self.assertIn("沒有入庫", notes)
        self.assertNotIn("store.lock", notes)
        self.assertFalse(self.stored(JAN2))

    def test_an_unforeseen_error_still_stops_but_says_which_episode(self):
        # 程式本身的錯：照舊停下來給人看，但 traceback 要帶集名
        works = {JAN: self.work_of(JAN, self.GOOD)}

        def boom(manifest):
            raise KeyError("index")

        with mock.patch.object(publish.redump_store, "dump", boom):
            with self.assertRaises(KeyError) as caught:
                self.run_main([entry(JAN)], works)
        notes = "".join(getattr(caught.exception, "__notes__", []))
        self.assertIn(JAN, notes)

    def test_all_written_is_still_zero(self):
        works = {JAN: self.work_of(JAN, self.GOOD, self.TABLE)}
        code, said = self.run_main([entry(JAN)], works)
        self.assertEqual(code, 0, said)
        self.assertTrue(self.stored(JAN))
        self.assertIn("段落表 write", said)


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
             segments.INTERVIEWEE: "", segments.SPEECH: ""},
            {"起秒": "100", "迄秒": "600.000", "類型": "島語時間",
             "單元語別": "泰雅", "字幕上緣y": "940", "字幕下緣y": "1060",
             "依據": basis, segments.INTERVIEWEE: "", segments.SPEECH: ""}]


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
        stored = segments.read(self.target)
        expected = segment_rows("Claude Vision 確認")
        for row in expected:
            del row["依據"]
        self.assertEqual(stored, expected)

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

    def test_same_area_name_cut_differently_is_still_stale(self):
        # 2026-10-16：`20240603_155_晚間_Amis_阿美` work dir 有 10-15
        # 用 titv-news-offband 切ê「帶外專題」，store 是 10-16 用
        # titv-news-flower 重切ê（919 條）。干焦比區域名，兩爿攏有就放
        # 過，publish 共 store 蓋轉去 855 條，rebuild --verify 才抓著。
        self.timeline(paths.refined_cues(self.work),
                      {"帶外專題": {"preset": "titv-news-offband",
                                "region": [392, 910, 1528, 122]}})
        self.spliced_store()
        work, reason = self.judge()
        self.assertEqual(work, "")
        self.assertIn("帶外專題", reason)

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

    def test_a_timeline_still_being_refined_holds_back_only_itself(self):
        # 2026-09-25：cut_months 當咧精修 20230703_184 晚間，work dir
        # 干焦有粗切。publishable() 放伊過，publish_one 才 raise，規輪
        # publish 倒去——排佇伊後壁ê集攏入袂去。
        from scripts import datadirs
        path = datadirs.coarse_cues(self.work)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"cues": [], "duration": 600.0}, handle)
        work, reason = self.judge()
        self.assertEqual(work, "")
        self.assertIn("精修", reason)


if __name__ == "__main__":
    unittest.main()
