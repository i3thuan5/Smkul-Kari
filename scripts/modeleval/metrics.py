"""WER、CER、BLEU、chrF++ 與評測前的正規化（只用 Python 標準函式庫）。

為什麼自己寫：sacrebleu、jiwer 都沒有裝，採購規定（CLAUDE.md〈外部服務與
套件的採購規定〉）是能用既有工具解決就不加新依賴。所以照兩個套件的原始碼
逐行重寫，分數要跟別人用套件報的數字對得上：

- WER／CER：jiwer v3.0.4。語料層級＝總編輯數÷總參考長度。WER 的 token 是
  `str.split()`；CER 照 jiwer `cer_default`（`Strip()` 再拆字）：首尾空白
  拿掉、中間空白照算一個字元、多個空白不合併。
- BLEU：sacrebleu v2.4.3 `BLEU()` 預設值——smooth_method="exp"、
  lowercase=False、語料層級 effective_order=False、單一參考譯文。斷詞
  `13a`（族語）與 `zh`（華語）照 `tokenizers/tokenizer_13a.py`、
  `tokenizer_re.py`、`tokenizer_zh.py`，連 zh 範圍表的怪處都照抄
  （`'\\u20000'` 字面值其實是 U+2000 加 "0"，結果 U+2001–2A6D 被當成
  中文字，真正的 Ext-B 漢字反而不算）。
- chrF++：sacrebleu v2.4.3 `CHRF(word_order=2)`——char_order=6、beta=2、
  eps_smoothing=False、whitespace=False、lowercase=False。

和套件不同、自己約定的地方：

- 空的 reference（分母 0）：jiwer 會報錯，這裡回傳沒錯時 0、有錯時
  inf。呼叫端應該先把空 ref 濾掉。
- 空語料（`corpus_bleu([], [])`、`corpus_chrf([], [])`）報 ValueError，
  跟 sacrebleu 讀 `hyps[0]` 出錯一致，不靜靜回 0 分。
- `bleu_stats` 的排法是交錯的，跟 sacrebleu 內部（先 m1..m4 再 t1..t4）
  不同；只在本模組內流通，`bleu_from_stats` 讀同一種排法。

`*_stats` 回傳可以逐項相加的整數列，呼叫端做句子層級 bootstrap 時只要
重抽、相加、再呼叫 `*_from_stats`，不必重新斷詞：

    bleu_stats  -> [hyp_len, ref_len, m1, t1, m2, t2, m3, t3, m4, t4]
                   （m＝命中數、t＝hyp 的 n-gram 總數，n＝1..4）
    chrf_stats  -> 每一階 [hyp_count, ref_count, match_count]，先字元
                   1..char_order 階、再詞 1..word_order 階，共
                   3 × (char_order + word_order) 個數；跟 sacrebleu
                   CHRF._compute_segment_statistics 的排法相同。
"""

import math
import re
import unicodedata


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

# sapolita 與翻譯服務用 U+02BC 當喉塞音，OCR 字幕用 ASCII '
_APOSTROPHES = {
    "\u2019": "'",   # RIGHT SINGLE QUOTATION MARK
    "\u2018": "'",   # LEFT SINGLE QUOTATION MARK
    "\u02bc": "'",   # MODIFIER LETTER APOSTROPHE
    "\u0060": "'",   # GRAVE ACCENT
    "\u00b4": "'",   # ACUTE ACCENT
    "\u2032": "'",   # PRIME
}

# sapolita 用 U+2303 寫字幕的 ^（mido⌃do），其他長得像的一起對照
_CARETS = {
    "\u2303": "^",  # UP ARROWHEAD
    "\u02c6": "^",  # MODIFIER LETTER CIRCUMFLEX ACCENT
    "\u2038": "^",  # CARET
}

_GLOTTAL_MARKS = set("'^:")
# 各模式要刪掉的符號
_DROPPED_MARKS = {'strict': '', 'marks': '^:', 'letters': "'^:"}


def _is_cjk_ideograph(ch):
    cp = ord(ch)
    if 0x3400 <= cp <= 0x4DBF:
        return True
    if 0x4E00 <= cp <= 0x9FFF:
        return True
    if 0xF900 <= cp <= 0xFAFF:
        return True
    if 0x20000 <= cp <= 0x2FA1F:
        return True
    return False


def normalize_formosan(text, mode):
    """族語字串在算 WER／CER／BLEU 之前的正規化。

    NFC、小寫、撇號的各種長相統一成 '；族語列裡夾的漢字、連字號與
    其他非字母數字的字元換成空白（漢字直接刪會把兩邊的詞黏起來）。
    mode "strict"：' ^ : 留在詞裡，只由這三種符號組成的 token 丟掉。
    mode "marks"：刪掉 ^ :、留下 '——字幕與辨識器標 ^ : 標得很不一致
    （8 集字幕 ^ 588、: 193 個，sapolita 只有 ⌃ 63、: 15 個），
    `scripts/mt/textsim.py` 也是拿掉再比。
    mode "letters"：' ^ : 全刪。
    """
    if mode not in _DROPPED_MARKS:
        raise ValueError(
            'mode must be "strict", "marks" or "letters": %r' % (mode,))
    text = unicodedata.normalize('NFC', text).lower()
    out = []
    for ch in text:
        if ch in _APOSTROPHES:
            ch = _APOSTROPHES[ch]
        if ch in _CARETS:
            ch = _CARETS[ch]
        if _is_cjk_ideograph(ch):
            out.append(' ')
            continue
        if ch == '-':
            out.append(' ')
            continue
        if ch in _GLOTTAL_MARKS:
            if ch in _DROPPED_MARKS[mode]:
                continue
            out.append(ch)
            continue
        if ch.isspace():
            out.append(' ')
            continue
        cat = unicodedata.category(ch)
        if cat.startswith('L') or cat == 'Nd':
            out.append(ch)
        else:
            out.append(' ')
    tokens = []
    for tok in ''.join(out).split():
        only_marks = True
        for ch in tok:
            if ch not in _GLOTTAL_MARKS:
                only_marks = False
                break
        if only_marks:
            continue
        tokens.append(tok)
    return ' '.join(tokens)


def normalize_zh(text):
    """華語：NFKC（全形摺半形）、小寫，刪掉空白、撇號與 P*、S* 類字元。

    撇號另外列：翻譯服務輸出的族語名字用 ʼ（U+02BC，Lm 類），P*／S*
    規則刪不掉，OCR 寫的 ASCII ' 卻會被刪，同一個名字就對不上。
    """
    text = unicodedata.normalize('NFKC', text).lower()
    out = []
    for ch in text:
        if ch.isspace() or ch in _APOSTROPHES:
            continue
        cat = unicodedata.category(ch)
        if cat.startswith('P') or cat.startswith('S'):
            continue
        out.append(ch)
    return ''.join(out)


# ---------------------------------------------------------------------------
# WER / CER
# ---------------------------------------------------------------------------

def _align_counts(ref, hyp):
    """(替換, 刪除, 插入)，三個數取自同一條最少編輯的對齊路徑。

    回溯時同分的選法固定：先斜走（相同／替換），再刪除（吃一個 ref），
    最後插入（吃一個 hyp）。
    """
    n = len(ref)
    m = len(hyp)
    d = []
    for i in range(n + 1):
        row = [0] * (m + 1)
        d.append(row)
    for i in range(n + 1):
        d[i][0] = i
    for j in range(m + 1):
        d[0][j] = j
    for i in range(1, n + 1):
        ri = ref[i - 1]
        prev = d[i - 1]
        cur = d[i]
        for j in range(1, m + 1):
            cost = 0 if ri == hyp[j - 1] else 1
            best = prev[j - 1] + cost
            v = prev[j] + 1
            if v < best:
                best = v
            v = cur[j - 1] + 1
            if v < best:
                best = v
            cur[j] = best
    sub = dele = ins = 0
    i = n
    j = m
    while i > 0 or j > 0:
        if i > 0 and j > 0:
            cost = 0 if ref[i - 1] == hyp[j - 1] else 1
            if d[i][j] == d[i - 1][j - 1] + cost:
                sub += cost
                i -= 1
                j -= 1
                continue
        if i > 0 and d[i][j] == d[i - 1][j] + 1:
            dele += 1
            i -= 1
            continue
        ins += 1
        j -= 1
    return sub, dele, ins


def _error_rate(ref_seqs, hyp_seqs):
    if len(ref_seqs) != len(hyp_seqs):
        raise ValueError('refs and hyps differ in length: %d vs %d'
                         % (len(ref_seqs), len(hyp_seqs)))
    sub = dele = ins = ref_len = 0
    for k in range(len(ref_seqs)):
        s, dl, it = _align_counts(ref_seqs[k], hyp_seqs[k])
        sub += s
        dele += dl
        ins += it
        ref_len += len(ref_seqs[k])
    errors = sub + dele + ins
    if ref_len > 0:
        score = errors / ref_len
    elif errors == 0:
        score = 0.0
    else:
        score = float('inf')
    return {'errors': errors, 'sub': sub, 'dele': dele, 'ins': ins,
            'ref_len': ref_len, 'score': score}


def wer(refs, hyps):
    """語料 WER：總詞編輯數÷總參考詞數；詞＝str.split()。score 是比例。"""
    ref_seqs = []
    hyp_seqs = []
    for r in refs:
        ref_seqs.append(r.split())
    for h in hyps:
        hyp_seqs.append(h.split())
    return _error_rate(ref_seqs, hyp_seqs)


def cer(refs, hyps):
    """語料 CER：jiwer cer_default，首尾 strip 後逐字元比，中間空白照算。"""
    ref_seqs = []
    hyp_seqs = []
    for r in refs:
        ref_seqs.append(list(r.strip()))
    for h in hyps:
        hyp_seqs.append(list(h.strip()))
    return _error_rate(ref_seqs, hyp_seqs)


# ---------------------------------------------------------------------------
# sacrebleu tokenizers (13a, zh)
# ---------------------------------------------------------------------------

# tokenizer_re.TokenizerRegexp
_RE_RULES = [
    (re.compile(r'([\{-\~\[-\` -\&\(-\+\:-\@\/])'), r' \1 '),
    (re.compile(r'([^0-9])([\.,])'), r'\1 \2 '),
    (re.compile(r'([\.,])([^0-9])'), r' \1 \2'),
    (re.compile(r'([0-9])(-)'), r'\1 \2 '),
]


def _tok_regexp(line):
    for rule in _RE_RULES:
        line = rule[0].sub(rule[1], line)
    return ' '.join(line.split())


def _tok_13a(line):
    line = line.replace('<skipped>', '')
    line = line.replace('-\n', '')
    line = line.replace('\n', ' ')
    if '&' in line:
        line = line.replace('&quot;', '"')
        line = line.replace('&amp;', '&')
        line = line.replace('&lt;', '<')
        line = line.replace('&gt;', '>')
    return _tok_regexp(' ' + line + ' ')


# 照抄 tokenizer_zh._UCODE_RANGES。注意 '\u20000'、'\u2a6d6' 這類寫法是
# 兩個字元的字串（U+2000 加 "0"），Python 照字典序比較，所以那兩列實際涵蓋
# U+2001..U+2A6D 與 U+2F81..U+2FA1，真正的 Ext-B 漢字反而不在範圍內。
# 為了跟 sacrebleu 分數一致，故意保留這個怪處，不要「修正」。
_ZH_RANGES = [
    ('\u3400', '\u4db5'),
    ('\u4e00', '\u9fa5'),
    ('\u9fa6', '\u9fbb'),
    ('\uf900', '\ufa2d'),
    ('\ufa30', '\ufa6a'),
    ('\ufa70', '\ufad9'),
    ('\u20000', '\u2a6d6'),
    ('\u2f800', '\u2fa1d'),
    ('\uff00', '\uffef'),
    ('\u2e80', '\u2eff'),
    ('\u3000', '\u303f'),
    ('\u31c0', '\u31ef'),
    ('\u2f00', '\u2fdf'),
    ('\u2ff0', '\u2fff'),
    ('\u3100', '\u312f'),
    ('\u31a0', '\u31bf'),
    ('\ufe10', '\ufe1f'),
    ('\ufe30', '\ufe4f'),
    ('\u2600', '\u26ff'),
    ('\u2700', '\u27bf'),
    ('\u3200', '\u32ff'),
    ('\u3300', '\u33ff'),
]


def _zh_is_chinese_char(uchar):
    for start, end in _ZH_RANGES:
        if start <= uchar <= end:
            return True
    return False


def _tok_zh(line):
    # tokenizer_zh.TokenizerZh.__call__: strip, pad "Chinese" chars with
    # spaces, then TokenizerRegexp only (NOT the 13a entity/<skipped> part).
    line = line.strip()
    parts = []
    for ch in line:
        if _zh_is_chinese_char(ch):
            parts.append(' ' + ch + ' ')
        else:
            parts.append(ch)
    return _tok_regexp(''.join(parts))


_TOKENIZERS = {'13a': _tok_13a, 'zh': _tok_zh}


def _bleu_preprocess(sent, tokenize):
    # BLEU._preprocess_segment: (lowercase=False) tokenizer(sent.rstrip())
    if tokenize not in _TOKENIZERS:
        raise ValueError('tokenize must be "13a" or "zh": %r' % (tokenize,))
    return _TOKENIZERS[tokenize](sent.rstrip())


# ---------------------------------------------------------------------------
# BLEU
# ---------------------------------------------------------------------------

MAX_NGRAM_ORDER = 4


def _word_ngrams(line, max_order):
    """helpers.extract_all_word_ngrams(line, 1, max_order)."""
    tokens = line.split()
    counts = {}
    for n in range(1, max_order + 1):
        for i in range(0, len(tokens) - n + 1):
            ng = tuple(tokens[i:i + n])
            counts[ng] = counts.get(ng, 0) + 1
    return counts, len(tokens)


def bleu_stats(hyp, ref, tokenize):
    """一句的 [hyp_len, ref_len, m1, t1, m2, t2, m3, t3, m4, t4]。"""
    hyp_tok = _bleu_preprocess(hyp, tokenize)
    ref_tok = _bleu_preprocess(ref, tokenize)
    ref_ngrams, ref_len = _word_ngrams(ref_tok, MAX_NGRAM_ORDER)
    hyp_ngrams, hyp_len = _word_ngrams(hyp_tok, MAX_NGRAM_ORDER)
    correct = [0] * MAX_NGRAM_ORDER
    total = [0] * MAX_NGRAM_ORDER
    for ng, cnt in hyp_ngrams.items():
        n = len(ng) - 1
        total[n] += cnt
        if ng in ref_ngrams:
            correct[n] += min(cnt, ref_ngrams[ng])
    stats = [hyp_len, ref_len]
    for n in range(MAX_NGRAM_ORDER):
        stats.append(correct[n])
        stats.append(total[n])
    return stats


def _my_log(num):
    # utils.my_log
    if num == 0.0:
        return -9999999999
    return math.log(num)


def bleu_from_stats(stats):
    """BLEU.compute_bleu，smooth_method='exp'、effective_order=False。

    回傳 score（0–100）、precisions、bp、sys_len、ref_len。
    """
    sys_len = int(stats[0])
    ref_len = int(stats[1])
    correct = []
    total = []
    for n in range(MAX_NGRAM_ORDER):
        correct.append(stats[2 + 2 * n])
        total.append(stats[3 + 2 * n])

    if sys_len < ref_len:
        bp = math.exp(1 - ref_len / sys_len) if sys_len > 0 else 0.0
    else:
        bp = 1.0

    precisions = [0.0] * MAX_NGRAM_ORDER
    has_match = False
    for c in correct:
        if c:
            has_match = True
            break
    if not has_match:
        return {'score': 0.0, 'precisions': precisions, 'bp': bp,
                'sys_len': sys_len, 'ref_len': ref_len}

    smooth_mteval = 1.0
    eff_order = MAX_NGRAM_ORDER
    for n in range(1, MAX_NGRAM_ORDER + 1):
        if total[n - 1] == 0:
            break
        if correct[n - 1] == 0:
            smooth_mteval *= 2
            precisions[n - 1] = 100.0 / (smooth_mteval * total[n - 1])
        else:
            precisions[n - 1] = 100.0 * correct[n - 1] / total[n - 1]

    log_sum = 0.0
    for p in precisions[:eff_order]:
        log_sum += _my_log(p)
    score = bp * math.exp(log_sum / eff_order)
    return {'score': score, 'precisions': precisions, 'bp': bp,
            'sys_len': sys_len, 'ref_len': ref_len}


def _sum_stats(all_stats, size):
    totals = [0] * size
    for st in all_stats:
        for i in range(size):
            totals[i] += st[i]
    return totals


def corpus_bleu(hyps, refs, tokenize):
    """各句 bleu_stats 相加後算一次 BLEU（sacrebleu corpus_score）。"""
    if len(hyps) != len(refs):
        raise ValueError('hyps and refs differ in length')
    if not hyps:
        raise ValueError('empty corpus: sacrebleu fails on hyps[0] too')
    all_stats = []
    for k in range(len(hyps)):
        all_stats.append(bleu_stats(hyps[k], refs[k], tokenize))
    return bleu_from_stats(_sum_stats(all_stats, 2 + 2 * MAX_NGRAM_ORDER))


# ---------------------------------------------------------------------------
# chrF / chrF++
# ---------------------------------------------------------------------------

_PUNCTS = set('!"#$%&\'()*+,-./:;<=>?@[\\]^_`{|}~')


def _remove_punctuation(sent):
    """CHRF._remove_punctuation：每個詞只拆下一個首或尾的 ASCII 標點
    （先看尾）。"""
    tokenized = []
    for w in sent.split():
        if len(w) == 1:
            tokenized.append(w)
        elif w[-1] in _PUNCTS:
            tokenized.append(w[:-1])
            tokenized.append(w[-1])
        elif w[0] in _PUNCTS:
            tokenized.append(w[0])
            tokenized.append(w[1:])
        else:
            tokenized.append(w)
    return tokenized


def _char_ngrams(line, max_order):
    """helpers.extract_all_char_ngrams with include_whitespace=False."""
    line = ''.join(line.split())
    counters = []
    for n in range(1, max_order + 1):
        c = {}
        for i in range(len(line) - n + 1):
            ng = line[i:i + n]
            c[ng] = c.get(ng, 0) + 1
        counters.append(c)
    return counters


def _word_ngram_counter(tokens, n):
    """helpers.extract_word_ngrams."""
    c = {}
    for i in range(len(tokens) - n + 1):
        ng = ' '.join(tokens[i:i + n])
        c[ng] = c.get(ng, 0) + 1
    return c


def _chrf_ngrams(sent, char_order, word_order):
    grams = _char_ngrams(sent, char_order)
    if word_order > 0:
        words = _remove_punctuation(sent)
        for n in range(1, word_order + 1):
            grams.append(_word_ngram_counter(words, n))
    return grams


def chrf_stats(hyp, ref, char_order=6, word_order=2):
    """每一階 [hyp_count, ref_count, match_count] 攤平，先字元階再詞階。"""
    hyp_grams = _chrf_ngrams(hyp, char_order, word_order)
    ref_grams = _chrf_ngrams(ref, char_order, word_order)
    stats = []
    for k in range(len(hyp_grams)):
        h = hyp_grams[k]
        r = ref_grams[k]
        match_count = 0
        hyp_count = 0
        for ng, cnt in h.items():
            hyp_count += cnt
            if ng in r:
                match_count += min(cnt, r[ng])
        ref_count = 0
        for cnt in r.values():
            ref_count += cnt
        # CHRF._get_match_statistics: hyp count zeroed if ref has no n-grams
        stats.append(hyp_count if r else 0)
        stats.append(ref_count)
        stats.append(match_count)
    return stats


def chrf_from_stats(stats, char_order=6, word_order=2, beta=2):
    """CHRF._compute_f_score，eps_smoothing=False；回傳 score（0–100）。"""
    order = char_order + word_order
    factor = beta ** 2
    avg_prec = 0.0
    avg_rec = 0.0
    effective_order = 0
    for i in range(order):
        n_hyp = stats[3 * i]
        n_ref = stats[3 * i + 1]
        n_match = stats[3 * i + 2]
        if n_hyp > 0 and n_ref > 0:
            avg_prec += n_match / n_hyp
            avg_rec += n_match / n_ref
            effective_order += 1
    if effective_order == 0:
        avg_prec = avg_rec = 0.0
    else:
        avg_prec /= effective_order
        avg_rec /= effective_order
    if avg_prec + avg_rec:
        score = (1 + factor) * avg_prec * avg_rec
        score /= (factor * avg_prec) + avg_rec
        return {'score': 100 * score}
    return {'score': 0.0}


def corpus_chrf(hyps, refs, word_order=2):
    """各句 chrf_stats 相加後算一次 chrF（word_order=2 即 chrF++）。"""
    if len(hyps) != len(refs):
        raise ValueError('hyps and refs differ in length')
    if not hyps:
        raise ValueError('empty corpus: sacrebleu fails on hyps[0] too')
    char_order = 6
    all_stats = []
    for k in range(len(hyps)):
        all_stats.append(chrf_stats(hyps[k], refs[k], char_order, word_order))
    size = 3 * (char_order + word_order)
    return chrf_from_stats(_sum_stats(all_stats, size), char_order,
                           word_order)
