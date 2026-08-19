#!/usr/bin/env python3
"""Turning timed cues plus text into SRT entries: the assembly chain.

Shared by both sides of the pipeline. The delivered subtitles and the
bilingual SRTs must carry identical timestamps, and they do because both
run through these very functions -- merge, gap rules, then edge padding
last (the CLAUDE.md 0.5s rule).
"""


def chain_with_spans(entries, merge_gap=1.0, min_gap=0.04, pad=0.5,
                     duration=None):
    """Run the assembly chain, keeping each entry's true window.

    Returns one dict per final entry: `true_start`/`true_end` are the
    merged span before gap rules and padding (the union of the source
    cues -- what word projection and the alignment check must use), and
    `srt_start`/`srt_end` are the display timestamps after both. Same
    operations in the same order as the delivered SRTs, so rendering
    from these rows is byte-identical to the old pipeline.
    """
    merged = merge_repeats(entries, merge_gap)
    trimmed = apply_gap_rules(merged, min_gap)
    padded = pad_edges(trimmed, pad=pad, duration=duration)
    rows = []
    for i, (true_start, true_end, text) in enumerate(merged):
        srt_start, srt_end, _ = padded[i]
        rows.append({
            "index": i + 1,
            "true_start": true_start, "true_end": true_end,
            "srt_start": srt_start, "srt_end": srt_end,
            "text": text,
        })
    return rows


def merge_repeats(entries, max_gap=1.0):
    """Fuse consecutive cues that carry exactly the same text.

    One burned-in subtitle gets split into several cues whenever the footage
    behind it moves enough to shift the mask -- video B does this constantly,
    because its glyphs sit straight on the picture. The recognised text is
    the honest arbiter of whether that was one subtitle or two, so repair it
    here instead of by loosening the pixel threshold, which would start
    swallowing genuinely different lines.
    """
    merged = []
    for start, end, text in entries:
        if (merged and merged[-1][2] == text
                and start - merged[-1][1] <= max_gap):
            merged[-1] = [merged[-1][0], max(end, merged[-1][1]), text]
            continue
        merged.append([start, end, text])
    out = []
    for start, end, text in merged:
        out.append((start, end, text))
    return out


def apply_gap_rules(entries, min_gap):
    """Stop adjacent cues from overlapping once times are rounded to ms."""
    fixed = []
    for index, (start, end, text) in enumerate(entries):
        if index + 1 < len(entries):
            nxt = entries[index + 1][0]
            if end > nxt - min_gap:
                end = max(start + 0.05, nxt - min_gap)
        fixed.append((start, end, text))
    return fixed


def pad_edges(entries, pad=0.5, duration=None):
    """Extend every entry into the silence around it, per the CLAUDE.md rule.

    Each side grows by up to `pad` seconds so downstream speech tooling gets
    the edge silence it wants to keep (Kaldi's segment_ctm_edits.py retains
    at most 0.5s per edge). Where two entries sit closer than 2*pad they
    meet at the midpoint of the true gap -- touching exactly, never
    overlapping -- and the result is clamped to [0, duration]. Must run
    LAST in assembly: apply_gap_rules would pull a midpoint-touching pair
    apart again.

    The stored cue data keeps the true switch points; this is display-only.
    """
    padded = []
    for index, (start, end, text) in enumerate(entries):
        if index:
            gap = start - entries[index - 1][1]
            start = start - min(pad, gap / 2.0)
        else:
            start = start - pad
        if index + 1 < len(entries):
            gap = entries[index + 1][0] - end
            end = end + min(pad, gap / 2.0)
        else:
            end = end + pad
        start = max(0.0, start)
        if duration is not None:
            end = min(duration, end)
        padded.append((start, end, text))
    return padded
