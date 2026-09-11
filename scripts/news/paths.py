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
import subprocess
import sys

from scripts.datadirs import ALLOWED_ROOTS   # noqa: F401  (re-export)
from scripts.datadirs import COARSE_STAGE    # noqa: F401  (re-export)
from scripts.datadirs import KARI
from scripts.datadirs import REFINED_STAGE   # noqa: F401  (re-export)
from scripts.datadirs import coarse_cues     # noqa: F401  (re-export)
from scripts.datadirs import cues_to_read    # noqa: F401  (re-export)
from scripts.datadirs import refined_cues    # noqa: F401  (re-export)
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


# The work dir's cue stages (`COARSE_STAGE`, `REFINED_STAGE`, and the two
# path helpers) are defined in `scripts.datadirs` -- the ocr engine writes
# the coarse one and does not depend on this package -- and re-exported
# above so `paths.X` call sites keep working. Why they are split at all is
# written where they are defined.


def cue_keyed(work, srt_name):
    """Every file that indexes cues by number, for one episode.

    Renumbering moves all of them or none: `safe_resplit`, `rescan_band`
    and `split_cue` each shift every cue after the one they touch, and
    anything keyed off those numbers goes stale without saying so. When
    `split_cue` renumbered the vision folder but not the rtf overlay,
    `ingest` did not notice -- it only walks the vision side -- and it
    took `rebuild --verify` to find it, on the two episodes out of four
    that happened to have overlay files.

    The list used to live in a docstring, where it disagreed with the
    code: it claimed five items and the code moved four. Here a test can
    read it (`tests/news/test_cue_key_registry.py`).

    `timeline` is whichever stage this work dir actually has, and where
    the coarse one belongs if it has none -- so a caller can both read an
    existing timeline and be told where to put a new one.
    """
    return {
        "timeline": cues_to_read(work) or coarse_cues(work),
        "sheets": os.path.join(work, "sheets.json"),
        "transcripts": os.path.join(work, "transcripts.json"),
        "vision": stage_path(KARI_VISION, srt_name),
    }


def timeline_is_refined(path):
    """Does this one timeline file record that the 25fps pass ran?

    The flag is how the pre-split layout said so, and the store still does:
    a store timeline is a single file, not a work dir. Unreadable counts as
    not refined -- the question is only ever asked to decide whether more
    work is needed, so failing towards "do the work" is the safe direction.
    """
    try:
        with open(path, encoding="utf-8") as handle:
            return bool(json.load(handle).get("refined"))
    except (OSError, ValueError):
        return False


def is_refined(work):
    """Has the 25fps pass produced a timeline for this work dir?

    The `2-refined/` file existing is the whole answer -- that is what makes
    the coarse file read-only and a killed refine harmless.

    There used to be a second arm here, reading a `refined` flag out of
    whatever `cues_to_read` returned, for the pre-split layout where a flat
    `cues.json` was the only place that could say so. `migrate_workdirs`
    swept those (news 75, 開會了 40, none left either side) and
    `cues_to_read` no longer reads the flat file, so the arm could only ever
    see `1-cues/cues.json` -- the coarse one. A stray flag in there would
    have passed a 0.2s-grid timeline off as refined.
    """
    return os.path.exists(refined_cues(work))


# One work dir per episode. There used to be two: `cues` wrote
# `<slug>.work`, then `gap_sheets` derived `<slug>.B.work` beside it with a
# copy of the timeline and a symlink back to the strips. The B stood for the
# second reading round -- the first one filled cues from the 文稿 and only
# sheeted what it could not supply. That round is gone (measured: of 4,344
# cues the script supplied, 336 disagreed with the picture and the picture
# was right every time), so B named a round that has no A. The copy and the
# symlink went with it.
WORK_EXT = ".work"


def work_dir(slug, work=None):
    """This episode's work dir."""
    return os.path.join(WORK if work is None else work, slug + WORK_EXT)


def has_cues(slug, work=None):
    """Has this episode been cut?

    One definition, because two callers act on it and they must not
    disagree. `make_all` asking the wrong dir reported fourteen finished
    episodes as 尚未切cue and `publish` then died looking for an SRT that
    was never assembled; the same mistake in `fetch_sftp.sh` is worse than
    a wrong report -- it re-cuts a delivered episode, which renumbers every
    cue, and the shipped SRT's timings come from the numbering that is
    there now.

    Asked through `cues_to_read`, so it accepts either stage rather than
    naming one.
    """
    return bool(cues_to_read(work_dir(slug, work)))


# Shared download staging area (fetch_sftp.sh convention):
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
# in one folder (twice that under 3-srt, which holds two files each); by
# month, a batch is one folder you can read, diff and review.
NEWS_STORE = os.path.join(KARI, "news")
OCR_STORE = os.path.join(NEWS_STORE, "1-ocr")
ASR_DIR = os.path.join(NEWS_STORE, "2-asr")
KARI_CUES = os.path.join(OCR_STORE, "1-cues")
KARI_VISION = os.path.join(OCR_STORE, "2-vision")
SRT_DIR = os.path.join(OCR_STORE, "3-srt")

# The speech side's stages, in production order: whole-episode recognition
# (1-words) -> the two-line deliverable (2-srt-raw) -> the analysis renders
# that add a machine translation (3-srt-ai) and the correspondence grade
# (4-srt-quality). The projection between words and entries is a pure
# function of 1-words and the picture side's timeline, so it is recomputed
# where it is needed rather than stored -- there is no stage for it.
ASR_WORDS = os.path.join(ASR_DIR, "1-words")
ASR_RAW = os.path.join(ASR_DIR, "2-srt-raw")
ASR_AI = os.path.join(ASR_DIR, "3-srt-ai")
ASR_QUALITY = os.path.join(ASR_DIR, "4-srt-quality")

# The two caches are content-addressed and shared across episodes, so they
# have neither a stage number nor a month layer: a line translated once for
# one episode is a hit for every other episode that says the same thing, and
# a re-projection after the timeline changes finds its work already done.
MT_CACHE = os.path.join(ASR_DIR, "mt-cache")
QUALITY_CACHE = os.path.join(ASR_DIR, "quality-cache")

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


# The interpreter `fetch_sftp.sh` and friends run the heavy steps with.
# This used to be the one hard-coded path below, which is fine on the
# machine it was written on and a dead stop everywhere else -- 使用者
# 2026-08-31 hit `列 67: /home/.../.venvs/subs2srt/bin/python: 沒有此一
# 檔案或目錄` and the whole month's fetch stopped there.
#
# Existing is not enough, either: `ocr-cli cues` needs numpy and PIL, and
# an interpreter without them fails halfway through, after the video is
# already downloaded. So a candidate has to import them before it counts.
DEFAULT_VENV = os.path.expanduser("~/.venvs/subs2srt/bin/python")


def venv_candidates():
    """Interpreters to try, best first."""
    out = []
    for path in (os.environ.get("SUBS2SRT_PY"),
                 DEFAULT_VENV,
                 os.path.join(ROOT, ".tox", "rebuild", "bin", "python"),
                 sys.executable):
        if path and path not in out:
            out.append(path)
    return out


def python_usable(path):
    """Can this interpreter actually run the decode steps?"""
    if not os.path.exists(path):
        return False
    try:
        done = subprocess.run([path, "-c", "import numpy, PIL"],
                              capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0


def venv_py(candidates=None, usable=None):
    """The first candidate that can run the decode steps.

    Falls back to the running interpreter rather than to nothing: a
    downstream step saying "No module named numpy" names the problem,
    while an empty string makes the shell say a file does not exist.
    """
    if candidates is None:
        candidates = venv_candidates()
    if usable is None:
        usable = python_usable
    for path in candidates:
        if usable(path):
            return path
    return sys.executable


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--var",
                    help="name of the path constant to print, e.g. WORK")
    ap.add_argument("--cues-of", metavar="WORK",
                    help="the best timeline this work dir has, or nothing")
    ap.add_argument("--coarse-of", metavar="WORK",
                    help="where this work dir's coarse timeline belongs")
    args = ap.parse_args()
    # Per-work-dir paths, so they are computed rather than looked up. Shell
    # callers ask for them here instead of spelling the stage folder out --
    # the layout is named in one place, and the flat pre-split fallback that
    # `cues_to_read` still honours comes with it for free.
    if args.cues_of:
        print(cues_to_read(args.cues_of) or "")
        return
    if args.coarse_of:
        print(coarse_cues(args.coarse_of))
        return
    if not args.var:
        raise PipelineError("--var、--cues-of、--coarse-of 揀一个")
    # A few "paths" have to be worked out rather than looked up: which
    # interpreter is present differs per machine, so VENV_PY is a call.
    computed = {"VENV_PY": venv_py}
    if args.var in computed:
        print(computed[args.var]())
        return
    value = globals().get(args.var)
    if not isinstance(value, str):
        known = []
        for name in sorted(globals()):
            if name.isupper() and isinstance(globals()[name], str):
                known.append(name)
        known += sorted(computed)
        raise PipelineError("no path named %r (have: %s)"
                            % (args.var, ", ".join(known)))
    print(value)


if __name__ == "__main__":
    main()
