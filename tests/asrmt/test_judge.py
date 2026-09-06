"""judge：族華對應品質ê判定——材料、批次、收件、快取、合成。

判定是問模型ê，所以三件代誌愛先講清楚：

**材料**。裁判看四項：族語 ASR 逝、本條ê華語字幕、族語逝ê機器譯文
（明講「參考、可能錯」），閣加前後各一條ê字幕。前後彼兩條是欲掠
「族語其實對著隔壁句」彼種偏移ê——無彼兩條，裁判干焦看會著「這兩逝
無仝」，看袂出「原來是徙一格」。

**收件**。一批一个請求檔、一个回覆檔，id 集合完全相等才收，標籤袂
合法嘛整批退。半收ê話，號碼一走精，判定就貼佇無仝ê條目頂懸，落尾
無人看會出來。這是視覺辨識彼爿佮 claude_mt 用過ê規矩。

**快取ê鍵是內容，毋是編號**。時間軸換版ê時條目編號會規排徙位——
試點 304 徙做 309——用編號做鍵，重投影了後判定全部對毋著位。鍵內底
連前後字幕嘛算：彼是裁判看著ê材料ê一部份，材料換去答案就可能無仝。
"""
import json
import os
import tempfile
import unittest

from scripts.asrmt import judge
from scripts.errors import PipelineError


def rows(count=3):
    out = []
    for i in range(count):
        out.append({"index": i + 1, "srt_start": i * 2.0,
                    "srt_end": i * 2.0 + 1.5,
                    "formosan": "f%d" % (i + 1),
                    "subtitle": "字幕%d" % (i + 1)})
    return out


def translate(text):
    return "譯:" + text


class TestSuspectTranslations(unittest.TestCase):
    """罐頭譯文愛標出來予裁判知影。

    ai-labs 信心低ê時陣袂講「我毋知」，伊會吐一段**罐頭句**——仝一段
    譯文逐字出現佇無仝ê族語輸入頂懸。量過規个 mt-cache：21% ê筆數
    ê譯文對應到超過一个輸入，重複上濟ê是族名由來ê故事、野菜湯ê
    故事，閣有「屬格標記」「女子名」這款辭典詞條（訓練語料摻著
    語言學詞彙表）。

    這會拖累判定：譯文是罐頭句ê條目，得著懸ê機會賰一半（11% 對
    23%）、得著低ê機會欲兩倍（34% 對 20%）。掠伊免用模型——「仝一
    段譯文對應到超過一个族語輸入」就是。標出來，裁判就知影彼條
    旁證莫採信。
    """

    def test_a_dictionary_gloss_is_canned_even_if_it_appears_once(self):
        """辭典詞條免重複就掠會著。

        重複比對掠ê是「仝一句出現幾若擺」，所以孤一擺ê幻覺走去。毋過
        有一類是認會出來ê：「屬格標記」「受格標記」「男子名」「年;歲」
        這款**語言學術語**——彼是訓練語料摻著詞彙表落來ê，袂使當做
        譯文。固定字串比對就好，免用模型。
        """
        for gloss in ("屬格標記", "受格標記", "男子名", "女子名",
                      "年;歲", "助詞"):
            self.assertTrue(judge.is_gloss(gloss), gloss)

    def test_a_real_translation_is_not_a_gloss(self):
        for text in ("大家好", "花蓮縣政府今天表示", "屬於部落的土地"):
            self.assertFalse(judge.is_gloss(text), text)

    def test_the_column_says_when_the_translation_is_canned(self):
        def suspect(text):
            return text == "譯:f2"
        items = judge.materials(rows(), translate, suspect=suspect)
        self.assertEqual(items[0]["suspect"], "")
        self.assertNotEqual(items[1]["suspect"], "")

    def test_without_a_detector_nothing_is_marked(self):
        for item in judge.materials(rows(), translate):
            self.assertEqual(item["suspect"], "")

    def test_marking_it_is_a_different_question(self):
        """材料變去就是無仝ê問題，愛閣問一擺——因為裁判看著ê物件
        無仝矣。"""
        cache = judge.QualityCache(tempfile.mkdtemp())
        plain = judge.materials(rows(), translate)[1]
        cache.put("sonnet", plain, "高")
        marked = dict(plain, suspect="罐頭句，莫採信")
        self.assertIsNone(cache.get("sonnet", marked))


class TestMaterials(unittest.TestCase):
    def test_each_item_carries_the_four_things_the_judge_sees(self):
        item = judge.materials(rows(), translate)[1]
        self.assertEqual(item["index"], 2)
        self.assertEqual(item["formosan"], "f2")
        self.assertEqual(item["subtitle"], "字幕2")
        self.assertEqual(item["translation"], "譯:f2")

    def test_the_neighbouring_subtitles_come_along(self):
        item = judge.materials(rows(), translate)[1]
        self.assertEqual(item["before"], "字幕1")
        self.assertEqual(item["after"], "字幕3")

    def test_the_first_and_last_entry_have_an_empty_neighbour(self):
        items = judge.materials(rows(), translate)
        self.assertEqual(items[0]["before"], "")
        self.assertEqual(items[-1]["after"], "")

    def test_an_empty_formosan_line_is_not_asked_about(self):
        """無語音ê條目無物件通判——問模型是白了錢。"""
        data = rows()
        data[1]["formosan"] = ""
        asked = []
        for item in judge.materials(data, translate):
            asked.append(item["index"])
        self.assertEqual(asked, [1, 3])

    def test_an_empty_subtitle_is_not_asked_about_either(self):
        data = rows()
        data[0]["subtitle"] = ""
        asked = []
        for item in judge.materials(data, translate):
            asked.append(item["index"])
        self.assertEqual(asked, [2, 3])

    def test_the_neighbours_are_the_real_ones_not_the_asked_ones(self):
        """跳過ê條目猶原是伊隔壁ê隔壁——若無，偏移就掠無。"""
        data = rows(4)
        data[1]["formosan"] = ""
        items = judge.materials(data, translate)
        self.assertEqual(items[1]["index"], 3)
        self.assertEqual(items[1]["before"], "字幕2")


class BatchFixture(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = tmp.name

    def _read(self, path):
        with open(path, encoding="utf-8") as handle:
            return handle.read()


class TestBatches(BatchFixture):
    def test_it_writes_numbered_files_of_a_fixed_size(self):
        items = judge.materials(rows(250), translate)
        paths = judge.write_batches(items, self.folder, "s", size=100)
        self.assertEqual(len(paths), 3)
        self.assertTrue(paths[0].endswith("s01.tsv"))
        self.assertEqual(len(self._read(paths[2]).splitlines()), 50)

    def test_every_row_is_id_then_the_material_columns(self):
        paths = judge.write_batches(judge.materials(rows(), translate),
                                    self.folder, "s")
        line = self._read(paths[0]).splitlines()[1]
        self.assertEqual(line.split("\t"),
                         ["2", "f2", "字幕2", "譯:f2", "", "字幕1", "字幕3"])

    def test_a_tab_in_the_text_does_not_break_the_columns(self):
        data = rows()
        data[0]["subtitle"] = "有\ttab"
        paths = judge.write_batches(judge.materials(data, translate),
                                    self.folder, "s")
        first = self._read(paths[0]).splitlines()[0]
        self.assertEqual(len(first.split("\t")), len(judge.COLUMNS) + 1)

    def test_no_items_writes_no_files(self):
        self.assertEqual(judge.write_batches([], self.folder, "s"), [])


class CacheFixture(BatchFixture):
    def setUp(self):
        super(CacheFixture, self).setUp()
        self.cache = judge.QualityCache(os.path.join(self.folder, "cache"))
        self.items = judge.materials(rows(), translate)


class TestIngest(CacheFixture):
    def _reply(self, text):
        path = os.path.join(self.folder, "s01.reply.tsv")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path

    def _request(self):
        return judge.write_batches(self.items, self.folder, "s")[0]

    def test_a_good_reply_lands_in_the_cache(self):
        got = judge.ingest_reply(self._request(),
                                 self._reply("1\t高\n2\t中\n3\t低\n"),
                                 self.cache, "sonnet", self.items)
        self.assertEqual(got, 3)
        self.assertEqual(self.cache.get("sonnet", self.items[0]), "高")

    def test_a_stranger_id_rejects_the_whole_batch(self):
        with self.assertRaises(PipelineError):
            judge.ingest_reply(self._request(),
                               self._reply("1\t高\n2\t中\n9\t低\n"),
                               self.cache, "sonnet", self.items)
        self.assertIsNone(self.cache.get("sonnet", self.items[0]))

    def test_a_missing_line_rejects_the_whole_batch(self):
        with self.assertRaises(PipelineError) as caught:
            judge.ingest_reply(self._request(),
                               self._reply("1\t高\n3\t低\n"),
                               self.cache, "sonnet", self.items)
        self.assertIn("2", str(caught.exception))

    def test_a_duplicate_id_rejects_the_whole_batch(self):
        with self.assertRaises(PipelineError):
            judge.ingest_reply(self._request(),
                               self._reply("1\t高\n1\t中\n2\t中\n3\t低\n"),
                               self.cache, "sonnet", self.items)

    def test_a_label_that_is_not_one_of_the_three_rejects_the_batch(self):
        """「還好」「不確定」這款自由發揮ê答案收落去就無法度統計，
        嘛表示裁判無照定義咧判。"""
        with self.assertRaises(PipelineError) as caught:
            judge.ingest_reply(self._request(),
                               self._reply("1\t高\n2\t還好\n3\t低\n"),
                               self.cache, "sonnet", self.items)
        self.assertIn("還好", str(caught.exception))
        self.assertIsNone(self.cache.get("sonnet", self.items[0]))


class TestCache(CacheFixture):
    def test_a_hit_needs_the_same_judge(self):
        self.cache.put("sonnet", self.items[0], "高")
        self.assertEqual(self.cache.get("sonnet", self.items[0]), "高")
        self.assertIsNone(self.cache.get("fable", self.items[0]))

    def test_changing_the_neighbouring_subtitle_is_a_new_question(self):
        self.cache.put("sonnet", self.items[1], "高")
        moved = dict(self.items[1], before="別條字幕")
        self.assertIsNone(self.cache.get("sonnet", moved))

    def test_the_entry_number_is_not_part_of_the_key(self):
        """重投影了後編號會規排徙位；用編號做鍵，判定就規排走精。"""
        self.cache.put("sonnet", self.items[0], "中")
        renumbered = dict(self.items[0], index=309)
        self.assertEqual(self.cache.get("sonnet", renumbered), "中")

    def test_it_is_read_back_from_disk_next_time(self):
        self.cache.put("sonnet", self.items[0], "高")
        again = judge.QualityCache(self.cache.folder)
        self.assertEqual(again.get("sonnet", self.items[0]), "高")

    def test_one_file_per_judge_one_record_per_line(self):
        self.cache.put("sonnet", self.items[0], "高")
        self.cache.put("fable", self.items[0], "中")
        self.assertEqual(sorted(os.listdir(self.cache.folder)),
                         ["fable.jsonl", "sonnet.jsonl"])
        path = os.path.join(self.cache.folder, "sonnet.jsonl")
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        self.assertEqual(len(text.splitlines()), 1)
        self.assertTrue(text.startswith('{"after"'))
        self.assertIn("字幕1", text)
        row = json.loads(text)
        self.assertEqual(row["prompt"], judge.PROMPT_VERSION)

    def test_a_cache_written_by_an_older_version_still_loads(self):
        """快取是 append-only ê，舊版寫ê逝永遠佇遐。

        欄位加一欄ê時，舊逝內底無彼个鍵——讀著就當場破，連新ê判定
        嘛提袂著。舊逝ê prompt 版本無仝，本來就袂命中，所以載入ê時
        當做空字串就好。
        """
        path = os.path.join(self.cache.folder, "sonnet.jsonl")
        old = {"judge": "sonnet", "prompt": "v1", "label": "高",
               "formosan": "f1", "subtitle": "字幕1",
               "translation": "譯:f1", "before": "", "after": "字幕2"}
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(old, ensure_ascii=False,
                                    sort_keys=True) + "\n")
        again = judge.QualityCache(self.cache.folder)
        self.assertIsNone(again.get("sonnet", self.items[0]))

    def test_a_new_prompt_version_invalidates_the_old_answers(self):
        """定義收較絚ê時，舊答案是照舊定義判ê，袂使閣算數。"""
        self.cache.put("sonnet", self.items[0], "高")
        stale = judge.QualityCache(self.cache.folder, prompt="沓沓仔")
        self.assertIsNone(stale.get("sonnet", self.items[0]))


class TestFinalLabel(unittest.TestCase):
    """高愛兩个裁判攏講高（使用者裁定 2026-09-04）。

    無人力做人工校準，所以「高」ê精度干焦有靠兩个獨立ê模型互相背書。
    第一个裁判講中抑是低ê，免閣問第二个——省錢，而且降級毋是欲擋ê
    彼款錯。
    """

    def test_both_say_high_so_it_is_high(self):
        self.assertEqual(judge.final_label("高", "高"), "高")

    def test_the_second_judge_disagreeing_drops_it_to_middle(self):
        self.assertEqual(judge.final_label("高", "中"), "中")
        self.assertEqual(judge.final_label("高", "低"), "中")

    def test_high_without_a_second_opinion_is_not_final(self):
        self.assertIsNone(judge.final_label("高", None))

    def test_middle_and_low_stand_on_the_first_judge_alone(self):
        self.assertEqual(judge.final_label("中", None), "中")
        self.assertEqual(judge.final_label("低", None), "低")


class TestVerdicts(CacheFixture):
    def _fill(self, first, second=None):
        for item, label in zip(self.items, first):
            self.cache.put("sonnet", item, label)
        if second:
            for item, label in zip(self.items, second):
                if label:
                    self.cache.put("fable", item, label)

    def test_it_maps_entry_numbers_to_final_labels(self):
        self._fill(["高", "中", "低"], ["高", None, None])
        got = judge.verdicts(rows(), self.cache, self.items)
        self.assertEqual(got, {1: "高", 2: "中", 3: "低"})

    def test_an_empty_line_is_low_without_anyone_being_asked(self):
        data = rows()
        data[1]["formosan"] = ""
        items = judge.materials(data, translate)
        for item in items:
            self.cache.put("sonnet", item, "中")
        got = judge.verdicts(data, self.cache, items)
        self.assertEqual(got[2], "低")

    def test_an_unjudged_entry_says_which_one(self):
        self._fill(["高", "中"], ["高", None])
        with self.assertRaises(PipelineError) as caught:
            judge.verdicts(rows(), self.cache, self.items)
        self.assertIn("條目 3", str(caught.exception))

    def test_a_high_still_waiting_on_the_second_judge_says_so(self):
        self._fill(["高", "中", "低"])
        with self.assertRaises(PipelineError) as caught:
            judge.verdicts(rows(), self.cache, self.items)
        self.assertIn("條目 1", str(caught.exception))


class TestPending(CacheFixture):
    def test_the_first_judge_is_asked_only_about_what_is_not_cached(self):
        self.cache.put("sonnet", self.items[0], "高")
        left = judge.pending(self.items, self.cache, "sonnet")
        indexes = []
        for item in left:
            indexes.append(item["index"])
        self.assertEqual(indexes, [2, 3])

    def test_the_second_judge_is_asked_only_about_the_highs(self):
        for item, label in zip(self.items, ["高", "中", "高"]):
            self.cache.put("sonnet", item, label)
        left = judge.pending(self.items, self.cache, "fable")
        indexes = []
        for item in left:
            indexes.append(item["index"])
        self.assertEqual(indexes, [1, 3])

    def test_a_high_the_second_judge_already_saw_is_not_asked_again(self):
        for item in self.items:
            self.cache.put("sonnet", item, "高")
        self.cache.put("fable", self.items[0], "高")
        left = judge.pending(self.items, self.cache, "fable")
        self.assertEqual(len(left), 2)


class TestPrompt(unittest.TestCase):
    """Prompt 是判定ê定義本身，愛佮 spec 逐字仝款。"""

    def setUp(self):
        self.text = judge.prompt_text()

    def test_it_carries_the_three_level_definitions(self):
        for phrase in ("高", "中", "低", "忠實濃縮", "增減事實",
                       "數字與專名一致", "不確定"):
            self.assertIn(phrase, self.text)

    def test_it_carries_what_earlier_rounds_learned(self):
        """判過ê經驗愛寫入去，無ê話逐擺ê標準攏無仝——判斷ê定義就
        佇這份檔案，別位寫ê裁判看袂著。"""
        for phrase in ("借詞", "罐頭句", "切點", "專題", "幻覺"):
            self.assertIn(phrase, self.text)

    def test_anchors_are_a_ticket_not_a_pass(self):
        """量過：干焦寫「兩類錨點互證」，裁判會湊到兩類就煞手。

        字幕ê數字予人改過、抑是後半句剁掉，伊照常予懸——因為伊揀ê
        彼兩類錨點拄好猶佇咧。所以錨點是入場券，愛閣有第二道關。
        """
        for phrase in ("必要條件", "整個比", "漏掉", "多出",
                       "兩個方向"):
            self.assertIn(phrase, self.text)

    def test_a_cut_off_subtitle_is_a_hard_stop(self):
        """探針量著ê：門檻放較冗ê時，漏網全部集中佇「字幕予人剖斷」
        彼一種（4/50）。彼種有明明白白ê表面特徵，寫做硬條件比用
        「愛兩類錨點」去間接擋較準——後者連好料嘛擋掉五分之四。"""
        for phrase in ("被切斷", "半個詞"):
            self.assertIn(phrase, self.text)

    def test_joining_up_with_a_neighbour_is_not_evidence(self):
        """新聞稿本底就是連紲ê，隔壁兩條接會起來是常態。

        實測著ê：kā「前後條接會起來」寫做切斷ê記號，規集逐條攏
        變做切斷，懸落做零。探針掠袂著這款——探針彼爿看起來猶
        原正常。真ê資料才掠會著。
        """
        self.assertIn("不要用「前後條接得起來」當切斷的證據", self.text)

    def test_it_points_at_the_glossary_file(self):
        """詞表算好矣就愛講予裁判知，無ê話伊照常家己推——彼就是
        欲省ê彼八擺重工。"""
        self.assertIn("glossary.tsv", self.text)
        self.assertIn("提議", self.text)

    def test_it_says_the_translation_may_be_wrong(self):
        self.assertIn("參考", self.text)
        self.assertIn("可能錯", self.text)

    def test_it_states_the_reply_format(self):
        self.assertIn("編號", self.text)
        self.assertIn("高|中|低", self.text)

    def test_the_version_constant_matches_the_file(self):
        self.assertIn(judge.PROMPT_VERSION, self.text)


if __name__ == "__main__":
    unittest.main()
