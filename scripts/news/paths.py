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
deliberate exception; the pipeline no longer reads from it -- episodes
arrive over SFTP and the video is deleted as soon as its cues are cut.

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
from scripts.errors import PipelineError

HERE = os.path.dirname(os.path.abspath(__file__))


def check_srt_name(name):
    """A valid episode key: <YYYYMMDD>_<NNN>_… and no path components."""
    # 空值與路徑成分交予 check_name 講，才免兩爿各講一句無仝款ê話
    name = check_name(name, "srt_name")
    # [0-9] 是刻意的，莫改做 \d：Python 的 \d 預設連 Unicode 數字都食
    # （٢٠٢١、２０２１），驗證會變較鬆。日期佮集數只認 ASCII 0-9。
    if not re.fullmatch(r"[0-9]{8}_[0-9]{3}_.+", name):
        raise PipelineError(
            "srt_name %r 不符「<日期8碼>_<集數3碼>_…」格式" % name)
    return name


def month_of(srt_name):
    """The broadcast month a srt_name belongs to: 20210201… -> "2021-02".

    Derived from the name, not stored anywhere: the name already opens with
    the broadcast date, and a second copy of the same truth is a thing that
    has to be kept in step -- inventory used to exist twice and publish had
    to overwrite one with the other to stop them drifting.

    `check_srt_name` only knows the first eight characters are digits, not
    that they are a date. Without the month check "2021-99/" would quietly
    appear in the store, and nothing downstream looks for a folder it does
    not expect, so nobody would find out.
    """
    name = check_srt_name(srt_name)
    month = name[4:6]
    if not "01" <= month <= "12":
        raise PipelineError(
            "srt_name %r 的月份 %r 不是 01–12" % (srt_name, month))
    return name[:4] + "-" + month


def stage_path(stage, srt_name, suffix=""):
    """Where one episode's file sits in a stage folder: <stage>/<年-月>/<名>.

    The single way to build a path inside a stage folder. Spread across the
    eleven programs that index into the store, a change to the layout would
    have to be made eleven times, and the symptom of missing one is an
    episode that assembles with no text rather than an error.
    """
    return os.path.join(stage, month_of(srt_name), srt_name + suffix)


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
#
# These stage constants are *base* folders. One episode's file does not sit
# directly in them -- it sits under the broadcast month, so ask stage_path()
# for it. Flat, fifteen months of this corpus would be about 1,065 episodes
# in one folder (twice that under 6-srt, which holds two files each); by
# month, a batch is one folder you can read, diff and review.
NEWS_STORE = os.path.join(KARI, "news")
OCR_STORE = os.path.join(NEWS_STORE, "1-ocr")
ASR_DIR = os.path.join(NEWS_STORE, "2-asr")
KARI_CUES = os.path.join(OCR_STORE, "1-cues")
KARI_FROM_RTF = os.path.join(OCR_STORE, "2-from_rtf")
KARI_VISION = os.path.join(OCR_STORE, "3-vision")
KARI_VISION_RTF = os.path.join(OCR_STORE, "4-vision-rtf")
KARI_REPORT = os.path.join(OCR_STORE, "5-report")
SRT_DIR = os.path.join(OCR_STORE, "6-srt")

# Cross-episode, so not layered by month: the translation cache is keyed by
# content and shared between episodes, and the rtf-vs-vision report compares
# the whole batch at once.
MT_CACHE = os.path.join(ASR_DIR, "mt-cache")

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

# The broadcaster's catalogue of the whole corpus -- which episode is which
# language, and which file it is. It lives in the store, at the top rather
# than under news/, because it lists 族語節目/開會了 as well as 族語新聞.
#
# It is source data, not a deliverable, and `rebuild --verify` never reads
# it. It is here because it cannot be regenerated: the original is an xlsx
# on the SFTP host, this CSV is what the pipeline was built to read, and it
# is the source of every naming decision downstream. It used to sit under
# kithann/, which is gitignored -- one rebuilt devcontainer and the thing
# every future month is planned from would have been gone.
CATALOGUE = os.path.join(KARI, "ilrdf-corpus.csv")

VENV_PY = os.path.expanduser("~/.venvs/subs2srt/bin/python")


# What one inventory entry holds, in the order inventory.json holds it.
# This is the shape eleven programs index into, and it was until now
# implicit in their `entry["…"]` lines; declaring it here makes the file's
# contract readable in one place and checkable at the boundary, so a
# truncated or hand-edited inventory says so instead of failing as a
# KeyError deep inside whichever program noticed first.
#
# The order is load-bearing, not decoration: publish / add_episodes /
# plan_month write these entries straight back, so rebuilding them in
# any other order would turn one publish into a diff of the whole file.
INVENTORY_FIELDS = (
    "file",          # the source's own file name, as the report shows it
    "video",         # master's path, relative to the corpus root
    "slug",          # work-dir name: <年度>_<集數>_<日期>_<時段>_<族英>_<族中>
    "srt_name",      # deliverable: <日期8碼>_<集數3碼>_<時段>_<族英>_<族中>
    "節目名稱", "年度", "集數", "播出日期", "播出時段",
    "族語別(英)", "族語別(中)",   # these seven go straight into smkul.csv
    "文稿位置",       # transcript folder, relative to the corpus root
    "truncated",     # why the source was too incomplete ("" = it was fine)
    "pending",       # registered, not yet delivered; publish deletes it
    "partial",       # note on an incomplete source, folded into the status
)

# Everything else in INVENTORY_FIELDS is required. Keeping only this list
# means one declaration governs the field set, its order and which are
# optional -- three things that used to be written down separately and had
# to be kept in step by hand.
INVENTORY_OPTIONAL = ("file", "pending", "partial")

# The two that become paths, so they are what gets checked on the way in.
INVENTORY_NAMES = ("slug", "srt_name")


def load_inventory(path=None):
    """The inventory, with every name checked before it can become a path.

    Eleven programs read this file and every one of them turns `slug` and
    `srt_name` into a work dir or a store file name. Checking here -- the
    single point where the file's contents enter the program -- is what
    lets them do that without each repeating the check, and turns "the
    names in the inventory are safe" from an assumption resting on
    `resolve_slug.safe()` into an invariant that is enforced and testable.

    Each entry is copied rather than edited in place, so what the parsed
    file held and what the pipeline works with stay separate things. The
    copy carries every field across: rebuilding from INVENTORY_REQUIRED
    would silently drop whatever is not on that list, and publish /
    add_episodes / plan_month write these entries straight back to
    the store -- see INVENTORY_OPTIONAL.

    The checked value is assigned into the copy rather than merely
    validated: downstream has to be handed the value that was checked,
    not a second reference to the one that was not.
    """
    with open(path or INVENTORY, encoding="utf-8") as handle:
        raw = json.load(handle)
    entries = []
    for position, entry in enumerate(raw):
        missing = []
        for field in INVENTORY_FIELDS:
            if field not in INVENTORY_OPTIONAL and field not in entry:
                missing.append(field)
        if missing:
            raise PipelineError("inventory 第 %d 筆缺欄位：%s"
                                % (position + 1, "、".join(missing)))

        unknown = []
        for field in entry:
            if field not in INVENTORY_FIELDS:
                unknown.append(field)
        if unknown:
            raise PipelineError(
                "inventory 第 %d 筆有未宣告的欄位：%s"
                "——條目是照 INVENTORY_FIELDS 一欄一欄重建的，未宣告的會"
                "佇寫轉去 store 時無去，先加入宣告"
                % (position + 1, "、".join(unknown)))

        checked = {}
        for field in INVENTORY_FIELDS:
            if field not in entry:
                continue
            if field in INVENTORY_NAMES:
                checked[field] = check_name(entry[field], field)
            else:
                checked[field] = entry[field]
        entries.append(checked)
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
        raise PipelineError("no path named %r (have: %s)"
                            % (args.var, ", ".join(known)))
    print(value)


if __name__ == "__main__":
    main()
