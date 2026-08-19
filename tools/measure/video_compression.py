#!/usr/bin/env python3
"""Measure what an ffmpeg setting costs the subtitle pipeline.

The 2 月 母帶 are MPEG-2 50 Mbps MXF: 19 GB for 48 minutes. The delivered
SRTs are already extracted, so the question is how hard the picture can be
squeezed and still be re-processable. "Re-processable" has three parts, and
this script measures all three against the same episode's delivered data:

    size        bytes of the encode, and the whole-episode extrapolation
    timing      cues run on the encode vs cues run on the untouched source
    text        the SRT text the encode yields vs the delivered SRT

Text is the part that needs a vision read, so it is not automatic: run
`vision-batches`, farm the batches to subagents exactly as the normal
pipeline does, drop their TSVs in, then run `score`.

Compare text as *merged SRT entries*, never per cue index. A re-encode can
split one subtitle into two cues, which renumbers everything after it; a
per-cue diff then reports full-string mismatches that are really an
off-by-one. `assemble.merge_repeats` fuses consecutive cues carrying the
same text, and that sequence is what ships and what is stable.

    python3 -m tools.measure.compression encode  <video> --out DIR
    python3 -m tools.measure.compression cues    <video> --out DIR
    python3 -m tools.measure.compression timing  --out DIR
    python3 -m tools.measure.compression vision-batches --out DIR --rung R
    python3 -m tools.measure.compression score   --out DIR --srt DELIVERED
"""
import argparse
import difflib
import json
import os
import subprocess
import sys

from scripts.news import paths
from scripts.srtlib import assemble

#: One rung per setting worth knowing about. `args` goes straight to ffmpeg
#: between the input and the output file.
#:
#: `h264-crf23-422` is the chroma control: the mask's max_spread test reads
#: the RGB spread of each pixel, so 4:2:0 subsampling was a suspect for the
#: spurious cue splits. Measured, it is not one -- the split count wanders by
#: about the same amount either way -- but the rung is kept so the next
#: person does not have to re-derive that.
LADDER = [
    ("h264-crf18", ["-c:v", "libx264", "-preset", "medium",
                    "-pix_fmt", "yuv420p", "-crf", "18"]),
    ("h264-crf23", ["-c:v", "libx264", "-preset", "medium",
                    "-pix_fmt", "yuv420p", "-crf", "23"]),
    ("h264-crf28", ["-c:v", "libx264", "-preset", "medium",
                    "-pix_fmt", "yuv420p", "-crf", "28"]),
    ("h264-crf32", ["-c:v", "libx264", "-preset", "medium",
                    "-pix_fmt", "yuv420p", "-crf", "32"]),
    ("h264-crf36", ["-c:v", "libx264", "-preset", "medium",
                    "-pix_fmt", "yuv420p", "-crf", "36"]),
    ("h264-crf23-422", ["-c:v", "libx264", "-preset", "medium",
                        "-pix_fmt", "yuv422p", "-crf", "23"]),
    ("h264-crf23-yadif", ["-c:v", "libx264", "-preset", "medium",
                          "-pix_fmt", "yuv420p", "-crf", "23",
                          "-vf", "yadif=0:-1:0"]),
    ("h264-crf28-5fps", ["-c:v", "libx264", "-preset", "medium",
                         "-pix_fmt", "yuv420p", "-crf", "28", "-r", "5"]),
    ("h264-crf28-720p", ["-c:v", "libx264", "-preset", "medium",
                         "-pix_fmt", "yuv420p", "-crf", "28",
                         "-vf", "scale=1280:720"]),
    ("h265-crf30", ["-c:v", "libx265", "-preset", "medium",
                    "-pix_fmt", "yuv420p", "-crf", "30"]),
    ("band-crf23", ["-c:v", "libx264", "-preset", "medium",
                    "-pix_fmt", "yuv420p", "-crf", "23",
                    "-vf", "crop=1920:122:0:722:exact=1"]),
]

#: Rungs that move the subtitle out from under the preset's box need the box
#: moved with them, or `cues` reads the wrong rows and the comparison is
#: meaningless. Note that passing --region also makes the CLI auto-detect the
#: line split instead of taking the preset's; on this programme it detects the
#: same single line, but check that before trusting a new rung here.
REGIONS = {
    "band-crf23": "0,0,1920,122",
    "h264-crf28-720p": "0,480,1280,82",
}

#: The window the February measurements were taken over: the busiest five
#: minutes of 2021-02-01 晚間 阿美 (143 cues). Both bounds are multiples of
#: 0.2 s so the encode lands on the same 5 fps sampling grid the coarse cues
#: pass uses -- otherwise every boundary is off by up to half a sample and
#: the timing numbers measure the offset rather than the codec.
START = 2100.0
DURATION = 300.0

PRESET = "amis-titv-news"
CUES = "cues.json"


def two_pass_rung(rate):
    """A rung that hits a byte target instead of a quality target."""
    return ("2pass-%dk" % rate,
            ["-c:v", "libx264", "-preset", "medium", "-pix_fmt", "yuv420p",
             "-b:v", "%dk" % rate])


def rungs(extra_rates):
    out = list(LADDER)
    for rate in extra_rates or []:
        out.append(two_pass_rung(rate))
    return out


def encode_one(video, name, args, outdir, start, duration):
    dst = os.path.join(outdir, name + ".mp4")
    if os.path.exists(dst) and os.path.getsize(dst) > 0:
        return dst
    window = ["-ss", "%.3f" % start, "-t", "%.3f" % duration]
    if "-b:v" in args:
        log = os.path.join(outdir, "plog_" + name)
        first = (["ffmpeg", "-v", "error", "-y"] + window +
                 ["-i", video, "-map", "0:v:0", "-an"] + args +
                 ["-pass", "1", "-passlogfile", log, "-f", "mp4", os.devnull])
        subprocess.run(first, check=True)
        args = args + ["-pass", "2", "-passlogfile", log]
    cmd = (["ffmpeg", "-v", "error", "-y"] + window +
           ["-i", video, "-map", "0:v:0", "-an"] + args + [dst])
    subprocess.run(cmd, check=True)
    return dst


def cmd_encode(args):
    os.makedirs(args.out, exist_ok=True)
    rows = []
    for name, ffargs in rungs(args.two_pass):
        path = encode_one(args.video, name, ffargs, args.out,
                          args.start, args.duration)
        size = os.path.getsize(path)
        rows.append({
            "rung": name,
            "bytes": size,
            "mbps": round(size * 8.0 / args.duration / 1e6, 3),
        })
        print(json.dumps(rows[-1], ensure_ascii=False))
    write_json(os.path.join(args.out, "sizes.json"), rows)


def cues_of(video, workdir, region=None, start=None, duration=None):
    cmd = [paths.VENV_PY, "-m", "scripts.ocr.cli", "cues", video,
           "-o", workdir, "--presets", paths.ENGINE_PRESETS,
           "--preset", PRESET, "--sheets"]
    if region:
        cmd += ["--region", region]
    if start is not None:
        cmd += ["--start", "%.3f" % start]
    if duration is not None:
        cmd += ["--duration", "%.3f" % duration]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)


def cmd_cues(args):
    """Reference run on the untouched source, then one run per rung."""
    work = os.path.join(args.out, "work")
    os.makedirs(work, exist_ok=True)
    ref = os.path.join(work, "ref")
    if not os.path.exists(os.path.join(ref, CUES)):
        print("ref")
        cues_of(args.video, ref, start=args.start, duration=args.duration)
    for name, _ in rungs(args.two_pass):
        dst = os.path.join(work, name)
        if os.path.exists(os.path.join(dst, CUES)):
            continue
        src = os.path.join(args.out, name + ".mp4")
        if not os.path.exists(src):
            continue
        print(name)
        cues_of(src, dst, region=REGIONS.get(name))


def load_cues(path, offset):
    data = json.load(open(path, encoding="utf-8"))
    out = []
    for cue in data["cues"]:
        out.append((cue["start"] + offset, cue["end"] + offset, cue["index"]))
    return out


def overlap(a, b):
    return max(0.0, min(a[1], b[1]) - max(a[0], b[0]))


def cmd_timing(args):
    """Cue-level drift: extra cues, and how far the boundaries moved.

    Extra cues are a cost, not an error -- merge_repeats fuses a split
    subtitle back together at assembly, as long as both halves are read the
    same. What they cost is contact sheets, and so vision-reading effort.
    """
    work = os.path.join(args.out, "work")
    ref = load_cues(os.path.join(work, "ref", CUES), 0.0)
    rows = []
    for name, _ in rungs(args.two_pass):
        path = os.path.join(work, name, CUES)
        if not os.path.exists(path):
            continue
        rows.append(_timing_row(name, ref, load_cues(path, args.start)))
        print(json.dumps(rows[-1], ensure_ascii=False))
    write_json(os.path.join(args.out, "timing.json"), rows)


def _timing_pairs(var, ref):
    """(mutually-picked pairs, extra cue count)."""
    pairs = []
    extra = 0
    for cue in var:
        best = pick(cue, ref)
        if best is None:
            extra += 1
            continue
        if pick(best, var) == cue:
            pairs.append((best, cue))
        else:
            extra += 1
    return pairs, extra


def _timing_row(name, ref, var):
    pairs, extra = _timing_pairs(var, ref)
    edges = []
    for one, other in pairs:
        edges.append(abs(one[0] - other[0]))
        edges.append(abs(one[1] - other[1]))
    edges.sort()
    count = max(len(edges), 1)
    exact = 0
    for value in edges:
        if value == 0:
            exact += 1
    return {
        "rung": name,
        "ref_cues": len(ref),
        "var_cues": len(var),
        "extra_cues": extra,
        "edges_exact_pct": round(100.0 * exact / count, 1),
        "edge_mean_s": round(sum(edges) / count, 3),
        "edge_max_s": round(edges[-1] if edges else 0.0, 3),
    }


def pick(cue, pool):
    best = None
    best_ov = 0.0
    for other in pool:
        value = overlap(cue, other)
        if value > best_ov:
            best_ov = value
            best = other
    return best


def cmd_vision_batches(args):
    """Print the sheet batches for one rung, ready to farm to subagents."""
    work = os.path.join(args.out, "work", args.rung)
    sheets = json.load(open(os.path.join(work, "sheets.json"),
                            encoding="utf-8"))
    names = sorted(sheets)
    print("# %s: %d sheet(s)" % (args.rung, len(names)))
    made = 0
    for start in range(0, len(names), args.size):
        batch = names[start:start + args.size]
        made += 1
        print("\n=== batch %02d (%d sheets) ===" % (made, len(batch)))
        print("DIR %s/sheets/" % work)
        print("SHEETS %s" % " ".join(batch))
        print("TSV %s/tsv/%s_b%02d.tsv" % (args.out, args.rung, made))


def merged(workdir, tsv_paths, offset):
    """(start, end, text) for what the SRT would actually ship."""
    manifest = json.load(open(os.path.join(workdir, CUES),
                              encoding="utf-8"))
    text = {}
    for path in tsv_paths:
        for line in open(path, encoding="utf-8"):
            parts = line.rstrip("\n").split("\t")
            if parts[0].strip().isdigit():
                value = parts[2].strip() if len(parts) >= 3 else ""
                text[int(parts[0])] = value
    entries = []
    for cue in manifest["cues"]:
        body = text.get(cue["index"], "")
        if body:
            entries.append((cue["start"] + offset, cue["end"] + offset, body))
    return assemble.merge_repeats(entries)


def entry_drift(ref, var):
    """How far the shipped entries moved, matched on their text.

    Cue-level drift (see `timing`) counts boundaries that merge_repeats will
    dissolve anyway. This counts only the boundaries that survive into the
    SRT, which is the number the 0.05 s refinement pass inherits.
    """
    by_text = {}
    for start, end, body in var:
        by_text.setdefault(body, []).append((start, end))
    edges = []
    missing = 0
    for start, end, body in ref:
        found = by_text.get(body)
        if not found:
            missing += 1
            continue
        best = None
        for other in found:
            gap = abs(other[0] - start)
            if best is None or gap < best[0]:
                best = (gap, other)
        edges.append(abs(best[1][0] - start))
        edges.append(abs(best[1][1] - end))
    edges.sort()
    count = max(len(edges), 1)
    exact = 0
    for value in edges:
        if value == 0:
            exact += 1
    return {
        "entries_text_not_found": missing,
        "entry_edges_exact_pct": round(100.0 * exact / count, 1),
        "entry_edge_mean_s": round(sum(edges) / count, 3),
        "entry_edge_max_s": round(edges[-1] if edges else 0.0, 3),
    }


def sequence(workdir, tsv_paths, offset):
    manifest = json.load(open(os.path.join(workdir, CUES),
                              encoding="utf-8"))
    text = {}
    for path in tsv_paths:
        for line in open(path, encoding="utf-8"):
            parts = line.rstrip("\n").split("\t")
            if parts[0].strip().isdigit():
                value = parts[2].strip() if len(parts) >= 3 else ""
                text[int(parts[0])] = value
    entries = []
    for cue in manifest["cues"]:
        body = text.get(cue["index"], "")
        if body:
            entries.append((cue["start"] + offset, cue["end"] + offset, body))
    out = []
    for _start, _end, body in assemble.merge_repeats(entries):
        out.append(body)
    return out


def delivered_sequence(srt, lo, hi):
    """The texts the delivered SRT ships inside [lo, hi) seconds.

    Parsed here rather than with cuelib.parse_srt so that `score` and
    `timing` run under plain python3 like the rest of scripts/news --
    cuelib pulls in numpy, which only the subs2srt venv has.
    """
    out = []
    with open(srt, encoding="utf-8") as handle:
        blocks = handle.read().replace("\r\n", "\n").strip().split("\n\n")
    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue
        head, _, _tail = lines[1].partition("-->")
        start = parse_timestamp(head.strip())
        if lo <= start < hi:
            out.append("\n".join(lines[2:]).strip())
    return out


def parse_timestamp(value):
    clock, _, millis = value.partition(",")
    hours, minutes, secs = clock.split(":")
    return (int(hours) * 3600 + int(minutes) * 60 + int(secs)
            + int(millis) / 1000.0)


def edit_distance(a, b):
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost))
        prev = cur
    return prev[-1]


def _rung_tsvs(tsv_dir, name):
    found = []
    for entry in sorted(os.listdir(tsv_dir)):
        if entry.startswith(name + "_b") and entry.endswith(".tsv"):
            found.append(os.path.join(tsv_dir, entry))
    return found


def cmd_score(args):
    want = delivered_sequence(args.srt, args.start, args.start + args.duration)
    tsv_dir = os.path.join(args.out, "tsv")
    rows = []
    ref_merged = None
    for name, _ in [("ref", None)] + rungs(args.two_pass):
        found = _rung_tsvs(tsv_dir, name)
        if not found:
            continue
        offset = 0.0 if name == "ref" else args.start
        work = os.path.join(args.out, "work", name)
        entries = merged(work, found, offset)
        got = []
        for _start, _end, body in entries:
            got.append(body)
        row = diff_sequences(name, want, got)
        if name == "ref":
            ref_merged = entries
        elif ref_merged is not None:
            row.update(entry_drift(ref_merged, entries))
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False))
    write_json(os.path.join(args.out, "score.json"), rows)


def diff_sequences(name, want, got):
    matcher = difflib.SequenceMatcher(None, want, got, autojunk=False)
    same = 0
    chars = 0
    errors = 0
    differing = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            same += i2 - i1
            for line in want[i1:i2]:
                chars += len(line)
            continue
        left = want[i1:i2]
        right = got[j1:j2]
        for index in range(max(len(left), len(right))):
            a = left[index] if index < len(left) else ""
            b = right[index] if index < len(right) else ""
            chars += len(a)
            errors += edit_distance(a, b)
            differing += 1
    return {
        "rung": name,
        "entries_delivered": len(want),
        "entries_variant": len(got),
        "entries_identical": same,
        "entries_differing": differing,
        "char_errors": errors,
        "CER_pct": round(100.0 * errors / max(chars, 1), 3),
    }


def write_json(path, rows):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(rows, handle, ensure_ascii=False, indent=1)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True,
                    help="scratch directory (must live under kithann/)")
    ap.add_argument("--start", type=float, default=START)
    ap.add_argument("--duration", type=float, default=DURATION)
    # One value per flag, repeatable. nargs="*" would swallow the subcommand:
    # `--two-pass 5200 score` parses 'score' as another rate and then dies on
    # a missing command.
    ap.add_argument("--two-pass", type=int, action="append", default=None,
                    metavar="KBPS",
                    help="add a 2-pass rung at this rate; repeatable")
    sub = ap.add_subparsers(dest="cmd", required=True)

    one = sub.add_parser("encode")
    one.add_argument("video")
    one.set_defaults(func=cmd_encode)

    two = sub.add_parser("cues")
    two.add_argument("video")
    two.set_defaults(func=cmd_cues)

    three = sub.add_parser("timing")
    three.set_defaults(func=cmd_timing)

    four = sub.add_parser("vision-batches")
    four.add_argument("--rung", required=True)
    four.add_argument("--size", type=int, default=20)
    four.set_defaults(func=cmd_vision_batches)

    five = sub.add_parser("score")
    five.add_argument("--srt", required=True, help="the delivered SRT")
    five.set_defaults(func=cmd_score)

    args = ap.parse_args()
    args.out = paths.check_under(args.out, "--out",
                                 roots=[paths.KITHANN])
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
