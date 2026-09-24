#!/usr/bin/env python3
"""高信心／中信心／不採用, and the one reason a group was dropped.

Every threshold of the pipeline lives here, the merge threshold
included: tuning changes one number in one place, then the whole
2021-01～10 batch is produced again.

The rules (whisper-parallel-corpus spec) come from the explore phase:
the dictionary hit rate separated good pairs from bad best (AUC
0.886～0.907 against Claude's grades), the MT-to-subtitle chrF next;
the word floors exist because a two-word fragment scores 1.0 on the
dictionary and carries nothing.
"""

# 字幕在兩段語音中較少的那邊佔字幕長度 ≥ 這個比例，兩段就併成一組。
# 調參決定（scripts/news/pairs_tune.py，2026-09-24）：新聞 485 處、五格
# 都是「合併較好」，取最低的候選值。結果表在 2-平行語料/README.md。
MERGE_FRACTION = 0.10

HIGH_SHARE = 0.8
MID_SHARE = 0.6
HIGH_CHRF = 0.02
HIGH_WORDS = 10
MID_WORDS = 5

# 1.2 s of a 4 s subtitle is 0.2999… in floating point; a value exactly
# on a line has to count as reaching it.
EPSILON = 1e-9

HIGH = "高信心"
MID = "中信心"
DROP = "不採用"
HALLUCINATION = "幻覺"
OTHER_LANGUAGE = "別族語言"
TOO_FEW_WORDS = "詞數不足"
LOW_RATE = "命中率不足"


def _reaches(value, line):
    return value >= line - EPSILON


def classify(hallucinated, other_language, rate, chrf, words, baseline):
    """(level, reason); reason is "" unless the group is dropped.

    Reasons in a fixed order, so one group always gets the same one:
    幻覺 ＞ 別族語言 ＞ 詞數不足 ＞ 命中率不足.
    """
    if hallucinated:
        return DROP, HALLUCINATION
    if other_language:
        return DROP, OTHER_LANGUAGE
    if (words >= HIGH_WORDS and _reaches(rate, HIGH_SHARE * baseline)
            and _reaches(chrf, HIGH_CHRF)):
        return HIGH, ""
    if words >= MID_WORDS and _reaches(rate, MID_SHARE * baseline):
        return MID, ""
    if words < MID_WORDS:
        return DROP, TOO_FEW_WORDS
    return DROP, LOW_RATE
