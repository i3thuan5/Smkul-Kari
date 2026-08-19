#!/usr/bin/env python3
"""Lift burned-in subtitles out of a video and write them as SRT.

Four stages, each usable on its own so a bad step can be redone without
paying for the ones before it:

    detect  VIDEO                 propose the subtitle band, write a preview
    cues    VIDEO -o WORK         segment into timed cues, export strips
    ocr     WORK                  fill in the text (pluggable backend)
    srt     WORK -o OUT.srt       assemble the SRT
    auto    VIDEO -o OUT.srt      all four in one go

Stages 1, 2 and 4 are deterministic pixel/bookkeeping work and are covered by
selftest.py. Stage 3 is the only one whose quality depends on a recogniser;
see SKILL.md for which backend to trust for which script.
"""

import argparse
import json
import os
import sys

import numpy as np
from PIL import Image

from scripts import datadirs
from scripts.ocr import transcripts
from scripts.srtlib import assemble
from scripts.ocr import cuelib
from scripts.srtlib import srt as srtfmt
from scripts.ocr import band as detector
from scripts.ocr import ocr as recogniser
from scripts.ocr import sheets as contact


# --------------------------------------------------------------- staging


def stage_detect(args):
    spec = cuelib.MaskSpec(outline=not args.no_outline)
    found = detector.detect_band(args.video, samples=args.samples, spec=spec)
    region = found["region"]
    lines, _ = detector.split_lines(args.video, region, spec)

    print("region (x,y,w,h): %d,%d,%d,%d" % tuple(region))
    print("sampled frames  : %d" % found["samples"])
    print("candidate bands (best first) -- detection is a proposal, always")
    print("confirm with --preview before trusting it:")
    for item in found["candidates"][:5]:
        print("  y=%d..%d  height %d  weight %.0f"
              % (item["y"], item["y"] + item["h"], item["h"],
                 item["weight"]))
    print("text lines in chosen band (offset within region):")
    for index, (lo, hi) in enumerate(lines):
        print("  line %d: y=%d..%d  (absolute y=%d..%d, height %d)"
              % (index, lo, hi, region[1] + lo, region[1] + hi, hi - lo))

    if args.preview:
        write_preview(args.video, region, lines, args.preview)
        print("preview written to %s" % args.preview)
    return 0


def write_preview(video_path, region, lines, path, count=6):
    info = detector.probe_or_die(video_path)
    tiles = []
    for index in range(count):
        ts = info["duration"] * (index + 1) / float(count + 1)
        frame = detector.grab_frame(video_path, ts, region)
        if frame is None:
            continue
        canvas = frame.copy()
        for lo, hi in lines:
            canvas[max(lo - 1, 0), :, :] = [255, 0, 0]
            canvas[min(hi, canvas.shape[0] - 1), :, :] = [255, 0, 0]
        tiles.append(canvas)
        tiles.append(np.zeros((6, region[2], 3), dtype=np.uint8))
    if tiles:
        Image.fromarray(np.vstack(tiles)).save(path)


def _region_spec_lines(video, args, key, preset):
    """The crop region: --region beats the preset beats detection."""
    spec = cuelib.MaskSpec()
    region = None
    lines = None
    if args.region:
        region = []
        for part in args.region.split(","):
            region.append(int(part))
    elif preset is not None and not args.autodetect:
        region = list(preset["region"])
        spec = cuelib.MaskSpec.from_dict(preset.get("mask", {}))
        lines = preset.get("lines")
        print("using preset '%s'" % key)
    if region is None:
        print("detecting subtitle band ...")
        found = detector.detect_band(video, samples=args.samples, spec=spec)
        region = found["region"]
        print("detected region: %d,%d,%d,%d" % tuple(region))
    return region, spec, lines


def _split_region_lines(video, region, spec, lang):
    """Line boxes inside the band, one OCR language each."""
    found_lines, _ = detector.split_lines(video, region, spec)
    lines = []
    if len(found_lines) <= 1:
        # One line: the region is already tight around it, so splitting
        # again would only risk shaving the glyphs.
        lines.append({"name": "line0", "y": 0, "h": region[3],
                      "lang": lang})
        return lines
    for index, (lo, hi) in enumerate(found_lines):
        lines.append({
            "name": "line%d" % index,
            "y": lo,
            "h": hi - lo,
            "lang": lang,
        })
    return lines


def _feed_frames(video, region, spec, seg, args, total):
    """Stream the band through the segmenter; returns (last_ts, seen)."""
    last_ts = args.start
    seen = 0
    for ts, frame in cuelib.stream_region(video, region, args.fps,
                                          start=args.start,
                                          duration=args.duration):
        seg.feed(ts, frame, cuelib.text_mask(frame, spec))
        last_ts = ts
        seen += 1
        if args.progress and seen % (int(args.fps) * 120) == 0:
            done = ts - args.start
            sys.stderr.write("\r  %.0f/%.0fs  cues=%d"
                             % (done, total, len(seg.cues)))
            sys.stderr.flush()
    if args.progress:
        sys.stderr.write("\r%-48s\r" % "")
    return last_ts, seen


def stage_cues(args):
    video = args.video
    # Read plainly, not through getattr(..., None). A caller that fails to
    # pass these should fail loudly here; reading a default turned `auto`
    # dropping --preset into a silent fall back to auto-detection, which on
    # this material segments the weather graphic instead of the dialogue.
    presets_path = args.presets
    key, preset = detector.match_preset(video, presets_path)

    # An explicit --preset beats guessing from the file name. File names in a
    # delivered corpus are not a reliable signal -- across one month of TITV
    # news the same programme appears as `魯凱語-霧台20210101S1100.mp4`,
    # `賽德克-20210102s1100.mp4` and `排灣-20210102s1800.mp4`, so no single
    # substring catches them all without also risking a hit on a different
    # programme with a completely different subtitle layout. What the file
    # sits *in* does identify the programme, so let the caller say so.
    if args.preset:
        presets = detector.load_presets(presets_path)
        if args.preset not in presets:
            raise SystemExit("no preset %r (have: %s)"
                             % (args.preset, ", ".join(sorted(presets))))
        key, preset = args.preset, presets[args.preset]

    region, spec, lines = _region_spec_lines(video, args, key, preset)

    info = detector.probe_or_die(video)
    fixed = cuelib.normalize_region(region, info["width"], info["height"])
    if fixed != list(region):
        print("region snapped to even crop bounds: %d,%d,%d,%d"
              % tuple(fixed))
    region = fixed

    if lines is None:
        lines = _split_region_lines(video, region, spec, args.lang)
    if not lines:
        lines = [{"name": "line0", "y": 0, "h": region[3],
                  "lang": args.lang}]

    workdir = args.out
    strips = os.path.join(workdir, "strips")
    os.makedirs(strips, exist_ok=True)

    records = []

    def write_cue(number, cue):
        """Called the moment a cue closes, so its frame can be released."""
        record = cue.as_dict(number)
        record["images"] = {}
        for line in lines:
            lo = line["y"]
            hi = lo + line["h"]
            crop = cue.best_rgb[lo:hi, :, :]
            name = "%05d_%s.png" % (number, line["name"])
            Image.fromarray(crop).save(os.path.join(strips, name))
            record["images"][line["name"]] = os.path.join("strips", name)
        records.append(record)

    frame_dt = 1.0 / float(args.fps)
    seg = cuelib.Segmenter(
        frame_dt=frame_dt,
        min_ink=args.min_ink,
        change=args.change,
        min_stable=args.min_stable,
        min_duration=args.min_duration,
        on_cue=write_cue,
    )

    total = info["duration"]
    if args.duration is not None:
        total = min(total, args.duration)
    last_ts, seen = _feed_frames(video, region, spec, seg, args, total)

    cues = seg.finish(last_ts + frame_dt)
    print("frames sampled: %d   cues found: %d" % (seen, len(cues)))

    manifest = {
        "video": os.path.abspath(video),
        "region": region,
        "lines": lines,
        "mask": spec.to_dict(),
        "sample_fps": args.fps,
        "segmenter": {
            "min_ink": args.min_ink,
            "change": args.change,
            "min_stable": args.min_stable,
            "min_duration": args.min_duration,
        },
        "cues": records,
    }
    path = os.path.join(workdir, "cues.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=1)
    print("wrote %s" % path)

    if args.sheets:
        made = contact.build_sheets(workdir, manifest,
                                    megapixels=args.sheet_megapixels)
        print("wrote %d contact sheet(s) to %s"
              % (made, os.path.join(workdir, "sheets")))
    return 0


# ------------------------------------------------------------------- ocr


def stage_ocr(args):
    workdir = args.work
    manifest = transcripts.read_manifest(workdir)
    if args.engine == "tesseract":
        texts = recogniser.ocr_tesseract(workdir, manifest, args)
    elif args.engine == "claude-api":
        texts = recogniser.ocr_claude_api(workdir, manifest, args)
    else:
        raise SystemExit("unknown engine %r" % args.engine)

    path = os.path.join(workdir, "transcripts.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(texts, handle, ensure_ascii=False, indent=1)
    print("wrote %s (%d cues)" % (path, len(texts)))
    return 0


# ------------------------------------------------------------------- srt


def _srt_entries(manifest, texts, order):
    """(start, end, joined text) per cue that has any text at all."""
    entries = []
    for cue in manifest["cues"]:
        got = texts.get(str(cue["index"]), {})
        parts = []
        for name in order:
            value = (got.get(name) or "").strip()
            if value:
                parts.append(value)
        if parts:
            entries.append((cue["start"], cue["end"], "\n".join(parts)))
    return entries


def stage_srt(args):
    workdir = args.work
    manifest = transcripts.read_manifest(workdir)
    texts = transcripts.load_transcripts(workdir)

    order = _line_names(manifest, args.only)
    entries = _srt_entries(manifest, texts, order)

    if args.merge_repeats:
        before = len(entries)
        entries = assemble.merge_repeats(entries, args.merge_gap)
        if before != len(entries):
            print("merged %d repeated-text cue(s)" % (before - len(entries)))
    entries = assemble.apply_gap_rules(entries, args.min_gap)
    body = srtfmt.render_srt(entries)
    with open(args.out, "w", encoding="utf-8") as handle:
        handle.write(body)
        if body and not body.endswith("\n"):
            handle.write("\n")
    print("wrote %s (%d subtitles)" % (args.out, body.count("-->")))
    return 0


def stage_import(args):
    imported, covered, total = transcripts.import_tsv(
        args.work, args.source, replace=args.replace)
    print("imported %d cue(s) from %s" % (imported, args.source))
    print("transcripts now cover %d/%d cues" % (covered, total))
    print("marked %d cue(s) as human-verified" % imported)
    return 0


def stage_export_gt(args):
    """Export corrected transcripts as a tesstrain ground-truth folder.

    The cue strips are already single text lines at a sane height, which is
    exactly what tesstrain wants, so building a training set is mostly a
    matter of pairing each strip with its text and trimming the empty margin.

    Only rows a human has confirmed (i.e. arrived via `import`) are exported
    by default. Ground truth is the one place where a wrong label is worse
    than a missing one: feeding a recogniser's own errors back as training
    targets teaches it to repeat them, and the mistakes are self-reinforcing.
    """
    workdir = args.work
    manifest = transcripts.read_manifest(workdir)
    texts = transcripts.load_transcripts(workdir)
    spec = cuelib.MaskSpec.from_dict(manifest.get("mask", {}))
    verified = transcripts.load_verified(workdir)

    wanted = None
    if args.line:
        wanted = set(_line_names(None, args.line))

    os.makedirs(args.out, exist_ok=True)
    written = 0
    skipped_blank = 0
    skipped_unverified = 0
    for cue, name, rel in _line_jobs(manifest, wanted):
        key = str(cue["index"])
        text = (texts.get(key, {}).get(name) or "").strip()
        if not text:
            # tesstrain rejects an empty .gt.txt outright
            skipped_blank += 1
            continue
        if (not args.include_unverified
                and not verified.get(key, {}).get(name)):
            skipped_unverified += 1
            continue
        _write_gt_pair(workdir, args.out, spec, args.prefix, cue, name,
                       rel, text)
        written += 1
    _report_gt(args, written, skipped_blank, skipped_unverified)


def _line_names(manifest, line_arg):
    """The line names to consider: --line beats the manifest's list."""
    names = []
    if line_arg:
        for name in line_arg.split(","):
            names.append(name.strip())
        return names
    for line in manifest["lines"]:
        names.append(line["name"])
    return names


def _line_jobs(manifest, wanted):
    """(cue, line name, image path) for every strip that exists."""
    jobs = []
    for cue in manifest["cues"]:
        for line in manifest["lines"]:
            name = line["name"]
            if wanted is not None and name not in wanted:
                continue
            rel = cue["images"].get(name)
            if rel:
                jobs.append((cue, name, rel))
    return jobs


def _write_gt_pair(workdir, out, spec, prefix, cue, name, rel, text):
    """One strip image + its .gt.txt label, margins trimmed."""
    img = Image.open(os.path.join(workdir, rel)).convert("RGB")
    box = contact.ink_bbox(np.asarray(img), spec, pad=8)
    if box is not None:
        img = img.crop((box[0], 0, box[1], img.height))
    stem = "%s_%05d_%s" % (prefix, cue["index"], name)
    img.save(os.path.join(out, stem + ".png"))
    path = os.path.join(out, stem + ".gt.txt")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text + "\n")


def _report_gt(args, written, skipped_blank, skipped_unverified):
    print("wrote %d line/label pairs to %s" % (written, args.out))
    print("skipped %d strip(s) with no text" % skipped_blank)
    if skipped_unverified:
        print("skipped %d unverified row(s) -- these still hold whatever the "
              "recogniser guessed. Proof-read them into a TSV and `import` "
              "it, or pass --include-unverified if you accept the risk."
              % skipped_unverified)
    if args.include_unverified:
        print("WARNING: --include-unverified exports unchecked recogniser "
              "output as training labels. Any error it made is now a target "
              "the new model will learn to reproduce.")
    if 0 < written < 50:
        print("NOTE: tesstrain checkpoints every 100 iterations; 50-100 "
              "lines is the practical floor for a fine-tune.")


def stage_pending(args):
    """Report which contact sheets still need a human read.

    Reading every sheet of a feature-length video does not fit in one
    sitting, so this is what makes the job resumable: it pairs the
    sheet->cue map written by `cues` against the rows already confirmed by
    `import`, and names the next batch to open.
    """
    workdir = args.work
    manifest = transcripts.read_manifest(workdir)
    verified = transcripts.load_verified(workdir)

    path = os.path.join(workdir, "sheets.json")
    if not os.path.exists(path):
        raise SystemExit(
            "no sheets.json in %s -- rebuild the contact sheets so the "
            "sheet-to-cue map exists" % workdir)
    with open(path, "r", encoding="utf-8") as handle:
        sheet_map = json.load(handle)

    names = _line_names(manifest, args.line)

    done = 0
    todo = []
    for sheet in sorted(sheet_map):
        missing = _sheet_missing(sheet_map[sheet], verified, names)
        if missing:
            todo.append((sheet, missing))
        else:
            done += 1

    total = len(sheet_map)
    print("sheets: %d done, %d remaining (of %d)"
          % (done, len(todo), total))
    if not todo:
        print("all sheets verified for line(s): %s" % ", ".join(names))
        return

    shown = todo
    if args.limit:
        shown = todo[:args.limit]
    print("next batch (%d shown):" % len(shown))
    for sheet, missing in shown:
        print("  sheets/%s  cues %s" % (sheet, missing))


def _sheet_missing(cues, verified, names):
    """Cues on one sheet still lacking a confirmed row for some line."""
    missing = []
    for index in cues:
        got = verified.get(str(index), {})
        for name in names:
            if not got.get(name):
                missing.append(index)
                break
    return missing


def _add_tokens(value, counts):
    for token in transcripts.glossary_tokens(value):
        counts[token] = counts.get(token, 0) + 1


def _glossary_counts(manifest, texts, verified, wanted, verified_only):
    counts = {}
    for cue in manifest["cues"]:
        key = str(cue["index"])
        row = texts.get(key, {})
        for line in manifest["lines"]:
            name = line["name"]
            if wanted is not None and name not in wanted:
                continue
            if verified_only and not verified.get(key, {}).get(name):
                continue
            value = (row.get(name) or "").strip()
            if value:
                _add_tokens(value, counts)
    return counts


def stage_glossary(args):
    """List recurring spellings so later batches can be told about them.

    A subagent only ever sees its own dozen sheets, so it cannot know how an
    earlier batch spelled a programme name or a mark-carrying word. Feeding
    this list into the prompt of subsequent batches is what keeps the corpus
    internally consistent -- checking afterwards catches the damage, telling
    them up front avoids it.
    """
    workdir = args.work
    manifest = transcripts.read_manifest(workdir)
    texts = transcripts.load_transcripts(workdir)
    verified = transcripts.load_verified(workdir)

    wanted = None
    if args.line:
        wanted = set(_line_names(None, args.line))

    counts = _glossary_counts(manifest, texts, verified, wanted,
                              args.verified_only)

    ranked = []
    for token in counts:
        if counts[token] >= args.min_count:
            ranked.append((counts[token], token))
    ranked.sort(key=lambda pair: (-pair[0], pair[1]))

    if not ranked:
        print("no recurring special-mark or proper-noun spellings found")
        return

    print("# 既定寫法（出現 >= %d 次）-- 貼進後續批次的 prompt"
          % args.min_count)
    shown = ranked
    if args.limit:
        shown = ranked[:args.limit]
    for count, token in shown:
        print("  %s   (%d 次)" % (token, count))
    if len(ranked) > len(shown):
        print("  ... 另有 %d 個未列出" % (len(ranked) - len(shown)))


def stage_for(args, **overrides):
    """A stage's arguments: everything the caller gave, plus the wiring.

    Derived from `args` rather than listed by hand. The hand-written list
    that used to be here had to be extended every time `cues` gained an
    option, and the one it was missing was `--preset`: accepted on the
    command line, dropped here, and read back as "not given" -- so `auto`
    quietly auto-detected the band instead of using the layout it was told
    to use. Deriving the arguments makes that class of omission impossible.
    """
    passed = argparse.Namespace(**vars(args))
    for name in overrides:
        setattr(passed, name, overrides[name])
    return passed


def stage_auto(args):
    workdir = args.work or (os.path.splitext(args.out)[0] + ".work")
    os.makedirs(workdir, exist_ok=True)

    # `cues` writes into the work dir; `auto`'s own -o is the finished SRT.
    stage_cues(stage_for(args, out=workdir))
    stage_ocr(stage_for(args, work=workdir))
    stage_srt(stage_for(args, work=workdir, out=args.out))
    return 0


# ------------------------------------------------------------------- cli


def build_parser():
    parser = argparse.ArgumentParser(
        prog="ocr-cli", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    subs = parser.add_subparsers(dest="command", required=True)

    detect = subs.add_parser("detect", help="propose the subtitle band")
    detect.add_argument("video")
    detect.add_argument("--samples", type=int, default=120)
    detect.add_argument("--no-outline", action="store_true",
                        help="skip the dark-outline test (band backgrounds)")
    detect.add_argument("--preview", help="write a stacked preview PNG here")
    detect.set_defaults(func=stage_detect)

    cues = subs.add_parser("cues", help="segment the video into timed cues")
    cues.add_argument("video")
    cues.add_argument("-o", "--out", required=True, help="work directory")
    add_cue_options(cues)
    cues.set_defaults(func=stage_cues)

    ocr = subs.add_parser("ocr", help="recognise the text in each cue")
    ocr.add_argument("work")
    ocr.add_argument("--engine", default="tesseract",
                     choices=["tesseract", "claude-api"])
    ocr.add_argument("--model", default="claude-opus-5")
    ocr.add_argument("--ocr-scale", type=float, default=2.0,
                     help="upscale before tesseract; presets may override "
                          "per line (see recogniser.prep_for_tesseract)")
    ocr.add_argument("--progress", action="store_true", default=True)
    ocr.set_defaults(func=stage_ocr)

    srt = subs.add_parser("srt", help="assemble cues + text into an SRT")
    srt.add_argument("work")
    srt.add_argument("-o", "--out", required=True)
    srt.add_argument("--only", help="comma-separated line names to keep")
    srt.add_argument("--min-gap", type=float, default=0.04)
    add_srt_options(srt)
    srt.set_defaults(func=stage_srt)

    imp = subs.add_parser("import",
                          help="load transcripts read off the contact sheets")
    imp.add_argument("work")
    imp.add_argument("--from", dest="source", required=True,
                     help="TSV: index<TAB>[line<TAB>]text")
    imp.add_argument("--replace", action="store_true",
                     help="discard existing transcripts instead of merging")
    imp.set_defaults(func=stage_import)

    gt = subs.add_parser("export-gt",
                         help="export checked text as tesstrain ground truth")
    gt.add_argument("work")
    gt.add_argument("-o", "--out", required=True,
                    help="ground-truth directory to create")
    gt.add_argument("--line", help="comma-separated line names to export")
    gt.add_argument("--prefix", default="sub",
                    help="file name prefix (default: sub)")
    gt.add_argument("--include-unverified", action="store_true",
                    help="also export rows no human has checked (risky: "
                         "teaches the recogniser its own mistakes)")
    gt.set_defaults(func=stage_export_gt)

    pend = subs.add_parser("pending",
                           help="list contact sheets still needing a read")
    pend.add_argument("work")
    pend.add_argument("--line", help="comma-separated line names to require")
    pend.add_argument("--limit", type=int, default=20,
                      help="how many remaining sheets to name (0 = all)")
    pend.set_defaults(func=stage_pending)

    glos = subs.add_parser("glossary",
                           help="list recurring spellings for prompt reuse")
    glos.add_argument("work")
    glos.add_argument("--line", help="comma-separated line names")
    glos.add_argument("--min-count", type=int, default=2)
    glos.add_argument("--limit", type=int, default=40)
    glos.add_argument("--verified-only", action="store_true", default=True)
    glos.add_argument("--all-rows", dest="verified_only",
                      action="store_false")
    glos.set_defaults(func=stage_glossary)

    auto = subs.add_parser("auto", help="cues + ocr + srt in one run")
    auto.add_argument("video")
    auto.add_argument("-o", "--out", required=True, help="output .srt")
    auto.add_argument("--work", help="work directory (default: OUT.work)")
    auto.add_argument("--engine", default="tesseract",
                      choices=["tesseract", "claude-api"])
    auto.add_argument("--model", default="claude-opus-5")
    auto.add_argument("--ocr-scale", type=float, default=2.0)
    auto.add_argument("--only")
    auto.add_argument("--min-gap", type=float, default=0.04)
    add_srt_options(auto)
    add_cue_options(auto)
    auto.set_defaults(func=stage_auto)

    return parser


def add_srt_options(parser):
    parser.add_argument("--merge-repeats", action="store_true", default=True,
                        help="fuse neighbouring cues with identical text")
    parser.add_argument("--no-merge-repeats", dest="merge_repeats",
                        action="store_false")
    parser.add_argument("--merge-gap", type=float, default=1.0,
                        help="largest gap that repeated text may span")


def add_cue_options(parser):
    parser.add_argument("--region", help="x,y,w,h (overrides preset)")
    parser.add_argument("--presets",
                        help="path to a presets.json; the engine ships none "
                             "of its own (corpus knowledge lives with the "
                             "caller, e.g. scripts/news/presets.json)")
    parser.add_argument("--preset",
                        help="name a preset explicitly rather than matching "
                             "it against the file name; use when the folder, "
                             "not the name, identifies the programme")
    parser.add_argument("--autodetect", action="store_true",
                        help="ignore any matching preset")
    parser.add_argument("--fps", type=float, default=5.0,
                        help="frames sampled per second (default 5)")
    parser.add_argument("--start", type=float, default=0.0)
    parser.add_argument("--duration", type=float, default=None)
    parser.add_argument("--min-ink", type=int, default=120,
                        help="mask pixels below which a frame is blank")
    parser.add_argument("--change", type=float, default=0.35,
                        help="Jaccard distance that starts a new cue")
    parser.add_argument("--min-stable", type=int, default=2,
                        help="repeats before a change is believed")
    parser.add_argument("--min-duration", type=float, default=0.30)
    parser.add_argument("--samples", type=int, default=120)
    parser.add_argument("--lang", default="chi_tra",
                        help="tesseract language for auto-found lines")
    parser.add_argument("--sheets", action="store_true", default=True,
                        help="also build contact sheets for vision OCR")
    parser.add_argument("--no-sheets", dest="sheets", action="store_false")
    parser.add_argument("--sheet-megapixels", type=float, default=1.10)
    parser.add_argument("--progress", action="store_true", default=True)


# Path-shaped arguments across every subcommand. Checked in one place so a
# new stage cannot quietly skip the guard; --presets is deliberately absent
# (it names a file that ships with the code, not data).
PATH_ARGS = ("video", "work", "out", "source")


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    for name in PATH_ARGS:
        value = getattr(args, name, "")
        if value:
            datadirs.check_under(value, name)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
