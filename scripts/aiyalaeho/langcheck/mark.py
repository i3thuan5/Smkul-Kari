#!/usr/bin/env python3
"""交付 SRT → 逐條ê「這列的語言」。

**材料干焦讀 `1-ocr/3-srt/`。** 行號、時間戳、兩逝文字攏佇彼內底，
是唯一需要ê輸入。莫閣去讀 cues 抑是 vision：

  行號    組裝會kā兩逝文字全款ê相黏 cue 併做一條。39 集有 4 集
          按呢，094 泰雅併掉 78 條。「有字ê cue 累計」佮行號差
          遐濟，而且是恬恬差ê。行號對 SRT 提就無這个問題。
  時間    起、結兩个時間戳 SRT ê時間有 0.5 秒留白，毋是真正ê切換
          點。抄過來就好；愛真正ê切換點ê人去 1-cues 提，這搭莫
          換算——換算是bug通覕ê所在。
  空白    兩逝攏空ê cue 本底就無入 SRT，所以這款情形袂出現。

四級標籤，頭三个是確定性ê計算、第四个是候選（見 spec）。
"""
import collections

from scripts.aiyalaeho import make_srt
from scripts.aiyalaeho.langcheck import script
from scripts.aiyalaeho.langcheck import vocab

# 四个標籤，封閉字彙。使用者裁定 2026-09-10。
#
# 「族語夾雜華語」**無帶族語別ê名**。本底寫做「卑南語夾華語」
# 「泰雅語夾華語」，逐族一款，篩ê人愛先知影有幾族才篩會齊。
#
# 「華語」＝族語列空白：畫面頂懸干焦一逝，彼逝是華語。（本底叫
# 「無」，毋過「無」講袂出彼逝是啥物。）
PURE = "純族語"
MIXED = "族語夾雜華語"
CHINESE = "華語"
UNSURE = "無法確定"

# 標做「無法確定」ê兩个門檻。無門檻ê話 39 集標出 4242 條（15.1%），
# 規份無路用；這兩條落去賰 748 條（2.7%），其中 678 條khû佇布農
# 111／122／119 三集——彼三集探索時用華語字幕ê自報族別交叉核對過，
# 確實有別族來賓。
#
# 詞數：傷短ê逝命中率毋是 0% 就是 100%，純粹是雜訊。
# 相差：上懸彼族ê命中率減本集族語ê，愛差 40% 以上。賽德克 102 對
#       太魯閣是 89% 對 82%，才差 7%——彼是仝一个語言ê兩个方言，
#       本底就該相像，毋是別族來賓。
MIN_WORDS = 5
MIN_MARGIN = 0.40

Entry = collections.namedtuple("Entry", "number start end formosan han")
Mark = collections.namedtuple(
    "Mark", "number start end label suspect rate formosan han")


def _rows_of(text):
    """條目內底彼兩逝，照行首ê標籤拆開。

    標籤對 make_srt 提，毋是家己寫一份——交付格式若改，這搭愛tuè
    咧改，兩爿家己寫會漸漸走精。
    """
    out = {}
    for line in text.split("\n"):
        for key, label in make_srt.LABELS:
            if line.startswith(label):
                out[key] = line[len(label):].strip()
    return out


def entries(text):
    """交付 SRT 文字 → [Entry]。行號佮時間戳照抄。"""
    out = []
    blocks = text.replace("\r\n", "\n").strip().split("\n\n")
    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue
        number = lines[0].strip()
        if not number.isdigit():
            continue
        start, _, end = lines[1].partition("-->")
        rows = _rows_of("\n".join(lines[2:]))
        out.append(Entry(int(number), start.strip(), end.strip(),
                         rows.get("formosan", ""), rows.get("han", "")))
    return out


def unswap(entry):
    """兩逝激反去ê條目，掉轉來。

    族語列規列漢字、華語列有拉丁字母——按呢是電視台（抑是排版）
    kā兩逝囥顛倒去。全 store 有兩條（114 布農 714 佮 919）。

    掉轉來才判是必要ê：無掉ê話彼條會判做「華語」，毋過伊明明有
    族語，會平白仔漏去。掉轉了後照一般判準判。

    `3-srt/` 一個 byte 都無動——掉ê是分析表遮ê兩欄爾。
    """
    formosan = script.counts(entry.formosan)
    han = script.counts(entry.han)
    if formosan.han and not formosan.latin and han.latin:
        return entry._replace(formosan=entry.han, han=entry.formosan)
    return entry


def label_of(entry, tribe, lexicons, language_code=None):
    """(標籤, 疑似語言, 命中率)。後兩項干焦「無法確定」才有值。"""
    counts = script.counts(entry.formosan)
    if not entry.formosan.strip():
        return CHINESE, "", 0.0
    if counts.han and not counts.latin:
        # 掉轉了猶原規列漢字（華語列嘛無拉丁字母）——真正兩逝攏華語。
        return CHINESE, "", 0.0
    if counts.han and counts.latin:
        return MIXED, "", 0.0

    words = script.words(entry.formosan)
    if len(words) < MIN_WORDS:
        # 傷短ê逝——賰記號、數字，抑是一兩个詞。無夠通判。
        return PURE, "", 0.0
    rates = vocab.scores(words, lexicons, language_code=language_code)
    top, rate = vocab.best(words, lexicons, language_code=language_code)
    if top is None or top == tribe:
        return PURE, "", 0.0
    if rate - rates.get(tribe, 0.0) < MIN_MARGIN:
        return PURE, "", 0.0
    return UNSURE, top, rate


def marks(text, tribe, lexicons, language_code=None):
    """交付 SRT 文字 → 逐條ê Mark，一條都無漏。"""
    out = []
    for raw in entries(text):
        entry = unswap(raw)
        label, suspect, rate = label_of(entry, tribe, lexicons,
                                        language_code)
        out.append(Mark(entry.number, entry.start, entry.end,
                        label, suspect, rate,
                        entry.formosan, entry.han))
    return out
