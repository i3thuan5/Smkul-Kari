#!/usr/bin/env python3
"""Banded monotone alignment between two timed unit sequences.

Pure function, no I/O and no translation calls: the similarity measure is
injected. The path may take 1-1, 1-2, 2-1 and 2-2 steps -- the 2-2 merge
is what recovers a VSO/SVO crossed pair, whose high similarities sit on
the anti-diagonal where no monotone 1-1 path can reach them -- or skip a
unit at a penalty. Steps whose merged time midpoints lie further apart
than the band are not considered at all, so nothing can be dragged in
from minutes away no matter how alike the text is.

Same setting as Bleualign (translate first, then align on surface
similarity); the band replaces its anchor-then-gapfill scaffolding
because our units carry timestamps and its did not.
"""

MATCH_MOVES = ((1, 1), (1, 2), (2, 1), (2, 2))


def _texts(units, lo, hi):
    parts = []
    for start, end, text in units[lo:hi]:
        parts.append(text)
    return " ".join(parts)


def _mid(units, lo, hi):
    return (units[lo][0] + units[hi - 1][1]) / 2.0


def align(a_units, b_units, sim, band_seconds=10.0, skip_penalty=0.3,
          bonus=None):
    """Return the best monotone pairing as a list of match dicts.

    `a_units`/`b_units`: time-ordered `(start, end, text)` tuples.
    `sim(a_text, b_text)`: similarity of two (possibly merged, space-
    joined) texts. `bonus(a_range, b_range)`: optional additive score for
    a candidate step -- anchors go here, as a soft push rather than a
    hard constraint so a misread anchor cannot wedge the path.

    Each match is `{"a": (i0, i1), "b": (j0, j1), "score": s}` with
    half-open index ranges, ascending in both sequences.
    """
    n = len(a_units)
    m = len(b_units)
    neg = float("-inf")
    score = []
    back = []
    for _ in range(n + 1):
        score.append([neg] * (m + 1))
        back.append([None] * (m + 1))
    score[0][0] = 0.0

    for i in range(n + 1):
        for j in range(m + 1):
            here = score[i][j]
            if here == neg:
                continue
            if i < n and here - skip_penalty > score[i + 1][j]:
                score[i + 1][j] = here - skip_penalty
                back[i + 1][j] = (i, j, None)
            if j < m and here - skip_penalty > score[i][j + 1]:
                score[i][j + 1] = here - skip_penalty
                back[i][j + 1] = (i, j, None)
            for di, dj in MATCH_MOVES:
                if i + di > n or j + dj > m:
                    continue
                gap = _mid(a_units, i, i + di) - _mid(b_units, j, j + dj)
                if abs(gap) > band_seconds:
                    continue
                got = sim(_texts(a_units, i, i + di),
                          _texts(b_units, j, j + dj))
                gain = got * (di + dj) / 2.0
                if bonus is not None:
                    gain += bonus((i, i + di), (j, j + dj))
                if here + gain > score[i + di][j + dj]:
                    score[i + di][j + dj] = here + gain
                    back[i + di][j + dj] = (i, j, got)

    matches = []
    i = n
    j = m
    while (i, j) != (0, 0):
        prev_i, prev_j, matched = back[i][j]
        if matched is not None:
            matches.append({"a": (prev_i, i), "b": (prev_j, j),
                            "score": matched})
        i = prev_i
        j = prev_j
    matches.reverse()
    return matches
