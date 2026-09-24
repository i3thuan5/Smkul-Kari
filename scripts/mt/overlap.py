#!/usr/bin/env python3
"""Grouping speech segments with subtitle entries by time overlap.

Each subtitle goes to the one segment it overlaps most (the same rule
`asrmt.project` uses for words); two segments are fused only when a
subtitle genuinely straddles them -- `straddle_frac` of its own length
in each. "Anything that overlaps anything is one group" was tried and
dropped: on the news corpus it welded 31,249 groups across several
segments, the longest 495 s, because a subtitle spilling a tenth of a
second into the next VAD segment links the two paragraphs.

`max_overlap_groups` returns (groups, lonely_segments, lonely_entries):
groups are {"segs": [...], "entries": [...]} in time order; the lonely
lists are indexes that touched nothing on the other side.
"""

EPSILON = 1e-9


def overlap(a_start, a_end, b_start, b_end):
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def links(segments, entries, min_frac=0.0):
    """Every (segment, entry) pair with positive overlap.

    Each link carries the overlap in seconds and as a fraction of the
    entry's and of the segment's own length. A link below `min_frac` of
    the entry's length is dropped.
    """
    out = []
    position = 0
    order = sorted(range(len(entries)), key=lambda j: entries[j][
        "true_start"])
    for i, seg in enumerate(segments):
        while (position < len(order)
               and entries[order[position]]["true_end"] <= seg["start"]):
            position += 1
        cursor = position
        while cursor < len(order):
            entry = entries[order[cursor]]
            if entry["true_start"] >= seg["end"]:
                break
            seconds = overlap(seg["start"], seg["end"],
                              entry["true_start"], entry["true_end"])
            cursor += 1
            if seconds <= 0.0:
                continue
            entry_len = entry["true_end"] - entry["true_start"]
            seg_len = seg["end"] - seg["start"]
            frac_entry = seconds / entry_len if entry_len > 0 else 1.0
            if frac_entry < min_frac:
                continue
            out.append({"seg": i, "entry": order[cursor - 1],
                        "seconds": seconds, "frac_entry": frac_entry,
                        "frac_seg": seconds / seg_len if seg_len > 0
                        else 1.0})
    return out


class _Union(object):
    def __init__(self):
        self.parent = {}

    def find(self, node):
        root = node
        while self.parent.setdefault(root, root) != root:
            root = self.parent[root]
        while self.parent[node] != root:
            self.parent[node], node = root, self.parent[node]
        return root

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def _collect(union, segments, entries):
    """Groups from a union-find, in time order, lonely sides apart."""
    members = {}
    for i in range(len(segments)):
        members.setdefault(union.find(("s", i)), []).append(("s", i))
    for j in range(len(entries)):
        members.setdefault(union.find(("e", j)), []).append(("e", j))
    groups, lonely_segs, lonely_entries = [], [], []
    for nodes in members.values():
        segs, ents = [], []
        for kind, index in nodes:
            if kind == "s":
                segs.append(index)
            else:
                ents.append(index)
        segs.sort()
        ents.sort()
        if not ents:
            lonely_segs.extend(segs)
            continue
        if not segs:
            lonely_entries.extend(ents)
            continue
        groups.append({"segs": segs, "entries": ents})
    groups.sort(key=lambda g: (segments[g["segs"][0]]["start"],
                               g["segs"][0]))
    return groups, sorted(lonely_segs), sorted(lonely_entries)


def max_overlap_groups(segments, entries, straddle_frac=None):
    """Each entry joins the segment it overlaps most; ties go earlier.

    With `straddle_frac`, an entry that overlaps two segments by at
    least that fraction of its own length in each fuses them -- the
    subtitle really spans the VAD boundary, so the paragraph does too.
    """
    best = {}
    heavy = {}
    for link in links(segments, entries):
        j = link["entry"]
        current = best.get(j)
        if current is None or link["seconds"] > current[0] + 1e-9:
            best[j] = (link["seconds"], link["seg"])
        # 1.2 s of a 4 s subtitle is 0.2999999… in floating point; a
        # share exactly at the threshold has to count as reaching it
        if (straddle_frac is not None
                and link["frac_entry"] >= straddle_frac - EPSILON):
            heavy.setdefault(j, []).append(link["seg"])
    union = _Union()
    for j, (_seconds, i) in best.items():
        union.union(("e", j), ("s", i))
    for j, segs in heavy.items():
        for i in segs[1:]:
            union.union(("s", segs[0]), ("s", i))
    return _collect(union, segments, entries)


def span(group, segments, entries):
    """(start, end) covering every member of the group."""
    starts, ends = [], []
    for i in group["segs"]:
        starts.append(segments[i]["start"])
        ends.append(segments[i]["end"])
    for j in group["entries"]:
        starts.append(entries[j]["true_start"])
        ends.append(entries[j]["true_end"])
    return min(starts), max(ends)
