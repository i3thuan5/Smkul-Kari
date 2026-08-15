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

# Working copy of the progress table, refreshed by make_all as often as you
# like. The delivered one lives in Kari-SRT and is written only by publish,
# once a whole batch is done: mid-batch a row says which step an episode is
# stuck at, and that lives in the work dir, which rebuild does not have -- so
# a mid-batch table in the store could never be rebuilt byte-for-byte.
TRACKER_CACHE = os.path.join(ROOT, "kithann", "out", "smkul.csv")

# Kari-SRT is the submodule holding the canonical data, layered
# corpus -> technique -> numbered stage (the numbers are the production
# order): news/1-ocr/ is the picture side, news/2-asr/ the speech side.
# kithann/ holds only sources and regenerable caches.
KARI = os.path.join(ROOT, "Kari-SRT")
NEWS_STORE = os.path.join(KARI, "news")
OCR_STORE = os.path.join(NEWS_STORE, "1-ocr")
ASR_DIR = os.path.join(NEWS_STORE, "2-asr")
KARI_CUES = os.path.join(OCR_STORE, "1-cues")
KARI_FROM_RTF = os.path.join(OCR_STORE, "2-from_rtf")
KARI_VISION = os.path.join(OCR_STORE, "3-vision")
KARI_VISION_RTF = os.path.join(OCR_STORE, "4-vision-rtf")
KARI_REPORT = os.path.join(OCR_STORE, "5-report")
SRT_DIR = os.path.join(OCR_STORE, "6-srt")

# The delivered progress table sits at the corpus level: it lists both
# techniques' per-episode state, so it belongs to neither directory.
TRACKER_STORE = os.path.join(NEWS_STORE, "smkul.csv")

# presets.json is corpus knowledge -- which programme is laid out how -- so it
# is part of the code and lives beside it. inventory.json is derived data (the
# catalogue, resolved against the files that actually arrived), so its one
# copy belongs in the store with everything else that is derived. There used
# to be a second copy here, and publish kept them in step by overwriting one
# with the other; two copies of the same truth is a synchronisation problem
# nobody asked for.
ENGINE_PRESETS = os.path.join(HERE, "presets.json")
INVENTORY = os.path.join(NEWS_STORE, "inventory.json")
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
