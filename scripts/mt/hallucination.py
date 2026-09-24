#!/usr/bin/env python3
"""Text-only hallucination flags for sapolita segments.

The server returns text, never log-probs or compression ratios, so the
flags are all on the text: a segment that is one short n-gram repeated
(closing music), an MT row that is a run of numerals (the service's own
tell that it saw nothing it understood), and a Formosan row whose words
are mostly not in the episode language's dictionary (another language,
or noise).
"""
import collections
import re

from scripts.lexicon import vocab
from scripts.mt import textsim

REPEAT_N = 3
REPEAT_FLOOR = 0.3
LEXICON_FLOOR = 0.2
# Same two floors as langcheck.mark: fewer than 5 words is noise either
# way, and two dialects of one language sit within 40 points of each
# other (賽德克 89% vs 太魯閣 82%), so a smaller margin is not another
# language.
MIN_WORDS = 5
MIN_MARGIN = 0.40
NUMBER_RUN = re.compile(r"(?:[零〇一二三四五六七八九十百千]{1,3}[、，,]){5,}")


def repeat_ratio(words, n=REPEAT_N):
    """Share of the segment's n-grams taken by its single commonest one."""
    if len(words) < 2 * n:
        return 0.0
    grams = collections.Counter()
    for i in range(len(words) - n + 1):
        grams[tuple(words[i:i + n])] += 1
    top = grams.most_common(1)[0][1]
    return top / (len(words) - n + 1)


def number_run(han):
    return bool(NUMBER_RUN.search(han))


def lexicon_rate(words, lexicon, fold=None):
    """Share of words found in the lexicon (apostrophes unified first).

    `fold` is an optional function applied to a word before the second
    look-up (the 南勢阿美 sound changes in lexicon.vocab.fold).
    """
    if not words:
        return 0.0
    hit = 0
    for word in words:
        plain = word
        for mark in textsim.APOSTROPHES:
            plain = plain.replace(mark, "'")
        if plain in lexicon or (fold and fold(plain) in lexicon):
            hit += 1
    return hit / len(words)


def _plain(words):
    out = []
    for word in words:
        plain = word
        for mark in textsim.APOSTROPHES:
            plain = plain.replace(mark, "'")
        out.append(plain)
    return out


def language_check(words, lexicons, tribe, code=None):
    """Which tribe's dictionary the words fit best, and whether that is
    another tribe by a margin -- the interviewee who speaks a different
    language from the programme's, which no judge reading the Chinese
    side can see.

    {"own_rate", "best_tribe", "best_rate", "foreign"}; `foreign` needs
    MIN_WORDS words and MIN_MARGIN over the episode's own rate."""
    plain = _plain(words)
    rates = vocab.scores(plain, lexicons, language_code=code)
    best_tribe, best_rate = vocab.best(plain, lexicons, language_code=code)
    own = rates.get(tribe, 0.0)
    foreign = (len(words) >= MIN_WORDS and best_tribe is not None
               and best_tribe != tribe and best_rate - own >= MIN_MARGIN)
    return {"own_rate": own, "best_tribe": best_tribe or "",
            "best_rate": best_rate, "foreign": foreign}


def flags(segment, lexicon=None, fold=None):
    words = textsim.formosan_words(segment.get("formosan", ""))
    out = {
        "words": len(words),
        "repeat": repeat_ratio(words) >= REPEAT_FLOOR,
        "number_run": number_run(segment.get("han", "")),
        "empty": not words,
    }
    if lexicon is not None:
        rate = lexicon_rate(words, lexicon, fold)
        out["lexicon_rate"] = rate
        out["foreign"] = len(words) >= 5 and rate < LEXICON_FLOOR
    else:
        out["foreign"] = False
    out["suspicious"] = bool(out["repeat"] or out["number_run"]
                             or out["empty"] or out["foreign"])
    return out
