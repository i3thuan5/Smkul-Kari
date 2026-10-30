"""plan_month：一批的工作單位是**播出月份**，毋是來源資料夾。

資料夾佮播出月份毋是一對一：全語料有 6 个播出月份散佇兩个資料夾，
而且 `110.1-110.10/7月/` 內底 140 條有 66 條是 2 月的節目。照資料夾做，
做出來的毋是彼个月。

**這支這馬是唯讀ê。** 節目目錄頭一工就涵蓋全部集數（新聞 969 逝），
所以無「登記」這个動作矣；跑進前跑了後 Kari-SRT 一个 byte 攏無變。
"""
import csv
import json
import os
import tempfile
import unittest

from scripts import catalogue_checks as checks
from scripts.news import episodes
from scripts.news import paths
from scripts.news import plan_month
from scripts.errors import PipelineError

HEAD = list(checks.head(checks.NEWS_KEYS)) + ["原始影片檔案位置", "備註"]

FEB = "ilrdf-corpus/族語新聞/110.1-110.10/2月原始mxf檔/"
JUL = "ilrdf-corpus/族語新聞/110.1-110.10/7月/"


def row(episode, date, slot, english, chinese, code, sources):
    one = {"節目名稱": "%s族語新聞" % slot, "年度": date[:4],
           "集數": episode, "播出日期": date, "族語別(英)": english,
           "族語別(中)": chinese, "語言別": "", "語言別代號": code,
           "原始影片檔案位置": ";".join(sources), "備註": ""}
    one["成果檔名"] = checks.srt_name_of(one)
    return one


ROWS = [
    # 這个月的兩集，來源散佇兩个資料夾
    row("32", "2021-02-01", "午間", "Atayal", "泰雅", "tay",
        [FEB + "20NL003_32午間族語新聞.mxf"]),
    row("41", "2021-02-10", "午間", "Cou", "鄒", "tsu",
        [JUL + "21NL003_41午間族語新聞.mp4"]),
    # 仝一个資料夾內底，毋是這个月的
    row("186", "2021-07-05", "晚間", "Amis", "阿美", "ami",
        [JUL + "21NL003_186晚間族語新聞.mp4"]),
    # 這个月，兩條候選揀袂出來
    row("44", "2021-02-13", "晚間", "Paiwan", "排灣", "pwn",
        [JUL + "21NL003_44晚間族語新聞.mp4",
         JUL + "21NL004_44晚間族語新聞.mp4"]),
]


class Fixture(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = tmp.name
        self.table = os.path.join(self.root, "smkul.csv")
        with open(self.table, "w", encoding="utf-8-sig",
                  newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=HEAD)
            writer.writeheader()
            for one in sorted(ROWS, key=lambda r: r["成果檔名"]):
                writer.writerow(one)

    def _entries(self):
        return episodes.load(self.table, srt_dir=set())

    def _plan(self, month="2021-02", limit=0):
        return plan_month.plan(month, self._entries(), limit=limit)

    def _names(self, report):
        found = []
        for entry in report.added:
            found.append(entry["srt_name"])
        return found


class TestSelection(Fixture):
    def test_a_month_plans_every_episode_whichever_folder_it_sat_in(self):
        # 2021-02 ê四集（頭三集），來源本底散佇兩个資料夾；這馬位置是由
        # 成果檔名推導ê，毋閣看資料夾，也毋閣挑檔。
        self.assertEqual(len(self._plan().added), 3)

    def test_other_months_in_the_same_folder_are_not_taken(self):
        for name in self._names(self._plan()):
            self.assertTrue(name.startswith("202102"), name)

    def test_each_entry_carries_its_canonical_place(self):
        for entry in self._plan().added:
            self.assertEqual(entry["video"],
                             paths.video_path(entry["srt_name"]))
            self.assertTrue(
                entry["video"].startswith("/home/news/mkv/2021-02/"))

    def test_a_month_with_no_episodes_says_so(self):
        with self.assertRaises(PipelineError):
            self._plan(month="1999-01")


class TestNothingIsSkippedAnymore(Fixture):
    """本底「揀袂出來」ê集數會被略過；位置改由成果檔名推導了，無這款代誌。"""

    def test_an_episode_with_several_candidates_is_planned_like_the_rest(self):
        report = self._plan()
        self.assertEqual(report.skipped, [])
        self.assertIn("20210213_044_晚間_Paiwan_排灣",
                      self._names(report))

    def test_a_blank_original_column_does_not_stop_the_plan(self):
        blank = row("45", "2021-02-14", "晚間", "Paiwan", "排灣", "pwn", [])
        with open(self.table, "a", encoding="utf-8-sig", newline="") as out:
            csv.DictWriter(out, fieldnames=HEAD).writerow(blank)
        report = self._plan()
        self.assertIn(blank["成果檔名"], self._names(report))
        self.assertEqual(report.skipped, [])

    def test_the_plan_never_asks_the_server(self):
        # 規劃是離線唯讀ê；找袂著ê時ê退路佇實際取檔ê時處理。
        for entry in self._plan().added:
            self.assertNotIn("sftp", entry["video"])


class TestLimit(Fixture):
    def test_one_at_a_time(self):
        self.assertEqual(len(self._plan(limit=1).added), 1)

    def test_zero_means_the_whole_month(self):
        self.assertEqual(len(self._plan(limit=0).added), 3)

    def test_broadcast_order_is_kept(self):
        # 列序照成果檔名排，所以 limit 提著ê是上頭前彼幾集。
        self.assertEqual(self._names(self._plan(limit=1)),
                         self._names(self._plan())[:1])


class TestItWritesNothing(Fixture):
    """唯讀：跑進前跑了後，表一个 byte 攏無變。"""

    def test_planning_does_not_touch_the_table(self):
        with open(self.table, "rb") as handle:
            before = handle.read()
        self._plan()
        with open(self.table, "rb") as handle:
            self.assertEqual(handle.read(), before)

    def test_there_is_no_write_function_left(self):
        # 有人閣加轉去ê話，唯讀這條性質就恬恬無去矣。
        self.assertFalse(hasattr(plan_month, "write"))
        self.assertFalse(hasattr(plan_month, "merge"))

    def test_rerunning_gives_the_same_answer(self):
        self.assertEqual(self._names(self._plan()),
                         self._names(self._plan()))


JAN22 = "ilrdf-corpus/族語新聞/111.1-111.5/1月/"
FEB22 = "ilrdf-corpus/族語新聞/111.1-111.5/2月/"
MAY21 = "ilrdf-corpus/族語新聞/110.1-110.10/5月/"


class TestTodoListsTheCanonicalPlace(unittest.TestCase):
    """`--todo` 是 `fetch_sftp.sh` 真正拿去下載的清單。

    本底愛先照 `sources.resolve` 挑檔（`原始影片檔案位置` 是候選清單，
    122 列用分號接幾若條，2026-09-14 有 59 集因為拿整格原樣去伺服器找
    著跳過）。位置改由成果檔名推導了，`todo` 交出ê就是正規位置，毋管
    原始欄寫啥——揣無ê時ê退路佇 `fetch_sftp.sh` 取檔ê時處理。
    """

    ROWS = [
        # 同一个檔名佇兩个資料夾
        row("1", "2022-01-01", "晨間", "Thau", "邵", "ssf",
            [JAN22 + "22NL005_001晨間族語新聞.mp4",
             FEB22 + "22NL005_001晨間族語新聞.mp4"]),
        # 本底挑袂出來：同時段、不同檔名
        row("2", "2022-01-02", "晨間", "Hla'alua", "拉阿魯哇", "sxr",
            [JAN22 + "22NL005_002晨間族語新聞.mp4",
             JAN22 + "22NL004_002晨間族語新聞.mp4"]),
        # 檔名上ê時段字對會著ê彼一條
        row("122", "2021-05-02", "晨間", "Hla'alua", "拉阿魯哇", "sxr",
            [MAY21 + "21NL005_122午間族語新聞.mp4",
             MAY21 + "21NL005_122晨間族語新聞.mp4"]),
    ]

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.table = os.path.join(tmp.name, "smkul.csv")
        with open(self.table, "w", encoding="utf-8-sig",
                  newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=HEAD)
            writer.writeheader()
            for one in self.ROWS:
                writer.writerow(one)

    def _todo(self, month):
        entries = episodes.load(self.table, srt_dir=set())
        found = {}
        for slug, video in plan_month.todo(month, entries,
                                           already_cut=lambda entry: False):
            found[slug] = video
        return found

    def test_the_path_is_the_canonical_one_not_a_candidate(self):
        found = self._todo("2022-01")
        video = found["2022_001_2022-01-01_晨間_Thau_邵"]
        self.assertNotIn(";", video)
        self.assertEqual(
            video, "/home/news/mkv/2022-01/20220101_001_晨間_Thau_邵.mkv")

    def test_the_slot_word_in_the_candidates_no_longer_matters(self):
        found = self._todo("2021-05")
        video = found["2021_122_2021-05-02_晨間_Hla'alua_拉阿魯哇"]
        self.assertEqual(
            video,
            "/home/news/mkv/2021-05/20210502_122_晨間_Hla'alua_拉阿魯哇.mkv")

    def test_an_episode_that_used_to_be_undecidable_is_listed_now(self):
        found = self._todo("2022-01")
        self.assertIn("2022_002_2022-01-02_晨間_Hla'alua_拉阿魯哇", found)


class TestTodoGivesServerPaths(unittest.TestCase):
    """`--todo` 交出伺服器上ê絕對路徑，`fetch_sftp.sh` 毋免閣加根目錄。

    影片攏佇 `/home/news/mkv/<年-月>/`，毋管本底佇 `/home/mkv-raw/`
    抑是 `/docker/ilrdf-corpus/`——位置由成果檔名推導，來源是佗位無關係。
    """

    RAW = "home/mkv-raw/112/7月/23NL003_183_族語午間新聞_Kanakanavu.mkv"
    ROWS = [
        row("183", "2023-07-02", "午間", "Kanakanavu", "卡那卡那富", "xnb",
            [RAW]),
        row("122", "2021-05-02", "晨間", "Hla'alua", "拉阿魯哇", "sxr",
            [JUL + "21NL005_122晨間族語新聞.mp4"]),
    ]

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.table = os.path.join(tmp.name, "smkul.csv")
        with open(self.table, "w", encoding="utf-8-sig",
                  newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=HEAD)
            writer.writeheader()
            for one in self.ROWS:
                writer.writerow(one)

    def _todo(self, month):
        entries = episodes.load(self.table, srt_dir=set())
        return dict(plan_month.todo(month, entries,
                                    already_cut=lambda entry: False))

    def test_a_mkv_raw_episode_is_fetched_from_the_canonical_place(self):
        found = self._todo("2023-07")
        self.assertEqual(
            list(found.values()),
            ["/home/news/mkv/2023-07/20230702_183_午間_Kanakanavu_"
             "卡那卡那富.mkv"])

    def test_a_corpus_episode_is_fetched_from_the_canonical_place_too(self):
        found = self._todo("2021-05")
        self.assertEqual(
            list(found.values()),
            ["/home/news/mkv/2021-05/20210502_122_晨間_Hla'alua_"
             "拉阿魯哇.mkv"])

    def test_the_todo_is_offline(self):
        # 退路（正規位置揣無）佇實際取檔ê時處理；列清單毋連伺服器。
        for entry in episodes.load(self.table, srt_dir=set()):
            self.assertEqual(entry["remote"],
                             paths.video_path(entry["srt_name"]))


class TestOpeningTodo(TestTodoGivesServerPaths):
    """`--opening`：已經切過ê集數，補做片頭辨識愛抓佗一支。

    2021 年 660 集攏入庫矣，`--todo` 一集都袂列（切過就毋免影片）；片頭
    辨識是另外一个問題：切過、猶未有片頭辨識ê集數。
    """

    def _opening(self, month, done=(), cut=True):
        entries = episodes.load(self.table, srt_dir=set())
        return dict(plan_month.opening_todo(
            month, entries, done=set(done),
            already_cut=lambda entry: cut))

    def test_a_cut_episode_without_an_opening_is_listed(self):
        found = self._opening("2021-05")
        self.assertEqual(
            list(found.values()),
            ["/home/news/mkv/2021-05/20210502_122_晨間_Hla'alua_"
             "拉阿魯哇.mkv"])

    def test_an_episode_already_read_is_not(self):
        name = "20210502_122_晨間_Hla'alua_拉阿魯哇"
        self.assertEqual(self._opening("2021-05", done=[name]), {})

    def test_there_is_no_light_copy_swap_anymore(self):
        # 本底 2021-02 揀著 mxf 母帶ê時愛換抓 mp4 轉檔（mxf 頭 60 MB 干焦
        # 幾秒，三格攏是廣告卡）。這馬每集攏是單一 mkv，彼段無閣有路用。
        self.assertFalse(hasattr(plan_month, "_light_copy"))

    def test_an_uncut_episode_is_left_to_the_normal_fetch(self):
        # 猶未切ê集數切 cue ê時就會截片頭，毋免另外抓。
        self.assertEqual(self._opening("2021-05", cut=False), {})


class TestAlreadyCut(unittest.TestCase):
    """「這集敢做好矣」——work dir 抑是 Kari-SRT 有精修過ê時間軸。"""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = tmp.name

    def _entry(self):
        return {"slug": "2021_032_2021-02-01_午間_Atayal_泰雅",
                "srt_name": "20210201_032_午間_Atayal_泰雅"}

    def _write(self, path, body):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(body, handle)

    def _work(self, entry, refined):
        work = paths.work_dir(entry["slug"], self.root)
        self._write(paths.coarse_cues(work), {"cues": []})
        if refined:
            self._write(paths.refined_cues(work),
                        {"cues": [], "refined": True})

    def _store(self, entry, refined):
        self._write(paths.stage_path(self.root, entry["srt_name"], ".json"),
                    {"cues": [], "refined": refined})

    def _cut(self, entry):
        return plan_month.already_cut(entry, work=self.root, store=self.root)

    def test_nothing_on_disk_is_not_finished(self):
        self.assertFalse(self._cut(self._entry()))

    def test_cut_but_not_refined_is_not_finished(self):
        entry = self._entry()
        self._work(entry, refined=False)
        self.assertFalse(self._cut(entry))

    def test_cut_and_refined_is_finished(self):
        entry = self._entry()
        self._work(entry, refined=True)
        self.assertTrue(self._cut(entry))

    def test_the_store_counts_on_its_own(self):
        """工作目錄早就清掉ê集數，猶原算做好矣。

        毋按呢ê話，逐集已交付ê攏會去予人**重切**——cue 全部重編號，
        而已經出去ê SRT ê時間是照舊編號來ê，無人會報錯。
        """
        entry = self._entry()
        self._store(entry, refined=True)
        self.assertTrue(self._cut(entry))

    def test_an_unrefined_store_timeline_is_not_finished_either(self):
        entry = self._entry()
        self._store(entry, refined=False)
        self.assertFalse(self._cut(entry))

    def test_a_flag_inside_the_coarse_file_does_not_mean_refined(self):
        """粗切彼份內底ê `refined` 旗標毋算數。

        彼條路是舊版面（平ê `<work>/cues.json`）用ê。遷移掃了後
        `cues_to_read` ê fallback 永遠讀著 `1-cues/cues.json`，彼是粗切
        彼份；伊內底若帶著旗標，舊寫法會kā 0.2 秒格點ê時間軸當做精修
        過，彼集就無閣重切矣。
        """
        entry = self._entry()
        work = paths.work_dir(entry["slug"], self.root)
        self._write(paths.coarse_cues(work), {"cues": [], "refined": True})
        self.assertFalse(self._cut(entry))


class TestPresetForMonth(unittest.TestCase):
    """逐月該用佗一个字幕帶 preset：照 preset 家己宣告ê `months`。

    2021 年紅條上緣 846／848，愛用下緣 844；紅條落到 851／852 了後用
    848。揀錯 fetch_sftp 前ê帶位把關會擋，毋過一个月切一半才擋就了工。
    """

    PRESETS = {
        "titv-news": {"months": ["2021-01", "2021-12"]},
        "titv-news-848": {"months": ["2022-01", "2024-12"]},
        "titv-news-island": {},
        "amis-titv-news": {},
    }

    def test_2024_december_takes_848(self):
        self.assertEqual(plan_month.preset_for("2024-12", self.PRESETS),
                         "titv-news-848")

    def test_2021_takes_the_old_one(self):
        self.assertEqual(plan_month.preset_for("2021-03", self.PRESETS),
                         "titv-news")

    def test_a_month_nobody_covers_is_refused(self):
        with self.assertRaises(PipelineError) as caught:
            plan_month.preset_for("2025-01", self.PRESETS)
        self.assertIn("2025-01", str(caught.exception))

    def test_two_presets_claiming_a_month_is_refused(self):
        both = dict(self.PRESETS)
        both["other"] = {"months": ["2024-06", "2025-06"]}
        with self.assertRaises(PipelineError) as caught:
            plan_month.preset_for("2024-12", both)
        self.assertIn("titv-news-848", str(caught.exception))
        self.assertIn("other", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
