#!/usr/bin/env python3
"""Project recognised words onto the subtitle entries' true windows.

Each word goes to the entry whose true window overlaps it most; ties go
to the earlier entry. A word that also touches a neighbouring window is
counted in that entry's `straddle` diagnostic. Words overlapping no
window at all are returned separately -- they stay in the word record,
never in any SRT. The word text is passed through untouched.
"""


def _overlap(a_start, a_end, b_start, b_end):
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def _best_entry(item, rows):
    """(position of the max-overlap entry, how many windows it touched)."""
    best = -1
    best_overlap = 0.0
    touched = 0
    for pos, row in enumerate(rows):
        got = _overlap(item["start"], item["end"],
                       row["true_start"], row["true_end"])
        if got <= 0.0:
            continue
        touched += 1
        # strictly-greater with a float tolerance: an exact tie (up to
        # arithmetic noise) stays with the earlier entry
        if got > best_overlap + 1e-9:
            best = pos
            best_overlap = got
    return best, touched


def project(words, entries):
    """Return (entries_out, unassigned_word_indexes).

    `words` is the time-ordered word list ({"w","start","end","conf"});
    `entries` are chain rows carrying true_start/true_end. Each returned
    entry copy gains `word_i` (indexes into `words`), `formosan` (the
    words joined in time order) and `straddle`.
    """
    out = []
    for row in entries:
        copy = dict(row)
        copy["word_i"] = []
        copy["straddle"] = 0
        out.append(copy)

    unassigned = []
    for index, item in enumerate(words):
        best, touched = _best_entry(item, out)
        if best < 0:
            unassigned.append(index)
            continue
        out[best]["word_i"].append(index)
        if touched > 1:
            out[best]["straddle"] += 1

    for row in out:
        parts = []
        for index in row["word_i"]:
            parts.append(words[index]["w"])
        row["formosan"] = " ".join(parts)
    return out, unassigned
