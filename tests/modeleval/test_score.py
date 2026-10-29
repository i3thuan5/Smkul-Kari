"""modeleval.score：ASR／MT 結果對 OCR 字幕組成計分用的資料。

指標本身在 test_metrics.py；這裡防的是「拿錯東西去比」。
"""
import unittest

from scripts.modeleval import score

SAPOLITA = (
    "1\n00:00:00,000 --> 00:00:30,000\n"
    "族語：ngaʼay ho kita\n華語：大家好\n\n"
    "2\n00:00:30,000 --> 00:01:00,000\n"
    "族語：o tilifi\n華語：電視\n")


def cue(index, start, end, formosan, han, label="純族語"):
    return {"srt_name": "a", "index": index, "start": start, "end": end,
            "formosan": formosan, "han": han, "label": label}


class TestSapolitaSRT(unittest.TestCase):
    def test_both_language_lines_are_split_out(self):
        """sapolita 一段回兩列（族語：…／華語：…），族語列才是 ASR；
        華語列是伊家己接的翻譯，若無分開，華語會算入族語的 WER。"""
        got = score.parse_sapolita(SAPOLITA)
        self.assertEqual(got[0], (0.0, 30.0, "ngaʼay ho kita", "大家好"))
        self.assertEqual(got[1][2], "o tilifi")


class TestOverlap(unittest.TestCase):
    def test_segment_kept_only_when_mostly_under_formosan_cues(self):
        """受訪者講華語的時段無族語字幕，sapolita 照樣硬聽成阿美語；
        彼款段若算入去，插入錯誤會灌爆 WER。whisper 一段 20–30 秒，
        過半落佇族語字幕內底才算。"""
        segments = [(0.0, 30.0, "x", ""), (30.0, 60.0, "y", "")]
        cues = [cue(1, 0.0, 20.0, "a", "甲"),
                cue(2, 30.0, 35.0, "b", "乙"),
                cue(3, 35.0, 60.0, "", "丙", label="華語")]
        kept = score.segments_under_formosan(segments, cues)
        self.assertEqual(kept, [(0.0, 30.0, "x", "")])

    def test_overlapping_cues_are_not_double_counted(self):
        segments = [(0.0, 10.0, "x", "")]
        cues = [cue(1, 0.0, 4.0, "a", "甲"), cue(2, 2.0, 4.0, "b", "乙")]
        self.assertEqual(score.segments_under_formosan(segments, cues), [])


class TestChunks(unittest.TestCase):
    def test_never_cut_through_a_cue(self):
        """整集接成一條算 CER 是 3 萬字 × 3 萬字的編輯距離，純 Python
        跑不動，所以要切塊；但 sapolita 在開會了切得很碎（068 集 1,034
        段、中位數 1.5 秒），照中點把字幕歸段，跨段字幕整條歸到一邊，
        另一邊的辨識結果全變插入——068 集 WER 因此量成 118%。切點不可以
        落在字幕中間（28–32 秒的字幕蓋住 30 秒那個段界）。"""
        segments = [(0.0, 30.0, "a b", ""), (30.0, 60.0, "c", "")]
        cues = [cue(1, 1.0, 5.0, "a", "甲"), cue(2, 28.0, 32.0, "b", "乙"),
                cue(3, 40.0, 45.0, "c", "丙")]
        got = score.asr_chunks(cues, segments, "全集", min_block=0.0)
        self.assertEqual(got, [("a b c", "a b c")])

    def test_short_segments_are_merged_into_blocks(self):
        """三秒一段、每個段界都乾淨，也要併到 min_block 秒才切，
        時間差一點點的字幕才不會歸錯塊。"""
        segments = []
        cues = []
        for i in range(20):
            segments.append((3.0 * i, 3.0 * i + 3.0, "w%d" % i, ""))
            cues.append(cue(i, 3.0 * i, 3.0 * i + 3.0, "w%d" % i, "字"))
        got = score.asr_chunks(cues, segments, "全集", min_block=30.0)
        self.assertEqual(len(got), 2)
        for ref, hyp in got:
            self.assertEqual(ref, hyp)

    def test_forced_cut_when_cues_never_leave_a_clean_gap(self):
        """字幕一條接一條、條條跨過段界時，最長 max_block 秒也要切，
        否則整集變一塊又跑不動。"""
        segments = []
        cues = []
        for i in range(10):
            segments.append((10.0 * i, 10.0 * i + 10.0, "s%d" % i, ""))
            cues.append(cue(i, 10.0 * i + 5.0, 10.0 * i + 15.0, "c", "字"))
        got = score.asr_chunks(cues, segments, "全集", min_block=0.0,
                               max_block=40.0)
        self.assertGreater(len(got), 1)

    def test_cue_in_a_silent_gap_counts_as_deleted(self):
        """sapolita 沒出段的地方（它判成沒講話）若有族語字幕，那是
        漏聽，要算刪除，不可因為沒有段可以歸就丟掉。"""
        segments = [(0.0, 10.0, "a", "")]
        cues = [cue(1, 1.0, 5.0, "a", "甲"), cue(2, 20.0, 25.0, "z", "乙")]
        got = score.asr_chunks(cues, segments, "全集")
        self.assertEqual(got, [("a z", "a")])

    def test_formosan_scope_drops_chinese_segments_and_their_cues(self):
        """族語字幕時段：華語訪談那段（族語字幕不到一半）整段不算，
        落在那段的零星族語字幕也一起拿掉，不可只拿掉辨識結果、
        留下參考答案變成全刪除。"""
        segments = [(0.0, 10.0, "a", ""), (10.0, 40.0, "zz yy", "")]
        cues = [cue(1, 0.0, 9.0, "a", "甲"), cue(2, 12.0, 14.0, "q", "乙"),
                cue(3, 14.0, 40.0, "", "丙", label="華語")]
        got = score.asr_chunks(cues, segments, "族語字幕時段", min_block=0.0)
        self.assertEqual(got, [("a", "a")])


class TestUncertainRows(unittest.TestCase):
    def test_uncertain_formosan_row_inside_a_kept_segment_stays(self):
        """「無法確定」的族語列（離線語言判定拿不準）若從參考答案拿掉，
        它底下的 sapolita 段因為鄰近純族語字幕而留著，辨識結果就全變
        假的插入（族語字幕時段 87 個詞、082 集 65 個）。段留著的話，
        有族語字的列都要進參考答案。"""
        segments = [(0.0, 30.0, "a b c", "")]
        cues = [cue(1, 0.0, 20.0, "a b", "甲"),
                cue(2, 20.0, 30.0, "c", "乙", label="無法確定")]
        got = score.asr_chunks(cues, segments, "族語字幕時段")
        self.assertEqual(got, [("a b c", "a b c")])


class TestCascade(unittest.TestCase):
    def test_cascade_and_mt_are_scored_on_the_same_blocks(self):
        """sapolita 自己接的華語列整集當一篇算 BLEU 是 20.82，逐句的
        MT 族→華是 13.00，看起來串接比較好；但整篇算 n-gram 不看順序，
        拿下一集的辨識結果去比都有 12.23。兩邊要在同一個塊上比：
        塊內的 OCR 華語列、sapolita 華語列、OCR 族語列的 MT 譯文。"""
        segments = [(0.0, 30.0, "a", "甲乙"), (30.0, 60.0, "b", "丙")]
        cues = [cue(1, 0.0, 30.0, "a", "甲乙"),
                cue(2, 30.0, 60.0, "b", "丙丁")]
        translations = {"a": "甲", "b": "丙丁"}
        got = score.cascade_blocks(cues, segments, translations,
                                   min_block=0.0)
        self.assertEqual(got, [("甲乙", "甲乙", "甲"), ("丙丁", "丙", "丙丁")])

    def test_block_without_all_translations_has_no_mt_side(self):
        """翻譯還沒跑完的塊，MT 那邊給 None，不可當成空字串算 0 分。"""
        segments = [(0.0, 30.0, "a", "甲")]
        cues = [cue(1, 0.0, 30.0, "a", "甲")]
        got = score.cascade_blocks(cues, segments, {}, min_block=0.0)
        self.assertEqual(got, [("甲", "甲", None)])


class TestCERTable(unittest.TestCase):
    def episode(self, name, norm, errors, ref_len, scope="族語字幕時段"):
        return {"成果檔名": name, "範圍": scope, "正規化": norm,
                "語別碼": "ami-x-pswl", "語別碼來源": "保底",
                "字元錯誤數": errors, "參考字元數": ref_len}

    def test_both_mark_treatments_side_by_side_and_total_from_counts(self):
        """使用者要逐集 CER、考慮與不考慮 ^ : 兩欄並排（2026-10-28）。
        合計要用錯誤數／參考字元數加總再除，不可把各集 CER 平均——
        082 只有 1.5 萬字、105 有 2.9 萬字，平均會讓短的集佔太重。"""
        strict, marks = score.FORMOSAN_NORMS[0][0], score.FORMOSAN_NORMS[1][0]
        rows = [self.episode("a", strict, 10, 100),
                self.episode("a", marks, 9, 98),
                self.episode("b", strict, 30, 300),
                self.episode("b", marks, 20, 290)]
        got = score.cer_table(rows)
        self.assertEqual(len(got), 3)
        self.assertEqual(got[0]["成果檔名"], "a")
        self.assertEqual(got[0]["CER（考慮 ^ :）"], "10.00")
        self.assertEqual(got[0]["CER（不考慮 ^ :）"], "9.18")
        self.assertEqual(got[2]["成果檔名"], "合計")
        self.assertEqual(got[2]["CER（考慮 ^ :）"], "10.00")
        self.assertEqual(got[2]["CER（不考慮 ^ :）"], "7.47")


class TestFoldOU(unittest.TestCase):
    def test_o_and_u_compare_equal_only_in_the_folded_variant(self):
        """阿美語 o／u 不分音位，南勢寫 u、其他語言別寫 o。sapolita 在
        海岸／秀姑巒的集也有約 40% 寫成 u（OCR 字幕幾乎全寫 o），替換錯誤
        前四名是 no→nu、ko→ku、to→tu、o→u（2026-10-28 量）。合併後的
        數字只當敏感度分析，主要數字照字幕原本的寫法比。"""
        self.assertEqual(score.fold_ou("nu kuku"), "no koko")
        self.assertEqual(score.FORMOSAN_NORMS[1][1]("Ko Sowal^"), "ko sowal")
        folded = score.FORMOSAN_NORMS[3][1]
        self.assertEqual(folded("ku suwal"), folded("ko sowal^"))


class TestMTRows(unittest.TestCase):
    def test_untranslated_rows_are_counted_not_silently_dropped(self):
        """翻譯批次猶未跑完就先算分的時陣，缺翻譯的句愛報出來，
        毋通當做全部攏算著。"""
        rows = [cue(1, 0, 1, "cecay", "一"), cue(2, 1, 2, "tosa", "二"),
                cue(3, 2, 3, "", "三", label="華語")]
        rows[0]["mt_code"] = rows[1]["mt_code"] = "ami_Coas"
        rows[2]["mt_code"] = "ami_Coas"
        cache = {("ailabs", "f2z", "ami_Coas", "cecay"): "一個"}
        got, missing = score.mt_pairs(rows, cache, "f2z")
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["hyp"], "一個")
        self.assertEqual(got[0]["ref"], "一")
        self.assertEqual(missing, {"純族語": 1})

    def test_missing_count_is_per_label(self):
        """摘要每個範圍的「另有 N 句猶未翻譯」要照該範圍的語言標記
        各自算；用整個方向的缺數，族語夾雜華語那列的缺數會灌十倍。"""
        rows = [cue(1, 0, 1, "cecay", "一"),
                cue(2, 1, 2, "tosa", "二", label="族語夾雜華語"),
                cue(3, 2, 3, "tolo", "三", label="族語夾雜華語")]
        for item in rows:
            item["mt_code"] = "ami_Coas"
        _got, missing = score.mt_pairs(rows, {}, "f2z")
        self.assertEqual(missing, {"純族語": 1, "族語夾雜華語": 2})
        self.assertEqual(score.missing_in(missing, ("族語夾雜華語",)), 2)

    def test_z2f_reference_is_the_formosan_row(self):
        rows = [cue(1, 0, 1, "cecay", "一")]
        rows[0]["mt_code"] = "ami_Coas"
        cache = {("ailabs", "z2f", "ami_Coas", "一"): "ceca"}
        got, _ = score.mt_pairs(rows, cache, "z2f")
        self.assertEqual((got[0]["src"], got[0]["hyp"], got[0]["ref"]),
                         ("一", "ceca", "cecay"))


class TestBootstrap(unittest.TestCase):
    def test_same_seed_same_interval(self):
        """報告上的信賴區間重跑愛仝款，種子固定。"""
        stats = []
        for value in range(50):
            stats.append([value % 7, 1])

        def total(sample):
            top = 0
            bottom = 0
            for a, b in sample:
                top += a
                bottom += b
            return 100.0 * top / bottom

        first = score.bootstrap(stats, total, rounds=200, seed=1)
        second = score.bootstrap(stats, total, rounds=200, seed=1)
        self.assertEqual(first, second)
        self.assertLessEqual(first[0], total(stats))
        self.assertGreaterEqual(first[1], total(stats))


if __name__ == "__main__":
    unittest.main()
