#!/usr/bin/env python3
"""Check a batch of vision TSVs and import them into their work dir.

Two things are checked before anything is written, because both fail
silently otherwise:

  format   a blank cue is written as `12<TAB>han` when the trailing tab gets
           stripped, which the importer reads as a missing field
  mapping  every cue number must actually appear on a sheet the reader was
           given. A row for a cue outside that set means the reader drifted,
           and the text would land on the wrong subtitle -- far worse than a
           misread character, because nothing downstream looks wrong.
"""
import argparse
import glob
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = "/workspaces/Corpus-Cleanup/.claude/skills/video-subtitle-srt/scripts"
PY = os.path.expanduser("~/.venvs/subs2srt/bin/python")
WORK = "/workspaces/Corpus-Cleanup/kithann/out/mxf"


def normalise(path):
    """Restore the empty third field on confirmed-blank rows."""
    rows = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            parts = line.split("\t")
            while len(parts) < 3:
                parts.append("")
            rows.append("\t".join(parts[:3]))
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(rows) + "\n")
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("tsvdir")
    ap.add_argument("--suffix", default=".B.work",
                    help="work-dir suffix; .C.work is the 文稿 re-read pass")
    args = ap.parse_args()

    work = os.path.join(WORK, args.slug + args.suffix)
    with open(os.path.join(work, "sheets.json"), encoding="utf-8") as handle:
        sheets = json.load(handle)
    on_sheets = set()
    for cues in sheets.values():
        on_sheets.update(cues)

    files = sorted(glob.glob(os.path.join(args.tsvdir, "*.tsv")))
    seen = {}
    problems = []
    for path in files:
        for row in normalise(path):
            index = row.split("\t")[0]
            if not index.isdigit():
                problems.append("%s: bad index %r" % (path, index))
                continue
            index = int(index)
            if index not in on_sheets:
                problems.append("%s: cue %d was not on any sheet given to a "
                                "reader" % (path, index))
            if index in seen and seen[index] != path:
                problems.append("cue %d appears in both %s and %s"
                                % (index, os.path.basename(seen[index]),
                                   os.path.basename(path)))
            seen[index] = path

    if problems:
        for line in problems[:20]:
            print("PROBLEM", line)
        raise SystemExit("%d problem(s); nothing imported" % len(problems))

    missing = sorted(on_sheets - set(seen))
    print("%d TSV file(s), %d cue(s) read, %d of %d gap cues covered"
          % (len(files), len(seen), len(seen), len(on_sheets)))
    if missing:
        print("still unread: %d (e.g. %s)" % (len(missing), missing[:10]))

    for path in files:
        out = subprocess.run(
            [PY, os.path.join(SKILL, "subs2srt.py"), "import", work,
             "--from", path], capture_output=True, text=True)
        if out.returncode != 0:
            sys.stderr.write(out.stdout + out.stderr)
            raise SystemExit("import failed for %s" % path)
    print("imported")


if __name__ == "__main__":
    main()
