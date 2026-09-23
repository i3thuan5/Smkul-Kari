"""whisper_run: language-code lookup, verbatim SRT, the log, resume.

Pins the whisper-asr-srt spec's per-episode contract against fakes for
`sapolita.recognize` and `audio.get_audio` -- no network, no ffmpeg.
"""
import csv
import os
import tempfile
import unittest

from scripts.news import paths
from scripts.news import whisper_run
from scripts.errors import PipelineError

SRT_WITH_TRAILING_HALLUCINATION = (
    "1\n00:00:00,031 --> 00:00:04,604\n"
    "族語：Santintai ita, cʉʼʉ cʉʼʉcʉʼʉ\n華語：我們是聖靈。\n\n"
    "2\n00:00:04,773 --> 00:00:24,331\n"
    "族語：kanuniza hudun lhmazʼazuan\n華語：但是山上住著許多動物。\n\n"
    "3\n00:00:24,972 --> 00:00:33,646\n"
    "族語：ʼa ʼa ʼa ʼa ʼa ʼa\n華語：\n")  # 片尾幻覺，檔尾故意不留換行


def _entry(**over):
    one = {
        "srt_name": "20210227_058_晨間_Thau_邵",
        "節目名稱": "晨間族語新聞", "播出日期": "2021-02-27",
        "族語別(英)": "Thau", "族語別(中)": "邵", "語言別代號": "ssf",
        "file": "邵語-20210227s0800.mp4",
        "原始影片檔案位置":
            "ilrdf-corpus/族語新聞/110.1-110.10/2月/邵語-20210227s0800.mp4",
    }
    one.update(over)
    return one


class Env(unittest.TestCase):
    """一套暫存目錄：新聞語言別代號.csv、辨識紀錄.csv、SRT 輸出、
    OCR 逐字稿——每項都獨立於真正的 Kari-SRT。
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = self.tmp.name
        self.srt_dir = os.path.join(root, "1-srt-sapolita")
        self.log_path = os.path.join(root, "1-srt-sapolita", "辨識紀錄.csv")
        self.vision_dir = os.path.join(root, "2-vision")
        self.variety_path = os.path.join(root, "新聞語言別代號.csv")
        self.work_dir = os.path.join(root, "work")
        os.makedirs(self.srt_dir)
        os.makedirs(self.vision_dir)
        os.makedirs(self.work_dir)
        self._write_varieties([
            ("邵", "ssf", "", "單一語別"),
            ("賽德克", "trv-x-tgdy", "德固達雅", "使用者保底"),
            ("太魯閣", "trv-x-truku", "", "單一語別"),
        ])

    def _write_varieties(self, rows):
        with open(
                self.variety_path, "w", encoding="utf-8",
                newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(["族語別(中)", "語言別代號", "語言別", "依據"])
            for row in rows:
                writer.writerow(row)

    def _write_vision(self, srt_name, lines):
        folder = paths.stage_path(self.vision_dir, srt_name)
        os.makedirs(folder, exist_ok=True)
        with open(
                os.path.join(folder, "b01.tsv"), "w",
                encoding="utf-8") as handle:
            for index, text in enumerate(lines, start=1):
                handle.write("%d\than\t%s\n" % (index, text))


class TestCodeFor(Env):
    def test_multi_variety_family_is_replaced_by_the_table_code(self):
        # smkul.csv 只記族語別，語言別代號留 `ami`／`trv` 這款光禿禿的
        entry = dict(_entry(), **{"族語別(中)": "賽德克", "語言別代號": "trv"})
        code = whisper_run.code_for(entry, variety_path=self.variety_path)
        self.assertEqual(code, "trv-x-tgdy")

    def test_seediq_and_truku_look_up_by_family_not_code_prefix(self):
        seediq = dict(_entry(), **{"族語別(中)": "賽德克",
                                   "語言別代號": "trv"})
        truku = dict(_entry(), **{"族語別(中)": "太魯閣",
                                  "語言別代號": "trv-x-truku"})
        self.assertEqual(
            whisper_run.code_for(seediq, variety_path=self.variety_path),
            "trv-x-tgdy")
        self.assertEqual(
            whisper_run.code_for(truku, variety_path=self.variety_path),
            "trv-x-truku")

    def test_missing_family_in_the_table_aborts_naming_the_episode(self):
        entry = dict(_entry(), **{"族語別(中)": "卑南"})
        with self.assertRaises(PipelineError) as caught:
            whisper_run.code_for(entry, variety_path=self.variety_path)
        self.assertIn("20210227_058", str(caught.exception))
        self.assertIn("卑南", str(caught.exception))

    def test_a_code_the_repo_table_does_not_know_aborts(self):
        self._write_varieties([("邵", "not-a-real-code", "", "手誤")])
        with self.assertRaises(PipelineError):
            whisper_run.code_for(_entry(), variety_path=self.variety_path)


class TestWriteSrt(Env):
    def test_the_stored_file_is_byte_identical_to_the_reply(self):
        path = whisper_run.write_srt(
            "20210227_058_晨間_Thau_邵", SRT_WITH_TRAILING_HALLUCINATION,
            srt_dir=self.srt_dir)
        with open(path, "rb") as handle:
            stored = handle.read()
        self.assertEqual(stored, SRT_WITH_TRAILING_HALLUCINATION
                         .encode("utf-8"))

    def test_no_trailing_newline_is_added(self):
        path = whisper_run.write_srt(
            "20210227_058_晨間_Thau_邵", SRT_WITH_TRAILING_HALLUCINATION,
            srt_dir=self.srt_dir)
        with open(path, "rb") as handle:
            stored = handle.read()
        self.assertFalse(stored.endswith(b"\n\n"))
        self.assertFalse(stored.endswith(b"\n\n\n"))

    def test_lands_in_its_broadcast_month(self):
        path = whisper_run.write_srt(
            "20210227_058_晨間_Thau_邵", "x", srt_dir=self.srt_dir)
        self.assertEqual(
            path, os.path.join(self.srt_dir, "2021-02",
                               "20210227_058_晨間_Thau_邵.srt"))


class TestAnchorName(Env):
    def test_takes_the_text_after_我是_in_the_first_fifteen_lines(self):
        name = "20210101_001_午間_Rukai_魯凱"
        self._write_vision(name, ["大家午安", "我是Sulryape Gadhu",
                                  "歡迎收看1100"])
        got = whisper_run.anchor_name(name, vision_dir=self.vision_dir)
        self.assertEqual(got, "Sulryape Gadhu")

    def test_no_vision_folder_is_unknown_not_an_error(self):
        got = whisper_run.anchor_name("20210112_012_晚間_Yami_雅美",
                                      vision_dir=self.vision_dir)
        self.assertEqual(got, "不明")

    def test_no_我是_in_the_opening_lines_is_unknown(self):
        name = "20210112_012_晚間_Yami_雅美"
        self._write_vision(name, ["各位族人 大家好", "歡迎收看晚間新聞"])
        got = whisper_run.anchor_name(name, vision_dir=self.vision_dir)
        self.assertEqual(got, "不明")


class TestLog(Env):
    def test_a_new_episode_is_appended(self):
        whisper_run.record_row(
            "20210227_058_晨間_Thau_邵", "ssf", "Kurali", "https://x",
            "2026-09-18 16:00", 2910.06, 193, log_path=self.log_path)
        with open(self.log_path, encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["成果檔名"], "20210227_058_晨間_Thau_邵")
        self.assertEqual(rows[0]["語言別代號"], "ssf")
        self.assertEqual(rows[0]["主播名"], "Kurali")

    def test_the_log_has_no_bom_and_no_crlf(self):
        whisper_run.record_row(
            "20210227_058_晨間_Thau_邵", "ssf", "不明", "https://x",
            "2026-09-18 16:00", 1.0, 1, log_path=self.log_path)
        with open(self.log_path, "rb") as handle:
            body = handle.read()
        self.assertFalse(body.startswith(b"\xef\xbb\xbf"))
        self.assertNotIn(b"\r", body)

    def test_redoing_an_episode_overwrites_its_row_not_adds_one(self):
        whisper_run.record_row(
            "20210227_058_晨間_Thau_邵", "ssf", "不明", "https://x",
            "2026-09-18 16:00", 100.0, 10, log_path=self.log_path)
        whisper_run.record_row(
            "20210227_058_晨間_Thau_邵", "ssf", "Kurali", "https://y",
            "2026-09-18 17:00", 2910.06, 193, log_path=self.log_path)
        with open(self.log_path, encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["主播名"], "Kurali")
        self.assertEqual(rows[0]["段數"], "193")

    def test_rows_are_sorted_by_srt_name(self):
        whisper_run.record_row("20210227_058_晨間_Thau_邵", "ssf", "不明",
                               "s", "d", 1.0, 1, log_path=self.log_path)
        whisper_run.record_row("20210101_001_午間_Rukai_魯凱", "dru-x-ngdr",
                               "不明", "s", "d", 1.0, 1,
                               log_path=self.log_path)
        with open(self.log_path, encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual([r["成果檔名"] for r in rows],
                         ["20210101_001_午間_Rukai_魯凱",
                          "20210227_058_晨間_Thau_邵"])


class TestResume(Env):
    def test_only_the_srt_is_not_done(self):
        whisper_run.write_srt(_entry()["srt_name"], "x",
                              srt_dir=self.srt_dir)
        self.assertFalse(whisper_run.is_done(
            _entry()["srt_name"], srt_dir=self.srt_dir,
            log_path=self.log_path))

    def test_srt_and_log_row_together_are_done(self):
        name = _entry()["srt_name"]
        whisper_run.write_srt(name, "x", srt_dir=self.srt_dir)
        whisper_run.record_row(name, "ssf", "不明", "s", "d", 1.0, 1,
                               log_path=self.log_path)
        self.assertTrue(whisper_run.is_done(
            name, srt_dir=self.srt_dir, log_path=self.log_path))

    def test_todo_skips_done_episodes(self):
        done = _entry(srt_name="20210101_001_午間_Rukai_魯凱")
        pending = _entry(srt_name="20210227_058_晨間_Thau_邵")
        whisper_run.write_srt(done["srt_name"], "x", srt_dir=self.srt_dir)
        whisper_run.record_row(done["srt_name"], "dru-x-ngdr", "不明",
                               "s", "d", 1.0, 1, log_path=self.log_path)
        queue = whisper_run.todo([done, pending], srt_dir=self.srt_dir,
                                 log_path=self.log_path)
        self.assertEqual([e["srt_name"] for e in queue],
                         [pending["srt_name"]])


class TestRunEpisode(Env):
    def _run(self, entry, recognize, audio_get=None, when=None):
        return whisper_run.run_episode(
            entry, "https://x/sapolita", recognize=recognize,
            audio_get=audio_get or (lambda e, out: open(out, "wb").close()),
            vision_dir=self.vision_dir, variety_path=self.variety_path,
            srt_dir=self.srt_dir, log_path=self.log_path,
            work_dir=self.work_dir, now=when)

    def test_a_successful_run_writes_srt_then_the_log_row(self):
        order = []

        def recognize(server, audio_path, code):
            order.append("recognize")
            self.assertTrue(os.path.exists(audio_path))
            self.assertEqual(code, "ssf")
            return SRT_WITH_TRAILING_HALLUCINATION

        self._write_vision(_entry()["srt_name"], ["我是Kurali"])
        self._run(_entry(), recognize, when=lambda: "2026-09-18 16:00")

        srt = os.path.join(self.srt_dir, "2021-02",
                           "20210227_058_晨間_Thau_邵.srt")
        self.assertTrue(os.path.exists(srt))
        with open(self.log_path, encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(rows[0]["主播名"], "Kurali")
        self.assertEqual(rows[0]["語言別代號"], "ssf")
        self.assertEqual(rows[0]["段數"], "3")

    def test_a_service_failure_leaves_no_srt_and_no_log_row(self):
        def recognize(server, audio_path, code):
            raise PipelineError("sapolita 無回傳文字")

        with self.assertRaises(PipelineError):
            self._run(_entry(), recognize)
        self.assertFalse(os.path.exists(
            os.path.join(
                self.srt_dir, "2021-02",
                "20210227_058_晨間_Thau_邵.srt")))
        self.assertFalse(os.path.exists(self.log_path))

    def test_the_temp_audio_file_is_removed_even_on_failure(self):
        written = {}

        def audio_get(entry, out):
            written["path"] = out
            open(out, "wb").close()

        def recognize(server, audio_path, code):
            raise PipelineError("boom")

        with self.assertRaises(PipelineError):
            self._run(_entry(), recognize, audio_get=audio_get)
        self.assertFalse(os.path.exists(written["path"]))


class TestBatch(Env):
    def test_episodes_run_one_at_a_time_in_order(self):
        seen = []

        def recognize(server, audio_path, code):
            seen.append("start")
            seen.append("end")
            return "1\n00:00:00,000 --> 00:00:01,000\n族語：a\n華語：b"

        entries = [
            _entry(srt_name="20210101_001_午間_Rukai_魯凱"),
            _entry(srt_name="20210227_058_晨間_Thau_邵")]
        entries[0]["族語別(中)"] = "邵"  # 借邵語代號，避免另開一族
        entries[1]["族語別(中)"] = "邵"
        done, failed = whisper_run.run_batch(
            entries, "https://x/sapolita", recognize=recognize,
            audio_get=lambda e, out: open(out, "wb").close(),
            vision_dir=self.vision_dir, variety_path=self.variety_path,
            srt_dir=self.srt_dir, log_path=self.log_path,
            work_dir=self.work_dir)
        self.assertEqual(seen, ["start", "end"] * 2)
        want = []
        for entry in entries:
            want.append(entry["srt_name"])
        self.assertEqual(done, want)
        self.assertEqual(failed, [])

    def test_one_failure_does_not_stop_the_rest(self):
        # 音檔暫存路徑本身就帶集名（見 _audio_tmp_path），recognize
        # 分得出是哪一集，不用另外標記。
        def recognize(server, audio_path, code):
            if "058" in audio_path:
                raise PipelineError("boom")
            return "1\n00:00:00,000 --> 00:00:01,000\n族語：a\n華語：b"

        first = dict(_entry(srt_name="20210227_058_晨間_Thau_邵"))
        first["族語別(中)"] = "邵"
        second = dict(_entry(srt_name="20210228_059_晨間_Thau_邵"))
        second["族語別(中)"] = "邵"

        done, failed = whisper_run.run_batch(
            [first, second], "https://x/sapolita", recognize=recognize,
            audio_get=lambda e, out: open(out, "wb").close(),
            vision_dir=self.vision_dir, variety_path=self.variety_path,
            srt_dir=self.srt_dir, log_path=self.log_path,
            work_dir=self.work_dir)
        self.assertEqual(done, [second["srt_name"]])
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0][0], first["srt_name"])


if __name__ == "__main__":
    unittest.main()
