#!/usr/bin/env python3
"""Similarity scores over the two scripts.

Chinese side (subtitle vs. the service's MT): character n-grams over
漢字／數字／拉丁字母 only. Punctuation and spacing differ between the
two sources for no reason that has to do with meaning.

Formosan side (ASR vs. gold subtitle): words, lower-cased, apostrophes
normalised to ASCII (the dictionary writes U+02BC, Word writes U+2019,
subtitles write '), and matched with an edit-distance tolerance because
the recogniser gets a letter wrong more often than a whole word.
"""
import collections
import unicodedata

APOSTROPHES = "ʼ’‘"


def han_chars(text):
    """Only the characters that carry content: 漢字, digits, letters."""
    out = []
    for char in text:
        category = unicodedata.category(char)
        if category.startswith("L") or category == "Nd":
            out.append(char)
    return "".join(out)


def _ngrams(chars, n):
    grams = collections.Counter()
    for i in range(len(chars) - n + 1):
        grams[chars[i:i + n]] += 1
    return grams


def _f(precision, recall, beta):
    if precision + recall == 0.0:
        return 0.0
    b2 = beta * beta
    return (1 + b2) * precision * recall / (b2 * precision + recall)


def ngram_f1(a, b, n=2):
    """Character n-gram F1 between two Chinese strings (symmetric)."""
    ca, cb = han_chars(a), han_chars(b)
    if len(ca) < n or len(cb) < n:
        if not ca or not cb:
            return 0.0
        return 1.0 if ca == cb else 0.0
    ga, gb = _ngrams(ca, n), _ngrams(cb, n)
    hit = sum((ga & gb).values())
    if hit == 0:
        return 0.0
    precision = hit / sum(ga.values())
    recall = hit / sum(gb.values())
    return _f(precision, recall, 1.0)


def chrf(hyp, ref, max_n=6, beta=2.0):
    """chrF over character n-grams 1..max_n, recall-weighted (beta=2).

    Averages precision and recall across orders the way sacrebleu's
    chrF does, minus the word n-grams (chrF++), which mean little for
    unsegmented Chinese.
    """
    ch, cr = han_chars(hyp), han_chars(ref)
    if not ch or not cr:
        return 0.0
    precisions, recalls = [], []
    for n in range(1, max_n + 1):
        gh, gr = _ngrams(ch, n), _ngrams(cr, n)
        if not gh or not gr:
            continue
        hit = sum((gh & gr).values())
        precisions.append(hit / sum(gh.values()))
        recalls.append(hit / sum(gr.values()))
    if not precisions:
        return 0.0
    precision = sum(precisions) / len(precisions)
    recall = sum(recalls) / len(recalls)
    return _f(precision, recall, beta)


# Length and stress marks the subtitles write (「ho^」「Po:long」) and the
# recogniser never emits. Dropped before comparing, or every marked word
# is a mismatch on both sides of the same speech.
LENGTH_MARKS = "^:"


def formosan_words(text):
    """Tokens of a Formosan line: lower-cased, apostrophes unified,
    length marks and edge punctuation stripped, every token kept."""
    plain = text
    for mark in APOSTROPHES:
        plain = plain.replace(mark, "'")
    for mark in LENGTH_MARKS:
        plain = plain.replace(mark, "")
    out = []
    for token in plain.lower().split():
        cleaned = token.strip(".,;!?\"()[]{}「」『』、。，")
        if cleaned:
            out.append(cleaned)
    return out


def _levenshtein(a, b):
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            current.append(min(previous[j] + 1, current[j - 1] + 1,
                               previous[j - 1] + cost))
        previous = current
    return previous[-1]


def word_similarity(a, b):
    """1 - edit distance / longer length; 1.0 for equal words."""
    if a == b:
        return 1.0
    longest = max(len(a), len(b))
    if longest == 0:
        return 1.0
    return 1.0 - _levenshtein(a, b) / longest


def word_f1(a_words, b_words, fuzzy=0.8):
    """Multiset F1 between two word lists, each match used once."""
    if not a_words or not b_words:
        return 0.0
    free = list(b_words)
    hit = 0
    for word in a_words:
        best, best_at = 0.0, -1
        for position, other in enumerate(free):
            score = word_similarity(word, other)
            if score > best:
                best, best_at = score, position
        if best >= fuzzy:
            hit += 1
            free.pop(best_at)
    precision = hit / len(a_words)
    recall = hit / len(b_words)
    return _f(precision, recall, 1.0)
