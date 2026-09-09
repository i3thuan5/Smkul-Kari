"""asrmt_run: the per-episode orchestration guards.

Pins the asr-bilingual-srt spec's 音檔時長不符 scenario -- fail loud,
naming the episode and both durations, producing nothing -- and the
resume rule: a step whose output already exists is skipped, so an
interrupted run continues instead of redoing paid work.
"""
import copy
import json
import os
import tempfile
import unittest
from unittest import mock

from scripts.asrmt import judge
from scripts.asrmt import mtclient
from scripts.news import asrmt_run
from scripts.news import paths
from scripts.errors import PipelineError


class TestVerifyAudio(unittest.TestCase):
    def test_within_tolerance_passes(self):
        asrmt_run.verify_audio("試集", 2880.168, 2880.144)

    def test_mismatch_names_the_episode_and_both_numbers(self):
        with self.assertRaises(PipelineError) as caught:
            asrmt_run.verify_audio("試集", 2760.0, 2880.144)
        message = str(caught.exception)
        self.assertIn("試集", message)
        self.assertIn("2760", message)
        self.assertIn("2880.144", message)

    def test_tolerance_is_one_second_by_default(self):
        with self.assertRaises(PipelineError):
            asrmt_run.verify_audio("試集", 2881.5, 2880.0)
        asrmt_run.verify_audio("試集", 2880.9, 2880.0)


class TestResume(unittest.TestCase):
    def test_existing_output_skips_the_step(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "done.json")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("{}")
            self.assertFalse(asrmt_run.step_needed(path))
            self.assertTrue(asrmt_run.step_needed(
                os.path.join(tmp, "not-there.json")))


class TestModelMapping(unittest.TestCase):
    def test_inventory_ethnicity_maps_to_hf_repo_name(self):
        # inventory 的族語別(英) 與 HF 模型 repo 名有五處不同拼法
        self.assertEqual(asrmt_run.model_id_of("Amis"),
                         "ILRDF/kaldi_formosan_250514_Amis")
        self.assertEqual(asrmt_run.model_id_of("SaySiyat"),
                         "ILRDF/kaldi_formosan_250514_Saisiyat")
        self.assertEqual(asrmt_run.model_id_of("Pinuyumayan"),
                         "ILRDF/kaldi_formosan_250514_Puyuma")
        self.assertEqual(asrmt_run.model_id_of("Hla'alua"),
                         "ILRDF/kaldi_formosan_250514_Saaroa")
        self.assertEqual(asrmt_run.model_id_of("Cou"),
                         "ILRDF/kaldi_formosan_250514_Tsou")
        self.assertEqual(asrmt_run.model_id_of("Thau"),
                         "ILRDF/kaldi_formosan_250514_Thao")

    def test_unknown_ethnicity_fails_loud(self):
        with self.assertRaises(PipelineError):
            asrmt_run.model_id_of("Klingon")


class TestMp3Resolution(unittest.TestCase):
    def test_remote_path_from_catalogue_row(self):
        rows = [{"播出日期": "2021-02-01", "播出時段": "晚間",
                 "音檔位置(mp3)": "ilrdf-corpus/族語新聞/7月/x.mp3"}]
        got = asrmt_run.mp3_remote("20210201_032_晚間_Amis_阿美", rows)
        self.assertEqual(got, "/docker/ilrdf-corpus/族語新聞/7月/x.mp3")

    def test_missing_row_fails_loud(self):
        with self.assertRaises(PipelineError):
            asrmt_run.mp3_remote("20210301_060_午間_Cou_鄒", [])

    def test_semicolon_cell_picks_the_matching_slot(self):
        # 型錄的 mp3 欄有同格塞多路徑的情況（037 晚間實例）
        rows = [{"播出日期": "2021-02-06", "播出時段": "晚間",
                 "音檔位置(mp3)":
                 "ilrdf-corpus/7月/21NL004_37午間族語新聞.mp3;"
                 "ilrdf-corpus/7月/21NL004_37晚間族語新聞.mp3"}]
        got = asrmt_run.mp3_remote("20210206_037_晚間_Paiwan_排灣", rows)
        self.assertEqual(got,
                         "/docker/ilrdf-corpus/7月/21NL004_37晚間族語新聞.mp3")

    def test_semicolon_cell_without_slot_match_takes_the_first(self):
        rows = [{"播出日期": "2021-02-06", "播出時段": "晚間",
                 "音檔位置(mp3)": "ilrdf-corpus/a.mp3;ilrdf-corpus/b.mp3"}]
        got = asrmt_run.mp3_remote("20210206_037_晚間_Paiwan_排灣", rows)
        self.assertEqual(got, "/docker/ilrdf-corpus/a.mp3")


class TestCuesPath(unittest.TestCase):
    """時間軸對佗位提：交付了ê對 store，猶未交付ê對 work dir。

    一集做到底ê流程，語音側是佇 publish **進前**跑ê（OCR → 2-srt-raw →
    publish），而 cues.json 是 publish 才對 work dir 徙入 store ê。若干焦
    看 store，語音側就永遠等袂著——publish 顛倒愛等伊。

    `.B.work` 彼个才是準ê：make_all 就是對彼跡組出交付ê SRT，publish 嘛
    是對彼跡kā cues.json 徙入 store。兩爿愛是仝一份，時間軸才對同。
    """

    NAME = "20210101_001_午間_Rukai_魯凱"
    SLUG = "2021_001_2021-01-01_午間_Rukai_魯凱"

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = tmp.name
        self.store = os.path.join(self.root, "1-cues")
        self.work = os.path.join(self.root, "work")
        os.makedirs(self.store)
        os.makedirs(self.work)
        patches = [mock.patch.object(paths, "KARI_CUES", self.store),
                   mock.patch.object(paths, "WORK", self.work)]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def _in_store(self):
        path = paths.stage_path(self.store, self.NAME, ".json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "w").close()
        return path

    def _in_work(self):
        folder = os.path.join(self.work, self.SLUG + ".B.work")
        os.makedirs(folder, exist_ok=True)
        os.makedirs(os.path.join(folder, "1-cues"), exist_ok=True)
        path = paths.coarse_cues(folder)
        open(path, "w").close()
        return path

    def test_the_store_wins_once_the_episode_is_published(self):
        want = self._in_store()
        self._in_work()
        self.assertEqual(asrmt_run._cues_path(self.NAME, self.SLUG), want)

    def test_the_work_dir_carries_a_pending_episode(self):
        want = self._in_work()
        self.assertEqual(asrmt_run._cues_path(self.NAME, self.SLUG), want)

    def test_neither_place_says_so_by_name(self):
        with self.assertRaises(PipelineError) as caught:
            asrmt_run._cues_path(self.NAME, self.SLUG)
        self.assertIn(self.NAME, str(caught.exception))


if __name__ == "__main__":
    unittest.main()


def _made(folder):
    os.makedirs(folder, exist_ok=True)
    return folder


class TestProjectionIsNotStored(unittest.TestCase):
    """投影是純函式，算出來ê物件無落地。

    本底伊會寫一份 `2-entries`，予人當做「來源追蹤」咧用。毋過彼
    是**視圖毋是正本**：時間軸換版就規份重產，頂懸補入去ê物件（譯文）
    綴leh予洗掉——2026-09-04 就按呢無去一集ê譯文。正本愛囥內容定址
    ê快取，中間過程當場算就好，才會使講「干焦靠 store 就重建會出來」。
    """

    NAME = "20210101_001_午間_Rukai_魯凱"
    ROWS = [{"index": 1, "true_start": 0.0, "true_end": 2.0,
             "srt_start": 0.0, "srt_end": 2.5, "text": "大家好"},
            {"index": 2, "true_start": 2.0, "true_end": 4.0,
             "srt_start": 2.5, "srt_end": 4.5, "text": "今天的新聞"}]
    WORDS = [{"w": "kai", "start": 0.2, "end": 0.8, "conf": 0.9},
             {"w": "nga", "start": 1.0, "end": 1.6, "conf": 0.8},
             {"w": "sudalu", "start": 2.4, "end": 3.4, "conf": 0.7}]

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.asr = tmp.name
        # 逐个階段常數攏愛換掉，一个漏去就會寫著**真正ê店面**——
        # ASR_AI 漏去彼擺，測試ê假資料就按呢寫入 Kari-SRT，
        # `rebuild --verify` 才kā伊掠著。
        for name, stage in (("ASR_DIR", ""), ("ASR_WORDS", "1-words"),
                            ("ASR_RAW", "2-srt-raw"), ("ASR_AI", "3-srt-ai"),
                            ("ASR_QUALITY", "4-srt-quality"),
                            ("QUALITY_CACHE", "quality-cache"),
                            ("MT_CACHE", "mt-cache")):
            patch = mock.patch.object(paths, name,
                                      os.path.join(self.asr, stage))
            patch.start()
            self.addCleanup(patch.stop)
        patch = mock.patch.object(asrmt_run, "_chain_rows",
                                  lambda name: copy.deepcopy(self.ROWS))
        patch.start()
        self.addCleanup(patch.stop)
        # `_workdir` 是對 repo 根算ê，無綴階段常數走。無kā伊換掉，
        # 批次檔就寫入真正ê `kithann/out/asrmt/`——測試ê假資料留佇
        # 使用者ê工作區，落尾閣有人當做真ê去收。
        work = os.path.join(self.asr, "work")
        patch = mock.patch.object(asrmt_run, "_workdir",
                                  lambda name: _made(os.path.join(work,
                                                                  name)))
        patch.start()
        self.addCleanup(patch.stop)
        words = paths.stage_path(paths.ASR_WORDS, self.NAME, ".json")
        os.makedirs(os.path.dirname(words), exist_ok=True)
        with open(words, "w", encoding="utf-8") as handle:
            json.dump({"srt_name": self.NAME, "words": self.WORDS}, handle,
                      ensure_ascii=False, indent=2, sort_keys=True)

    def _json_files(self):
        found = []
        for folder, _dirs, names in os.walk(self.asr):
            for name in names:
                if name.endswith(".json"):
                    found.append(os.path.join(folder, name))
        return found

    def test_the_rows_come_from_the_words_and_the_timeline(self):
        rows, unassigned = asrmt_run.rows_of(self.NAME)
        self.assertEqual(rows[0]["formosan"], "kai nga")
        self.assertEqual(rows[0]["subtitle"], "大家好")
        self.assertEqual(rows[1]["formosan"], "sudalu")
        self.assertEqual(unassigned, [])

    def test_projecting_twice_gives_the_same_thing(self):
        first, _ = asrmt_run.rows_of(self.NAME)
        second, _ = asrmt_run.rows_of(self.NAME)
        self.assertEqual(first, second)

    def test_the_raw_body_renders_off_those_rows(self):
        body = asrmt_run.raw_body_of(self.NAME)
        self.assertIn("族語：kai nga", body)
        self.assertIn("華語：大家好", body)

    def test_the_raw_step_writes_the_second_stage(self):
        asrmt_run.step_raw(self.NAME)
        out = paths.stage_path(paths.ASR_RAW, self.NAME, ".srt")
        with open(out, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), asrmt_run.raw_body_of(self.NAME))

    def test_nothing_but_the_words_file_is_written(self):
        asrmt_run.step_raw(self.NAME)
        self.assertEqual(self._json_files(),
                         [paths.stage_path(paths.ASR_WORDS, self.NAME,
                                           ".json")])

    def test_the_entries_step_is_gone(self):
        for gone in ("step_entries", "_entries_path"):
            self.assertFalse(hasattr(asrmt_run, gone), gone)

    def test_the_default_pipeline_is_words_then_raw(self):
        names = []
        for name, _ in asrmt_run.STEPS:
            names.append(name)
        self.assertEqual(names[:2], ["words", "raw"])
        self.assertNotIn("entries", names)


class TestTranslationStep(TestProjectionIsNotStored):
    """mt 步：逐條非空ê族語逝翻做華語，寫 3-srt-ai。

    快取是內容定址ê，所以「翻過ê免閣翻」佮「重投影了後照常命中」是
    仝一件代誌。服務是公共ê，單併發、逐擺歇一秒，一集愛十外分鐘——
    所以斷去閣走一擺袂使閣付一擺錢。
    """

    def setUp(self):
        super(TestTranslationStep, self).setUp()
        patch = mock.patch.object(
            asrmt_run, "_entry_of",
            lambda name: {"srt_name": name, "族語別(英)": "Rukai",
                          "slug": "x"})
        patch.start()
        self.addCleanup(patch.stop)

    class FakeClient(object):
        def __init__(self, table):
            self.table = table
            self.calls = []

        def translate_cached(self, cache, engine, direction, lang, text):
            hit = cache.get(engine, direction, lang, text)
            if hit is not None:
                return hit
            self.calls.append(text)
            out = self.table[text]
            cache.put(engine, direction, lang, text, out)
            return out

    TABLE = {"kai nga": "大家好啊", "sudalu": "今天"}

    def test_it_writes_the_third_stage_with_the_translation(self):
        client = self.FakeClient(self.TABLE)
        asrmt_run.step_mt(self.NAME, client=client)
        path = paths.stage_path(paths.ASR_AI, self.NAME, ".srt")
        with open(path, encoding="utf-8") as handle:
            body = handle.read()
        self.assertIn("族語ASR結果翻譯華語-ailabs：大家好啊", body)
        self.assertIn("華語OCR字幕：大家好", body)

    def test_the_language_code_comes_from_the_table(self):
        client = self.FakeClient(self.TABLE)
        asrmt_run.step_mt(self.NAME, client=client)
        cache = mtclient.MTCache(paths.MT_CACHE)
        self.assertEqual(cache.get("ailabs", "f2z", "dru_Dawu", "kai nga"),
                         "大家好啊")

    def test_a_second_run_asks_the_service_nothing(self):
        first = self.FakeClient(self.TABLE)
        asrmt_run.step_mt(self.NAME, client=first)
        again = self.FakeClient(self.TABLE)
        asrmt_run.step_mt(self.NAME, client=again)
        self.assertEqual(again.calls, [])

    def test_the_offline_rebuild_reads_the_cache_and_never_the_service(self):
        client = self.FakeClient(self.TABLE)
        asrmt_run.step_mt(self.NAME, client=client)
        path = paths.stage_path(paths.ASR_AI, self.NAME, ".srt")
        with open(path, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), asrmt_run.ai_body_of(self.NAME))

    def test_a_missing_cache_entry_makes_the_rebuild_fail_by_name(self):
        client = self.FakeClient(self.TABLE)
        asrmt_run.step_mt(self.NAME, client=client)
        for name in os.listdir(paths.MT_CACHE):
            os.remove(os.path.join(paths.MT_CACHE, name))
        with self.assertRaises(PipelineError) as caught:
            asrmt_run.ai_body_of(self.NAME)
        self.assertIn("條目 1", str(caught.exception))


class TestJudgingSteps(TestTranslationStep):
    """judge／ingest／quality 三步：寫批次、收回覆、render。

    模型ê部份是 Claude Code ê subagent 讀批次檔、寫回覆檔——容器內底
    無 SDK 嘛無金鑰，而且視覺辨識彼爿本底就是按呢做ê。所以程式這爿
    ê責任是：批次寫予好、回覆檢查予絚、判定囥入快取。
    """

    def setUp(self):
        super(TestJudgingSteps, self).setUp()
        asrmt_run.step_mt(self.NAME, client=self.FakeClient(self.TABLE))

    def _folder(self):
        return asrmt_run.judge_folder(self.NAME)

    def _reply(self, request, labels):
        path = request[:-len(".tsv")] + ".reply.tsv"
        lines = []
        with open(request, encoding="utf-8") as handle:
            for line in handle:
                key = line.split("\t")[0]
                lines.append("%s\t%s\n" % (key, labels[key]))
        with open(path, "w", encoding="utf-8") as handle:
            handle.writelines(lines)
        return path

    def test_the_glossary_lands_beside_the_batches(self):
        """詞表佮批次做伙產，逐个 agent 讀仝一份。

        本底逐个 agent 家己推——三个 agent 推出仝一个詞是常有ê代誌，
        而且無仝批對仝一个詞ê認定會無仝。掃規集算一擺，較緊嘛較一致。
        """
        asrmt_run.step_judge(self.NAME)
        path = os.path.join(asrmt_run.judge_folder(self.NAME),
                            "glossary.tsv")
        self.assertTrue(os.path.exists(path))
        with open(path, encoding="utf-8") as handle:
            self.assertTrue(handle.read().strip())

    def test_the_glossary_is_not_wiped_by_the_second_round(self):
        asrmt_run.step_judge(self.NAME)
        written = asrmt_run.step_judge(self.NAME)
        self.assertIsNotNone(written)
        path = os.path.join(asrmt_run.judge_folder(self.NAME),
                            "glossary.tsv")
        self.assertTrue(os.path.exists(path))

    def test_the_batch_is_big_enough_to_be_worth_an_agent(self):
        """一批愛夠大，若無固定開銷食掉一半。

        逐个 agent ê固定開銷量著約 9 萬到 10 萬 token（系統提示、判定
        規則、詞表，逐回合閣重送一擺），逐列ê邊際成本才 1300。50 列
        一批ê時，固定開銷佔欲一半——雅美尾批 3 列嘛開 5 萬 1。

        使用者裁定 2026-09-08：**一批至少 200 列，愈大愈好，用會著
        sonnet context ê 50%；超過 15 分鐘無要緊，先省 token。**
        第二輪 fable 仝款。

        揀 500：一列量著 204 bytes，500 列約 102KB、4 萬 1 token ê
        材料，加規則佮詞表大約佔 20 萬 context ê四分之一，離 50% 猶
        有偌濟通予 agent 想。無揀「規集一批」（上大彼集 966 列）ê
        因端有兩个：一批去予退ê時，了ê是規集ê工，毋是半集；閣有，
        材料家己就食 45% ê context，賰無偌濟通推理。省ê差額才一成
        外。
        """
        self.assertGreaterEqual(asrmt_run.BATCH_SIZE, 200)

    def test_rewriting_batches_over_an_uningested_reply_is_refused(self):
        """回覆猶未收就閣寫一擺批次，會kā飛咧ê彼幾个agent害死。

        `step_judge` 寫批次進前會kā本版ê請求檔攏刣掉重寫。快取若佇這
        中間加了幾若條，賰ê條目就會重新分批——原本 s03 彼五十條會徙
        去 s02 佮 s03 中央。彼陣iáu咧做ê agent 讀ê是舊ê s03，寫轉來ê
        回覆貼佇新ê s03 頂懸，編號全部走精，koh袂有人看會出來。

        所以：有本版ê回覆檔猶未收，就毋准重寫。先 `--step ingest`。
        """
        written = asrmt_run.step_judge(self.NAME)
        self._reply(written[0], {"1": "高", "2": "中"})
        with self.assertRaises(PipelineError) as caught:
            asrmt_run.step_judge(self.NAME)
        self.assertIn("ingest", str(caught.exception))

    def test_rewriting_after_the_reply_is_ingested_is_fine(self):
        written = asrmt_run.step_judge(self.NAME)
        self._reply(written[0], {"1": "高", "2": "中"})
        asrmt_run.step_ingest(self.NAME)
        self.assertEqual(asrmt_run.step_judge(self.NAME), [])

    def test_the_first_judge_gets_a_batch_of_everything(self):
        written = asrmt_run.step_judge(self.NAME)
        self.assertEqual(len(written), 1)
        self.assertTrue(os.path.basename(written[0]).startswith("s"))
        with open(written[0], encoding="utf-8") as handle:
            self.assertEqual(len(handle.read().splitlines()), 2)

    def test_ingesting_a_reply_fills_the_cache(self):
        written = asrmt_run.step_judge(self.NAME)
        self._reply(written[0], {"1": "高", "2": "中"})
        self.assertEqual(asrmt_run.step_ingest(self.NAME), 2)

    def test_the_second_judge_only_sees_what_the_first_called_high(self):
        written = asrmt_run.step_judge(self.NAME)
        self._reply(written[0], {"1": "高", "2": "中"})
        asrmt_run.step_ingest(self.NAME)
        second = asrmt_run.step_judge(self.NAME, second=True)
        with open(second[0], encoding="utf-8") as handle:
            keys = []
            for line in handle:
                keys.append(line.split("\t")[0])
        self.assertEqual(keys, ["1"])

    def test_the_batch_name_carries_the_prompt_version(self):
        """版本入去檔名，就免「清掉才閣寫」。

        本底ê做法是寫新批次進前kā仝前綴ê檔攏刣掉——因為舊ê回覆檔
        佮新ê請求檔編號拄好相仝ê時，`ingest` 會kā舊定義下跤ê答案當
        做新ê收落去。

        毋過彼刣ê毋若是舊ê：**猶咧走ê agent，伊ê請求檔佮伊寫好ê
        回覆檔嘛做伙予人刣掉**。今仔日「回報講寫好、檔案無佇咧」
        彼八擺，泰半是按呢來ê——毋是 agent 失敗，是我家己刣ê。

        版本入檔名了後，無仝版本本底就無仝名，免刣，跑咧ê嘛袂去予
        害著。
        """
        written = asrmt_run.step_judge(self.NAME)
        self.assertIn(judge.PROMPT_VERSION, os.path.basename(written[0]))

    def test_a_new_batch_leaves_a_running_agents_reply_alone(self):
        """跑咧ê agent 寫入來ê物件袂使去予後一擺ê寫批次刣掉。

        這馬是兩重ê：第二擺 `step_judge` 家己就予擋落來（見
        `_refuse_over_uningested`），就算擋無著，`_clear_batches` 嘛
        袂去振動著回覆檔。
        """
        written = asrmt_run.step_judge(self.NAME)
        self._reply(written[0], {"1": "高", "2": "中"})
        reply = written[0][:-len(".tsv")] + ".reply.tsv"
        with self.assertRaises(PipelineError):
            asrmt_run.step_judge(self.NAME)
        self.assertTrue(os.path.exists(reply))
        asrmt_run._clear_batches(self._folder(), judge.PREFIX[judge.FIRST])
        self.assertTrue(os.path.exists(reply))

    def test_an_older_versions_reply_is_not_mistaken_for_this_ones(self):
        """舊版ê回覆檔留咧無要緊——名無仝，`ingest` 揣袂著伊。"""
        folder = asrmt_run.judge_folder(self.NAME)
        stale = os.path.join(folder, "s01.v0.reply.tsv")
        with open(stale, "w", encoding="utf-8") as handle:
            handle.write("1\t高\n2\t高\n")
        written = asrmt_run.step_judge(self.NAME)
        self._reply(written[0], {"1": "低", "2": "低"})
        asrmt_run.step_ingest(self.NAME)
        cache = judge.QualityCache(paths.QUALITY_CACHE)
        _rows, items = asrmt_run._judge_items(self.NAME)
        self.assertEqual(cache.get(judge.FIRST, items[0]), "低")

    def test_the_same_versions_batch_is_rewritten_not_accumulated(self):
        """仝一版閣寫一擺，是重寫，毋是閣加一份。

        本底這條測ê是「寫新批次愛kā舊回覆檔刣掉」——彼是版本猶未
        入檔名彼陣ê保護：無仝定義ê批次檔仝名，舊答案會予人當做新ê
        收落去。

        版本入檔名了後彼个危險無矣（無仝版本無仝名），毋過清仝一版
        ê檔猶原著愛——按呢重寫ê時陣，批次數目變少ê話，賰彼幾份舊ê
        才袂留咧。
        """
        written = asrmt_run.step_judge(self.NAME, size=1)
        self.assertEqual(len(written), 2)
        again = asrmt_run.step_judge(self.NAME, size=50)
        self.assertEqual(len(again), 1)
        folder = asrmt_run.judge_folder(self.NAME)
        left = []
        for entry in sorted(os.listdir(folder)):
            if entry.startswith("s") and entry.endswith(".tsv"):
                left.append(entry)
        self.assertEqual(len(left), 1)

    def test_it_does_not_clear_the_other_judges_files(self):
        written = asrmt_run.step_judge(self.NAME)
        self._reply(written[0], {"1": "高", "2": "中"})
        asrmt_run.step_ingest(self.NAME)
        second = asrmt_run.step_judge(self.NAME, second=True)
        self._reply(second[0], {"1": "高"})
        asrmt_run.step_judge(self.NAME)
        kept = second[0][:-len(".tsv")] + ".reply.tsv"
        self.assertTrue(os.path.exists(kept))

    def test_the_second_round_refuses_while_the_first_is_unfinished(self):
        """頭一輪無收齊就寫第二輪，會**恬恬**漏掉。

        第二輪干焦問頭一个裁判講懸ê。頭一輪若閣有一批無收，彼批內
        底ê懸就iáu無入快取，第二輪就無問著——落尾產品質檔ê時才發
        現彼幾條無判定，抑是閣較穤：無發現。
        """
        written = asrmt_run.step_judge(self.NAME, size=1)
        self._reply(written[0], {"1": "高"})
        asrmt_run.step_ingest(self.NAME)
        with self.assertRaises(PipelineError) as caught:
            asrmt_run.step_judge(self.NAME, second=True)
        self.assertIn("頭一輪", str(caught.exception))

    def test_the_second_round_goes_once_the_first_is_complete(self):
        written = asrmt_run.step_judge(self.NAME)
        self._reply(written[0], {"1": "高", "2": "中"})
        asrmt_run.step_ingest(self.NAME)
        self.assertEqual(len(asrmt_run.step_judge(self.NAME, second=True)), 1)

    def test_nothing_left_to_ask_writes_no_batch(self):
        written = asrmt_run.step_judge(self.NAME)
        self._reply(written[0], {"1": "低", "2": "中"})
        asrmt_run.step_ingest(self.NAME)
        self.assertEqual(asrmt_run.step_judge(self.NAME), [])
        self.assertEqual(asrmt_run.step_judge(self.NAME, second=True), [])

    def _grade_everything(self, first, second=None):
        written = asrmt_run.step_judge(self.NAME)
        self._reply(written[0], first)
        asrmt_run.step_ingest(self.NAME)
        again = asrmt_run.step_judge(self.NAME, second=True)
        if again:
            self._reply(again[0], second)
            asrmt_run.step_ingest(self.NAME, second=True)

    def test_the_quality_step_writes_the_fourth_stage(self):
        self._grade_everything({"1": "高", "2": "中"}, {"1": "高"})
        asrmt_run.step_quality(self.NAME)
        path = paths.stage_path(paths.ASR_QUALITY, self.NAME, ".srt")
        with open(path, encoding="utf-8") as handle:
            body = handle.read()
        self.assertIn("族華對應品質：高", body)
        self.assertIn("族華對應品質：中", body)
        self.assertNotIn("ailabs", body)

    def test_the_second_judge_disagreeing_lands_as_middle(self):
        self._grade_everything({"1": "高", "2": "中"}, {"1": "低"})
        asrmt_run.step_quality(self.NAME)
        path = paths.stage_path(paths.ASR_QUALITY, self.NAME, ".srt")
        with open(path, encoding="utf-8") as handle:
            self.assertNotIn("品質：高", handle.read())

    def test_an_unjudged_episode_says_which_entry(self):
        with self.assertRaises(PipelineError) as caught:
            asrmt_run.step_quality(self.NAME)
        self.assertIn("條目 1", str(caught.exception))

    def test_the_offline_rebuild_matches_what_was_written(self):
        self._grade_everything({"1": "高", "2": "中"}, {"1": "高"})
        asrmt_run.step_quality(self.NAME)
        path = paths.stage_path(paths.ASR_QUALITY, self.NAME, ".srt")
        with open(path, encoding="utf-8") as handle:
            self.assertEqual(handle.read(),
                             asrmt_run.quality_body_of(self.NAME))


class TestNameGuardWiring(unittest.TestCase):
    def test_path_escaping_srt_name_dies_before_touching_anything(self):
        # 帶路徑成分的參數在入口就擋下，不是走到 inventory 查無此集
        # 才失敗；訊息要指名是路徑成分，毋是含含糊糊講格式不對
        with self.assertRaisesRegex(PipelineError, "帶路徑成分"):
            asrmt_run.main(["../../home/somebody/.sftp-pass"])

    def test_a_wrong_shaped_name_still_reports_the_format(self):
        with self.assertRaisesRegex(PipelineError, "格式"):
            asrmt_run.main(["2021_32_晚間_Amis_阿美"])
