#!/usr/bin/env python3
"""Picking the merge threshold from Claude's grades on news samples.

A *location* is the boundary between two neighbouring recognised
segments that some subtitle straddles. The largest share a straddling
subtitle leaves on the smaller side puts the location in a bucket
(0–10, 10–20, 20–30, 30–40, 40–50%); a threshold t merges exactly the
locations whose share is ≥ t, so moving t across a bucket changes only
the locations in it, and each bucket is judged on its own.

Per location three groups are judged, the pair isolated from its other
neighbours: G (both segments merged), A and B (split, the straddler on
the side it overlaps more). G and A/B go to different batches so the
judge never sees the two versions side by side. A version is worth its
Formosan words × (高 1, 中 0.5, 低 0) -- the corpus is worth the usable
words it keeps, not the number of groups.

Per bucket, p = merge-better ÷ (merge-better + split-better), ties left
out; the Wilson 95% interval of p entirely above 0.5 means merging is
better, entirely below means splitting is, otherwise undecided. The
threshold is the lowest candidate t such that no bucket from t upward
is split-better; undecided counts in favour of merging (使用者裁定
2026-09-24: 分不出勝負時以較低的門檻為主).
"""
import math
import random

from scripts.errors import PipelineError
from scripts.mt import overlap

BUCKETS = 5
CANDIDATES = (0.1, 0.2, 0.3, 0.4)
MAX_ROW = 1800
LABELS = ("高", "中", "低")
WEIGHT = {"高": 1.0, "中": 0.5, "低": 0.0}
MERGE_BETTER = "合併較好"
SPLIT_BETTER = "拆開較好"
SAME = "一樣"
UNDECIDED = "分不出"
EPSILON = 1e-9


def bucket_of(share):
    return min(int(share * 10 + EPSILON), BUCKETS - 1)


def locations(segments, entries):
    """Every straddled boundary: segs, the two sides' subtitles, bucket."""
    per_entry = {}
    for link in overlap.links(segments, entries):
        per_entry.setdefault(link["entry"], {})[link["seg"]] = \
            link["frac_entry"]
    base, _, _ = overlap.max_overlap_groups(segments, entries)
    home = {}
    for group in base:
        for j in group["entries"]:
            home[j] = group["segs"][0]
    shares = {}
    for j, fracs in per_entry.items():
        for i in fracs:
            if i + 1 in fracs:
                share = min(fracs[i], fracs[i + 1])
                if share > shares.get(i, -1.0):
                    shares[i] = share
    out = []
    for i in sorted(shares):
        side_a = []
        side_b = []
        for j in sorted(home):
            if home[j] == i:
                side_a.append(j)
            elif home[j] == i + 1:
                side_b.append(j)
        # a straddler owned by a third segment leaves this pair with
        # nothing to judge
        if not side_a and not side_b:
            continue
        out.append({"boundary": i, "share": shares[i],
                    "bucket": bucket_of(shares[i]),
                    "entries_a": side_a, "entries_b": side_b})
    return out


def versions(location):
    """(G, A, B) groups; a side with no subtitle is None."""
    i = location["boundary"]
    merged = {"segs": [i, i + 1],
              "entries": sorted(location["entries_a"]
                                + location["entries_b"])}
    part_a = None
    if location["entries_a"]:
        part_a = {"segs": [i], "entries": list(location["entries_a"])}
    part_b = None
    if location["entries_b"]:
        part_b = {"segs": [i + 1], "entries": list(location["entries_b"])}
    return merged, part_a, part_b


def sample(pool, per_bucket, seed):
    """(chosen, short): per bucket, `per_bucket` items by a fixed seed;
    buckets with fewer are taken whole and reported {bucket: count}."""
    rng = random.Random(seed)
    by_bucket = {}
    for item in pool:
        by_bucket.setdefault(item["bucket"], []).append(item)
    chosen = []
    short = {}
    for bucket in sorted(by_bucket):
        items = sorted(by_bucket[bucket], key=lambda item: item["key"])
        if len(items) <= per_bucket:
            if len(items) < per_bucket:
                short[bucket] = len(items)
            chosen.extend(items)
            continue
        chosen.extend(rng.sample(items, per_bucket))
    return chosen, short


def too_long(line):
    """The Read tool truncates long lines; such a location is not asked."""
    return len(line) > MAX_ROW


def batches(items, size=200, part=50):
    """[[part, …], …]: merged items and split items never share a batch."""
    merged = []
    split = []
    for item in items:
        if item["kind"] == "G":
            merged.append(item)
        else:
            split.append(item)
    out = []
    for pool in (merged, split):
        for start in range(0, len(pool), size):
            chunk = pool[start:start + size]
            parts = []
            for inner in range(0, len(chunk), part):
                parts.append(chunk[inner:inner + part])
            out.append(parts)
    return out


def ingest(ids, text):
    """{id: label} for a reply that answers exactly `ids`, or a refusal
    naming what is wrong -- a half-taken batch lands grades on the wrong
    groups (the kaldi line's rule)."""
    found = {}
    problems = []
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        key = parts[0].strip()
        if not key.isdigit():
            problems.append("編號不是數字：%r" % key)
            continue
        number = int(key)
        label = parts[1].strip() if len(parts) > 1 else ""
        if label not in LABELS:
            problems.append("%d 的標籤是 %r" % (number, label))
        if number in found:
            problems.append("%d 重複" % number)
        found[number] = label
    wanted = set(ids)
    missing = sorted(wanted - set(found))
    extra = sorted(set(found) - wanted)
    if missing:
        problems.append("缺 %s" % "、".join(str(n) for n in missing))
    if extra:
        problems.append("多出 %s" % "、".join(str(n) for n in extra))
    if problems:
        raise PipelineError("回覆整批退回：%s" % "；".join(problems))
    return found


def _worth(version):
    if version is None:
        return 0.0
    label, words = version
    return words * WEIGHT[label]


def outcome(merged, part_a, part_b):
    """Each argument is (label, words) or None for a missing side."""
    whole = _worth(merged)
    parts = _worth(part_a) + _worth(part_b)
    if whole > parts + EPSILON:
        return MERGE_BETTER
    if whole < parts - EPSILON:
        return SPLIT_BETTER
    return SAME


def wilson(successes, total, z=1.96):
    """Wilson score interval of a proportion."""
    if total == 0:
        return 0.0, 1.0
    p = successes / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    half = z * math.sqrt(p * (1 - p) / total
                         + z * z / (4 * total * total)) / denominator
    return centre - half, centre + half


def verdict(merge_better, split_better):
    low, high = wilson(merge_better, merge_better + split_better)
    if merge_better + split_better == 0:
        return UNDECIDED
    if low > 0.5:
        return MERGE_BETTER
    if high < 0.5:
        return SPLIT_BETTER
    return UNDECIDED


def choose(verdicts):
    """The lowest candidate with no split-better bucket from it upward;
    None (never merge) if even the top bucket is split-better."""
    for threshold in CANDIDATES:
        first = bucket_of(threshold)
        fine = True
        for bucket in range(first, BUCKETS):
            if verdicts.get(bucket) == SPLIT_BETTER:
                fine = False
        if fine:
            return threshold
    return None
