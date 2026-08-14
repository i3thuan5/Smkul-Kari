#!/usr/bin/env python3
"""Reading a work dir and turning cues plus text into SRT entries.

Bookkeeping and plain text arithmetic, no pixels and no recogniser. It is
separate from the command line because the news pipeline calls these
directly -- assembling an episode is not a thing you should have to spawn a
CLI to do.
"""
import json
import os
import sys


def read_manifest(workdir):
    path = os.path.join(workdir, "cues.json")
    if not os.path.exists(path):
        raise SystemExit("no cues.json in %s -- run the `cues` stage first"
                         % workdir)
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def load_transcripts(workdir):
    path = os.path.join(workdir, "transcripts.json")
    if not os.path.exists(path):
        raise SystemExit("no transcripts.json in %s -- run `ocr` first"
                         % workdir)
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


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
        if merged and merged[-1][2] == text:
            if start - merged[-1][1] <= max_gap:
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


def parse_transcript_tsv(text, default_line):
    """Read `index <TAB> [line <TAB>] text` rows into a transcript dict.

    This is the hand-off for reading the contact sheets with a vision model
    (see SKILL.md): the sheets carry the cue numbers, so the reader only has
    to type a number and the text it can see.
    """
    out = {}
    errors = []
    for number, raw in enumerate(text.replace("\r\n", "\n").split("\n"), 1):
        row = raw.rstrip("\n")
        if not row.strip() or row.lstrip().startswith("#"):
            continue
        parts = row.split("\t")
        if len(parts) < 2:
            errors.append("line %d: need at least index<TAB>text" % number)
            continue
        key = parts[0].strip()
        if not key.isdigit():
            errors.append("line %d: %r is not a cue index" % (number, key))
            continue
        if len(parts) == 2:
            name, value = default_line, parts[1]
        else:
            name, value = parts[1].strip(), "\t".join(parts[2:])
        out.setdefault(key, {})[name] = value.strip()
    return out, errors


VERIFIED_NAME = "verified.json"


def import_tsv(workdir, source, replace=False):
    """Load a TSV of read-off-the-sheet text into a work dir.

    Returns (imported cue count, cues now covered, cue total). Raises
    SystemExit naming every problem if any row is unusable -- and imports
    nothing at all in that case. A partial import is the worst outcome
    available: the rows that landed look no different from the rows that did
    not, so nobody can tell afterwards which half was read.

    The two things checked are the two that fail silently otherwise: a cue
    number that is not in this episode, and a line name that is not one of
    its lines. Both would otherwise put text on the wrong subtitle, which
    nothing downstream can detect.
    """
    manifest = read_manifest(workdir)
    default_line = manifest["lines"][0]["name"]
    known = set()
    for line in manifest["lines"]:
        known.add(line["name"])
    valid = set()
    for cue in manifest["cues"]:
        valid.add(str(cue["index"]))

    with open(source, "r", encoding="utf-8") as handle:
        parsed, errors = parse_transcript_tsv(handle.read(), default_line)

    for key in sorted(parsed):
        if key not in valid:
            errors.append("cue %s is not in cues.json" % key)
        for name in parsed[key]:
            if name not in known:
                errors.append("cue %s: unknown line name %r (known: %s)"
                              % (key, name, ", ".join(sorted(known))))
    if errors:
        for message in errors[:20]:
            sys.stderr.write("  %s\n" % message)
        raise SystemExit("%d problem(s) in %s; nothing imported"
                         % (len(errors), source))

    path = os.path.join(workdir, "transcripts.json")
    existing = {}
    if os.path.exists(path) and not replace:
        with open(path, "r", encoding="utf-8") as handle:
            existing = json.load(handle)
    for key in parsed:
        existing.setdefault(key, {}).update(parsed[key])
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(existing, handle, ensure_ascii=False, indent=1)

    # Record which rows a human actually looked at. export-gt trusts only
    # these, so a recogniser's own mistakes can never become training labels.
    verified = load_verified(workdir)
    for key in parsed:
        for name in parsed[key]:
            verified.setdefault(key, {})[name] = True
    save_verified(workdir, verified)

    covered = 0
    for cue in manifest["cues"]:
        if existing.get(str(cue["index"])):
            covered += 1
    return len(parsed), covered, len(manifest["cues"])


def load_verified(workdir):
    path = os.path.join(workdir, VERIFIED_NAME)
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def save_verified(workdir, verified):
    path = os.path.join(workdir, VERIFIED_NAME)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(verified, handle, ensure_ascii=False, indent=1)


SPECIAL_MARKS = "^\'\":"


def glossary_tokens(text):
    """Pull out the words whose spelling batches are likely to disagree on."""
    found = []
    for raw in text.replace("\u3000", " ").split():
        word = raw.strip(".,!?()[]")
        if len(word) < 2:
            continue
        special = False
        for mark in SPECIAL_MARKS:
            if mark in word:
                special = True
                break
        proper = word[:1].isupper() and word[:1].isalpha()
        if special or proper:
            found.append(word)
    return found
