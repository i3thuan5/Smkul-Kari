#!/usr/bin/env python3
"""Every path the 開會了 corpus touches, in one place.

Same shape as `scripts.news.paths`, and deliberately a separate file: the
two corpora name their episodes differently and lay their stores out
differently, and the news side is being worked on batch by batch. What is
genuinely shared -- the repo layout and the CLI argument guards -- comes
from `scripts.datadirs`, which neither corpus owns.

Two differences from the news layout, both consequences of what this
programme is:

  no month layer   news runs to ~1,065 episodes over fifteen months, so a
                   flat stage folder would be unreadable; this one is
                   forty-odd episodes and a flat folder is the readable
                   thing. The key carries no broadcast date to layer by
                   in any case (see check_srt_name).
  no speech side   the picture already carries the Formosan text, so
                   there is nothing for a recogniser to add: the store
                   stops at 1-ocr/.

Shell scripts read values through the CLI:

    python3 -m scripts.aiyalaeho.paths --var WORK
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

# What every key of this corpus opens with. The catalogue has no broadcast
# date for these episodes -- the delivery it came from lists 序列, 節目名稱,
# 集數 and 備註 and nothing else, and the mp4s were re-encoded so their
# creation_time is gone -- so the key is the programme, the episode number
# and the language. It is also what keeps the two corpora's keys apart:
# a news key opens with eight digits, this one with 開會了_.
KEY_PREFIX = "開會了_"


def check_srt_name(name):
    """A valid episode key: 開會了_<NNN>_<族語英>_<族語中>, no path parts."""
    # 空值佮路徑成分交予 check_name 講，才免兩爿各講一句無仝款ê話。
    name = check_name(name, "srt_name")
    # [0-9] 是刻意的，莫改做 \d：Python ê \d 連 Unicode 數字都食
    # （٠٦٨、０６８），驗證會變較鬆。集數只認 ASCII 0-9，而且三碼——
    # 零補了才會照集數排。
    if not re.fullmatch(KEY_PREFIX + r"[0-9]{3}_.+", name):
        raise PipelineError(
            "srt_name %r 不符「開會了_<集數3碼>_<族語英>_<族語中>」格式"
            % name)
    return name


def stage_path(stage, srt_name, suffix=""):
    """Where one episode's file sits in a stage folder: <stage>/<名>.

    The single way to build a path inside a stage folder, for the same
    reason the news side has one: spread across the programs that index
    into the store, a layout change would have to be made in each of them,
    and the symptom of missing one is an episode that assembles with no
    text rather than an error.
    """
    return os.path.join(stage, check_srt_name(srt_name) + suffix)


# ---------------------------------------------------------- 工作區（可重生）

# Work dirs, one per episode: cues.json, strips/, sheets/, transcripts.
# Everything here can be rebuilt from the store plus the video, so it is
# under kithann/ and gitignored.
WORK = os.path.join(KITHANN, "out", "aiyalaeho")
LOGS = os.path.join(WORK, "logs")

# The local copy of the source folder. The file names in it *are* the
# episode list -- see catalogue.py -- so this is the one place that says
# where they are.
SOURCE = os.path.join(KITHANN, "開會了")

# Working copy of the progress table, refreshed as often as you like. The
# delivered one is written by publish, once a whole batch is done: a
# mid-batch row says which step an episode is stuck at, and that lives in
# the work dir, which rebuild does not have.
TRACKER_CACHE = os.path.join(WORK, "smkul.csv")


def work_dir(srt_name):
    """This episode's work dir. The slug is the key -- one name, no table.

    The news side keeps a separate slug because its work dirs were already
    being referenced by long-running decodes when the delivered names
    changed, and renaming them would have orphaned work in progress. This
    corpus has no such history, so one string locates an episode
    everywhere.
    """
    return os.path.join(WORK, check_srt_name(srt_name) + ".work")


def band_json(srt_name):
    """Where `verify_band` leaves the rows it measured, for `cues` to read.

    A work-dir cache, not store: what reaches the store is the range that
    ended up in `cues.json`'s `mask`, written when the episode was cut.
    This file only carries the measurement between the two steps.
    """
    return os.path.join(work_dir(srt_name), "band.json")


# ------------------------------------------------------------ store（正本）

# Kari-SRT is the submodule holding the canonical data, layered
# corpus -> technique -> numbered stage (the numbers are the production
# order). 開會了 is a corpus of its own beside news/, not a folder inside
# it: it shares no episode, no naming key and no progress table with the
# news, and the catalogue lists it as a separate programme.
AIYA_STORE = os.path.join(KARI, "aiyalaeho")
OCR_STORE = os.path.join(AIYA_STORE, "1-ocr")

# Stage folders, in production order. These are *base* folders -- ask
# stage_path() for one episode's file rather than joining by hand.
KARI_CUES = os.path.join(OCR_STORE, "1-cues")
KARI_VISION = os.path.join(OCR_STORE, "2-vision")
SRT_DIR = os.path.join(OCR_STORE, "3-srt")

# Corpus-level tables: both list every episode, one row each, so they are
# not layered and do not belong to any one stage.
INVENTORY = os.path.join(AIYA_STORE, "inventory.json")
TRACKER_STORE = os.path.join(AIYA_STORE, "smkul.csv")

# Episodes that cannot go through this programme's two-row bilingual
# pipeline get a table of their own, with the reason in a column. Keeping
# them out of smkul.csv is what lets a reader of that table trust every
# row in it: a row there means a delivered SRT exists.
ABNORMAL_STORE = os.path.join(AIYA_STORE, "smkul-字幕版型異常.csv")
ABNORMAL_CACHE = os.path.join(WORK, "smkul-字幕版型異常.csv")

# presets.json is corpus knowledge -- which programme is laid out how -- so
# it is part of the code and lives beside it.
ENGINE_PRESETS = os.path.join(HERE, "presets.json")

VENV_PY = os.path.expanduser("~/.venvs/subs2srt/bin/python")


# What one inventory entry holds, in the order inventory.json holds it.
# Declaring the shape here makes the file's contract readable in one place
# and checkable at the boundary, so a truncated or hand-edited inventory
# says so instead of failing as a KeyError deep inside whichever program
# noticed first.
#
# The order is load-bearing: catalogue and publish write these entries
# straight back, so rebuilding them in another order would turn one
# publish into a diff of the whole file.
INVENTORY_FIELDS = (
    "file",          # the source's own file name, as the report shows it
    "video",         # path relative to the corpus root
    "srt_name",      # deliverable and work dir: 開會了_<NNN>_<族英>_<族中>
    "節目名稱",       # these six go straight into smkul.csv
    "集數",
    "族語別(英)", "族語別(中)",
    "語言別",         # the variety named in the file name, or ""
    "語言代號",       # ISO 639 three-letter, or an RFC 5646 private tag
    "pending",       # registered, not yet delivered; publish deletes it
    # Non-empty means this episode cannot go through the two-row bilingual
    # pipeline, and says why: 無字幕 / 僅華語字幕 (from the file name),
    # 版型不符：… (measured), 人工判定：… (somebody looked). It is the
    # tenth column of smkul-字幕版型異常.csv, and the only thing that
    # decides which of the two tables an episode lands in.
    "理由",
    # Seconds, as the container reports them. Only the abnormal episodes
    # carry it: they have no timeline in 1-cues/ to derive a length from,
    # and the offline rebuild may not open a video. Named for its unit so
    # that nobody confuses it with smkul.csv's 影片長度, which is 時:分:秒.
    "影片長度秒",
)

# Everything else in INVENTORY_FIELDS is required.
INVENTORY_OPTIONAL = ("file", "pending", "理由", "影片長度秒")

# The one that becomes a path, so it is what gets checked on the way in.
INVENTORY_NAMES = ("srt_name",)


def load_inventory(path=None):
    """The inventory, with the key checked before it can become a path.

    Every program that reads this file turns `srt_name` into a work dir or
    a store file name. Checking here -- the single point where the file's
    contents enter the program -- lets them do that without each repeating
    the check.

    Each entry is copied rather than edited in place, and the copy carries
    every declared field across: rebuilding from a shorter list would
    silently drop whatever is not on it, and catalogue / publish write
    these entries straight back to the store.
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
                checked[field] = check_srt_name(entry[field])
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
