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
    def test_a_month_may_span_two_source_folders(self):
        self.assertEqual(len(self._plan().added), 2)

    def test_other_months_in_the_same_folder_are_not_taken(self):
        for name in self._names(self._plan()):
            self.assertTrue(name.startswith("202102"), name)

    def test_each_entry_carries_its_own_remote_path(self):
        for entry in self._plan().added:
            self.assertTrue(entry["video"].endswith((".mxf", ".mp4")))

    def test_a_month_with_no_episodes_says_so(self):
        with self.assertRaises(PipelineError):
            self._plan(month="1999-01")


class TestSkipped(Fixture):
    def test_an_undecidable_episode_is_reported_not_planned(self):
        report = self._plan()
        self.assertEqual(len(report.skipped), 1)
        for name in self._names(report):
            self.assertNotIn("_044_", name)

    def test_the_skip_report_is_not_cut_by_the_limit(self):
        """揀袂出來ê逐擺攏報，才袂等 limit 拄好行到彼跡才現形。"""
        self.assertEqual(len(self._plan(limit=1).skipped), 1)


class TestLimit(Fixture):
    def test_one_at_a_time(self):
        self.assertEqual(len(self._plan(limit=1).added), 1)

    def test_zero_means_the_whole_month(self):
        self.assertEqual(len(self._plan(limit=0).added), 2)

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


class TestTodoFetchesOneChosenFile(unittest.TestCase):
    """`--todo` 是 `fetch_sftp.sh` 真正拿去下載的清單，要先照規則挑檔。

    `原始影片檔案位置` 是候選清單，122 列用分號接了好幾條。報表
    （`plan`）有照 `sources.resolve` 挑，`todo` 卻直接把整格原樣交出去，
    `fetch_sftp.sh` 拿「a.mp4;b.mp4」去伺服器找，當然找不到。2026-09-14
    量到還沒切的集數裡有 59 集這樣被跳過：2022-01 一整批同檔名同時在
    「1月」「2月」、2022-04 同時在「4月」「5月」，另有 090午間鄒、
    122晨間拉阿魯哇這種午間／晨間兩個檔名擺在一起的。
    """

    ROWS = [
        # 規則 3：同一個檔名在兩個資料夾，是同一支檔
        row("1", "2022-01-01", "晨間", "Thau", "邵", "ssf",
            [JAN22 + "22NL005_001晨間族語新聞.mp4",
             FEB22 + "22NL005_001晨間族語新聞.mp4"]),
        # 挑不出來：同時段、不同檔名
        row("2", "2022-01-02", "晨間", "Hla'alua", "拉阿魯哇", "sxr",
            [JAN22 + "22NL005_002晨間族語新聞.mp4",
             JAN22 + "22NL004_002晨間族語新聞.mp4"]),
        # 規則 2：檔名上的時段字對得上的那一條
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

    def test_one_file_name_in_two_folders_fetches_one_path(self):
        found = self._todo("2022-01")
        video = found["2022_001_2022-01-01_晨間_Thau_邵"]
        self.assertNotIn(";", video)
        self.assertTrue(video.endswith("111.1-111.5/1月/22NL005_001晨間族語新聞.mp4"))

    def test_the_file_named_for_the_slot_is_the_one_fetched(self):
        found = self._todo("2021-05")
        video = found["2021_122_2021-05-02_晨間_Hla'alua_拉阿魯哇"]
        self.assertNotIn(";", video)
        self.assertTrue(video.endswith("5月/21NL005_122晨間族語新聞.mp4"))

    def test_an_undecidable_episode_is_not_on_the_fetch_list(self):
        found = self._todo("2022-01")
        self.assertNotIn("2022_002_2022-01-02_晨間_Hla'alua_拉阿魯哇", found)


class TestTodoGivesServerPaths(unittest.TestCase):
    """`--todo` 交出伺服器上的絕對路徑，`fetch_sftp.sh` 毋免閣加根目錄。

    新母帶（2026-09-23，1223 集）佇 `/home/mkv-raw/`，毋是 `/docker/
    ilrdf-corpus/`；`fetch_sftp.sh` 若照舊加 `/docker/ilrdf-corpus/`，
    規批攏揣無。
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

    def test_a_mkv_raw_episode_is_fetched_from_home(self):
        found = self._todo("2023-07")
        self.assertEqual(list(found.values()), ["/" + self.RAW])

    def test_a_corpus_episode_is_fetched_from_docker(self):
        found = self._todo("2021-05")
        self.assertEqual(list(found.values()),
                         ["/docker/" + JUL + "21NL005_122晨間族語新聞.mp4"])


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


if __name__ == "__main__":
    unittest.main()
