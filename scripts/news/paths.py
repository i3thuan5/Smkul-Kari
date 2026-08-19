#!/usr/bin/env python3
"""Every path the news corpus touches, in one place.

Nothing here is absolute: every value is derived from ROOT, which
`scripts.datadirs` derives from the checkout's own location, so a clone
works wherever it sits -- the previous layout had 17 hard-coded absolute
paths pointing at a workspace name that no longer exists, and nothing
failed until run time.

The repo layout itself (ROOT, kithann/, Kari-SRT/) and the CLI argument
guards live in `scripts.datadirs`, because the ocr engine needs them too
and deliberately does not depend on this package; they are re-exported
here so existing `paths.X` call sites keep working. What stays here is
corpus-specific: which stage folder holds what.

Everything is inside the checkout. The corpus mount used to be a
deliberate exception; the pipeline no longer reads from it (episodes
arrive over SFTP), so the only place that still names it is
`build_inventory`, the one-off February scan, which keeps its own
constant.

Shell scripts read values through the CLI:

    python3 -m scripts.news.paths --var WORK
"""
import argparse
import json
import os
import re

from scripts.datadirs import ALLOWED_ROOTS   # noqa: F401  (re-export)
from scripts.datadirs import KARI
from scripts.datadirs import KITHANN
from scripts.datadirs import ROOT           # noqa: F401  (re-export)
from scripts.datadirs import check_name
from scripts.datadirs import check_under     # noqa: F401  (re-export)

HERE = os.path.dirname(os.path.abspath(__file__))


def check_srt_name(name):
    """A valid episode key: <YYYYMMDD>_<NNN>_… and no path components."""
    # 空值與路徑成分交予 check_name 講，才免兩爿各講一句無仝款ê話
    name = check_name(name, "srt_name")
    # [0-9] 是刻意的，莫改做 \d：Python 的 \d 預設連 Unicode 數字都食
    # （٢٠٢١、２０２１），驗證會變較鬆。日期佮集數只認 ASCII 0-9。
    if not re.fullmatch(r"[0-9]{8}_[0-9]{3}_.+", name):
        raise SystemExit(
            "srt_name %r 不符「<日期8碼>_<集數3碼>_…」格式" % name)
    return name


WORK = os.path.join(KITHANN, "out", "mxf")
LOGS = os.path.join(KITHANN, "out", "mxf-logs")

# Shared download staging area (fetch_sftp.sh / refine_fetch.sh convention):
# big disk, survives restarts, a file with the right byte count is reused
# rather than re-fetched.
STAGE = os.path.join(KITHANN, "out", "stage")

# Archival mkv copies (scripts/transcode/encode_master.sh output), one per
# episode -- see .claude/skills/video-subtitle-srt/壓縮率分析.md for the spec.
MKV_ARCHIVE = os.path.join(KITHANN, "out", "mkv")

# Working copy of the progress table, refreshed by make_all as often as you
# like. The delivered one lives in Kari-SRT and is written only by publish,
# once a whole batch is done: mid-batch a row says which step an episode is
# stuck at, and that lives in the work dir, which rebuild does not have -- so
# a mid-batch table in the store could never be rebuilt byte-for-byte.
TRACKER_CACHE = os.path.join(KITHANN, "out", "smkul.csv")

# Kari-SRT is the submodule holding the canonical data, layered
# corpus -> technique -> numbered stage (the numbers are the production
# order): news/1-ocr/ is the picture side, news/2-asr/ the speech side.
# kithann/ holds only sources and regenerable caches.
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
CATALOGUE = os.path.join(KITHANN, "tongan", "ilrdf-corpus.csv")

VENV_PY = os.path.expanduser("~/.venvs/subs2srt/bin/python")


# What one inventory entry holds. This is the shape eleven programs index
# into, and it was until now implicit in their `entry["…"]` lines; declaring
# it here makes the file's contract readable in one place and checkable at
# the boundary, so a truncated or hand-edited inventory says so instead of
# failing as a KeyError deep inside whichever program noticed first.
INVENTORY_REQUIRED = (
    "slug",          # work-dir name: <年度>_<集數>_<日期>_<時段>_<族英>_<族中>
    "srt_name",      # deliverable name: <日期8碼>_<集數3碼>_<時段>_<族英>_<族中>
    "video",         # master's path, relative to the corpus root
    "truncated",     # why the source was too incomplete ("" = it was fine)
    "文稿位置",       # transcript folder, relative to the corpus root ("" = none)
    "節目名稱", "年度", "集數", "播出日期", "播出時段",
    "族語別(英)", "族語別(中)",   # these seven go straight into smkul.csv
)

# Present only sometimes, and never dropped: the inventory is read, edited
# and written back by publish / add_episodes / build_inventory, so anything
# this loader discarded would be discarded from the store on the next write.
#   file     the master's own file name, kept by build_inventory's scan report
#   pending  registered but not yet delivered; publish deletes it when done
#   partial  note on an incomplete source, folded into the smkul.csv status
INVENTORY_OPTIONAL = ("file", "pending", "partial")


def load_inventory(path=None):
    """The inventory, with every name checked before it can become a path.

    Eleven programs read this file and every one of them turns `slug` and
    `srt_name` into a work dir or a store file name. Checking here -- the
    single point where the file's contents enter the program -- is what
    lets them do that without each repeating the check, and turns "the
    names in the inventory are safe" from an assumption resting on
    `resolve_slug.safe()` into an invariant that is enforced and testable.

    The checked value is assigned back rather than merely validated:
    downstream has to be handed the value that was checked, not a second
    reference to the one that was not. Entries are otherwise passed
    through untouched -- see INVENTORY_OPTIONAL for why nothing is
    rebuilt from a field list.
    """
    with open(path or INVENTORY, encoding="utf-8") as handle:
        entries = json.load(handle)
    for position, entry in enumerate(entries):
        missing = []
        for field in INVENTORY_REQUIRED:
            if field not in entry:
                missing.append(field)
        if missing:
            raise SystemExit("inventory 第 %d 筆缺欄位：%s"
                             % (position + 1, "、".join(missing)))
        entry["slug"] = check_name(entry["slug"], "slug")
        entry["srt_name"] = check_name(entry["srt_name"], "srt_name")
    return entries


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
