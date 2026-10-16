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
lists are indexes that touched nothing on the other side. A lonely
segment lying between a group's first and last segment is filled into
that group.
"""

from scripts.errors import PipelineError
from scripts.srtlib import assemble

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
    groups, lonely_segs, lonely_entries = _collect(union, segments, entries)
    return _fill_holes(groups, lonely_segs) + (lonely_entries,)


def _fill_holes(groups, lonely_segs):
    """Lonely segments between a group's first and last one join it.

    A long subtitle over several short VAD segments gives each under
    the merge threshold; nobody picks the middle ones, yet they lie in
    the group's time, so its Formosan would miss speech its window
    holds. Segments outside every group's first..last stay lonely.
    """
    lonely = set(lonely_segs)
    for group in groups:
        first, last = group["segs"][0], group["segs"][-1]
        for i in range(first + 1, last):
            if i in lonely:
                group["segs"].append(i)
                lonely.discard(i)
        group["segs"].sort()
    return groups, sorted(lonely)


def span(group, segments):
    """(start, end) of the group's speech -- the true VAD edges.

    Subtitles are left out: their switch points do not follow the
    Formosan, and counting them made neighbours overlap (5,393 times in
    the 133 episodes of 2021-01..02). This is the time the pairing, the
    calibration's opening window and the features use; the padded time
    the CSV shows is `padded_spans`.
    """
    starts, ends = [], []
    for i in group["segs"]:
        starts.append(segments[i]["start"])
        ends.append(segments[i]["end"])
    return min(starts), max(ends)


def padded_spans(groups, segments, duration):
    """[(start, end)] per group: its speech padded 0.5 s a side.

    Every VAD segment of the episode is a neighbour -- the other groups,
    dropped or not, and the segments no group took: all of it is
    someone speaking, and padding into it frames another voice. The
    whole timeline goes through the same `pad_edges` the delivered SRTs
    use, so closer than 1 s meets at the midpoint, clamped to
    [0, duration]. True spans that overlap are refused: midpoint
    stitching would hide that they were not made by `span`.
    """
    timeline = []
    taken = set()
    for number, group in enumerate(groups):
        start, end = span(group, segments)
        timeline.append((start, end, number))
        taken.update(group["segs"])
    for i, segment in enumerate(segments):
        if i not in taken:
            timeline.append((segment["start"], segment["end"], None))
    timeline.sort(key=lambda item: (item[0], item[1]))
    for before, after in zip(timeline, timeline[1:]):
        if after[0] < before[1] - EPSILON:
            raise PipelineError(
                "語音範圍重疊：%.3f–%.3f 與 %.3f–%.3f，組的時間不是照真實語音段算的"
                % (before[0], before[1], after[0], after[1]))
    padded = assemble.pad_edges(timeline, duration=duration)
    out = [None] * len(groups)
    for start, end, number in padded:
        if number is not None:
            out[number] = (start, end)
    return out
