"""news/pairs_run: every episode with both sides into 2-csv-analysis,
3-srt-paragraph.

A synthetic store (a few tribes, a few episodes); the dictionaries and
the E樂園 supplement are passed in, so nothing reaches the SFTP or
kithann/.
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
    # 官方魯凱辭典只收霧台
    "魯凱": {"kudra", "drekay", "kay", "ki", "ngudradrekadane"},
}
# E樂園 萬山詞表（官方辭典沒有的詞）
WANSHAN = {"dhona": None, "taoa": None, "kinioa": None, "ahaopo": None,
           "ina": None}
SUPPLEMENT = {"dru-x-opnh": set(WANSHAN)}


def read_bytes(path):
    with open(path, "rb") as handle:
        return handle.read()


AMIS = ("o tanosok a lalan no salikaka no kiwit a niyaroʼ i kalingko "
        "matini sowal no romiʼad")
ATAYAL = "lokah balay squliq tayal qani kawas miru nqrqes kmayal yabaʼ"
# 一半萬山詞、一半霧台詞：聯集才會全中
OPONOHO = "dhona taoa kinioa ahaopo ina kudra drekay kay ki ngudradrekadane"
RUKAI_169 = "20210618_169_午間_Rukai_魯凱"


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
    def test_2024_12_is_done_too(self):
        # 範圍原本寫死 2021-10，2496 集被擋在外面（2026-11-16）
        self.standard()
        self.episode("20241213_348_晚間_Amis_阿美", "Amis", "阿美", "ami", AMIS)
        self.write_catalogue()
        pairs_run.run(recalibrate=True, lexicons=LEXICONS)
        self.assertTrue(os.path.exists(self.out("20210201_032_晚間_Amis_阿美")))
        self.assertTrue(os.path.exists(
            self.out("20241213_348_晚間_Amis_阿美")))

    def test_ready_means_both_sides_whatever_the_month(self):
        # place_cue／offband_backfill／rebroadcast_port 改了 2023 年某集的
        # OCR SRT 也要重產；只有一側的不重產。
        self.episode("20230801_213_晚間_Amis_阿美", "Amis", "阿美", "ami", AMIS)
        self.episode("20230802_214_晚間_Amis_阿美", "Amis", "阿美", "ami", AMIS,
                     whisper=False)
        self.assertTrue(pairs_run.ready("20230801_213_晚間_Amis_阿美"))
        self.assertFalse(pairs_run.ready("20230802_214_晚間_Amis_阿美"))
        self.assertFalse(hasattr(pairs_run, "in_scope"))

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

    def test_recalibrate_only_fills_missing_rows(self):
        # 全量重算魯凱 0.27→0.44，已交付 657 集的分層全變（2026-11-16 量）
        self.standard()
        pairs_run.run(recalibrate=True, lexicons=LEXICONS)
        with open(self.table, "w", encoding="utf-8") as handle:
            handle.write("族語別,語言別代號,開場組數,辭典命中率中位數\n"
                         "阿美,ami,1,0.9000\n")
        pairs_run.run(recalibrate=True, lexicons=LEXICONS)
        table = read_bytes(self.table).decode("utf-8")
        self.assertIn("阿美,ami,1,0.9000\n", table)
        self.assertIn("泰雅,tay,", table)

    def test_the_wanshan_row_is_added_and_the_rest_stay_byte_identical(self):
        self.standard()
        pairs_run.run(recalibrate=True, lexicons=LEXICONS)
        before = read_bytes(self.table)
        self.episode(RUKAI_169, "Rukai", "魯凱", "dru-x-opnh", OPONOHO)
        self.write_catalogue()
        pairs_run.run(recalibrate=True, lexicons=LEXICONS,
                      supplements=SUPPLEMENT)
        after = read_bytes(self.table)
        self.assertIn("魯凱,dru-x-opnh,".encode("utf-8"), after)
        for line in before.splitlines():
            self.assertIn(line, after.splitlines())
        self.assertEqual(len(after.splitlines()), len(before.splitlines()) + 1)


class TestSupplement(Store):
    """萬山主播 Lavoras Tavelengae：官方魯凱辭典只收霧台，開場命中率 0.048、
    85% 不採用（2026-11-16 量）。"""

    def rate(self, name):
        return float(self.csv_rows(name)[0]["辭典命中率"])

    def test_a_wanshan_episode_scores_against_the_union(self):
        self.episode(RUKAI_169, "Rukai", "魯凱", "dru-x-opnh", OPONOHO)
        self.write_catalogue()
        pairs_run.run(recalibrate=True, lexicons=LEXICONS,
                      supplements=SUPPLEMENT)
        # 萬山詞與霧台詞都算命中——不是整個換成萬山（同集霧台受訪者會掉）
        self.assertEqual(self.rate(RUKAI_169), 1.0)

    def test_a_wutai_episode_ignores_the_supplement(self):
        name = "20220107_007_午間_Rukai_魯凱"
        self.episode(name, "Rukai", "魯凱", "dru-x-ngdr", OPONOHO)
        self.write_catalogue()
        pairs_run.run(recalibrate=True, lexicons=LEXICONS,
                      supplements=SUPPLEMENT)
        self.assertEqual(self.rate(name), 0.5)

    def test_no_wanshan_episode_never_reads_e_paradise(self):
        self.standard()
        with mock.patch.object(pairs_run.lexicon_fetch, "supplements",
                               side_effect=AssertionError("讀了 E樂園")):
            pairs_run.run(recalibrate=True, lexicons=LEXICONS)

    def test_a_wanshan_episode_without_e_paradise_stops(self):
        self.episode(RUKAI_169, "Rukai", "魯凱", "dru-x-opnh", OPONOHO)
        self.write_catalogue()
        refusal = PipelineError("/x/kithann/E樂園-解壓 不在")
        with mock.patch.object(pairs_run.lexicon_fetch, "supplements",
                               side_effect=refusal):
            with self.assertRaises(PipelineError) as caught:
                pairs_run.run(recalibrate=True, lexicons=LEXICONS)
        self.assertIn("E樂園", str(caught.exception))


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
        entry = {"srt_name": AMIS_032, "族語別(中)": "阿美", "語言別代號": "ami"}
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
        self.assertEqual(table[("阿美", "ami")]["groups"], 1)

    def test_a_subtitle_at_89_does_not_make_speech_at_91_the_opening(self):
        _samples, table = self.opening(91.0, 89.0)
        self.assertEqual(table, {})


if __name__ == "__main__":
    unittest.main()
