#!/usr/bin/env python3
"""Read the 文稿 (news scripts) that ship with the corpus as Big5 RTF.

The burned-in Chinese subtitle is the narration from these scripts broken
into subtitle-length lines, so the script is a far better source of text than
any recogniser -- provided each cue can be tied back to the right stretch of
it. This module only does the reading and cleaning; the tying-back lives in
align.py.

The files are RTF 1.0 with `\\'xx` escapes and `\\fcharset136`, i.e. Big5,
despite the `\\ansicpg1252` in the header. Decoding them as cp1252 yields
mojibake, so the escapes are turned back into bytes and decoded as Big5.
"""
import os
import re

# Production markup that never reaches the screen as dialogue.
MARKUP = re.compile(r"\[\[.*?\]\]", re.S)
SECTION = re.compile(r"^\s*(##|&&)\s*$", re.M)

CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")


def rtf_text(path):
    """Decode one Big5 RTF into plain text."""
    raw = open(path, "rb").read().decode("latin-1")
    raw = re.sub(
        r"\{\\(?:fonttbl|colortbl|stylesheet|info|\*)[^{}]*"
        r"(?:\{[^{}]*\}[^{}]*)*\}", "", raw)
    out = bytearray()
    i = 0
    while i < len(raw):
        ch = raw[i]
        if ch == "\\":
            nxt = raw[i + 1:i + 2]
            if nxt == "'":
                out.append(int(raw[i + 2:i + 4], 16))
                i += 4
                continue
            match = re.match(r"\\(par|line|pard|tab)\b ?", raw[i:])
            if match:
                out.extend(b"\n")
                i += match.end()
                continue
            match = re.match(r"\\[a-zA-Z]+-?\d* ?", raw[i:])
            if match:
                i += match.end()
                continue
            out.extend(raw[i + 1:i + 2].encode("latin-1"))
            i += 2
            continue
        if ch in "{}":
            i += 1
            continue
        out.extend(ch.encode("latin-1"))
        i += 1
    return out.decode("big5", "replace")


def is_cjk_line(line):
    """True when a line is mostly Han characters.

    Each script carries the story twice: once in Chinese and once in the
    indigenous language in Latin script. Only the Chinese is burned in as the
    dialogue subtitle, so the Latin lines are dropped.
    """
    letters = 0
    han = 0
    for ch in line:
        if ch.isalpha():
            letters += 1
            if CJK.match(ch):
                han += 1
    if letters == 0:
        return False
    return han >= letters * 0.5


def clean(text):
    """Strip production markup and the indigenous-language lines."""
    text = MARKUP.sub("\n", text)
    text = SECTION.sub("\n", text)
    lines = []
    for line in text.splitlines():
        line = line.strip().strip("()（）")
        if not line:
            continue
        if not is_cjk_line(line):
            continue
        lines.append(line)
    return lines


def episode_text(folder):
    """All Chinese lines of one episode's 文稿 folder, file by file."""
    items = []
    if not folder or not os.path.isdir(folder):
        return items
    for name in sorted(os.listdir(folder)):
        if not name.lower().endswith(".rtf"):
            continue
        path = os.path.join(folder, name)
        try:
            lines = clean(rtf_text(path))
        except Exception as exc:                     # noqa: BLE001
            print("  ! cannot read %s: %s" % (name, exc))
            continue
        if lines:
            items.append({"file": name, "lines": lines})
    return items


if __name__ == "__main__":
    import sys
    folder = sys.argv[1]
    total = 0
    for item in episode_text(folder):
        chars = sum(len(x) for x in item["lines"])
        total += chars
        print("%-46s %3d lines %5d chars" % (item["file"][:46],
                                             len(item["lines"]), chars))
        for line in item["lines"][:3]:
            print("      ", line[:70])
    print("total %d chars" % total)
