"""modeleval.metrics：WER、CER、BLEU、chrF++ 與正規化。

sacrebleu、jiwer 沒有裝（採購規定：不另裝套件），metrics.py 照
sacrebleu v2.4.3 與 jiwer v3.0.4 的原始碼重寫。這裡的 GOLDEN 是兩個
各自獨立寫的版本交叉比對後定下來的：17 筆是手算（算式見各列說明），
47 筆是邊界例子；每列最後一欄寫它防的是哪一種算錯。浮點數容許 1e-9。

全部離線，不讀檔。
"""
import math
import unittest

from scripts.modeleval import metrics

TOLERANCE = 1e-9

GOLDEN = (
    ('wer',
     (['a b c'], ['a x c d']),
     {'dele': 0, 'errors': 2, 'ins': 1, 'ref_len': 3,
      'score': 0.6666666666666666, 'sub': 1},
     '一個替換加一個插入，插入也要算進分子：2/3'),
    ('cer',
     (['ab c'], ['ab  d']),
     {'dele': 0, 'errors': 2, 'ins': 1, 'ref_len': 4, 'score': 0.5,
      'sub': 1},
     '中間的空白照算字元，兩個空白不合併：2/4'),
    ('cer',
     ([' ab'], ['ab ']),
     {'dele': 0, 'errors': 0, 'ins': 0, 'ref_len': 2, 'score': 0.0,
      'sub': 0},
     '首尾空白要先 strip（jiwer cer_default 的 '
     'Strip）；直接 list(s) 會把 " ab" 對 "ab '
     '" 算成 2/3，正確是 0/2'),
    ('bleu_stats',
     ('the cat sat on the mat.', 'the cat is on the mat.', '13a'),
     [7, 7, 6, 7, 4, 6, 2, 5, 1, 4],
     '13a 把句尾句點切成獨立 token；統計交錯排成 [hyp, '
     'ref, m1, t1, ...]'),
    ('corpus_bleu',
     (['the cat sat on the mat.'], ['the cat is on the mat.'], '13a'),
     {'bp': 1.0,
      'precisions': [85.71428571428571, 66.66666666666667, 40.0, 25.0],
      'ref_len': 7, 'score': 48.892302243490086, 'sys_len': 7},
     '13a 整句 BLEU 手算 48.8923'),
    ('bleu_stats',
     ('我們是阿美族。', '我們都是阿美族人。', 'zh'),
     [7, 9, 7, 7, 4, 6, 2, 5, 1, 4],
     'zh 斷詞一個漢字一個 token，全形句點 。 也切開'),
    ('corpus_bleu',
     (['我們是阿美族。'], ['我們都是阿美族人。'], 'zh'),
     {'bp': 0.7514772930752859,
      'precisions': [100.0, 66.66666666666667, 40.0, 25.0], 'ref_len': 9,
      'score': 38.185022210613596, 'sys_len': 7},
     'hyp 比 ref 短要乘 brevity penalty '
     'exp(1-9/7)，漏乘會高估成 50.8'),
    ('corpus_bleu',
     (['a b c d'], ['a b e d'], '13a'),
     {'bp': 1.0, 'precisions': [75.0, 33.333333333333336, 25.0, 25.0],
      'ref_len': 4, 'score': 35.35533905932737, 'sys_len': 4},
     '連續沒命中的階平滑分母逐階加倍（1/2、1/4），每階都當 1/2 '
     '會算錯：25√2'),
    ('corpus_bleu',
     (['a b c'], ['a b c'], '13a'),
     {'bp': 1.0, 'precisions': [100.0, 100.0, 100.0, 0.0], 'ref_len': 3,
      'score': 0.0, 'sys_len': 3},
     '3 個詞的句子跟自己比是 0：沒有 4-gram 不可以拿 '
     'effective order 救'),
    ('chrf_stats',
     ('ab cd', 'ab ce'),
     [4, 4, 3, 3, 3, 2, 2, 2, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 2, 2, 1, 1,
      1, 0],
     'chrF 統計排法：每階 [hyp, ref, match]，字元 '
     '1–6 階再詞 1–2 階'),
    ('corpus_chrf',
     (['ab cd'], ['ab ce']),
     {'score': 40.27777777777778},
     'chrF++ 手算 29/72 → 40.2778'),
    ('chrf_stats',
     ('(hi) there.', 'hi there'),
     [10, 7, 7, 9, 6, 5, 8, 5, 3, 7, 4, 2, 6, 3, 1, 5, 2, 0, 4, 2, 1,
      3, 1, 0],
     '詞 n-gram 前每個詞只拆一個首或尾標點：(hi) 拆成 '
     '(hi 和 )'),
    ('corpus_chrf',
     (['(hi) there.'], ['hi there']),
     {'score': 41.92967108983681},
     'chrF++ 標點拆分手算 41.9297'),
    ('chrf_stats',
     ('ab', 'abcdefg'),
     [2, 7, 2, 1, 6, 1, 0, 5, 0, 0, 4, 0, 0, 3, 0, 0, 2, 0, 1, 1, 0, 0,
      0, 0],
     'hyp 比 ref 短，高階的 hyp n-gram 數是 0'),
    ('corpus_chrf',
     (['ab'], ['abcdefg']),
     {'score': 17.84037558685446},
     'hyp 沒有 n-gram 的階不平均進去，當 0 平均會低估：'
     '17.8404'),
    ('chrf_stats',
     ('abcdefgh', 'abc'),
     [8, 3, 3, 7, 2, 2, 6, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 0, 0,
      0, 0],
     'ref 沒有該階 n-gram 時 hyp 計數記 '
     '0（sacrebleu 的寫法），照實數會錯'),
    ('corpus_chrf',
     (['abcdefgh'], ['abc']),
     {'score': 49.17452830188679},
     'ref 為空的階 hyp 記 0 之後的分數 49.1745'),
    ('normalize_formosan',
     ("Nga'ay ho, kapah^ ʼamis to’as: 阿美 mipaliw.", 'strict'),
     "nga'ay ho kapah^ 'amis to'as: mipaliw",
     'sapolita／翻譯服務用 ʼ（U+02BC）、OCR 用 '
     "ASCII '，不統一每個喉塞音詞都算錯；族語列夾的漢字、"
     '逗號句點拿掉，^ : 留著'),
    ('normalize_formosan',
     ("Nga'ay ho, kapah^ ʼamis to’as: 阿美 mipaliw.", 'letters'),
     'ngaay ho kapah amis toas mipaliw',
     "letters 模式 ' ^ : 全刪"),
    ('normalize_formosan',
     ("pa-ka-'orip", 'strict'),
     "pa ka 'orip",
     "連字號當空白：OCR 寫 pa-ka-'orip 一個詞，"
     '辨識器分開寫是三個詞'),
    ('normalize_formosan',
     ("' ^ : 「」 ...", 'strict'),
     '',
     "只剩 ' ^ : 的 token 要丟掉，不然殘留的 ^ "
     '變成一個詞算插入；「」... 也拿掉'),
    ('normalize_formosan',
     ("O Fa:loco' no MAKO‘ira’ `ka´ ′", 'strict'),
     "o fa:loco' no mako'ira' 'ka'",
     'U+2018 U+2019 U+0060 U+00B4 '
     "U+2032 都換成 '；OCR 句首大寫要轉小寫"),
    ('normalize_formosan',
     ('é abc中def', 'strict'),
     'é abc def',
     'e＋組合尖音不 NFC 會跟 é 算不同字；'
     '夾在兩詞中間的漢字換成空白——直接刪會把 kako施ko 黏成 kakoko'),
    ('normalize_formosan',
     ('Ａmis１２３\tko\nna', 'letters'),
     'ａmis１２３ ko na',
     '族語用 NFC 不是 NFKC：全形字母數字保留只轉小寫；tab、'
     '換行變空白'),
    ('normalize_zh',
     ('我們，是 阿美族 ！ ＡＢＣ\u3000１２３',),
     '我們是阿美族abc123',
     '翻譯輸出用全形標點、字幕用空白斷句：NFKC 摺全形，空白標點都刪'),
    ('normalize_zh',
     ('「你好」…—“ok”',),
     '你好ok',
     '「」…—“” 這類 P* 都刪，不然標點也算字'),
    ('normalize_zh',
     ('$100 + 5%',),
     '1005',
     '$ + % 這類 S* 也刪'),
    ('wer',
     (['a b c'], ['']),
     {'dele': 3, 'errors': 3, 'ins': 0, 'ref_len': 3, 'score': 1.0,
      'sub': 0},
     '空的 hypothesis 全部算刪除，不可以除以零'),
    ('wer',
     (['a b', 'c d e'], ['a b', 'c e']),
     {'dele': 1, 'errors': 1, 'ins': 0, 'ref_len': 5, 'score': 0.2,
      'sub': 0},
     '語料 WER 是總錯誤÷總參考詞（1/5），不是每句 WER '
     '平均（1/6）'),
    ('wer',
     (['a b'], ['b a']),
     {'dele': 0, 'errors': 2, 'ins': 0, 'ref_len': 2, 'score': 1.0,
      'sub': 2},
     'a b 對 b a：最少 2 步時回報兩個替換，不是刪除加插入'),
    ('wer',
     (['a'], ['b c']),
     {'dele': 0, 'errors': 2, 'ins': 1, 'ref_len': 1, 'score': 2.0,
      'sub': 1},
     'a 對 b c：一個替換加一個插入，不是刪除加兩個插入'),
    ('wer',
     (['a  b\t'], [' a b']),
     {'dele': 0, 'errors': 0, 'ins': 0, 'ref_len': 2, 'score': 0.0,
      'sub': 0},
     'str.split()：多個空白、tab 不會變成空 token'),
    ('cer',
     (['我們是阿美族'], ['我們試阿美']),
     {'dele': 1, 'errors': 2, 'ins': 0, 'ref_len': 6,
      'score': 0.3333333333333333, 'sub': 1},
     '華語 CER：1 替換＋1 刪除，分母是參考 6 字'),
    ('cer',
     (['abc'], ['']),
     {'dele': 3, 'errors': 3, 'ins': 0, 'ref_len': 3, 'score': 1.0,
      'sub': 0},
     'CER 空的 hypothesis 全部算刪除，不可以除以零'),
    ('cer',
     (['a  b'], ['a b']),
     {'dele': 1, 'errors': 1, 'ins': 0, 'ref_len': 4, 'score': 0.25,
      'sub': 0},
     'jiwer 的 CER 不合併中間的兩個空白：1 刪除／4'),
    ('bleu_stats',
     ("&quot;Nga'ay ho&quot; &amp; 1,000.5", '"Nga\'ay ho" & 1,000.5',
      '13a'),
     [6, 6, 6, 6, 5, 5, 4, 4, 3, 3],
     '13a 只在有 & 時解 &quot; &amp;；撇號留在詞裡；'
     '1,000.5 不切'),
    ('bleu_stats',
     ("&quot;Nga'ay ho&quot; &amp; 1,000.5", '"Nga\'ay ho" & 1,000.5',
      'zh'),
     [12, 6, 4, 12, 1, 11, 0, 10, 0, 9],
     'zh 斷詞不解實體：& quot ; 各自成 token'),
    ('bleu_stats',
     ('a <skipped> b', 'a b', '13a'),
     [2, 2, 2, 2, 1, 1, 0, 0, 0, 0],
     '13a 刪掉 <skipped>'),
    ('bleu_stats',
     ('a <skipped> b', 'a b', 'zh'),
     [5, 2, 2, 5, 0, 4, 0, 3, 0, 2],
     'zh 不刪 <skipped>，切成 < skipped >'),
    ('bleu_stats',
     ('1,000.5.', '1,000.5 .', '13a'),
     [2, 2, 2, 2, 1, 1, 0, 0, 0, 0],
     '13a 前後補空白，所以數字後面的句尾句點會切開'),
    ('bleu_stats',
     ('1,000.5.', '1,000.5 .', 'zh'),
     [1, 2, 0, 1, 0, 0, 0, 0, 0, 0],
     'zh 沒補空白，數字後面的句尾句點黏著'),
    ('bleu_stats',
     ('line-\nbreak', 'linebreak', '13a'),
     [1, 1, 1, 1, 0, 0, 0, 0, 0, 0],
     '13a 把 -換行 接起來'),
    ('bleu_stats',
     ('“ok”', 'ok', 'zh'),
     [3, 1, 1, 3, 0, 2, 0, 1, 0, 0],
     'zh 範圍表的怪處：u"\\u20000" 字面值讓 '
     'U+2001–2A6D 算中文，彎引號被切開——照抄 '
     'sacrebleu，不要「修正」'),
    ('bleu_stats',
     ('“ok”', 'ok', '13a'),
     [1, 1, 0, 1, 0, 0, 0, 0, 0, 0],
     '13a 不切彎引號'),
    ('bleu_stats',
     ('𠀀𠀁', '𠀀𠀁', 'zh'),
     [1, 1, 1, 1, 0, 0, 0, 0, 0, 0],
     'zh 範圍表的怪處：真正的 Ext-B 漢字反而不切'),
    ('bleu_stats',
     ('', 'a b', '13a'),
     [0, 2, 0, 0, 0, 0, 0, 0, 0, 0],
     '空的 hypothesis 只貢獻 ref_len'),
    ('bleu_stats',
     ('price 3-4 is 1.5, ok.', 'price 3-4 is 1.5, ok.', '13a'),
     [9, 9, 9, 9, 8, 8, 7, 7, 6, 6],
     '13a：數字-連字號切開、1.5 不切、空白前的逗號句點切開'),
    ('bleu_stats',
     ("wasn't well-known", "wasn't well-known", '13a'),
     [2, 2, 2, 2, 1, 1, 0, 0, 0, 0],
     "13a 的 regex 不含 ' 和 -：族語喉塞音 ' "
     '不會把詞切開'),
    ('bleu_stats',
     ('我們，是阿美族 。 ', '我們,是阿美族。', 'zh'),
     [8, 8, 7, 8, 5, 7, 3, 6, 2, 5],
     'zh：全形逗號 U+FF0C 在 FF00–FFEF 範圍內被切開；'
     '句尾先 rstrip'),
    ('bleu_from_stats',
     ([5, 6, 0, 5, 0, 4, 0, 3, 0, 2],),
     {'bp': 0.8187307530779819, 'precisions': [0.0, 0.0, 0.0, 0.0],
      'ref_len': 6, 'score': 0.0, 'sys_len': 5},
     '完全沒命中：分數 0、precision 全 0，bp 照算'),
    ('bleu_from_stats',
     ([0, 3, 0, 0, 0, 0, 0, 0, 0, 0],),
     {'bp': 0.0, 'precisions': [0.0, 0.0, 0.0, 0.0], 'ref_len': 3,
      'score': 0.0, 'sys_len': 0},
     'hyp 長度 0：bp 是 0.0，不可以除以零'),
    ('bleu_from_stats',
     ([11, 11, 9, 11, 5, 9, 2, 7, 1, 5],),
     {'bp': 1.0,
      'precisions': [81.81818181818181, 55.55555555555556,
                     28.571428571428573, 20.0],
      'ref_len': 11, 'score': 40.145310162592594, 'sys_len': 11},
     'bootstrap 走的路：兩句統計相加再算，不是兩句分數平均'),
    ('corpus_bleu',
     (['ko pangcah a tamdaw'], ['ko pangcah a tamdaw'], '13a'),
     {'bp': 1.0, 'precisions': [100.0, 100.0, 100.0, 100.0],
      'ref_len': 4, 'score': 100.00000000000004, 'sys_len': 4},
     '4 個詞以上完全相同：100'),
    ('corpus_bleu',
     (['the cat sat on the mat.', 'a b c d'],
      ['the cat is on the mat.', 'a b e d'], '13a'),
     {'bp': 1.0,
      'precisions': [81.81818181818181, 55.55555555555556,
                     28.571428571428573, 20.0],
      'ref_len': 11, 'score': 40.145310162592594, 'sys_len': 11},
     '語料 BLEU 是各句統計相加（= 前面兩筆手算句子的統計和）'),
    ('corpus_bleu',
     (['', 'a b c d e'], ['x y', 'a b c d e'], '13a'),
     {'bp': 0.6703200460356393,
      'precisions': [100.0, 100.0, 100.0, 100.0], 'ref_len': 7,
      'score': 67.03200460356396, 'sys_len': 5},
     '空的 hyp 句子只貢獻 ref_len，拉低 bp'),
    ('corpus_chrf',
     (["Nga'ay ho kapah"], ["Nga'ay ho kapah"]),
     {'score': 100.0},
     '完全相同：100'),
    ('corpus_chrf',
     (['abc'], ['']),
     {'score': 0.0},
     'ref 空：每階 ref 都是 0 → 分數 0，不可以除以零'),
    ('corpus_chrf',
     ([''], ['abc']),
     {'score': 0.0},
     'hyp 空：分數 0，不可以除以零'),
    ('corpus_chrf',
     (['a b c'], ['abc'], 0),
     {'score': 100.0},
     'chrF（word_order 0）字元 n-gram 不看空白：'
     'a b c 對 abc 是 100'),
    ('chrf_stats',
     ('a b c', 'abc', 6, 0),
     [3, 3, 3, 2, 2, 2, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0],
     '只算字元階：3×6 個數，空白先拿掉'),
    ('chrf_from_stats',
     ([0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
       0, 0, 0],),
     {'score': 0.0},
     '統計全 0：分數 0，不可以除以零'),
    ('corpus_chrf',
     (['我們是阿美族。'], ['我們都是阿美族人。']),
     {'score': 26.03479324755306},
     '中文沒有空白，chrF++ 的詞 n-gram 退化成整句一個詞：'
     '26.0348'),
    ('corpus_chrf',
     (['ab cd', '(hi) there.'], ['ab ce', 'hi there']),
     {'score': 40.21473063123886},
     '語料 chrF 先把各句統計相加（前面兩筆手算）才算 F 分數'),
    ('chrf_stats',
     ("'a' b,", 'a b'),
     [5, 2, 2, 4, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 4, 2, 1, 3,
      1, 0],
     "_remove_punctuation 每個詞只拆一個字元：'a' "
     "→ 'a 和 '；b, → b 和 ,"),
)


def assert_close(test, got, want, where):
    """dict／list 逐項比；浮點數容許 TOLERANCE，整數、字串要完全相同。"""
    if isinstance(want, dict):
        test.assertIsInstance(got, dict, where)
        for key in want:
            test.assertIn(key, got, where)
            assert_close(test, got[key], want[key], "%s[%r]" % (where, key))
        return
    if isinstance(want, (list, tuple)):
        test.assertEqual(len(got), len(want), where)
        for k in range(len(want)):
            assert_close(test, got[k], want[k], "%s[%d]" % (where, k))
        return
    if isinstance(want, float):
        test.assertAlmostEqual(got, want, delta=TOLERANCE, msg=where)
        return
    test.assertEqual(got, want, where)


def run_golden(test, functions):
    count = 0
    for function, args, want, note in GOLDEN:
        if function not in functions:
            continue
        count += 1
        with test.subTest(function=function, note=note):
            got = getattr(metrics, function)(*args)
            assert_close(test, got, want, "%s %s" % (function, note))
    test.assertGreater(count, 0)


def edit_distance(ref, hyp):
    """測試自己的 Levenshtein，只算距離，不回溯。"""
    prev = list(range(len(hyp) + 1))
    for i in range(1, len(ref) + 1):
        cur = [i] + [0] * len(hyp)
        for j in range(1, len(hyp) + 1):
            cost = 0 if ref[i - 1] == hyp[j - 1] else 1
            cur[j] = min(prev[j - 1] + cost, prev[j] + 1, cur[j - 1] + 1)
        prev = cur
    return prev[len(hyp)]


class TestGolden(unittest.TestCase):
    def test_normalization_vectors(self):
        """正規化：撇號長相不同（U+02BC、U+2019…）、族語列夾漢字、
        全形標點、NFC／NFKC 用錯，任何一個沒處理，同一個詞就被當成
        兩個不同的詞。"""
        run_golden(self, ("normalize_formosan", "normalize_zh"))

    def test_wer_cer_vectors(self):
        """WER／CER：語料層級要總錯誤÷總參考長度，不是逐句平均；
        CER 首尾空白要 strip、中間空白照算；空 hypothesis 不可以
        除以零。"""
        run_golden(self, ("wer", "cer"))

    def test_bleu_vectors(self):
        """BLEU：13a 與 zh 兩種斷詞各有怪處（實體解碼、<skipped>、
        範圍表），exp 平滑分母逐階加倍，hyp 長度 0 時 bp 是 0——
        任何一處跟 sacrebleu 不同，分數就對不上別人報的數字。"""
        run_golden(self, ("bleu_stats", "bleu_from_stats", "corpus_bleu"))

    def test_chrf_vectors(self):
        """chrF++：ref 沒有該階時 hyp 計數記 0、只平均兩邊都有的階、
        詞 n-gram 前每個詞只拆一個標點——照直覺寫都會跟 sacrebleu
        差幾分。"""
        run_golden(self, ("chrf_stats", "chrf_from_stats", "corpus_chrf"))


class TestFormosanNormalization(unittest.TestCase):
    def test_modifier_apostrophe_from_services_matches_ocr_ascii(self):
        """sapolita 和翻譯服務輸出用 ʼ（U+02BC）當喉塞音、OCR 用
        ASCII '，不統一的話每個有喉塞音的詞都算錯。"""
        ref = metrics.normalize_formosan("Nga'ay ho, kapah!", "strict")
        hyp = metrics.normalize_formosan("ngaʼay ho kapah", "strict")
        self.assertEqual(ref, hyp)
        self.assertEqual(metrics.wer([ref], [hyp])["errors"], 0)

    def test_marks_mode_drops_length_marks_but_keeps_glottal(self):
        """字幕與 sapolita 標 ^ : 很不一致（8 集字幕 ^ 588、: 193 個，
        sapolita 只有 ⌃ 63、: 15 個），marks 模式拿掉再比；但 ' 兩邊
        都寫（sapolita 寫 ʼ），跟 ^ : 混在 letters 模式一起刪會把 ' 的
        錯也蓋掉。"""
        self.assertEqual(
            metrics.normalize_formosan("Po:long nga'ay ho^ ^", "marks"),
            "polong nga'ay ho")

    def test_chinese_between_words_does_not_glue_them(self):
        """OCR 族語列有時夾漢字（「kako施ko」），直接刪掉兩個詞會黏成
        一個，參考答案就少一個詞。"""
        self.assertEqual(
            metrics.normalize_formosan("kako施ko", "marks"), "kako ko")

    def test_caret_look_alikes_from_sapolita_are_the_same_mark(self):
        """sapolita 用 U+2303「⌃」寫字幕的 ^（8 集族語列 63 個：
        mido⌃do、fa⌃elohay），⌃ 是 Sm 類，沒對照的話被當成詞的分界，
        mido⌃do 拆成兩個詞、每個都算錯。"""
        for mode in ("strict", "marks", "letters"):
            self.assertEqual(
                metrics.normalize_formosan("mido\u2303do\u2303", mode),
                metrics.normalize_formosan("mido^do^", mode))
        self.assertEqual(
            metrics.normalize_formosan("mido\u2303do", "marks"), "midodo")

    def test_unknown_mode_is_refused(self):
        """mode 拼錯（例如 "letter"）不可以靜靜照 strict 算，報出來的
        長音記號保留／拿掉兩欄會變成一樣。"""
        with self.assertRaises(ValueError):
            metrics.normalize_formosan("kapah", "letter")

    def test_combining_mark_without_precomposed_form_splits_word(self):
        """已知限制：NFC 之後還留著的組合符號（類別 M）照規格變成空白，
        字會被切成兩個。目前阿美語用不到；哪個族語字母需要沒有預組形
        的變音符號時，這條測試會提醒要改規格。"""
        self.assertEqual(
            metrics.normalize_formosan("a̱b", "strict"), "a b")


class TestChineseNormalization(unittest.TestCase):
    def test_modifier_apostrophe_in_chinese_output_is_dropped(self):
        """翻譯服務華語輸出裡的族語名字用 ʼ（U+02BC，Lm 類，不是標點），
        P*／S* 規則刪不掉；OCR 華語列寫 ASCII '、會被刪，同一個名字就
        對不上。"""
        self.assertEqual(metrics.normalize_zh("會長叫\u02bcAriray"),
                         metrics.normalize_zh("會長叫'Ariray"))
        self.assertEqual(metrics.normalize_zh("會長叫\u02bcAriray"),
                         "會長叫ariray")


class TestErrorRate(unittest.TestCase):
    def test_cer_strips_outer_whitespace_like_jiwer(self):
        """jiwer 的 cer_default 先 Strip() 再拆字；直接 list(s) 的版本把
        " ab" 對 "ab " 算成 2/3，正確是 0/2。交叉比對時 4000 組隨機
        語料有 2405 筆就是錯在這裡。"""
        got = metrics.cer([" ab"], ["ab "])
        self.assertEqual(got["errors"], 0)
        self.assertEqual(got["ref_len"], 2)

    def test_breakdown_comes_from_one_minimum_alignment(self):
        """替換、刪除、插入若從不同的對齊路徑各數各的，加起來會大於
        最少編輯距離，或兜不攏 hyp 長度（hyp = ref − 刪除 + 插入）。"""
        cases = (
            ("a b c d", "a x c d e"),
            ("a b", "b a"),
            ("o tilifi ko", "tilifi ko o"),
            ("", "a b"),
            ("a b c", ""),
            ("x y z w", "y z w x"),
        )
        for ref, hyp in cases:
            with self.subTest(ref=ref, hyp=hyp):
                got = metrics.wer([ref], [hyp])
                total = got["sub"] + got["dele"] + got["ins"]
                self.assertEqual(got["errors"], total)
                self.assertEqual(
                    got["errors"], edit_distance(ref.split(), hyp.split()))
                self.assertEqual(
                    len(hyp.split()),
                    got["ref_len"] - got["dele"] + got["ins"])

    def test_empty_reference_gives_zero_or_infinity(self):
        """空的 reference 分母是 0：jiwer 會直接報錯，這裡約定沒錯是 0、
        有錯是 inf，不可以丟 ZeroDivisionError 讓整份報表倒掉。呼叫端
        要先把空 ref 濾掉。"""
        self.assertEqual(metrics.wer([""], [""])["score"], 0.0)
        self.assertTrue(math.isinf(metrics.wer([""], ["a"])["score"]))
        self.assertEqual(metrics.cer([""], [""])["score"], 0.0)
        self.assertTrue(math.isinf(metrics.cer([""], ["ab"])["score"]))

    def test_refs_and_hyps_of_different_length_are_refused(self):
        """少一句時 zip 會靜靜截掉最後幾句，整份分數換了一批句子在算。"""
        with self.assertRaises(ValueError):
            metrics.wer(["a", "b"], ["a"])
        with self.assertRaises(ValueError):
            metrics.cer(["a"], ["a", "b"])


class TestBleu(unittest.TestCase):
    def test_13a_splits_caret_and_colon_into_tokens(self):
        """13a 會把 ^ 和 : 切成獨立 token（regex 類別含 ^ 與 :-@），
        strict 正規化留下的長音記號在 BLEU 裡各算一個詞；' 不在類別裡，
        喉塞音不會把詞切開。"""
        got = metrics.bleu_stats("kapah^ to'as:", "kapah^ to'as:", "13a")
        self.assertEqual(got, [4, 4, 4, 4, 3, 3, 2, 2, 1, 1])

    def test_empty_corpus_is_refused(self):
        """sacrebleu 碰到空語料會讀 hyps[0] 出錯；靜靜回 0 分的話，
        一個方向的翻譯整批沒跑到，報表上看起來只是翻得很差。"""
        with self.assertRaises(ValueError):
            metrics.corpus_bleu([], [], "13a")

    def test_unknown_tokenizer_is_refused(self):
        """tokenize 拼錯（例如 "13A"）不可以退回空白斷詞照算。"""
        with self.assertRaises(ValueError):
            metrics.bleu_stats("a", "a", "13A")

    def test_summed_sentence_stats_equal_corpus_bleu(self):
        """bootstrap 是重抽句子、把統計相加再算分；若各句統計不能直接
        相加（例如排法跟 bleu_from_stats 讀的不同），信賴區間就是錯的。"""
        hyps = ["the cat sat on the mat.", "a b c d", "", "ko pangcah"]
        refs = ["the cat is on the mat.", "a b e d", "x y", "ko pangcah a"]
        total = [0] * 10
        for k in range(len(hyps)):
            one = metrics.bleu_stats(hyps[k], refs[k], "13a")
            for i in range(10):
                total[i] += one[i]
        want = metrics.corpus_bleu(hyps, refs, "13a")
        got = metrics.bleu_from_stats(total)
        self.assertAlmostEqual(got["score"], want["score"], delta=TOLERANCE)


class TestChrf(unittest.TestCase):
    def test_chinese_word_ngram_is_the_whole_sentence(self):
        """中文沒有空白，chrF++ 的詞 n-gram 退化成整句一個詞：差一個字
        詞 1-gram 就是 0 命中，詞 2-gram 根本不存在。照 sacrebleu 算，
        不另外斷詞。"""
        got = metrics.chrf_stats("我們是阿美族", "我們是阿美族人")
        self.assertEqual(len(got), 3 * (6 + 2))
        self.assertEqual(got[18:21], [1, 1, 0])
        self.assertEqual(got[21:24], [0, 0, 0])

    def test_empty_corpus_is_refused(self):
        """空語料回 0 分會讓整批沒跑到的方向看起來只是翻得差。"""
        with self.assertRaises(ValueError):
            metrics.corpus_chrf([], [])

    def test_summed_sentence_stats_equal_corpus_chrf(self):
        """chrF 的語料分數是各句統計相加後算一次 F 分數，不是各句
        分數平均；bootstrap 靠這個性質。"""
        hyps = ["ab cd", "(hi) there.", "我們是阿美族。"]
        refs = ["ab ce", "hi there", "我們都是阿美族人。"]
        total = [0] * 24
        for k in range(len(hyps)):
            one = metrics.chrf_stats(hyps[k], refs[k])
            for i in range(24):
                total[i] += one[i]
        want = metrics.corpus_chrf(hyps, refs)
        got = metrics.chrf_from_stats(total)
        self.assertAlmostEqual(got["score"], want["score"], delta=TOLERANCE)


if __name__ == "__main__":
    unittest.main()
