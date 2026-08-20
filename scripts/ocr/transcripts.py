#!/usr/bin/env python3
"""The vision transcript ledger: TSV in, transcripts.json + verified.json.

Reading a work dir and importing what the vision pass read off the
contact sheets. Whole-batch rejection on any bad row; verified.json
records which rows a human actually looked at.
"""
import json
import os
import sys
from scripts.errors import PipelineError


def read_manifest(workdir):
    path = os.path.join(workdir, "cues.json")
    if not os.path.exists(path):
        raise PipelineError("no cues.json in %s -- run the `cues` stage first"
                            % workdir)
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def load_transcripts(workdir):
    path = os.path.join(workdir, "transcripts.json")
    if not os.path.exists(path):
        raise PipelineError("no transcripts.json in %s -- run `ocr` first"
                            % workdir)
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


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
    PipelineError naming every problem if any row is unusable -- and imports
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
    _collect_row_errors(parsed, valid, known, errors)
    if errors:
        for message in errors[:20]:
            sys.stderr.write("  %s\n" % message)
        raise PipelineError("%d problem(s) in %s; nothing imported"
                            % (len(errors), source))

    existing = _merge_transcripts(workdir, parsed, replace)
    _mark_verified(workdir, parsed)

    covered = 0
    for cue in manifest["cues"]:
        if existing.get(str(cue["index"])):
            covered += 1
    return len(parsed), covered, len(manifest["cues"])


def _collect_row_errors(parsed, valid, known, errors):
    for key in sorted(parsed):
        if key not in valid:
            errors.append("cue %s is not in cues.json" % key)
        for name in parsed[key]:
            if name not in known:
                errors.append("cue %s: unknown line name %r (known: %s)"
                              % (key, name, ", ".join(sorted(known))))


def _merge_transcripts(workdir, parsed, replace):
    path = os.path.join(workdir, "transcripts.json")
    existing = {}
    if os.path.exists(path) and not replace:
        with open(path, "r", encoding="utf-8") as handle:
            existing = json.load(handle)
    for key in parsed:
        existing.setdefault(key, {}).update(parsed[key])
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(existing, handle, ensure_ascii=False, indent=1)
    return existing


def _mark_verified(workdir, parsed):
    """Record which rows a human actually looked at. export-gt trusts
    only these, so a recogniser's own mistakes can never become training
    labels."""
    verified = load_verified(workdir)
    for key in parsed:
        for name in parsed[key]:
            verified.setdefault(key, {})[name] = True
    save_verified(workdir, verified)


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
