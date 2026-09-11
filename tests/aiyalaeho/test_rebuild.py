"""rebuild: put every delivered SRT back together from the store alone.

This is the store's core promise in executable form -- code plus
`1-cues/` plus `2-vision/` reproduce `3-srt/` and `smkul.csv` byte for
byte, with no video and no model. If it holds, everything in the
workspace really is a cache.
"""
import csv
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from scripts import catalogue_checks as checks
from scripts import datadirs
from scripts.aiyalaeho import episodes
from scripts.aiyalaeho import paths
from scripts.aiyalaeho import rebuild
from scripts.aiyalaeho.langcheck import report
from scripts.errors import PipelineError


class Store(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="aiya-rebuild-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.cues = os.path.join(self.tmp, "1-cues")
        self.vision = os.path.join(self.tmp, "2-vision")
        self.srt = os.path.join(self.tmp, "3-srt")
        for folder in (self.cues, self.vision, self.srt):
            os.makedirs(folder)
        self.table = os.path.join(self.tmp, "smkul.csv")
        self.abnormal = os.path.join(self.tmp, "smkul-字幕版型異常.csv")
        self.lexicons = os.path.join(self.tmp, "詞庫")
        os.makedirs(self.lexicons)
        self.marks = os.path.join(self.tmp, "逐條語言標記.csv")
        self.dist = os.path.join(self.tmp, "逐集語言分布.csv")
        self._patch(paths, "KARI_CUES", self.cues)
        self._patch(paths, "KARI_VISION", self.vision)
        self._patch(paths, "SRT_DIR", self.srt)
        self._patch(paths, "TRACKER_STORE", self.table)
        self._patch(paths, "ABNORMAL_STORE", self.abnormal)
        self._patch(paths, "LEXICON_DIR", self.lexicons)
        self._patch(paths, "LANGCHECK_MARKS", self.marks)
        self._patch(paths, "LANGCHECK_DIST", self.dist)
        self.entries = []
        # 兩份詞庫刻意無相濫，測試才分會出「本集族語」佮「別族」。
        self.lexicon("阿美", ["kako", "matini", "sowal", "mafana", "tangasa"])
        self.lexicon("泰雅", ["nanak", "kmayal", "squliq", "tayal", "pyux"])

    def lexicon(self, tribe, words):
        with open(os.path.join(self.lexicons, tribe + ".txt"), "w",
                  encoding="utf-8") as handle:
            for word in sorted(words):
                handle.write(word + "\n")

    def _patch(self, module, name, value):
        old = getattr(module, name)
        setattr(module, name, value)
        self.addCleanup(setattr, module, name, old)

    def abnormal_episode(self, number, reason="無字幕", seconds=2969.967,
                         pending=False):
        """登記矣、有理由、`1-ocr/` 底下一隻檔都無ê集。"""
        name = "開會了_%03d_Atayal_泰雅" % number
        self.entries.append({
            "成果檔名": name,
            "節目名稱": "開會了",
            "集數": str(number),
            "族語別(英)": "Atayal",
            "族語別(中)": "泰雅",
            "語言別": "",
            "語言別代號": "tay",
            "原始影片檔案位置":
                "ilrdf-corpus/族語節目/開會了/%d-泰雅語-無字幕.mp4" % number,
            "備註": reason,
        })
        self._write_tables()
        self.deliver()
        return name

    def episode(self, number, cues=2, rows=True, pending=False,
                deliver=True):
        name = "開會了_%03d_Amis_阿美" % number
        self.entries.append({
            "成果檔名": name,
            "節目名稱": "開會了",
            "集數": str(number),
            "族語別(英)": "Amis",
            "族語別(中)": "阿美",
            "語言別": "",
            "語言別代號": "ami",
            "原始影片檔案位置":
                "ilrdf-corpus/族語節目/開會了/%03d-x.mp4" % number,
            "備註": "",
        })

        manifest = {"duration": 3000.0,
                    "lines": [{"name": "formosan", "y": 12, "h": 60},
                              {"name": "han", "y": 72, "h": 64}],
                    "cues": []}
        for index in range(1, cues + 1):
            manifest["cues"].append({"index": index, "start": 10.0 * index,
                                     "end": 10.0 * index + 4.0})
        with open(os.path.join(self.cues, name + ".json"), "w",
                  encoding="utf-8") as handle:
            json.dump(manifest, handle, ensure_ascii=False)

        if rows and cues:
            folder = os.path.join(self.vision, name)
            os.makedirs(folder, exist_ok=True)
            lines = []
            for index in range(1, cues + 1):
                lines.append("%d\tformosan\ta%d" % (index, index))
                lines.append("%d\than\t甲%d" % (index, index))
            with open(os.path.join(folder, "b01.tsv"), "w",
                      encoding="utf-8") as handle:
                handle.write("\n".join(lines) + "\n")

        self._write_tables()
        if deliver:
            self.deliver()
        return name

    def _write_tables(self):
        head = list(checks.head(checks.EPISODE_KEYS)) + [
            "原始影片檔案位置", "備註"]
        normal, abnormal = [], []
        for row in sorted(self.entries, key=lambda one: one["成果檔名"]):
            (abnormal if row["備註"] else normal).append(row)
        for path, rows in ((self.table, normal),
                           (self.abnormal, abnormal)):
            with open(path, "w", encoding="utf-8-sig",
                      newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=head)
                writer.writeheader()
                for row in rows:
                    writer.writerow(row)

    def deliver(self):
        """Produce the deliverables the way the pipeline would have.

        `pending` 是問「`3-srt/` 有無彼支」——交付品猶未產出ê時逐集
        攏是 pending，所以遮愛明講「這幾集當做已交付」，若無會啥物
        攏無組。
        """
        entries = episodes.load()
        for entry in entries:
            entry["pending"] = False
        built = rebuild.rebuild_all(entries)
        for name in built["srt"]:
            with open(os.path.join(self.srt, name + ".srt"), "w",
                      encoding="utf-8") as handle:
                handle.write(built["srt"][name])
        report.write_table(paths.LANGCHECK_MARKS, report.MARK_HEADER,
                           built["lang_marks"])
        report.write_table(paths.LANGCHECK_DIST, report.DIST_HEADER,
                           built["lang_dist"])


class TestRebuild(Store):
    def test_a_delivered_batch_rebuilds_byte_for_byte(self):
        self.episode(68)
        self.episode(82, cues=3)
        self.assertEqual(rebuild.verify(), [])

    def test_the_two_rows_come_back_labelled(self):
        name = self.episode(68)
        with open(os.path.join(self.srt, name + ".srt"),
                  encoding="utf-8") as handle:
            body = handle.read()
        self.assertIn("族語：a1", body)
        self.assertIn("華語：甲1", body)

    def test_an_abnormal_episode_needs_no_inputs_at_all(self):
        # 無切、無讀、無組裝——`1-ocr/` 底下一隻檔都無，猶原愛過。
        self.episode(68)
        self.abnormal_episode(88)
        self.assertEqual(rebuild.verify(), [])

    def test_a_changed_deliverable_is_reported(self):
        name = self.episode(68)
        with open(os.path.join(self.srt, name + ".srt"), "a",
                  encoding="utf-8") as handle:
            handle.write("\n999\n00:00:01,000 --> 00:00:02,000\n族語：x\n")
        self.assertEqual(rebuild.verify(), [name + ".srt"])

    def test_a_hand_broken_row_is_named_by_line_and_column(self):
        """表這馬是輸入——逐 byte 比對無意義矣，換做不變量。

        逐 byte 干焦會講「smkul.csv 對袂起來」，不變量會講是佗一逝、
        佗一欄、按怎毋著。
        """
        self.episode(68)
        self.entries[0]["語言別代號"] = "amis"
        self._write_tables()
        problems = rebuild.verify()
        self.assertTrue(any("amis" in p for p in problems), problems)


class TestMissing(Store):
    def test_a_missing_timeline_is_named(self):
        name = self.episode(68)
        os.remove(os.path.join(self.cues, name + ".json"))
        with self.assertRaises(PipelineError):
            rebuild.verify()

    def test_missing_transcripts_are_named(self):
        name = self.episode(68)
        shutil.rmtree(os.path.join(self.vision, name))
        problems = rebuild.check_inputs(episodes.load())
        self.assertEqual(len(problems), 1)
        self.assertIn(name, problems[0])

    def test_a_pending_episode_is_skipped_not_demanded(self):
        # 登記矣、猶未做煞ê集數：無交付品嘛袂使予驗證失敗。
        self.episode(68)
        self.entries.append({
            "成果檔名": "開會了_085_Amis_阿美",
            "節目名稱": "開會了", "集數": "85",
            "族語別(英)": "Amis", "族語別(中)": "阿美",
            "語言別": "", "語言別代號": "ami",
            "原始影片檔案位置": "ilrdf-corpus/族語節目/開會了/085-x.mp4",
            "備註": ""})
        self._write_tables()
        self.assertEqual(rebuild.check_inputs(episodes.load()), [])
        self.assertEqual(rebuild.verify(), [])


class TestAbnormalTable(Store):
    """字幕版型異常表這馬是**輸入**，驗ê是不變量毋是逐 byte。

    兩張表欄位完全相仝，分別干焦佇「這一逝佇佗一个檔」——所以「異常
    表逐逝ê `備註` 愛非空」是彼張表唯一ê自我宣告。有人kā一逝徙毋著
    檔ê話，對欄位看袂出來。
    """

    def test_an_abnormal_episode_needs_no_inputs(self):
        self.abnormal_episode(88)
        self.assertEqual(rebuild.verify(), [])

    def test_a_blank_note_is_named(self):
        self.abnormal_episode(88)
        # 空備註ê彼逝會予 `_write_tables` 排去正常表，所以家己寫
        head = list(checks.head(checks.EPISODE_KEYS)) + [
            "原始影片檔案位置", "備註"]
        row = dict(self.entries[0], 備註="")
        with open(self.abnormal, "w", encoding="utf-8-sig",
                  newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=head)
            writer.writeheader()
            writer.writerow(row)
        problems = rebuild.verify()
        self.assertTrue(any("開會了_088_Atayal_泰雅" in p for p in problems))

    def test_a_broken_language_code_is_named(self):
        self.abnormal_episode(88)
        self.entries[0]["語言別代號"] = "atayal"
        self._write_tables()
        self.assertTrue(any("atayal" in p for p in rebuild.verify()))

    def test_no_abnormal_episodes_is_fine(self):
        self.episode(68)
        self.assertEqual(rebuild.verify(), [])


class TestLanguageTables(Store):
    """兩張語言檢查 CSV 嘛愛入重建驗證。"""

    def test_they_rebuild_byte_for_byte(self):
        self.episode(68)
        self.assertEqual(rebuild.verify(), [])

    def test_a_changed_mark_table_is_reported(self):
        self.episode(68)
        with open(self.marks, "a", encoding="utf-8") as handle:
            handle.write("開會了_068_Amis_阿美,阿美,9,x,無,,,,x\n")
        self.assertIn("逐條語言標記.csv", rebuild.verify())

    def test_a_changed_distribution_table_is_reported(self):
        self.episode(68)
        with open(self.dist, "a", encoding="utf-8") as handle:
            handle.write("開會了_999_Amis_阿美,阿美,1,1,0,0,0,0\n")
        self.assertIn("逐集語言分布.csv", rebuild.verify())

    def test_a_stale_table_is_reported_when_the_srt_changes(self):
        # 上游換版、下游無綴——重建若食 store 家己彼份 SRT 就驗袂出來。
        name = self.episode(68)
        folder = os.path.join(self.vision, name)
        with open(os.path.join(folder, "b01.tsv"), "w",
                  encoding="utf-8") as handle:
            # 阿美彼集出現一逝泰雅——逐條表本底無彼逝，重產了才有。
            handle.write("1\tformosan\tnanak kmayal squliq tayal pyux\n"
                         "1\than\t甲1\n"
                         "2\tformosan\ta2\n"
                         "2\than\t甲2\n")
        # 交付 SRT 綴咧重產，兩張 CSV 無重產。
        built = rebuild.rebuild_all()
        with open(os.path.join(self.srt, name + ".srt"), "w",
                  encoding="utf-8") as handle:
            handle.write(built["srt"][name])
        self.assertIn("逐條語言標記.csv", rebuild.verify())

    def test_a_missing_lexicon_is_named(self):
        self.episode(68)
        os.remove(os.path.join(self.lexicons, "阿美.txt"))
        with self.assertRaises(PipelineError) as caught:
            rebuild.verify()
        self.assertIn("阿美", str(caught.exception))


class TestStageContainment(unittest.TestCase):
    """下跤階段愛是頂懸ê子集——本語料ê store 無月份彼層。

    `3-srt` 有一份 SRT、`1-cues` 無彼集ê時間軸，彼份交付物重建袂出來。
    倒轉來（`1-cues` 39 集、`3-srt` 才 20 集）是分階段入庫ê正常狀態。
    """

    def _store(self, cues, vision, srt):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        made = {}
        for stage, names, ext in (("1-cues", cues, ".json"),
                                  ("2-vision", vision, ""),
                                  ("3-srt", srt, ".srt")):
            base = os.path.join(tmp.name, stage)
            os.makedirs(base)
            made[stage] = base
            for name in names:
                path = os.path.join(base, name + ext)
                if ext:
                    with open(path, "w", encoding="utf-8") as handle:
                        handle.write("{}")
                else:
                    os.makedirs(path)
        return made

    def _problems(self, cues, vision, srt):
        made = self._store(cues, vision, srt)
        with mock.patch.object(rebuild.paths, "KARI_CUES", made["1-cues"]), \
             mock.patch.object(rebuild.paths, "KARI_VISION",
                               made["2-vision"]), \
             mock.patch.object(rebuild.paths, "SRT_DIR", made["3-srt"]):
            return datadirs.stage_problems(rebuild.stage_names())

    def test_an_srt_with_no_timeline_is_named(self):
        problems = self._problems(["a"], ["a"], ["a", "b"])
        self.assertEqual(len(problems), 1)
        self.assertIn("b", problems[0])

    def test_upstream_running_ahead_is_fine(self):
        self.assertEqual(self._problems(["a", "b", "c"], ["a", "b"], ["a"]),
                         [])
