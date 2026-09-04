"""What `smkul.csv` carries, and why each column can be recomputed.

The table has to be rebuildable byte-for-byte from the store alone --
that is what `rebuild --verify` checks -- so every column is derived,
never typed in. These are the columns and their sources.

Three changes, 使用者裁定 2026-09-03:

  加 `成果檔名`   ＝ the episode's `srt_name`, the key that locates its
                  files in every stage folder. 欄名佮《開會了》彼份仝款。
  加 `cues`      the delivered timeline: refined or coarse, read off
                  `1-cues/`. Constant in the store's copy (publish only
                  takes refined ones) and alive in the working copy,
                  which is where "cut but not yet refined" shows up.
  刪 `文稿位置`   the 文稿 route is retired; the column pointed at
                  nothing anybody could act on.
  刪 `播出時段`   **只會使佮加 `成果檔名` 做伙做**：無時段了後
                  `(年度, 集數, 播出日期)` 就無唯一矣——74 逝干焦 33 組
                  日期，內底 31 組是一工 2–3 集。分會開in ê就是成果檔名
                  （`20210201_032_午間_…` 本身就含時段）。
"""
import json
import os
import tempfile
import unittest

from scripts.news import paths
from scripts.news import tracker

ENTRY = {
    "節目名稱": "午間族語新聞", "年度": "2021", "集數": "32",
    "播出日期": "2021-02-01", "播出時段": "午間",
    "族語別(英)": "Atayal", "族語別(中)": "泰雅",
    "video": "ilrdf-corpus/族語新聞/x.mp4", "文稿位置": "稿/x.rtf",
    "truncated": "", "slug": "s",
    "srt_name": "20210201_032_午間_Atayal_泰雅",
}
COARSE = {"duration": 2880.0, "cues": [{"index": 1, "start": 1.0,
                                        "end": 2.0}]}
REFINED = dict(COARSE, refined=True)


class Fixture(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.cues = os.path.join(tmp.name, "1-cues")
        self.asr = os.path.join(tmp.name, "2-asr")

    def _timeline(self, body):
        path = paths.stage_path(self.cues, ENTRY["srt_name"], ".json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(body, handle)

    def _row(self):
        return tracker.tracker_row(dict(ENTRY), "狀態",
                                   cues_dir=self.cues, asr_dir=self.asr)


class TestTheColumnList(unittest.TestCase):
    WANT = ["年度", "集數", "播出日期", "節目名稱", "族語別(英)",
            "族語別(中)", "影片檔案位置", "影片長度", "成果檔名", "cues",
            "字幕srt狀態", "語音辨識模型"]

    def test_the_columns_and_their_order(self):
        self.assertEqual(tracker.FIELDS, self.WANT)

    def test_the_retired_columns_are_gone(self):
        self.assertNotIn("文稿位置", tracker.FIELDS)
        self.assertNotIn("播出時段", tracker.FIELDS)

    def test_identity_then_source_then_progress(self):
        """三段讀：這集是啥 → 素材佇佗 → 做到佗。"""
        order = tracker.FIELDS
        self.assertLess(order.index("播出日期"), order.index("影片檔案位置"))
        self.assertLess(order.index("影片檔案位置"), order.index("成果檔名"))
        self.assertLess(order.index("成果檔名"), order.index("cues"))
        self.assertLess(order.index("cues"), order.index("字幕srt狀態"))


class TestDeliverableName(Fixture):
    def test_it_is_the_srt_name(self):
        self._timeline(REFINED)
        self.assertEqual(self._row()["成果檔名"], ENTRY["srt_name"])

    def test_same_day_episodes_are_told_apart_by_it(self):
        """無時段矣，分會開一工幾集ê就賰這欄。"""
        other = dict(ENTRY, 播出時段="晚間",
                     srt_name="20210201_032_晚間_Amis_阿美")
        rows = [tracker.tracker_row(dict(ENTRY), "x", cues_dir=self.cues,
                                    asr_dir=self.asr),
                tracker.tracker_row(other, "x", cues_dir=self.cues,
                                    asr_dir=self.asr)]
        self.assertNotEqual(rows[0]["成果檔名"], rows[1]["成果檔名"])


class TestCuesColumn(Fixture):
    def test_a_refined_timeline_says_so(self):
        self._timeline(REFINED)
        self.assertEqual(self._row()["cues"], tracker.CUES_REFINED)

    def test_a_coarse_timeline_says_so_too(self):
        """粗切ê愛照實講——袂使講做已經精修，嘛袂使留白。"""
        self._timeline(COARSE)
        self.assertEqual(self._row()["cues"], tracker.CUES_COARSE)

    def test_no_timeline_at_all_is_blank(self):
        self.assertEqual(self._row()["cues"], "")

    def test_it_is_read_off_the_store_not_typed_in(self):
        """任何時點重算攏著仝款——逐 byte 重建才袂予增欄拍歹。"""
        self._timeline(REFINED)
        first = self._row()["cues"]
        self.assertEqual(self._row()["cues"], first)


if __name__ == "__main__":
    unittest.main()
