"""語言別推測：一集的族語列最像該族的哪個語別。

覆蓋率＝族語列詞次中，出現在該語別 E樂園 詞表的比例。光看全集最高
不夠：082 阿美各語別都在 53～59%，是南勢講者和秀姑巒／馬蘭講者輪流
講；所以每 60 條分一段，看各段第一名穩不穩。

門檻是拿這 10 集量出來的（2026-10-15）：

  高    全集領先 ≥ 10 點，且 ≥ 90% 的段第一名相同（085 領先 38、086 49）
  中    其餘，但 ≥ 70% 的段第一名是全集第一（084 領先 3、087 領先 2）
  混合  其餘（082 只有 6/10 段）

smkul.csv 已標語別的集照標記、不推測——068 標秀姑巒，卻只比海岸高
3 點，重推會掉成「中」。只有一個語別的族語（賽夏）不推測。

語言別代號照 CLAUDE.md：有確定語言別（高、已標記）才用語言別代號，
中、混合退族語別代號，推測的語別另外寫。
"""
import collections

from scripts import languages
from scripts.lexicon import script

Result = collections.namedtuple(
    "Result", "verdict variety code rates windows considered")

WINDOW = 60
MIN_WORDS = 40
HIGH_MARGIN = 0.10
HIGH_SHARE = 0.9
MID_SHARE = 0.7


def _rates(counter, vocabs):
    total = sum(counter.values())
    out = {}
    for name in vocabs:
        hit = 0
        for word, count in counter.items():
            if word in vocabs[name]:
                hit += count
        out[name] = hit / total if total else 0.0
    return out


def _ranked(rates):
    """由高到低；同分照名字排，重跑順序固定。"""
    return sorted(rates, key=lambda name: (-rates[name], name))


def _counter(text_lines):
    counter = collections.Counter()
    for text in text_lines:
        counter.update(script.words(text))
    return counter


def infer(text_lines, vocabs, language, labelled="", window=WINDOW,
          min_words=MIN_WORDS):
    """text_lines 是一集的族語列；vocabs 是 {語別: set(詞)}。"""
    rates = _rates(_counter(text_lines), vocabs)
    windows = collections.Counter()
    for start in range(0, len(text_lines), window):
        counter = _counter(text_lines[start:start + window])
        if sum(counter.values()) < min_words:
            continue
        windows[_ranked(_rates(counter, vocabs))[0]] += 1
    windows = dict(windows)

    if len(vocabs) == 1:
        only = list(vocabs)[0]
        return Result("單一語別", only, languages.code_for(language, only),
                      rates, windows, (only,))
    if labelled:
        return Result("已標記", labelled,
                      languages.code_for(language, labelled), rates, windows,
                      (labelled,))

    order = _ranked(rates)
    best = order[0]
    margin = rates[best] - rates[order[1]]
    voted = sum(windows.values())
    share = windows.get(best, 0) / voted if voted else 0.0
    fallback = languages.code_for(language, "")
    if margin >= HIGH_MARGIN and share >= HIGH_SHARE:
        return Result("高", best, languages.code_for(language, best), rates,
                      windows, (best,))
    if share >= MID_SHARE:
        return Result("中", best, fallback, rates, windows,
                      tuple(order[:2]))
    return Result("混合", best, fallback, rates, windows, tuple(order))
