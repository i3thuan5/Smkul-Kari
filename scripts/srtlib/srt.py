#!/usr/bin/env python3
"""SRT text format: timestamps, rendering, parsing.

Shared by both sides of the pipeline -- the picture side renders the
delivered subtitles through this and the speech side renders the
bilingual SRTs -- so it lives beside the assembly chain, away from the
pixel engine.
"""


def srt_timestamp(seconds):
    if seconds < 0:
        seconds = 0.0
    total_ms = int(round(seconds * 1000.0))
    hours, total_ms = divmod(total_ms, 3600000)
    minutes, total_ms = divmod(total_ms, 60000)
    secs, millis = divmod(total_ms, 1000)
    return "%02d:%02d:%02d,%03d" % (hours, minutes, secs, millis)


def render_srt(entries):
    """entries: list of (start, end, text). Returns SRT text."""
    chunks = []
    number = 0
    for start, end, text in entries:
        body = text.strip()
        if not body:
            continue
        number += 1
        chunks.append("%d\n%s --> %s\n%s\n" % (
            number, srt_timestamp(start), srt_timestamp(end), body))
    return "\n".join(chunks)


def parse_srt(text):
    """Minimal SRT reader -- used by the self-test to check round trips."""
    entries = []
    blocks = text.replace("\r\n", "\n").strip().split("\n\n")
    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue
        start_s, _, end_s = lines[1].partition("-->")
        entries.append((
            _parse_ts(start_s.strip()),
            _parse_ts(end_s.strip()),
            "\n".join(lines[2:]).strip(),
        ))
    return entries


def _parse_ts(value):
    clock, _, millis = value.partition(",")
    hours, minutes, secs = clock.split(":")
    return (int(hours) * 3600 + int(minutes) * 60 + int(secs)
            + int(millis) / 1000.0)
