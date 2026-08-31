#!/usr/bin/env python3
"""Re-cut one stretch of an episode against a corrected subtitle band.

    python3 -m scripts.news.rescan_band <work-dir stem> <lo> <hi> \\
        --region 420,900,1500,135

WHY THIS EXISTS
---------------
Some feature packages -- the白色恐怖／二二八 documentary series that ran the
week before 2 月 28 in 2021 -- print their Chinese subtitles at y≈940-1035,
while `REGION` covers y 722-844. The band catches the interviewee's name
plate instead of the dialogue: the layout is inverted, with the plate pushed
up into the band and the speech below it.

Six of the fourteen episodes cut on 2026-08-30 carry such a stretch, 55 to
147 cues each. Reading the low strips is not enough to fix them, and two
readers worked that out independently: the cue *boundaries* in that stretch
came from ink changes in the wrong region -- a shirt's white pattern, a
camera move -- so they have nothing to do with where the subtitles change.
Text poured into those cues would land on the wrong seconds. The stretch has
to be cut again.

WHAT MAKES THIS THE RISKIEST STEP IN THE PIPELINE
-------------------------------------------------
Re-cutting a stretch changes how many cues it holds, so **every cue after it
is renumbered** -- and five artefacts are keyed by cue number: `cues.json`,
the `b*.tsv` the readers wrote, `transcripts.json`, `sheets.json`, and the
`strips/` filenames. Miss one and its text lands on the wrong seconds with
nothing to catch it: the line count still matches, the column count still
matches, `ingest` still reports 100% coverage.

So the arithmetic -- splice, renumber, remap -- is pure and separately
tested (`tests/news/test_rescan_band.py`), and the I/O around it does one
artefact at a time with the same mapping.

THE REGION
----------
`420,900,1500,135`, not `0,900,1920,135`: the red language badge and the
programme's lower-third sit at x < 400 in exactly these rows, and a static
graphic inflates the Jaccard denominator so real changes stop registering.
Measured on 058晚: the full width found 220 cues of which 26 were shorter
than half a second (the badge's own animation); the centred window found
152, of which 7. The README's rule -- crop wide, analyse narrow -- again.
"""
import argparse
import glob
import json
import os
import shutil
import subprocess
import sys

from scripts.errors import PipelineError
from scripts.news import paths
from scripts.ocr import sheets

REGION = "420,900,1500,135"


def splice(cues, lo, hi, replacement):
    """`cues` with [lo, hi] (1-based, inclusive) replaced, renumbered 1..N.

    Times are carried through untouched -- the replacement's own times come
    from the re-cut and are already absolute, because `ocr-cli cues` was
    given `--start` and keeps real seconds.
    """
    if lo < 1 or hi > len(cues) or hi < lo:
        raise PipelineError("範圍 %d–%d 佮 %d 條 cue 無合" % (lo, hi, len(cues)))
    if not replacement:
        raise PipelineError(
            "換入去ê是空ê。「這段無字幕」是一項結論，愛家己講出來，"
            "袂使當做重切ê結果恬恬做出來")
    out = []
    for cue in cues[:lo - 1]:
        out.append(dict(cue))
    for cue in replacement:
        out.append(dict(cue))
    for cue in cues[hi:]:
        out.append(dict(cue))
    for number, cue in enumerate(out, 1):
        cue["index"] = number
    return out


def mapping(total, lo, hi, count):
    """{old cue number: new cue number} for the cues that survive.

    Cues inside [lo, hi] are gone -- they were replaced -- so they have no
    entry at all rather than a `None`, which makes "was it dropped?" a
    membership test the callers cannot get subtly wrong.
    """
    shift = count - (hi - lo + 1)
    out = {}
    for old in range(1, total + 1):
        if lo <= old <= hi:
            continue
        out[old] = old if old < lo else old + shift
    return out


def remap_rows(rows, moves):
    """[(cue, text)] renumbered by `moves`; rows of dropped cues are gone.

    Text is passed through byte for byte -- a reader's trailing space or an
    embedded tab is what they saw on screen, and this step has no business
    tidying it.
    """
    out = []
    for cue, text in rows:
        if cue not in moves:
            continue
        out.append((moves[cue], text))
    out.sort(key=lambda row: row[0])
    return out


# ------------------------------------------------------------------ I/O


def read_tsv(path):
    """[(cue, text)] off one vision TSV."""
    rows = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 3 and parts[0].isdigit():
                rows.append((int(parts[0]), parts[2]))
    return rows


def write_tsv(path, rows):
    with open(path, "w", encoding="utf-8") as handle:
        for cue, text in rows:
            handle.write("%d\than\t%s\n" % (cue, text))


def recut(video, start, duration, out, region=REGION, venv=None):
    """Run the segmenter over one stretch; return its cue list."""
    if os.path.exists(out):
        shutil.rmtree(out)
    python = venv or sys.executable
    cmd = [python, "-m", "scripts.ocr.cli", "cues", video, "-o", out,
           "--region", region, "--start", "%.3f" % start,
           "--duration", "%.3f" % duration, "--no-sheets"]
    env = dict(os.environ, PYTHONPATH=".")
    with open(os.devnull) as devnull:
        done = subprocess.run(cmd, stdin=devnull, env=env,
                              capture_output=True, text=True)
    if done.returncode:
        raise PipelineError("重切失敗：%s" % done.stderr[-400:])
    with open(os.path.join(out, "cues.json"), encoding="utf-8") as handle:
        return json.load(handle)["cues"]


def move_strips(work, moves, fresh, lo, count):
    """Rename surviving strips and drop the re-cut range's in from `fresh`.

    Renames go through a temporary name first: cue 400 moving to 402 while
    402 is still on disk would clobber it, and the safe order depends on
    which way the numbering shifted.
    """
    strips = os.path.join(work, "strips")
    staging = os.path.join(work, "strips.new")
    if os.path.exists(staging):
        shutil.rmtree(staging)
    os.makedirs(staging)
    moved = 0
    for old in sorted(moves):
        source = os.path.join(strips, "%05d_han.png" % old)
        if not os.path.exists(source):
            continue
        shutil.copy2(source, os.path.join(staging,
                                          "%05d_han.png" % moves[old]))
        moved += 1
    added = 0
    for number in range(count):
        source = os.path.join(fresh, "strips",
                              "%05d_line0.png" % (number + 1))
        if not os.path.exists(source):
            source = os.path.join(fresh, "strips",
                                  "%05d_han.png" % (number + 1))
        if not os.path.exists(source):
            continue
        shutil.copy2(source, os.path.join(staging,
                                          "%05d_han.png" % (lo + number)))
        added += 1
    shutil.rmtree(strips)
    os.rename(staging, strips)
    return moved, added


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("stem", help="work-dir stem, e.g. 2021_058_..._排灣")
    ap.add_argument("lo", type=int)
    ap.add_argument("hi", type=int)
    ap.add_argument("--region", default=REGION)
    ap.add_argument("--video", help="override the mkv path")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--sheets-only", action="store_true",
                    help="rebuild the contact sheets and stop")
    args = ap.parse_args(argv)

    work = os.path.join(paths.WORK, args.stem + ".B.work")
    with open(os.path.join(work, "cues.json"), encoding="utf-8") as handle:
        book = json.load(handle)
    cues = book["cues"]
    if args.sheets_only:
        rebuild_sheets(work, book)
        return 0
    if args.hi > len(cues) or args.lo < 1 or args.hi < args.lo:
        raise PipelineError("範圍 %d–%d 佮 %d 條 cue 無合"
                            % (args.lo, args.hi, len(cues)))
    start = cues[args.lo - 1]["start"]
    end = cues[args.hi - 1]["end"]
    print("舊 cue %d–%d：%.1f–%.1f 秒（%d 條）"
          % (args.lo, args.hi, start, end, args.hi - args.lo + 1))

    video = args.video or os.path.join(paths.MKV_ARCHIVE,
                                       book["video"].split("/")[-1])
    if not os.path.exists(video):
        raise PipelineError("揣無影片：%s" % video)

    fresh = os.path.join(work, "..", args.stem + ".recut")
    fresh = os.path.normpath(fresh)
    new = recut(video, start, end - start, fresh, args.region,
                venv=paths.VENV_PY if hasattr(paths, "VENV_PY") else None)
    print("重切出 %d 條" % len(new))

    spliced = splice(cues, args.lo, args.hi, new)
    moves = mapping(len(cues), args.lo, args.hi, len(new))
    print("cue 總數 %d → %d" % (len(cues), len(spliced)))

    if args.dry_run:
        print("（--dry-run，無寫）")
        return 0

    for cue in spliced:
        cue["images"] = {"han": "strips/%05d_han.png" % cue["index"]}
    book["cues"] = spliced
    book["rescanned"] = book.get("rescanned", []) + [
        {"lo": args.lo, "hi": args.hi, "region": args.region,
         "count": len(new)}]
    with open(os.path.join(work, "cues.json"), "w", encoding="utf-8") as out:
        json.dump(book, out, ensure_ascii=False, indent=2)

    moved, added = move_strips(work, moves, fresh, args.lo, len(new))
    print("strips：徙 %d 張、新 %d 張" % (moved, added))

    folder = os.path.join(paths.KARI_VISION,
                          paths.month_of(_srt_name(args.stem)),
                          _srt_name(args.stem))
    for path in sorted(glob.glob(os.path.join(folder, "b*.tsv"))):
        rows = remap_rows(read_tsv(path), moves)
        write_tsv(path, rows)
        print("  %s → %d 逝" % (os.path.basename(path), len(rows)))

    rebuild_sheets(work, book)
    return 0


def rebuild_sheets(work, book):
    """Throw the old contact sheets away and tile fresh ones.

    Not optional and not `gap_sheets`' job: the sheets have the cue numbers
    **printed on them**, and the reader is told to trust what is printed
    over any arithmetic of their own. After a renumber every sheet from the
    re-cut stretch onward is captioned with numbers that no longer mean
    anything. `gap_sheets` cannot do it either -- it builds `.B.work` out of
    a `.work` beside it, and this batch was cut straight into `.B.work`.
    """
    for stale in ("transcripts.json", "verified.json"):
        target = os.path.join(work, stale)
        if os.path.exists(target):
            os.rename(target, target + ".before-rescan")
    folder = os.path.join(work, "sheets")
    if os.path.isdir(folder):
        shutil.rmtree(folder)
    made = sheets.build_sheets(work, book)
    with open(os.path.join(work, "transcripts.json"), "w",
              encoding="utf-8") as handle:
        json.dump({}, handle, ensure_ascii=False, indent=1)
    print("重做 %d 張 contact sheet" % made)
    return made


def _srt_name(stem):
    """srt_name for a work-dir stem, off the inventory."""
    for entry in paths.load_inventory():
        if entry["slug"] == stem:
            return entry["srt_name"]
    raise PipelineError("inventory 內底揣無 %s" % stem)


if __name__ == "__main__":
    sys.exit(main())
