#!/usr/bin/env python3
"""One anchor list per episode, shared by every batch that judges it.

Each judging agent used to derive its anchors from its own fifty rows.
That cost twice over. **Slow**: part of the twelve seconds a row takes
was rediscovering what another agent had already worked out -- three
agents on one Kavalan episode each arrived at `qaqanan`＝食物
separately. **Inconsistent**: different batches of one episode settled
on different readings of the same word, so the grade depended on which
batch a row landed in.

So the anchors are worked out once, over the whole episode, before any
judging starts. The rule is the one the prompt already states: a
Formosan word that turns up in several unrelated rows always beside the
same Chinese topic is an anchor. Three occurrences, not two -- Formosan
words are short and two co-occurrences happen by chance.

This is a first pass done by counting, not by a model: it proposes,
the judge still verifies against the row in front of it. What it buys
is that every batch starts from the same list.
"""
import collections
import re

MIN_TIMES = 3
MIN_LETTERS = 3

# 華語主題ê候選：字幕內底ê漢字連讀。短ê（一字）予人湊出來ê「主題」
# 無意義，所以上少兩字。
HAN = re.compile(r"[一-鿿]{2,}")


def _words(text):
    out = []
    for word in text.split():
        cleaned = word.strip("⌃,.;:!?\"'()")
        if len(cleaned) >= MIN_LETTERS:
            out.append(cleaned)
    return out


def _topics(subtitle):
    """Two-character-and-longer Han runs, and their substrings.

    A topic word is what recurs, and it can sit anywhere inside the
    subtitle, so每 run 的每個二字窗都算候選——「拳擊隊今天成立」要能
    產出「拳擊」。
    """
    out = set()
    for run in HAN.findall(subtitle):
        for size in (2, 3):
            for start in range(0, len(run) - size + 1):
                out.add(run[start:start + size])
    return out


def anchors(rows, min_times=MIN_TIMES):
    """{族語詞: 華語主題} for words that always keep the same company."""
    seen = collections.defaultdict(list)
    for row in rows:
        topics = _topics(row["subtitle"])
        if not topics:
            continue
        for word in _words(row["formosan"]):
            seen[word].append(topics)

    found = {}
    for word in sorted(seen):
        appearances = seen[word]
        if len(appearances) < min_times:
            continue
        shared = set(appearances[0])
        for topics in appearances[1:]:
            shared &= topics
        if not shared:
            continue
        # 賰幾若个ê時，揀上長ê——「拳擊」贏過「拳」，較有內容。
        best = sorted(shared, key=lambda topic: (-len(topic), topic))[0]
        found[word] = best
    return found


def render(found):
    """The list as the judging agents read it."""
    if not found:
        return "（這集揣無會使做錨點ê重複詞——照 prompt 家己揣。）\n"
    lines = []
    for word in sorted(found):
        lines.append("%s\t%s" % (word, found[word]))
    return "\n".join(lines) + "\n"
