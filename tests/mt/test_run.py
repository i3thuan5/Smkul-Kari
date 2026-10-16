"""news/pairs_run: the 2021-01～10 batch into 2-csv-analysis, 3-srt-paragraph.

A synthetic store (two tribes, three episodes); the dictionaries are
passed in, so nothing reaches the SFTP.
"""
import csv
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from scripts.errors import PipelineError
from scripts.mt import calibration
from scripts.mt import tier
from scripts.srtlib import srt
from scripts.news import pairs_run
from scripts.news import paths

HEADER = ["成果檔名", "節目名稱", "年度", "集數", "播出日期", "族語別(英)",
          "族語別(中)", "語言別", "語言別代號", "原始影片檔案位置", "備註"]
LEXICONS = {
    "阿美": {"salikaka", "niyaro'", "kayakay", "kiwit", "lalan",
           "tanosok", "matini", "kalingko", "sowal", "romi'ad"},
    "泰雅": {"tayal", "qani", "kawas", "miru", "nqrqes", "squliq",
           "lokah", "balay", "yaba'", "kmayal"},
}


def read_bytes(path):
    with open(path, "rb") as handle:
        return handle.read()


AMIS = ("o tanosok a lalan no salikaka no kiwit a niyaroʼ i kalingko "
        "matini sowal no romiʼad")
ATAYAL = "lokah balay squliq tayal qani kawas miru nqrqes kmayal yabaʼ"


class Store(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="pairs-run-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        news = os.path.join(self.tmp, "news")
        self.dirs = {
            "KARI_CUES": os.path.join(news, "1-ocr", "1-cues"),
            "KARI_VISION": os.path.join(news, "1-ocr", "2-vision"),
            "SRT_DIR": os.path.join(news, "1-ocr", "3-srt"),
            "SAPOLITA_SRT": os.path.join(news, "2-asr-whisper",
                                         "1-srt-sapolita"),
            "PAIRS_DIR": os.path.join(news, "2-asr-whisper", "2-csv-analysis"),
            "PARAGRAPH_SRT": os.path.join(news, "2-asr-whisper",
                                          "3-srt-paragraph"),
            "LEGACY_PAIRS_DIR": os.path.join(news, "2-asr-whisper",
                                             "2-平行語料"),
        }
        for name, value in self.dirs.items():
            patcher = mock.patch.object(paths, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.table = os.path.join(self.dirs["PAIRS_DIR"], "校正基準.csv")
        self.catalogue = os.path.join(news, "smkul.csv")
        self.log = os.path.join(self.dirs["SAPOLITA_SRT"], "辨識紀錄.csv")
        for name, value in (("PAIRS_CALIBRATION", self.table),
                            ("TRACKER_STORE", self.catalogue),
                            ("SAPOLITA_LOG", self.log)):
            patcher = mock.patch.object(paths, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.rows = []
        self.lengths = {}

    def episode(self, name, tribe_en, tribe, code, formosan,
                ocr=True, whisper=True, length="200.000"):
        date = name[:8]
        self.rows.append({
            "成果檔名": name, "節目名稱": "晚間族語新聞", "年度": date[:4],
            "集數": name[9:12], "播出日期": "%s-%s-%s" % (
                date[:4], date[4:6], date[6:]),
            "族語別(英)": tribe_en, "族語別(中)": tribe, "語言別": "",
            "語言別代號": code, "原始影片檔案位置": "x/%s.mp4" % name,
            "備註": ""})
        month = paths.month_of(name)
        cues = [{"index": 1, "start": 20.0, "end": 24.0},
                {"index": 2, "start": 24.0, "end": 28.0},
                {"index": 3, "start": 120.0, "end": 124.0}]
        folder = os.path.join(self.dirs["KARI_CUES"], month)
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, name + ".json"), "w",
                  encoding="utf-8") as handle:
            json.dump({"cues": cues, "duration": 200.0}, handle)
        vision = os.path.join(self.dirs["KARI_VISION"], month, name)
        os.makedirs(vision, exist_ok=True)
        with open(os.path.join(vision, "b01.tsv"), "w",
                  encoding="utf-8") as handle:
            handle.write("1\than\t奇美部落的道路\n2\than\t花蓮縣的族人\n"
                         "3\than\t節目最後\n")
        if ocr:
            folder = os.path.join(self.dirs["SRT_DIR"], month)
            os.makedirs(folder, exist_ok=True)
            open(os.path.join(folder, name + ".srt"), "w").close()
        if whisper:
            folder = os.path.join(self.dirs["SAPOLITA_SRT"], month)
            os.makedirs(folder, exist_ok=True)
            with open(os.path.join(folder, name + ".srt"), "w",
                      encoding="utf-8") as handle:
                handle.write("1\n00:00:19,500 --> 00:00:28,200\n族語：%s\n"
                             "華語：奇美部落的道路\n\n2\n00:02:00,000 --> "
                             "00:02:04,000\n族語：ʼa ʼa ʼa ʼa ʼa ʼa ʼa ʼa\n"
                             "華語：一、二、三、四、五、六\n" % formosan)
            if length is not None:
                self.lengths[name] = length

    def write_log(self):
        os.makedirs(os.path.dirname(self.log), exist_ok=True)
        with open(self.log, "w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(["成果檔名", "語言別代號", "主播名", "伺服器",
                             "辨識日期", "音長秒", "段數"])
            for name in sorted(self.lengths):
                writer.writerow([name, "ami", "不明", "x", "2026-09-18 18:05",
                                 self.lengths[name], "2"])

    def write_catalogue(self):
        self.write_log()
        with open(self.catalogue, "w", encoding="utf-8-sig",
                  newline="") as handle:
            writer = csv.DictWriter(handle, HEADER, lineterminator="\r\n")
            writer.writeheader()
            for row in sorted(self.rows, key=lambda r: r["成果檔名"]):
                writer.writerow(row)

    def out(self, name):
        return os.path.join(self.dirs["PAIRS_DIR"], paths.month_of(name),
                            name + ".csv")

    def srt_out(self, name):
        return os.path.join(self.dirs["PARAGRAPH_SRT"], paths.month_of(name),
                            name + ".srt")

    def csv_rows(self, name):
        with open(self.out(name), encoding="utf-8") as handle:
            return list(csv.DictReader(handle))

    def standard(self):
        self.episode("20210201_032_晚間_Amis_阿美", "Amis", "阿美", "ami", AMIS)
        self.episode("20210202_033_晚間_Atayal_泰雅", "Atayal", "泰雅", "tay",
                     ATAYAL)
        self.write_catalogue()


class TestScope(Store):
    def test_only_2021_01_to_10(self):
        self.standard()
        self.episode("20211101_305_晚間_Amis_阿美", "Amis", "阿美", "ami", AMIS)
        self.write_catalogue()
        pairs_run.run(recalibrate=True, lexicons=LEXICONS)
        self.assertTrue(os.path.exists(self.out("20210201_032_晚間_Amis_阿美")))
        self.assertFalse(os.path.exists(
            self.out("20211101_305_晚間_Amis_阿美")))

    def test_one_side_missing_is_listed_not_an_error(self):
        self.standard()
        self.episode("20210703_184_晚間_Amis_阿美", "Amis", "阿美", "ami", AMIS,
                     ocr=False)
        self.write_catalogue()
        written, skipped = pairs_run.run(recalibrate=True, lexicons=LEXICONS)
        self.assertEqual(len(written), 2)
        self.assertEqual([name for name, _why in skipped],
                         ["20210703_184_晚間_Amis_阿美"])


class TestCalibration(Store):
    def test_no_table_without_recalibrate_is_refused(self):
        self.standard()
        with self.assertRaises(PipelineError):
            pairs_run.run(lexicons=LEXICONS)

    def test_new_month_leaves_table_and_old_files_alone(self):
        self.standard()
        pairs_run.run(recalibrate=True, lexicons=LEXICONS)
        table = read_bytes(self.table)
        old = read_bytes(self.out("20210201_032_晚間_Amis_阿美"))
        self.episode("20210301_060_晚間_Amis_阿美", "Amis", "阿美", "ami",
                     "tada ko matini")
        self.write_catalogue()
        pairs_run.run(lexicons=LEXICONS)
        self.assertEqual(read_bytes(self.table), table)
        self.assertEqual(read_bytes(self.out("20210201_032_晚間_Amis_阿美")),
                         old)
        self.assertTrue(os.path.exists(self.out("20210301_060_晚間_Amis_阿美")))

    def test_recalibrate_rewrites_the_table(self):
        self.standard()
        pairs_run.run(recalibrate=True, lexicons=LEXICONS)
        with open(self.table, "w", encoding="utf-8") as handle:
            handle.write("族語別,開場組數,辭典命中率中位數\n阿美,1,0.9000\n"
                         "泰雅,1,0.9000\n")
        pairs_run.run(recalibrate=True, lexicons=LEXICONS)
        self.assertNotIn(b"0.9000", read_bytes(self.table))


class TestContent(Store):
    def test_rows_are_tiered_with_reasons(self):
        self.standard()
        pairs_run.run(recalibrate=True, lexicons=LEXICONS)
        with open(self.out("20210201_032_晚間_Amis_阿美"),
                  encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 2)
        self.assertNotEqual(rows[0]["信心層級"], "不採用")
        self.assertEqual((rows[1]["信心層級"], rows[1]["不採用原因"]),
                         ("不採用", "幻覺"))
        self.assertEqual(rows[0]["語言別代號"], "ami")

    def test_no_model_is_called(self):
        self.standard()
        with mock.patch("scripts.asrmt.gradio.Client",
                        side_effect=AssertionError("model call")):
            pairs_run.run(recalibrate=True, lexicons=LEXICONS)

    def test_merge_threshold_is_read_from_tier(self):
        self.standard()
        seen = []
        real = pairs_run.overlap.max_overlap_groups

        def spy(segments, entries, straddle_frac=None):
            seen.append(straddle_frac)
            return real(segments, entries, straddle_frac=straddle_frac)
        with mock.patch.object(pairs_run.overlap, "max_overlap_groups", spy):
            pairs_run.run(recalibrate=True, lexicons=LEXICONS)
        self.assertEqual(set(seen), {tier.MERGE_FRACTION})


AMIS_032 = "20210201_032_晚間_Amis_阿美"


class TestParagraphSrt(Store):
    def test_the_srt_is_written_in_the_same_run_from_the_same_rows(self):
        self.standard()
        pairs_run.run(recalibrate=True, lexicons=LEXICONS)
        rows = self.csv_rows(AMIS_032)
        kept = []
        for r in rows:
            if r["信心層級"] != "不採用":
                kept.append(r)
        with open(self.srt_out(AMIS_032), encoding="utf-8") as handle:
            cues = srt.parse_srt(handle.read())
        self.assertEqual(len(cues), len(kept))
        for (start, end, text), r in zip(cues, kept):
            self.assertEqual(srt.srt_timestamp(start), r["開始時間"])
            self.assertEqual(srt.srt_timestamp(end), r["結束時間"])
            self.assertEqual(text, "族語：%s\n華語：%s" % (r["族語"], r["華語"]))

    def test_the_old_directory_still_there_stops_the_run(self):
        self.standard()
        os.makedirs(self.dirs["LEGACY_PAIRS_DIR"])
        with self.assertRaises(PipelineError) as caught:
            pairs_run.run(recalibrate=True, lexicons=LEXICONS)
        self.assertIn("2-平行語料", str(caught.exception))

    def test_no_audio_length_names_the_episode(self):
        self.episode(AMIS_032, "Amis", "阿美", "ami", AMIS, length=None)
        self.write_catalogue()
        with self.assertRaises(PipelineError) as caught:
            pairs_run.run(recalibrate=True, lexicons=LEXICONS)
        self.assertIn(AMIS_032, str(caught.exception))

    def test_a_blank_audio_length_names_the_episode(self):
        self.episode(AMIS_032, "Amis", "阿美", "ami", AMIS, length="")
        self.write_catalogue()
        with self.assertRaises(PipelineError) as caught:
            pairs_run.run(recalibrate=True, lexicons=LEXICONS)
        self.assertIn(AMIS_032, str(caught.exception))


class TestTwoTimes(Store):
    """The true time feeds the pairing, the calibration and the
    features; only the CSV (and the SRT copying it) shows the padded
    one. Each mix-up below goes wrong without any error."""

    def test_the_csv_shows_the_padded_time(self):
        # speech 19.5-28.2, the next speech 2 minutes on: 19.0-28.7
        self.standard()
        pairs_run.run(recalibrate=True, lexicons=LEXICONS)
        first = self.csv_rows(AMIS_032)[0]
        self.assertEqual((first["開始時間"], first["結束時間"]),
                         ("00:00:19,000", "00:00:28,700"))

    def test_the_pairing_sees_the_true_segments(self):
        self.standard()
        seen = []
        real = pairs_run.overlap.max_overlap_groups

        def spy(segments, entries, straddle_frac=None):
            seen.append(segments[0]["start"])
            return real(segments, entries, straddle_frac=straddle_frac)
        with mock.patch.object(pairs_run.overlap, "max_overlap_groups", spy):
            pairs_run.run(recalibrate=True, lexicons=LEXICONS)
        self.assertEqual(set(seen), {19.5})

    def test_features_measure_the_true_duration(self):
        self.standard()
        entry = {"srt_name": AMIS_032, "族語別(中)": "阿美", "語言別代號": "ami"}
        _groups, _segs, _ents, feats = pairs_run.measured(entry, LEXICONS)
        self.assertAlmostEqual(feats[0]["duration"], 8.7)

    def opening(self, speech_start, subtitle_start):
        segments = [{"index": 0, "start": speech_start,
                     "end": speech_start + 5.0, "formosan": AMIS, "han": ""}]
        entries = [{"index": 0, "true_start": subtitle_start,
                    "true_end": speech_start + 4.0, "han": "道路",
                    "formosan": "", "cues": [0]}]
        group = {"segs": [0], "entries": [0]}
        feats = [{"asr_words": 12, "lexicon_rate": 0.5}]
        entry = {"srt_name": AMIS_032, "族語別(中)": "阿美"}
        with mock.patch.object(pairs_run, "measured",
                               return_value=([group], segments, entries,
                                             feats)):
            samples = pairs_run.opening_samples(entry, LEXICONS)
        return samples, calibration.baseline(samples)

    def test_true_90_3_is_not_the_opening_though_padded_is_89_8(self):
        samples, table = self.opening(90.3, 90.0)
        self.assertEqual(samples[0]["start"], 90.3)
        self.assertEqual(table, {})

    def test_true_89_8_is_the_opening(self):
        _samples, table = self.opening(89.8, 89.5)
        self.assertEqual(table["阿美"]["groups"], 1)

    def test_a_subtitle_at_89_does_not_make_speech_at_91_the_opening(self):
        _samples, table = self.opening(91.0, 89.0)
        self.assertEqual(table, {})


if __name__ == "__main__":
    unittest.main()
