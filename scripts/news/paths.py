#!/usr/bin/env python3
"""Every path the news pipeline touches, in one place.

ROOT is derived from this file's location, so a clone works wherever it is
checked out -- the previous layout had 17 hard-coded absolute paths pointing
at a workspace name that no longer exists, and nothing failed until run time.

The corpus mount is the single deliberate exception: it lives outside the
repo, so it is an absolute path, overridable with the ILRDF_CORPUS
environment variable.

Shell scripts read values through the CLI:

    python3 -m scripts.news.paths --var WORK
"""
import argparse
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))

CORPUS = os.environ.get("ILRDF_CORPUS", "/home/vscode/ilrdf-corpus")

WORK = os.path.join(ROOT, "kithann", "out", "mxf")
LOGS = os.path.join(ROOT, "kithann", "out", "mxf-logs")

# Kari-SRT is the submodule holding the canonical data: delivered SRTs,
# per-episode timing, and the vision transcripts. kithann/ holds only
# sources and regenerable caches.
KARI = os.path.join(ROOT, "Kari-SRT")
SRT_DIR = os.path.join(KARI, "srt")
KARI_CUES = os.path.join(KARI, "cues")
KARI_FROM_RTF = os.path.join(KARI, "from_rtf")
KARI_VISION = os.path.join(KARI, "vision")
KARI_VISION_RTF = os.path.join(KARI, "vision-rtf")

ENGINE_PRESETS = os.path.join(HERE, "presets.json")
INVENTORY = os.path.join(HERE, "inventory.json")
CATALOGUE = os.path.join(ROOT, "kithann", "tongan", "ilrdf-corpus.csv")

VENV_PY = os.path.expanduser("~/.venvs/subs2srt/bin/python")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--var", required=True,
                    help="name of the path constant to print, e.g. WORK")
    args = ap.parse_args()
    value = globals().get(args.var)
    if not isinstance(value, str):
        known = []
        for name in sorted(globals()):
            if name.isupper() and isinstance(globals()[name], str):
                known.append(name)
        raise SystemExit("no path named %r (have: %s)"
                         % (args.var, ", ".join(known)))
    print(value)


if __name__ == "__main__":
    main()
