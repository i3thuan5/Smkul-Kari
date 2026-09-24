#!/usr/bin/env python3
"""A method's groups graded against the text-based truth.

For one group (some segments, some entries) the truth is the union of
the entries the segments' ASR words came from (goldalign), and the
grade is word-weighted: an entry counts by the gold words it carries,
so a one-word straddling cue cannot swing the score the way a ten-word
one can.

  precision  gold-backed words among the group's entry words
  recall     of the words the segments really cover, how many the
             group's entries hold
  strict     the entry set is exactly the truth set (Sennrich & Volk
             2010's strict bead match; a truth entry is one with at
             least half its words matched)
  lax        the entry set overlaps the truth set at all
"""

TRUTH_SHARE = 0.5


def group_score(group, truth, entry_words):
    covered = {}
    no_truth = False
    for i in group["segs"]:
        found = truth.get(i, {}).get("entries", {})
        if not found:
            no_truth = True
        for index, (matched, _total) in found.items():
            covered[index] = max(covered.get(index, 0), matched)
    chosen = 0
    backed = 0
    for j in group["entries"]:
        chosen += entry_words.get(j, 0)
        if j in covered:
            backed += entry_words.get(j, 0)
    want = 0
    have = 0
    for index, matched in covered.items():
        want += matched
        if index in group["entries"]:
            have += matched
    truth_set = set()
    for i in group["segs"]:
        found = truth.get(i, {}).get("entries", {})
        for index, (matched, total) in found.items():
            if total and matched / total >= TRUTH_SHARE:
                truth_set.add(index)
    chosen_set = set(group["entries"])
    return {
        "precision": backed / chosen if chosen else 0.0,
        "recall": have / want if want else 0.0,
        "no_truth": no_truth,
        "strict": bool(truth_set) and chosen_set == truth_set,
        "lax": bool(chosen_set & truth_set),
    }


def summarize(groups, truth, entry_words, threshold=0.8):
    """Counts over all groups; `correct` needs both scores >= threshold."""
    correct = 0
    recovered = 0
    scores = []
    for group in groups:
        score = group_score(group, truth, entry_words)
        scores.append(score)
        if (score["precision"] >= threshold
                and score["recall"] >= threshold):
            correct += 1
            for i in group["segs"]:
                found = truth.get(i, {}).get("entries", {})
                for _index, (matched, _total) in found.items():
                    recovered += matched
    gold_words = 0
    for i in truth:
        found = truth[i].get("entries", {})
        for _index, (matched, _total) in found.items():
            gold_words += matched
    return {
        "groups": len(groups),
        "correct": correct,
        "scores": scores,
        "gold_word_recall": recovered / gold_words if gold_words else 0.0,
    }


def auc(positives, negatives):
    """Probability a positive scores above a negative (ties half).

    The area under the ROC curve, by the Mann-Whitney count; nan when
    a side is empty, because there is nothing to compare."""
    if not positives or not negatives:
        return float("nan")
    wins = 0.0
    for p in positives:
        for n in negatives:
            if p > n:
                wins += 1.0
            elif p == n:
                wins += 0.5
    return wins / (len(positives) * len(negatives))


def retention(good, bad, thresholds):
    """For each threshold: share of good kept, share of bad kept, and
    the precision of what is kept (score >= threshold keeps)."""
    table = []
    for threshold in thresholds:
        good_kept = sum(1 for s in good if s >= threshold)
        bad_kept = sum(1 for s in bad if s >= threshold)
        kept = good_kept + bad_kept
        table.append({
            "threshold": threshold,
            "good_kept": good_kept / len(good) if good else 0.0,
            "bad_kept": bad_kept / len(bad) if bad else 0.0,
            "precision": good_kept / kept if kept else 0.0,
        })
    return table
