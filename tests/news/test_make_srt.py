"""make_srt: the slate guard, source priority, and rebuild's missing-input
failure (the srt-data-store spec's "缺件時明確失敗" scenario)."""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from scripts.news import make_srt
from scripts.news import paths
from scripts.news import rebuild


def record(index, start, end, text=""):
    return {"index": index, "start": start, "end": end, "text": text}


class TestDropLeader(unittest.TestCase):
    def test_cue_opening_on_frame_zero_is_blanked(self):
        # broadcast masters open on bars and a slate whose white text sits in
        # the subtitle band; a cue starting at 0.0 cannot be dialogue
        records = [record(1, 0.0, 14.0, text="x2同。"),
                   record(2, 15.0, 18.0, text="真正的第一句")]
        got = make_srt.drop_leader(records)
        self.assertEqual(got[0]["text"], "")
        self.assertEqual(got[1]["text"], "真正的第一句")

    def test_nothing_after_half_a_second_is_touched(self):
        records = [record(1, 5.8, 8.0, text="最早的真實字幕")]
        got = make_srt.drop_leader(records)
        self.assertEqual(got[0]["text"], "最早的真實字幕")


class TestEntriesFrom(unittest.TestCase):
    def test_a_cue_with_no_text_is_left_out(self):
        # Not every cue carries a subtitle: the segmenter opens one wherever
        # the band holds ink, and a reader marks the blanks as blank.
        records = [record(1, 0.0, 1.0, text="有字"),
                   record(2, 1.0, 2.0),
                   record(3, 2.0, 3.0, text="   ")]
        self.assertEqual(make_srt.entries_from(records),
                         [(0.0, 1.0, "有字")])


class TestNoQcSummaryFile(unittest.TestCase):
    """組裝了後 SRT 邊仔無仝名ê .qc.json。

    彼份摘要（cue 數、有字 cue 數、SRT 行數）無半个生產程式咧讀——
    `make_all` 佮 `rebuild` 用ê是 `run()` ê**回傳值**，毋是彼个檔；
    `rebuild --verify` 嘛無比對伊。逐一个數字對時間軸佮交付 SRT 當場
    算會出來，愛予人看ê逐集數字應該囥一張逐集 CSV，毋是散做一集
    一个細檔。
    """

    def test_main_writes_the_srt_but_no_qc_json(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        work = os.path.join(tmp, "20210201_032.work")
        timeline = paths.coarse_cues(work)
        os.makedirs(os.path.dirname(timeline))
        with open(timeline, "w", encoding="utf-8") as handle:
            json.dump({"duration": 10.0, "refined": True,
                       "cues": [{"index": 1, "start": 1.0, "end": 2.0}]},
                      handle, ensure_ascii=False, indent=2, sort_keys=True)
        with open(os.path.join(work, "transcripts.json"), "w",
                  encoding="utf-8") as handle:
            json.dump({"1": {"han": "有字"}}, handle, ensure_ascii=False,
                      indent=2, sort_keys=True)

        out = os.path.join(tmp, "20210201_032.srt")
        make_srt.main([work, "-o", out])

        self.assertTrue(os.path.exists(out))
        self.assertFalse(os.path.exists(os.path.splitext(out)[0] + ".qc.json"))


class TestRebuildMissingInputs(unittest.TestCase):
    """Missing pieces are named and fail the run -- no partial delivery."""

    ENTRY = {"srt_name": "20210201_032_午間_Atayal_泰雅",
             "pending": False}

    def test_missing_cues_json_is_named(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty = os.path.join(tmp, "empty")
            os.makedirs(empty)
            with mock.patch.object(paths, "KARI_CUES", empty), \
                    mock.patch.object(paths, "KARI_VISION", empty), \
                    mock.patch.object(paths, "SRT_DIR", empty):
                problems = rebuild.check_inputs([dict(self.ENTRY)])
        text = "\n".join(problems)
        self.assertIn("cues/20210201_032_午間_Atayal_泰雅.json", text)
        self.assertIn("no vision TSVs", text)

    def test_a_pending_episode_needs_no_inputs(self):
        """猶未做ê集數毋是缺件。

        表有 969 逝、階段目錄才 75 集——分階段入庫ê正常狀態。
        """
        entry = {"srt_name": "whatever", "pending": True}
        self.assertEqual(rebuild.check_inputs([entry]), [])


if __name__ == "__main__":
    unittest.main()
