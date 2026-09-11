"""Only a refined timeline may enter the store.

Every delivered timestamp is derived from this one file, and coarse and
refined differ by an order of magnitude -- 0.2s grid against 0.05s. Once
both kinds are in the same folder nothing tells them apart, so the gate
goes at the door: `1-ocr/1-cues/` gets a property it can state outright,
**every file in here has been refined**. 使用者裁定 2026-09-03.

The old code copied `<work>/cues.json` and, finding none, **carried on
without saying so**. That branch was written for `from_rtf.json`, which
legitimately is missing for most episodes; cues only shared the loop. It
turns into a real defect the moment the write side moves the timeline
into `1-cues/`: the episode is published with no timeline at all and
nothing reports it.

「揣無時間軸」佮「時間軸猶未精修」愛各講各ê——補救無仝款：一个是
去走 `refine_cues`，一个是愛重切。
"""
import json
import os
import tempfile
import unittest
from unittest import mock

from scripts.news import paths
from scripts.news import publish
from scripts.errors import PipelineError

ENTRY = {"srt_name": "20210201_032_午間_Atayal_泰雅"}
COARSE = {"cues": [{"index": 1, "start": 1.0, "end": 2.0}]}
REFINED = dict(COARSE, refined=True)


class Fixture(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = tmp.name
        self.work = os.path.join(self.root, "work")
        self.store = os.path.join(self.root, "store", "1-cues")
        os.makedirs(self.work)

    def _timeline(self, path, body):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(body, handle, ensure_ascii=False)

    def _published(self):
        return paths.stage_path(self.store, ENTRY["srt_name"], ".json")


class TestRefinedTimelinesArePublished(Fixture):
    def test_a_refined_timeline_lands_in_the_store(self):
        self._timeline(paths.refined_cues(self.work), REFINED)
        publish.publish_one(ENTRY, self.work, cues_dir=self.store)
        self.assertTrue(os.path.exists(self._published()))

    def test_what_lands_is_the_refined_one(self):
        self._timeline(paths.coarse_cues(self.work), COARSE)
        self._timeline(paths.refined_cues(self.work), REFINED)
        publish.publish_one(ENTRY, self.work, cues_dir=self.store)
        with open(self._published(), encoding="utf-8") as handle:
            self.assertTrue(json.load(handle)["refined"])

    def test_a_pre_split_flat_timeline_is_no_longer_seen(self):
        """遷移掃過矣（news 75 个、《開會了》40 个），平版面ê路提掉。

        平ê彼份這馬讀無，所以這集算做「揣無時間軸」——大聲擋落來，
        毋是恬恬入一份無時間軸ê。
        """
        self._timeline(os.path.join(self.work, "cues.json"), REFINED)
        with self.assertRaises(PipelineError):
            publish.publish_one(ENTRY, self.work, cues_dir=self.store)
        self.assertFalse(os.path.exists(self._published()))


class TestMachineLocalFieldsAreStripped(Fixture):
    """入 Kari-SRT ê時間軸內底無本機專屬ê路徑。

    工作目錄彼份ê `video` 記ê是彼台機器ê暫存位置
    （`/…/kithann/out/stage/魯凱語-霧台20210101S1100.mp4`），換一台機器
    就無意義，煞會予 Kari-SRT ê內容縛佇一台機器頂——仝一份資料佇別
    台機器重算會得著無仝ê位元組。`tracker.corpus_path()` 本底就咧防
    inventory 彼欄，時間軸這欄無人顧著。影片位置由節目目錄ê
    `原始影片檔案位置` 記，彼是相對語料根ê路徑。
    """

    def test_the_video_path_does_not_reach_the_store(self):
        self._timeline(paths.refined_cues(self.work),
                       dict(REFINED, video="/tmp/out/stage/魯凱語-霧台.mp4"))
        publish.publish_one(ENTRY, self.work, cues_dir=self.store)
        with open(self._published(), encoding="utf-8") as handle:
            self.assertNotIn("video", json.load(handle))

    def test_everything_else_survives(self):
        self._timeline(paths.refined_cues(self.work),
                       dict(REFINED, video="/tmp/x.mp4", duration=800.099))
        publish.publish_one(ENTRY, self.work, cues_dir=self.store)
        with open(self._published(), encoding="utf-8") as handle:
            got = json.load(handle)
        self.assertEqual(got["duration"], 800.099)
        self.assertEqual(got["cues"], REFINED["cues"])
        self.assertTrue(got["refined"])

    def test_a_timeline_without_the_field_is_unaffected(self):
        self._timeline(paths.refined_cues(self.work), REFINED)
        publish.publish_one(ENTRY, self.work, cues_dir=self.store)
        with open(self._published(), encoding="utf-8") as handle:
            self.assertEqual(json.load(handle), REFINED)


class TestCoarseTimelinesAreRefused(Fixture):
    def test_a_coarse_only_work_dir_is_named_and_stops_the_run(self):
        self._timeline(paths.coarse_cues(self.work), COARSE)
        with self.assertRaises(PipelineError) as caught:
            publish.publish_one(ENTRY, self.work, cues_dir=self.store)
        self.assertIn(ENTRY["srt_name"], str(caught.exception))

    def test_it_says_which_of_the_two_problems_it_is(self):
        self._timeline(paths.coarse_cues(self.work), COARSE)
        with self.assertRaises(PipelineError) as caught:
            publish.publish_one(ENTRY, self.work, cues_dir=self.store)
        self.assertIn("精修", str(caught.exception))

    def test_nothing_is_written_when_it_refuses(self):
        self._timeline(paths.coarse_cues(self.work), COARSE)
        with self.assertRaises(PipelineError):
            publish.publish_one(ENTRY, self.work, cues_dir=self.store)
        self.assertFalse(os.path.exists(self._published()))


class TestAMissingTimelineIsADifferentMessage(Fixture):
    def test_no_timeline_at_all_is_named_too(self):
        with self.assertRaises(PipelineError) as caught:
            publish.publish_one(ENTRY, self.work, cues_dir=self.store)
        self.assertIn(ENTRY["srt_name"], str(caught.exception))

    def test_it_does_not_call_a_missing_timeline_unrefined(self):
        """兩款狀況ê補救無仝，所以話嘛袂使講做仝一句。"""
        with self.assertRaises(PipelineError) as caught:
            publish.publish_one(ENTRY, self.work, cues_dir=self.store)
        self.assertNotIn("精修", str(caught.exception))

    def test_it_never_falls_through_silently(self):
        try:
            publish.publish_one(ENTRY, self.work, cues_dir=self.store)
        except PipelineError:
            pass
        else:
            self.fail("無時間軸soah恬恬過關——這就是本底彼个空喙")


class TestPublishableSeesTheNewLayout(Fixture):
    """`publishable()` 嘛愛對 helper 問，無就會報「尚未切cue」。

    伊本底是家己拼 `<work>/cues.json`。新版面ê work dir 佇伊眼中就是
    「猶未切」——批次會hőng擋落來，理由閣是毋著ê彼一項。
    """

    SLUG = "2021_032_2021-02-01_午間_Atayal_泰雅"

    def _entry(self):
        return dict(ENTRY, slug=self.SLUG, truncated="")

    def _work_dir(self):
        return os.path.join(self.root, self.SLUG + ".work")

    def _ready(self, body):
        work = self._work_dir()
        self._timeline(paths.refined_cues(work), body)
        # vision_complete 讀ê物件，予伊講「讀煞矣」
        with open(os.path.join(work, "transcripts.json"), "w",
                  encoding="utf-8") as handle:
            json.dump({"1": {"han": "有"}}, handle)
        return work

    def test_a_new_layout_work_dir_is_not_called_uncut(self):
        self._ready(REFINED)
        with mock.patch.object(publish, "WORK", self.root):
            _work, reason = publish.publishable(self._entry())
        self.assertNotIn("切cue", reason)

    def test_a_work_dir_with_no_timeline_is_still_called_uncut(self):
        os.makedirs(self._work_dir(), exist_ok=True)
        with mock.patch.object(publish, "WORK", self.root):
            _work, reason = publish.publishable(self._entry())
        self.assertIn("切cue", reason)


if __name__ == "__main__":
    unittest.main()
