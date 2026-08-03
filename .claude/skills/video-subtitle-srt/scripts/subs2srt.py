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
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cuelib  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PRESETS_PATH = os.path.join(HERE, "presets.json")
LABEL_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


# --------------------------------------------------------------- presets


def load_presets():
    if not os.path.exists(PRESETS_PATH):
        return {}
    with open(PRESETS_PATH, "r", encoding="utf-8") as handle:
        return json.load(handle)


def match_preset(video_path):
    """Pick a preset whose `match` substring occurs in the file name."""
    name = os.path.basename(video_path)
    presets = load_presets()
    for key in sorted(presets):
        preset = presets[key]
        needle = preset.get("match")
        if needle and needle in name:
            return key, preset
    return None, None


# ---------------------------------------------------------- band detect


def detect_band(video_path, samples=120, spec=None, search_top=0.55,
                min_hits=0.04, max_band=220):
    """Propose a subtitle band by asking which rows hold text most often.

    Sampling is spread across the whole file rather than taken from one
    stretch, so a band that only appears during interviews still registers.
    """
    if spec is None:
        spec = cuelib.MaskSpec()
    info = probe_or_die(video_path)
    width = info["width"]
    height = info["height"]
    top = int(height * search_top)
    region = cuelib.normalize_region((0, top, width, height - top),
                                     width, height)
    top = region[1]

    step = max(info["duration"] / float(samples), 0.5)
    rows = np.zeros(height - top, dtype=np.float64)
    cols = np.zeros(width, dtype=np.float64)
    taken = 0
    for index in range(samples):
        ts = step * index
        if ts >= info["duration"]:
            break
        frames = grab_burst(video_path, ts, region, count=2)
        if len(frames) < 2:
            continue
        mask = stable_text_mask(frames, spec)
        if mask is None:
            continue
        rows += mask.sum(axis=1)
        cols += mask.sum(axis=0)
        taken += 1
    if taken == 0:
        raise RuntimeError("could not sample any frame from %s" % video_path)
    rows /= taken
    cols /= taken

    region, ranked = region_from_profile(rows, cols, top, width, height,
                                         min_hits=min_hits,
                                         max_band=max_band)
    return {
        "region": region,
        "candidates": ranked,
        "row_profile": rows.tolist(),
        "row_offset": top,
        "samples": taken,
    }


def region_from_profile(rows, cols, top, width, height,
                        min_hits=0.04, max_band=220, pad=6):
    """Turn per-row/per-column ink profiles into a proposed crop box.

    Split out of detect_band so it can be exercised without decoding a video.
    That matters: this is the arithmetic where a candidate band's height once
    shared the name `height` with the frame height, and shadowing it collapsed
    the returned box to 2px -- a bug no amount of reading the profile code
    would reveal, because the profile was right and only the last few lines
    were wrong.
    """
    threshold = max(rows.max() * min_hits, 1.0)
    bands = []
    start = None
    for y in range(len(rows)):
        if rows[y] >= threshold and start is None:
            start = y
        elif rows[y] < threshold and start is not None:
            bands.append((start, y))
            start = None
    if start is not None:
        bands.append((start, len(rows)))

    # Keep the merge gap small: a news lower-third sitting just below the
    # dialogue is also text, and merging the two produces one 300px "band"
    # that is mostly station graphics.
    merged = merge_bands(bands, gap=8)
    candidates = []
    for lo, hi in merged:
        band_h = hi - lo
        if band_h < 16 or band_h > max_band:
            continue
        candidates.append((float(rows[lo:hi].sum()), lo, hi))
    if not candidates:
        for lo, hi in merged:
            candidates.append((float(rows[lo:hi].sum()), lo, hi))
    if not candidates:
        raise RuntimeError("no subtitle band found; pass --region manually")

    candidates.sort(reverse=True)
    ranked = []
    for weight, lo, hi in candidates:
        ranked.append({"y": top + lo, "h": hi - lo,
                       "weight": round(weight, 1)})

    _, lo, hi = candidates[0]
    y0 = max(top + lo - pad, 0)
    y1 = min(top + hi + pad, height)

    col_thresh = max(cols.max() * 0.02, 0.5)
    xs = np.nonzero(cols >= col_thresh)[0]
    if len(xs):
        x0 = max(int(xs[0]) - 12, 0)
        x1 = min(int(xs[-1]) + 13, width)
    else:
        x0, x1 = 0, width

    region = cuelib.normalize_region((x0, y0, x1 - x0, y1 - y0),
                                     width, height)
    if region[3] < 12:
        # The chosen band was tens of pixels tall; if the box that came out
        # is not, the arithmetic above lost track of the frame height.
        raise RuntimeError(
            "band detection produced a %dpx-tall region from a %dpx band "
            "-- refusing to return it" % (region[3], hi - lo))
    return region, ranked


def merge_bands(bands, gap):
    merged = []
    for lo, hi in bands:
        if merged and lo - merged[-1][1] <= gap:
            merged[-1] = (merged[-1][0], hi)
        else:
            merged.append((lo, hi))
    return merged


def split_lines(video_path, region, spec, samples=80, min_gap=10, pad=10):
    """Split a band into individual text lines by finding blank rows.

    Video A stacks Amis over Chinese in one band; each needs its own OCR
    language, so they have to be cut apart before recognition.

    The threshold has to stay low and the result has to be padded: a row
    holding only the dot of an `i` or the tail of a `g` carries a tiny
    fraction of the peak row's ink, and clipping those rows away hands the
    recogniser decapitated glyphs.
    """
    info = probe_or_die(video_path)
    step = max(info["duration"] / float(samples), 0.5)
    rows = np.zeros(region[3], dtype=np.float64)
    taken = 0
    for index in range(samples):
        ts = step * index
        if ts >= info["duration"]:
            break
        frames = grab_burst(video_path, ts, region, count=2)
        if len(frames) < 2:
            continue
        mask = stable_text_mask(frames, spec)
        if mask is None:
            continue
        rows += mask.sum(axis=1)
        taken += 1
    if taken:
        rows /= taken

    threshold = max(rows.max() * 0.03, 0.3)
    runs = []
    start = None
    for y in range(len(rows)):
        if rows[y] >= threshold and start is None:
            start = y
        elif rows[y] < threshold and start is not None:
            runs.append((start, y))
            start = None
    if start is not None:
        runs.append((start, len(rows)))

    runs = merge_bands(runs, gap=min_gap)
    kept = []
    for lo, hi in runs:
        if hi - lo >= 12:
            kept.append((lo, hi))

    # Pad to recover ascenders and descenders, but never by more than half
    # the gap to the neighbouring line -- otherwise video A's stacked Amis
    # and Chinese lines grow into each other and merge back into one band,
    # and they need separate OCR languages.
    padded = []
    for index, (lo, hi) in enumerate(kept):
        up = pad
        down = pad
        if index > 0:
            up = min(pad, max((lo - kept[index - 1][1]) // 2, 0))
        if index + 1 < len(kept):
            down = min(pad, max((kept[index + 1][0] - hi) // 2, 0))
        padded.append((max(lo - up, 0), min(hi + down, region[3])))
    return padded, rows.tolist()


# ------------------------------------------------------------- ffmpeg io


def probe_or_die(video_path):
    try:
        return cuelib.probe_video(video_path)
    except Exception as exc:
        raise SystemExit("ffprobe failed on %s: %s" % (video_path, exc))


def grab_frame(video_path, ts, region):
    x, y, w, h = cuelib.normalize_region(region)
    cmd = [
        "ffmpeg", "-v", "error", "-ss", "%.3f" % ts, "-i", video_path,
        "-frames:v", "1",
        "-vf", cuelib.crop_chain((x, y, w, h), "format=rgb24"),
        "-f", "rawvideo", "-",
    ]
    out = subprocess.run(cmd, stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL).stdout
    if len(out) < w * h * 3:
        return None
    return np.frombuffer(out[:w * h * 3], dtype=np.uint8).reshape(h, w, 3)


def grab_burst(video_path, ts, region, count=2, fps=5.0):
    """Grab `count` consecutive samples from one seek."""
    x, y, w, h = cuelib.normalize_region(region)
    span = (count + 0.5) / float(fps)
    cmd = [
        "ffmpeg", "-v", "error", "-ss", "%.3f" % ts, "-t", "%.3f" % span,
        "-i", video_path,
        "-vf", "fps=%s,%s" % (
            fps, cuelib.crop_chain((x, y, w, h), "format=rgb24")),
        "-f", "rawvideo", "-",
    ]
    out = subprocess.run(cmd, stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL).stdout
    nbytes = w * h * 3
    frames = []
    for index in range(count):
        chunk = out[index * nbytes:(index + 1) * nbytes]
        if len(chunk) < nbytes:
            break
        frames.append(np.frombuffer(chunk, dtype=np.uint8).reshape(h, w, 3))
    return frames


def stable_text_mask(frames, spec):
    """Mask of text pixels that held still across the whole burst.

    A subtitle is frozen for its entire cue; footage underneath it is not.
    Intersecting the masks of frames a fifth of a second apart therefore
    keeps glyphs and drops moving content -- which is what stops band
    detection from locking onto a busy background.
    """
    mask = None
    for frame in frames:
        current = cuelib.text_mask(frame, spec)
        if mask is None:
            mask = current
        else:
            mask &= current
    if mask is None:
        return None
    return mask


# --------------------------------------------------------------- staging


def stage_detect(args):
    spec = cuelib.MaskSpec(outline=not args.no_outline)
    found = detect_band(args.video, samples=args.samples, spec=spec)
    region = found["region"]
    lines, _ = split_lines(args.video, region, spec)

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
    info = probe_or_die(video_path)
    tiles = []
    for index in range(count):
        ts = info["duration"] * (index + 1) / float(count + 1)
        frame = grab_frame(video_path, ts, region)
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


def stage_cues(args):
    video = args.video
    key, preset = match_preset(video)
    spec = cuelib.MaskSpec()
    region = None
    lines = None

    if args.region:
        parts = args.region.split(",")
        region = [int(p) for p in parts]
    elif preset is not None and not args.autodetect:
        region = list(preset["region"])
        spec = cuelib.MaskSpec.from_dict(preset.get("mask", {}))
        lines = preset.get("lines")
        print("using preset '%s'" % key)

    if region is None:
        print("detecting subtitle band ...")
        found = detect_band(video, samples=args.samples, spec=spec)
        region = found["region"]
        print("detected region: %d,%d,%d,%d" % tuple(region))

    info = probe_or_die(video)
    fixed = cuelib.normalize_region(region, info["width"], info["height"])
    if fixed != list(region):
        print("region snapped to even crop bounds: %d,%d,%d,%d"
              % tuple(fixed))
    region = fixed

    if lines is None:
        found_lines, _ = split_lines(video, region, spec)
        lines = []
        if len(found_lines) <= 1:
            # One line: the region is already tight around it, so splitting
            # again would only risk shaving the glyphs.
            lines.append({"name": "line0", "y": 0, "h": region[3],
                          "lang": args.lang})
        else:
            for index, (lo, hi) in enumerate(found_lines):
                lines.append({
                    "name": "line%d" % index,
                    "y": lo,
                    "h": hi - lo,
                    "lang": args.lang,
                })
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
        made = build_sheets(workdir, manifest,
                            megapixels=args.sheet_megapixels)
        print("wrote %d contact sheet(s) to %s"
              % (made, os.path.join(workdir, "sheets")))
    return 0


# -------------------------------------------------------- contact sheets


def ink_bbox(rgb, spec, pad=6):
    mask = cuelib.text_mask(rgb, spec)
    cols = np.nonzero(mask.sum(axis=0) > 0)[0]
    if len(cols) == 0:
        return None
    x0 = max(int(cols[0]) - pad, 0)
    x1 = min(int(cols[-1]) + pad + 1, rgb.shape[1])
    return (x0, x1)


def build_sheets(workdir, manifest, megapixels=1.10):
    """Tile cue strips into a few big images for a vision model to read.

    Reading 800 separate crops costs 800 round trips; reading 40 sheets costs
    40. The budget is expressed in megapixels because that is what actually
    limits a vision model -- overshoot it and the page gets downscaled and the
    glyphs stop being legible, which defeats the point.
    """
    sheets_dir = os.path.join(workdir, "sheets")
    os.makedirs(sheets_dir, exist_ok=True)
    spec = cuelib.MaskSpec.from_dict(manifest.get("mask", {}))
    gutter = 108
    gap = 10
    try:
        font = ImageFont.truetype(LABEL_FONT, 34)
    except OSError:
        font = ImageFont.load_default()

    index_map = {}
    blocks = []
    for cue in manifest["cues"]:
        tiles = []
        for line in manifest["lines"]:
            rel = cue["images"].get(line["name"])
            if not rel:
                continue
            img = Image.open(os.path.join(workdir, rel)).convert("RGB")
            box = ink_bbox(np.asarray(img), spec)
            if box is not None:
                img = img.crop((box[0], 0, box[1], img.height))
            tiles.append(img)
        if tiles:
            # Carry the timestamp, not just the index. Cue numbers are only
            # meaningful for one particular cues.json -- re-running `cues`
            # renumbers everything, and a TSV keyed on stale numbers silently
            # lands each transcription on the wrong subtitle.
            clock = "%d:%02d" % (int(cue["start"]) // 60,
                                 int(cue["start"]) % 60)
            blocks.append((cue["index"], clock, tiles))

    max_tile = 0
    for _, _, tiles in blocks:
        for tile in tiles:
            max_tile = max(max_tile, tile.width)
    sheet_w = gutter + max_tile + 16
    budget_h = int(megapixels * 1000000 / max(sheet_w, 1))

    made = 0
    batch = []
    height = 0
    for index, clock, tiles in blocks:
        block_h = gap
        for tile in tiles:
            block_h += tile.height + 2
        if batch and height + block_h > budget_h:
            name, covered = flush_sheet(sheets_dir, made + 1, batch,
                                        sheet_w, height, gutter, gap, font)
            index_map[name] = covered
            made += 1
            batch = []
            height = 0
        batch.append((index, clock, tiles, block_h))
        height += block_h
    if batch:
        name, covered = flush_sheet(sheets_dir, made + 1, batch, sheet_w,
                                    height, gutter, gap, font)
        index_map[name] = covered
        made += 1

    # Record which cues landed on which sheet. Reading 389 sheets does not
    # fit in one sitting, so the map is what lets the job be picked up again
    # later -- see the `pending` stage.
    path = os.path.join(workdir, "sheets.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(index_map, handle, ensure_ascii=False, indent=1)
    return made


def flush_sheet(sheets_dir, number, batch, width, height, gutter, gap, font):
    sheet = Image.new("RGB", (width, max(height, 1)), (250, 250, 250))
    draw = ImageDraw.Draw(sheet)
    small = font
    try:
        small = ImageFont.truetype(LABEL_FONT, 20)
    except OSError:
        pass
    y = 0
    for index, clock, tiles, block_h in batch:
        draw.line([(0, y), (width, y)], fill=(190, 190, 190), width=1)
        draw.text((10, y + 6), "%d" % index, font=font, fill=(0, 0, 0))
        draw.text((10, y + 44), clock, font=small, fill=(120, 120, 120))
        cursor = y + gap
        for tile in tiles:
            sheet.paste(tile, (gutter, cursor))
            cursor += tile.height + 2
        y += block_h
    path = os.path.join(sheets_dir, "sheet_%03d.png" % number)
    sheet.save(path)
    covered = []
    for index, _clock, _tiles, _bh in batch:
        covered.append(index)
    return os.path.basename(path), covered


# ------------------------------------------------------------------- ocr


def stage_ocr(args):
    workdir = args.work
    manifest = read_manifest(workdir)
    if args.engine == "tesseract":
        texts = ocr_tesseract(workdir, manifest, args)
    elif args.engine == "claude-api":
        texts = ocr_claude_api(workdir, manifest, args)
    else:
        raise SystemExit("unknown engine %r" % args.engine)

    path = os.path.join(workdir, "transcripts.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(texts, handle, ensure_ascii=False, indent=1)
    print("wrote %s (%d cues)" % (path, len(texts)))
    return 0


def read_manifest(workdir):
    path = os.path.join(workdir, "cues.json")
    if not os.path.exists(path):
        raise SystemExit("no cues.json in %s -- run the `cues` stage first"
                         % workdir)
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


TESS_COMMON = [
    "-c", "load_system_dawg=0",
    "-c", "load_freq_dawg=0",
    "-c", "load_punc_dawg=0",
    "-c", "load_number_dawg=0",
    "-c", "load_unambig_dawg=0",
    "-c", "load_bigram_dawg=0",
]


def prep_for_tesseract(path, spec, scale=2):
    """Binarise a strip to dark glyphs on white, which tesseract prefers.

    Do not upscale much. These subtitles are already rendered large in a
    1080p frame, and enlarging a *binarised* image only interpolates new grey
    between strokes. Measured on 12 Amis and 17 Chinese hand-read lines,
    whole-line accuracy by scale factor:

        scale   1x     2x     3x     5x
        Amis    13.3%  20.0%   6.7%   6.7%
        Chinese 52.9%  47.1%  41.2%  29.4%

    so 2x suits the Latin rows and 1x the Chinese ones; 3x (the original
    guess, never measured) was the worst of both.
    """
    rgb = np.asarray(Image.open(path).convert("RGB"))
    mask = cuelib.text_mask(rgb, spec)
    page = np.full(mask.shape, 255, dtype=np.uint8)
    page[mask] = 0
    img = Image.fromarray(page, mode="L")
    if scale == 1:
        return img
    return img.resize((int(img.width * scale), int(img.height * scale)),
                      Image.LANCZOS)


def run_tesseract(img, lang, whitelist=None, tmp=None):
    img.save(tmp)
    cmd = ["tesseract", tmp, "stdout", "-l", lang, "--psm", "7"]
    cmd += TESS_COMMON
    if whitelist:
        cmd += ["-c", "tessedit_char_whitelist=%s" % whitelist]
    out = subprocess.run(cmd, stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL).stdout
    return out.decode("utf-8", "replace").strip()


def ocr_tesseract(workdir, manifest, args):
    spec = cuelib.MaskSpec.from_dict(manifest.get("mask", {}))
    tmp = os.path.join(workdir, "_tess_tmp.png")
    results = {}
    total = len(manifest["cues"])
    for position, cue in enumerate(manifest["cues"]):
        got = {}
        for line in manifest["lines"]:
            rel = cue["images"].get(line["name"])
            if not rel:
                continue
            scale = line.get("ocr_scale", args.ocr_scale)
            img = prep_for_tesseract(os.path.join(workdir, rel), spec,
                                     scale=scale)
            text = run_tesseract(img, line.get("lang", "eng"),
                                 line.get("whitelist"), tmp)
            got[line["name"]] = clean_text(text, line)
        results[str(cue["index"])] = got
        if args.progress and position % 25 == 0:
            sys.stderr.write("\r  ocr %d/%d" % (position, total))
            sys.stderr.flush()
    if args.progress:
        sys.stderr.write("\r%-32s\r" % "")
    if os.path.exists(tmp):
        os.remove(tmp)
    return results


def clean_text(text, line):
    out = text.replace("\n", " ").strip()
    if line.get("lang", "").startswith("chi"):
        out = out.replace(" ", "")
    while "  " in out:
        out = out.replace("  ", " ")
    return out


def ocr_claude_api(workdir, manifest, args):
    """Recognise strips with Claude vision through the Anthropic API.

    Kept separate from the offline path because it needs a key and costs
    money; the offline path is what the self-test exercises.
    """
    try:
        import anthropic
    except ImportError:
        raise SystemExit(
            "claude-api engine needs the `anthropic` package: "
            "pip install anthropic")
    import base64

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("set ANTHROPIC_API_KEY to use --engine claude-api")

    client = anthropic.Anthropic()
    results = {}
    total = len(manifest["cues"])
    for position, cue in enumerate(manifest["cues"]):
        got = {}
        for line in manifest["lines"]:
            rel = cue["images"].get(line["name"])
            if not rel:
                continue
            with open(os.path.join(workdir, rel), "rb") as handle:
                blob = base64.standard_b64encode(handle.read()).decode()
            prompt = line.get("prompt") or default_prompt(line)
            message = client.messages.create(
                model=args.model,
                max_tokens=400,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": blob}},
                        {"type": "text", "text": prompt},
                    ],
                }],
            )
            parts = []
            for block in message.content:
                if block.type == "text":
                    parts.append(block.text)
            got[line["name"]] = clean_text("".join(parts).strip(), line)
        results[str(cue["index"])] = got
        if args.progress and position % 10 == 0:
            sys.stderr.write("\r  ocr %d/%d" % (position, total))
            sys.stderr.flush()
    if args.progress:
        sys.stderr.write("\r%-32s\r" % "")
    return results


def default_prompt(line):
    lang = line.get("lang", "")
    if lang.startswith("chi"):
        what = "one line of Traditional Chinese subtitle text"
    else:
        what = ("one line of Amis (Latin-script Formosan language) "
                "subtitle text; keep apostrophes and ^ exactly as shown")
    return ("This image is %s. Reply with the transcription only -- no "
            "quotes, no commentary, no translation. If the strip is blank, "
            "reply with an empty response." % what)


# ------------------------------------------------------------------- srt


def stage_srt(args):
    workdir = args.work
    manifest = read_manifest(workdir)
    texts = load_transcripts(workdir)

    order = []
    for line in manifest["lines"]:
        order.append(line["name"])
    if args.only:
        wanted = args.only.split(",")
        order = []
        for name in wanted:
            order.append(name.strip())

    entries = []
    for cue in manifest["cues"]:
        got = texts.get(str(cue["index"]), {})
        parts = []
        for name in order:
            value = (got.get(name) or "").strip()
            if value:
                parts.append(value)
        if not parts:
            continue
        entries.append((cue["start"], cue["end"], "\n".join(parts)))

    if args.merge_repeats:
        before = len(entries)
        entries = merge_repeats(entries, args.merge_gap)
        if before != len(entries):
            print("merged %d repeated-text cue(s)" % (before - len(entries)))
    entries = apply_gap_rules(entries, args.min_gap)
    body = cuelib.render_srt(entries)
    with open(args.out, "w", encoding="utf-8") as handle:
        handle.write(body)
        if body and not body.endswith("\n"):
            handle.write("\n")
    print("wrote %s (%d subtitles)" % (args.out, body.count("-->")))
    return 0


def load_transcripts(workdir):
    path = os.path.join(workdir, "transcripts.json")
    if not os.path.exists(path):
        raise SystemExit("no transcripts.json in %s -- run `ocr` first"
                         % workdir)
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def merge_repeats(entries, max_gap=1.0):
    """Fuse consecutive cues that carry exactly the same text.

    One burned-in subtitle gets split into several cues whenever the footage
    behind it moves enough to shift the mask -- video B does this constantly,
    because its glyphs sit straight on the picture. The recognised text is
    the honest arbiter of whether that was one subtitle or two, so repair it
    here instead of by loosening the pixel threshold, which would start
    swallowing genuinely different lines.
    """
    merged = []
    for start, end, text in entries:
        if merged and merged[-1][2] == text:
            if start - merged[-1][1] <= max_gap:
                merged[-1] = [merged[-1][0], max(end, merged[-1][1]), text]
                continue
        merged.append([start, end, text])
    out = []
    for start, end, text in merged:
        out.append((start, end, text))
    return out


def apply_gap_rules(entries, min_gap):
    """Stop adjacent cues from overlapping once times are rounded to ms."""
    fixed = []
    for index, (start, end, text) in enumerate(entries):
        if index + 1 < len(entries):
            nxt = entries[index + 1][0]
            if end > nxt - min_gap:
                end = max(start + 0.05, nxt - min_gap)
        fixed.append((start, end, text))
    return fixed


def parse_transcript_tsv(text, default_line):
    """Read `index <TAB> [line <TAB>] text` rows into a transcript dict.

    This is the hand-off for reading the contact sheets with a vision model
    (see SKILL.md): the sheets carry the cue numbers, so the reader only has
    to type a number and the text it can see.
    """
    out = {}
    errors = []
    for number, raw in enumerate(text.replace("\r\n", "\n").split("\n"), 1):
        row = raw.rstrip("\n")
        if not row.strip() or row.lstrip().startswith("#"):
            continue
        parts = row.split("\t")
        if len(parts) < 2:
            errors.append("line %d: need at least index<TAB>text" % number)
            continue
        key = parts[0].strip()
        if not key.isdigit():
            errors.append("line %d: %r is not a cue index" % (number, key))
            continue
        if len(parts) == 2:
            name, value = default_line, parts[1]
        else:
            name, value = parts[1].strip(), "\t".join(parts[2:])
        out.setdefault(key, {})[name] = value.strip()
    return out, errors


def stage_import(args):
    workdir = args.work
    manifest = read_manifest(workdir)
    default_line = manifest["lines"][0]["name"]
    known = set()
    for line in manifest["lines"]:
        known.add(line["name"])
    valid = set()
    for cue in manifest["cues"]:
        valid.add(str(cue["index"]))

    with open(args.source, "r", encoding="utf-8") as handle:
        parsed, errors = parse_transcript_tsv(handle.read(), default_line)

    for key in sorted(parsed):
        if key not in valid:
            errors.append("cue %s is not in cues.json" % key)
        for name in parsed[key]:
            if name not in known:
                errors.append("cue %s: unknown line name %r (known: %s)"
                              % (key, name, ", ".join(sorted(known))))
    if errors:
        for message in errors[:20]:
            sys.stderr.write("  %s\n" % message)
        raise SystemExit("%d problem(s) in %s; nothing imported"
                         % (len(errors), args.source))

    path = os.path.join(workdir, "transcripts.json")
    existing = {}
    if os.path.exists(path) and not args.replace:
        with open(path, "r", encoding="utf-8") as handle:
            existing = json.load(handle)
    for key in parsed:
        existing.setdefault(key, {}).update(parsed[key])
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(existing, handle, ensure_ascii=False, indent=1)

    # Record which rows a human actually looked at. export-gt trusts only
    # these, so a recogniser's own mistakes can never become training labels.
    verified = load_verified(workdir)
    for key in parsed:
        for name in parsed[key]:
            verified.setdefault(key, {})[name] = True
    save_verified(workdir, verified)

    covered = 0
    for cue in manifest["cues"]:
        if existing.get(str(cue["index"])):
            covered += 1
    print("imported %d cue(s) from %s" % (len(parsed), args.source))
    print("transcripts now cover %d/%d cues"
          % (covered, len(manifest["cues"])))
    print("marked %d cue(s) as human-verified" % len(parsed))
    return 0


VERIFIED_NAME = "verified.json"


def load_verified(workdir):
    path = os.path.join(workdir, VERIFIED_NAME)
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def save_verified(workdir, verified):
    path = os.path.join(workdir, VERIFIED_NAME)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(verified, handle, ensure_ascii=False, indent=1)


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
    manifest = read_manifest(workdir)
    texts = load_transcripts(workdir)
    spec = cuelib.MaskSpec.from_dict(manifest.get("mask", {}))
    verified = load_verified(workdir)

    wanted = None
    if args.line:
        wanted = set()
        for name in args.line.split(","):
            wanted.add(name.strip())

    os.makedirs(args.out, exist_ok=True)
    written = 0
    skipped_blank = 0
    skipped_unverified = 0
    for cue in manifest["cues"]:
        key = str(cue["index"])
        got = texts.get(key, {})
        for line in manifest["lines"]:
            name = line["name"]
            if wanted is not None and name not in wanted:
                continue
            text = (got.get(name) or "").strip()
            rel = cue["images"].get(name)
            if not rel:
                continue
            if not text:
                # tesstrain rejects an empty .gt.txt outright
                skipped_blank += 1
                continue
            if not args.include_unverified:
                if not verified.get(key, {}).get(name):
                    skipped_unverified += 1
                    continue
            img = Image.open(os.path.join(workdir, rel)).convert("RGB")
            box = ink_bbox(np.asarray(img), spec, pad=8)
            if box is not None:
                img = img.crop((box[0], 0, box[1], img.height))
            stem = "%s_%05d_%s" % (args.prefix, cue["index"], name)
            img.save(os.path.join(args.out, stem + ".png"))
            path = os.path.join(args.out, stem + ".gt.txt")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(text + "\n")
            written += 1

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
    return 0


def stage_pending(args):
    """Report which contact sheets still need a human read.

    Reading every sheet of a feature-length video does not fit in one
    sitting, so this is what makes the job resumable: it pairs the
    sheet->cue map written by `cues` against the rows already confirmed by
    `import`, and names the next batch to open.
    """
    workdir = args.work
    manifest = read_manifest(workdir)
    verified = load_verified(workdir)

    path = os.path.join(workdir, "sheets.json")
    if not os.path.exists(path):
        raise SystemExit(
            "no sheets.json in %s -- rebuild the contact sheets so the "
            "sheet-to-cue map exists" % workdir)
    with open(path, "r", encoding="utf-8") as handle:
        sheet_map = json.load(handle)

    names = []
    for line in manifest["lines"]:
        names.append(line["name"])
    if args.line:
        names = []
        for name in args.line.split(","):
            names.append(name.strip())

    done = 0
    todo = []
    for sheet in sorted(sheet_map):
        missing = []
        for index in sheet_map[sheet]:
            got = verified.get(str(index), {})
            for name in names:
                if not got.get(name):
                    missing.append(index)
                    break
        if missing:
            todo.append((sheet, missing))
        else:
            done += 1

    total = len(sheet_map)
    print("sheets: %d done, %d remaining (of %d)"
          % (done, len(todo), total))
    if not todo:
        print("all sheets verified for line(s): %s" % ", ".join(names))
        return 0

    shown = todo
    if args.limit:
        shown = todo[:args.limit]
    print("next batch (%d shown):" % len(shown))
    for sheet, missing in shown:
        print("  sheets/%s  cues %s" % (sheet, missing))
    return 0


SPECIAL_MARKS = "^\'\":"


def glossary_tokens(text):
    """Pull out the words whose spelling batches are likely to disagree on."""
    found = []
    for raw in text.replace("\u3000", " ").split():
        word = raw.strip(".,!?()[]")
        if len(word) < 2:
            continue
        special = False
        for mark in SPECIAL_MARKS:
            if mark in word:
                special = True
                break
        proper = word[:1].isupper() and word[:1].isalpha()
        if special or proper:
            found.append(word)
    return found


def stage_glossary(args):
    """List recurring spellings so later batches can be told about them.

    A subagent only ever sees its own dozen sheets, so it cannot know how an
    earlier batch spelled a programme name or a mark-carrying word. Feeding
    this list into the prompt of subsequent batches is what keeps the corpus
    internally consistent -- checking afterwards catches the damage, telling
    them up front avoids it.
    """
    workdir = args.work
    manifest = read_manifest(workdir)
    texts = load_transcripts(workdir)
    verified = load_verified(workdir)

    wanted = None
    if args.line:
        wanted = set()
        for name in args.line.split(","):
            wanted.add(name.strip())

    counts = {}
    for cue in manifest["cues"]:
        key = str(cue["index"])
        row = texts.get(key, {})
        for line in manifest["lines"]:
            name = line["name"]
            if wanted is not None and name not in wanted:
                continue
            if args.verified_only and not verified.get(key, {}).get(name):
                continue
            value = (row.get(name) or "").strip()
            if not value:
                continue
            for token in glossary_tokens(value):
                counts[token] = counts.get(token, 0) + 1

    ranked = []
    for token in counts:
        if counts[token] >= args.min_count:
            ranked.append((counts[token], token))
    ranked.sort(key=lambda pair: (-pair[0], pair[1]))

    if not ranked:
        print("no recurring special-mark or proper-noun spellings found")
        return 0

    print("# 既定寫法（出現 >= %d 次）-- 貼進後續批次的 prompt"
          % args.min_count)
    shown = ranked
    if args.limit:
        shown = ranked[:args.limit]
    for count, token in shown:
        print("  %s   (%d 次)" % (token, count))
    if len(ranked) > len(shown):
        print("  ... 另有 %d 個未列出" % (len(ranked) - len(shown)))
    return 0


def stage_auto(args):
    workdir = args.work or (os.path.splitext(args.out)[0] + ".work")
    os.makedirs(workdir, exist_ok=True)

    cue_args = argparse.Namespace(
        video=args.video, out=workdir, region=args.region,
        autodetect=args.autodetect, fps=args.fps, start=args.start,
        duration=args.duration, min_ink=args.min_ink, change=args.change,
        min_stable=args.min_stable, min_duration=args.min_duration,
        samples=args.samples, lang=args.lang, sheets=args.sheets,
        sheet_megapixels=args.sheet_megapixels, progress=args.progress)
    stage_cues(cue_args)

    ocr_args = argparse.Namespace(
        work=workdir, engine=args.engine, model=args.model,
        ocr_scale=args.ocr_scale, progress=args.progress)
    stage_ocr(ocr_args)

    srt_args = argparse.Namespace(
        work=workdir, out=args.out, only=args.only, min_gap=args.min_gap,
        merge_repeats=args.merge_repeats, merge_gap=args.merge_gap)
    stage_srt(srt_args)
    return 0


# ------------------------------------------------------------------- cli


def build_parser():
    parser = argparse.ArgumentParser(
        prog="subs2srt", description=__doc__,
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
                          "per line (see prep_for_tesseract)")
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


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
