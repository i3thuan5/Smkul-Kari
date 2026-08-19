#!/usr/bin/env python3
"""Tiling cue strips into contact sheets for a vision model to read.

Reading 800 separate crops costs 800 round trips; reading 40 sheets costs 40.
Everything here exists to make one page carry as many legible lines as
possible, and to record which cue landed on which sheet so a part-finished
read can be picked up again.
"""
import json
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from scripts.ocr import cuelib

LABEL_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


# -------------------------------------------------------- contact sheets


def ink_bbox(rgb, spec, pad=6):
    mask = cuelib.text_mask(rgb, spec)
    cols = np.nonzero(mask.sum(axis=0) > 0)[0]
    if len(cols) == 0:
        return None
    x0 = max(int(cols[0]) - pad, 0)
    x1 = min(int(cols[-1]) + pad + 1, rgb.shape[1])
    return (x0, x1)


def _cue_blocks(workdir, manifest, spec):
    """(index, clock, tiles) per cue that has at least one strip."""
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
    return blocks


def _sheet_width(blocks, gutter):
    max_tile = 0
    for _, _, tiles in blocks:
        for tile in tiles:
            max_tile = max(max_tile, tile.width)
    return gutter + max_tile + 16


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
    blocks = _cue_blocks(workdir, manifest, spec)
    sheet_w = _sheet_width(blocks, gutter)
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
