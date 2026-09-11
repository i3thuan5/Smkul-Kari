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


def lexicon_path(tribe):
    """一个族語別ê詞庫：`詞庫/<族語別>.txt`，一逝一詞。

    佮 stage_path 仝款是「單一出口」，毋過鍵是族語別（阿美、布農）
    毋是 srt_name——詞庫是規族公用ê，毋是逐集一份。
    """
    return os.path.join(LEXICON_DIR, check_name(tribe, "族語別") + ".txt")


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

# 逐條語言判定。編號接佇 3-srt 後壁，因為伊**干焦食交付 SRT**——是仝
# 一條線ê下游，毋是另外一種技術（án-ne才免另開一層）。
LANGCHECK_STORE = os.path.join(OCR_STORE, "4-語言檢查")

# 詞庫是 store 正本，毋是衍生ê視圖：伊由外口ê族語辭典蒸餾來ê，無伊
# 判定就離線重走袂起來。辭典原檔（16 个 xlsx、五十外 MB、二進位）
# 留佇 SFTP，莫入 store。
LEXICON_DIR = os.path.join(LANGCHECK_STORE, "詞庫")
LANGCHECK_MARKS = os.path.join(LANGCHECK_STORE, "逐條語言標記.csv")
LANGCHECK_DIST = os.path.join(LANGCHECK_STORE, "逐集語言分布.csv")

# 辭典佇 SFTP ê位置。原民族語言研究發展基金會ê「16 族前台上線單字」，
# 佮影片、文稿仝一台機器。
LEXICON_REMOTE = "/docker/族語辭典_單詞與例句"

# Corpus-level tables: both list every episode, one row each, so they are
# not layered and do not belong to any one stage.
TRACKER_STORE = os.path.join(AIYA_STORE, "smkul.csv")

# Episodes that cannot go through this programme's two-row bilingual
# pipeline get a table of their own, with the reason in a column. Keeping
# them out of smkul.csv is what lets a reader of that table trust every
# row in it: a row there means a delivered SRT exists.
ABNORMAL_STORE = os.path.join(AIYA_STORE, "smkul-字幕版型異常.csv")
ABNORMAL_CACHE = os.path.join(WORK, "smkul-字幕版型異常.csv")

# The upstream text transcripts sit beside 1-ocr/, not inside it: they are
# a different technique (typed by hand, not read off the picture) for a
# different, non-overlapping set of episodes (001-045, no video) -- see
# scripts.aiyalaeho.text. One stage so far, still numbered "1-" in case a
# video timeline ever follows it.
TEXT_STORE = os.path.join(AIYA_STORE, "text")
TEXT_PAIRS = os.path.join(TEXT_STORE, "1-句對.csv")

# Staging copy of the 243 source files, refetched from SFTP each run --
# unlike the news side's fetch_sftp.sh, this corpus is 9.2 MB total, so
# there is no disk pressure to manage and nothing here is kept once
# 1-句對.csv is built.
TEXT_WORK = os.path.join(KITHANN, "out", "aiyalaeho-text")

# Where fetch.sh lists and downloads from.
TEXT_REMOTE = "/docker/ilrdf-corpus/族語節目/開會了_a_iyalaeho=上字文稿"

# presets.json is corpus knowledge -- which programme is laid out how -- so
# it is part of the code and lives beside it.
ENGINE_PRESETS = os.path.join(HERE, "presets.json")

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
        raise PipelineError("no path named %r (have: %s)"
                            % (args.var, ", ".join(known)))
    print(value)


if __name__ == "__main__":
    main()
