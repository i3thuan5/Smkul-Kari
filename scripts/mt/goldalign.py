#!/usr/bin/env python3
"""Text-based truth for 開會了: which gold cues an ASR segment covers.

The programme burns the Formosan line into the picture, so every cue
carries the words that were spoken during it. Aligning the recogniser's
words to those (locally, inside a time window) tells which cues a
segment really spans -- a truth that owes nothing to the VAD boundaries
the time-based methods are being graded on.

Local alignment (Smith-Waterman), not global: the segment is a short
substring of the window, and the recogniser drops and garbles words.
"""
from scripts.mt import textsim

MATCH_FLOOR = 0.75
SHORT_WORD = 3
GAP = -0.5
MISMATCH = -1.0
WINDOW = 20.0


def _similarity(word, other, min_sim):
    """Edit-distance similarity, but short words must match exactly:
    one letter off in a three-letter word is a different word."""
    if min(len(word), len(other)) <= SHORT_WORD:
        return 1.0 if word == other else 0.0
    score = textsim.word_similarity(word, other)
    return score if score >= min_sim else 0.0


def align_words(asr, gold, min_sim=MATCH_FLOOR):
    """For each ASR word, the gold position it aligns to, or None."""
    m, n = len(asr), len(gold)
    if not m or not n:
        return [None] * m
    sims = []
    for word in asr:
        row = []
        for other in gold:
            row.append(_similarity(word, other, min_sim))
        sims.append(row)
    score = [[0.0] * (n + 1) for _ in range(m + 1)]
    move = [[0] * (n + 1) for _ in range(m + 1)]   # 1 diag, 2 up, 3 left
    best, best_at = 0.0, (0, 0)
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            sim = sims[i - 1][j - 1]
            gain = sim if sim >= min_sim else MISMATCH
            diag = score[i - 1][j - 1] + gain
            up = score[i - 1][j] + GAP
            left = score[i][j - 1] + GAP
            top = max(0.0, diag, up, left)
            score[i][j] = top
            if top == 0.0:
                move[i][j] = 0
            elif top == diag:
                move[i][j] = 1
            elif top == up:
                move[i][j] = 2
            else:
                move[i][j] = 3
            if top > best:
                best, best_at = top, (i, j)
    out = [None] * m
    i, j = best_at
    while i > 0 and j > 0 and move[i][j]:
        if move[i][j] == 1:
            if sims[i - 1][j - 1] >= min_sim:
                out[i - 1] = j - 1
            i -= 1
            j -= 1
        elif move[i][j] == 2:
            i -= 1
        else:
            j -= 1
    return out


def gold_cues(segment, entries, window=WINDOW):
    """{"entries": {entry index: (matched, total words)}, "match_rate"}.

    Candidates are the entries with a Formosan row inside the time
    window around the segment; `match_rate` is the share of the ASR
    words that found a gold word at all.
    """
    asr = textsim.formosan_words(segment["formosan"])
    lo, hi = segment["start"] - window, segment["end"] + window
    gold, owner, totals = [], [], {}
    for entry in entries:
        if entry["true_end"] < lo or entry["true_start"] > hi:
            continue
        words = textsim.formosan_words(entry.get("formosan", ""))
        if not words:
            continue
        totals[entry["index"]] = len(words)
        for word in words:
            gold.append(word)
            owner.append(entry["index"])
    matched = {}
    hits = 0
    for position in align_words(asr, gold):
        if position is None:
            continue
        hits += 1
        matched[owner[position]] = matched.get(owner[position], 0) + 1
    found = {}
    for index, count in matched.items():
        found[index] = (count, totals[index])
    return {"entries": found,
            "match_rate": hits / len(asr) if asr else 0.0}
