#!/usr/bin/env python3
"""Which file is this episode? The rules, and nothing but the rules.

`ilrdf-corpus.csv` lists sources in a column that is a **candidate list**,
not an identifier: one row can carry several paths separated by semicolons
-- the master and its transcode, and sometimes a couple of file names the
cataloguer was not sure about. 2021-02-06 晚間 排灣 lists four, and the
first of them is named 午間. A program with no policy takes the first one
and cuts the lunchtime broadcast into the evening episode's subtitles;
nothing downstream notices, because every step after this one only knows
the name it was handed.

So the policy is written down here, in four rules applied in order:

1. the master (`.mxf`) wins; if there is one, transcodes are not considered
2. the slot word in the file name must agree with the episode's slot. A word
   that is not a slot -- `五間`, a typo for `午間` -- means *no slot
   information*, never some other slot
3. what is left, if it is one file name sitting in two folders, is one
   source; take either
4. one file belongs to one episode: if two episodes both land on it,
   neither gets it

Anything still undecided is reported, not guessed. Rule 4 needs the whole
batch in hand -- judged episode by episode, whoever ran first would take the
file and the other would fail, which makes the outcome depend on iteration
order. `resolve()` therefore picks first and checks collisions afterwards.

No I/O here on purpose: this is the one place in the pipeline that can be
silently wrong, so it has to be exercisable with synthetic rows alone.
"""
import os
import re

from scripts import catalogue_checks as checks

# The Chinese word, not the NL code: 21NL004_37午間 carries the 晚間 series
# code on a 午間 file, and the word is the one that is right.
SLOT_RE = re.compile(r"(午間|晚間|晨間)")

MASTER_EXT = ".mxf"

# Not a verdict to be judged, just an episode the catalogue has no file for
# (沒影片的集數根本不進表). Compared by identity, so a caller
# can tell "nothing to decide" from "could not decide".
NO_SOURCE = "無來源"


def candidates(row):
    """Every path the catalogue lists for this episode."""
    out = []
    for part in (row.get("原始影片檔案位置") or "").split(";"):
        part = part.strip()
        if part:
            out.append(part)
    return out


def slot_of(path):
    """The broadcast slot the file name claims, or None if it claims none."""
    found = SLOT_RE.search(os.path.basename(path))
    if not found:
        return None
    return found.group(1)


def _masters_first(paths):
    """Rule 1."""
    masters = []
    for path in paths:
        if path.lower().endswith(MASTER_EXT):
            masters.append(path)
    return masters or paths


def _agreeing_slot(paths, slot):
    """Rule 2, and only when it discriminates.

    If no candidate names the episode's slot there is nothing to go on --
    the bare-timestamp names (`20220313s1100.mp4`) carry no slot word at
    all -- so the list is handed back untouched rather than emptied.
    """
    named = []
    for path in paths:
        if slot_of(path) == slot:
            named.append(path)
    return named or paths


def _one_name_in_two_folders(paths):
    """Rule 3: same file name, different folder, is the same file."""
    names = set()
    for path in paths:
        names.add(os.path.basename(path))
    if len(names) == 1:
        return paths[:1]
    return paths


def pick(row):
    """(path, problem) for one episode, rules 1-3.

    `problem` is "" when a source was chosen, `NO_SOURCE` when the catalogue
    lists none, and otherwise a sentence naming what was left over -- the
    caller has to be able to put it in a report and act on it.

    A lone candidate is taken even if its file name disagrees about the slot:
    that is the only thing the catalogue offers for the episode, and the
    byte-count check and `verify_band` still stand behind it. Rejecting it
    would drop episodes over what is, in every observed case, a typo in the
    catalogue rather than a wrong file.
    """
    paths = candidates(row)
    if not paths:
        return None, NO_SOURCE
    paths = _masters_first(paths)
    if len(paths) > 1:
        paths = _agreeing_slot(paths, checks.slot_of(row["節目名稱"]))
    if len(paths) > 1:
        paths = _one_name_in_two_folders(paths)
    if len(paths) == 1:
        return paths[0], ""
    return None, "揀袂出來，賰 %d 條候選：%s" % (len(paths), "、".join(paths))


def resolve(rows):
    """[(path, problem)] for a whole batch, rules 1-4, in the order given.

    Rule 4 lives here rather than in `pick` because it is the only one that
    needs to see more than one episode.
    """
    picked = []
    for row in rows:
        picked.append(pick(row))

    taken = {}
    for path, _ in picked:
        if path:
            taken[path] = taken.get(path, 0) + 1

    out = []
    for path, problem in picked:
        if path and taken[path] > 1:
            out.append((None, "%s 予兩集以上選著：一支檔干焦准一集用"
                        % path))
        else:
            out.append((path, problem))
    return out


# What the pipeline's own archive writes. `archive_batch.py` encodes each
# master to this once and verifies it, so by the time an episode has been
# delivered there is a faithful, much smaller copy of it to read from.
ARCHIVE_EXT = ".mkv"


def reading_copy(row, archived=None):
    """The file to read this episode's subtitles from: mkv, then mxf, then mp4.

    使用者裁定 -- the order used to be master-then-transcode, and for
    *cutting* an episode that is still right: the mxf is what the cues and
    the delivered timings come from.

    But re-reading a delivered episode -- checking what the contact sheet's
    median composite washed out -- only ever touches the subtitle band's
    pixels, and our own archive mkv (CRF 23, 1920x1080, byte-verified on
    upload) carries those intact. Measured on 20210222_053 cue 201: the line
    the sheet hid, 「保障孩子安全」, reads identically off the 1.9 GB mkv and
    the 19 GB mxf. Across February that is 665 GB of downloads against none,
    since the mkvs are already on this disk.

    `archived` is the path to that mkv, or None/"" when the episode has not
    been archived. The caller looks it up -- this module stays free of I/O
    so the four rules can be exercised on synthetic rows alone.
    """
    if archived:
        return archived
    return pick(row)[0]
