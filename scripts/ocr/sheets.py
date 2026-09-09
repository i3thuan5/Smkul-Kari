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
from scripts.ocr import stripname

LABEL_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


# -------------------------------------------------------- contact sheets


def ink_bbox(rgb, spec, pad=6):
    return _ink_columns(cuelib.text_mask(rgb, spec), pad)


def _ink_columns(mask, pad=6):
    """(x0, x1) around every column with ink, or None when there is none.

    Any ink at all counts, unlike the row crop next door: a single stroke at
    the edge of a line is a character, and trimming by "most of the ink"
    was measured to shave apostrophes and the dots off i's.
    """
    cols = np.nonzero(mask.sum(axis=0) > 0)[0]
    if len(cols) == 0:
        return None
    x0 = max(int(cols[0]) - pad, 0)
    x1 = min(int(cols[-1]) + pad + 1, mask.shape[1])
    return (x0, x1)


def slot_crop(mask, slots):
    """Which of the band's two slots this line is in, as (lo, hi) rows.

    None means "cannot tell, keep the whole band" -- the behaviour before
    this existed. That fallback is the safety of the whole idea: every case
    it cannot decide costs only the saving, never a subtitle.

    What it is really guarding against is not two rows of subtitle -- the
    layout has one row in one of two heights, and 3,339 strips contained no
    counter-example. It is the picture's own text competing for the strip:
    banners, newspaper pages, full-screen graphic cards. Those come out
    white-on-dark exactly like a subtitle and the mask cannot tell them
    apart, so when both slots carry comparable ink the strip is left whole.
    """
    if not slots:
        return None
    split = int(slots.get("split", 0))
    height = mask.shape[0]
    if split <= 0 or split >= height:
        return None
    pad = int(slots.get("pad", 6))
    ratio = float(slots.get("min_ratio", 2.0))
    floor = int(slots.get("min_ink", 200))
    rows = mask.sum(axis=1)
    upper = int(rows[:split].sum())
    lower = int(rows[split:].sum())
    if upper + lower < floor:
        return None
    big, small = max(upper, lower), min(upper, lower)
    if big < ratio * max(small, 1):
        return None
    if upper > lower:
        return (0, min(split + pad, height))
    return (max(split - pad, 0), height)


def undecided_share(undecided, decided, blank=0):
    """Fraction of the strips that had text but could not be placed.

    Blank strips are deliberately outside both halves of the fraction: how
    much of an episode is silent says nothing about its layout, and folding
    them in widened the spread across 27 episodes from 3.5 to 5.7 points,
    which is the opposite of what a signal should do.
    """
    total = undecided + decided
    if total <= 0:
        return 0.0
    return float(undecided) / total


def _cue_blocks(workdir, manifest, spec, row_slots=None, compare_cols=None):
    """(blocks, undecided, decided, blank) -- one block per cue with a strip.

    Columns are cropped as they always were, to wherever there is ink. Rows
    are cropped to the slot the line is in, when that can be told; the ink
    used to tell is measured only inside `compare_cols`, because over the
    whole width a bright background (dry grass, a newspaper page) levels the
    two slots out and the answer comes back "cannot tell" for strips that
    are perfectly clear -- 186 of 1,188 on one episode, against 79 when
    measured inside the window.
    """
    blocks = []
    undecided = decided = blank = 0
    for cue in manifest["cues"]:
        tiles = []
        for line in manifest["lines"]:
            rel = cue["images"].get(line["name"])
            if not rel:
                continue
            img = Image.open(os.path.join(workdir, rel)).convert("RGB")
            mask = cuelib.text_mask(np.asarray(img), spec)
            box = _ink_columns(mask)
            narrow = mask
            if compare_cols:
                narrow = mask[:, int(compare_cols[0]):int(compare_cols[1])]
            rows = slot_crop(narrow, row_slots)
            if row_slots:
                if rows is not None:
                    decided += 1
                elif int(narrow.sum()) < int(row_slots.get("min_ink", 200)):
                    blank += 1
                else:
                    undecided += 1
            top, bottom = rows if rows else (0, img.height)
            if box is not None or rows is not None:
                left, right = box if box is not None else (0, img.width)
                img = img.crop((left, top, right, bottom))
            tiles.append(img)
        if tiles:
            # Carry the timestamp, not just the index. Cue numbers are only
            # meaningful for one particular cues.json -- re-running `cues`
            # renumbers everything, and a TSV keyed on stale numbers silently
            # lands each transcription on the wrong subtitle.
            clock = "%d:%02d" % (int(cue["start"]) // 60,
                                 int(cue["start"]) % 60)
            blocks.append((cue["index"], clock, tiles, cue["start"]))
    return blocks, undecided, decided, blank


def _sheet_width(blocks, gutter):
    max_tile = 0
    for _, _, tiles, _start in blocks:
        for tile in tiles:
            max_tile = max(max_tile, tile.width)
    return gutter + max_tile + 16


def build_sheets(workdir, manifest, megapixels=1.10, row_slots=None,
                 compare_cols=None):
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
    blocks, undecided, decided, blank = _cue_blocks(
        workdir, manifest, spec, row_slots, compare_cols)
    if row_slots:
        print("row slots: %d cropped, %d could not be told (%.1f%%), "
              "%d blank" % (decided, undecided,
                            100.0 * undecided_share(undecided, decided,
                                                    blank), blank))
    sheet_w = _sheet_width(blocks, gutter)
    budget_h = int(megapixels * 1000000 / max(sheet_w, 1))

    made = 0
    batch = []
    height = 0
    for index, clock, tiles, start in blocks:
        block_h = gap
        for tile in tiles:
            block_h += tile.height + 2
        if batch and height + block_h > budget_h:
            name, covered = flush_sheet(sheets_dir, batch,
                                        sheet_w, height, gutter, gap, font)
            index_map[name] = covered
            made += 1
            batch = []
            height = 0
        batch.append((index, clock, tiles, block_h, start))
        height += block_h
    if batch:
        name, covered = flush_sheet(sheets_dir, batch, sheet_w,
                                    height, gutter, gap, font)
        index_map[name] = covered
        made += 1

    # Record which cues landed on which sheet. Reading 389 sheets does not
    # fit in one sitting, so the map is what lets the job be picked up again
    # later -- see the `pending` stage.
    path = os.path.join(workdir, "sheets.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(index_map, handle, ensure_ascii=False, indent=2,
                  sort_keys=True)
    return made


def flush_sheet(sheets_dir, batch, width, height, gutter, gap, font):
    sheet = Image.new("RGB", (width, max(height, 1)), (250, 250, 250))
    draw = ImageDraw.Draw(sheet)
    small = font
    try:
        small = ImageFont.truetype(LABEL_FONT, 20)
    except OSError:
        pass
    y = 0
    for index, clock, tiles, block_h, _start in batch:
        draw.line([(0, y), (width, y)], fill=(190, 190, 190), width=1)
        draw.text((10, y + 6), "%d" % index, font=font, fill=(0, 0, 0))
        draw.text((10, y + 44), clock, font=small, fill=(120, 120, 120))
        cursor = y + gap
        for tile in tiles:
            sheet.paste(tile, (gutter, cursor))
            cursor += tile.height + 2
        y += block_h
    # Named for where it begins, not for its place in the batch: cue
    # numbers move when a cue is split and the sheets are rebuilt, so an
    # ordinal names a different piece of programme than it did before.
    path = os.path.join(sheets_dir, stripname.sheet_of(batch[0][4]))
    sheet.save(path)
    covered = []
    for index, _clock, _tiles, _bh, _start in batch:
        covered.append(index)
    return os.path.basename(path), covered
