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


# A column carrying this many lit pixels is a stroke rather than a stray:
# it is enough to tell the subtitle's run from bright background, and low
# enough that no run of type fails to reach it.
STRONG_INK = 3
# Two strong runs further apart than this are different things. A line of
# type never leaves this much white inside itself -- the widest gap
# measured inside one was a phrase break of about 80px -- while the
# picture's own bright patches sit hundreds of pixels away.
FAR_GAP = 200
# ...but ink this close to the chosen run belongs to it however faint it
# is. This is what keeps an apostrophe: `'` is three or four columns of
# one or two lit pixels, a few px past the last glyph.
NEAR_GAP = 30
# Below this there is no run to choose between; keep every lit column.
MIN_STRONG_COLUMNS = 8


def _ink_columns(mask, pad=6, anchor=None):
    """(x0, x1) around the columns the subtitle occupies, or None.

    Two jobs pull against each other here. Ink that is not the subtitle has
    to go: the mask is a brightness threshold, so on news it catches dry
    grass and newspaper pages across the whole 1920, and on 開會了 the
    lower line's strip catches the bottom edge of the line above it -- on
    111's cue 228 "any ink" spans 279..1725 for a seven-character line that
    occupies 799..1295. Keeping that ink made every Claude Vision input
    sheet in an episode as wide as its worst strip.

    But every stroke of the subtitle has to stay, including the ones the
    mask barely registers. Choosing by ink alone does not do that: asking
    for `STRONG_INK` in every column shaved 40 of 085's formosan lines,
    all of them ending in `'`, because an apostrophe lights one or two
    pixels per column.

    So the two questions are separated. Strong ink decides **which** run is
    the subtitle -- runs more than `FAR_GAP` apart are different things,
    and the one carrying the most ink wins. Any ink then decides **where
    that run ends**, growing the answer outwards while the next lit column
    is within `NEAR_GAP`.

    Columns further left than `MAX_TILE` from the right edge are dropped
    before either question is asked, so that the strip can never make a
    page too wide to be delivered at full size; see that constant.

    `anchor` is the x a right-anchored subtitle's right edge is known to
    reach, and it comes from the preset because it is a fact about one
    programme, not about subtitles. On 族語新聞 the line is flush right
    (27 episodes: the ink's right edge sits at 1735-1737 against a
    standard deviation of 460-470 for the left edge). There, choosing by
    ink alone loses whole lines: an anchor desk's white top, a
    full-screen card, a field of dry grass all sit mid-frame and carry
    more ink than the line does, so they win the run and the line falls
    outside the crop -- 168 of 5,798 cues over six episodes (2.9%), and
    nothing reports it. When an anchor is given, the run whose right edge
    reaches it is **added** to the chosen run rather than replacing it:
    the window can only grow, so nothing that was visible before can be
    lost. Measured over those 5,798 cues: 0 dropped lines, 0 windows
    narrower than before, 4% more visual tokens.

    Left as None it does nothing at all, which is what 開會了 needs --
    that programme's line is centred (111's cue 228 occupies 799..1295)
    and the ink at 1710 is the line above bleeding in, which must still
    be dropped.
    """
    # The far left goes before anything else is decided, not after. Trim
    # the answer instead and a bright left edge can win the run and take
    # the crop with it, and the line is gone with nothing reporting it.
    dropped = max(mask.shape[1] - MAX_TILE, 0)
    if dropped:
        mask = mask[:, dropped:]
    cols = mask.sum(axis=0)
    lit = np.nonzero(cols > 0)[0]
    if len(lit) == 0:
        return None
    strong = np.nonzero(cols >= STRONG_INK)[0]
    if len(strong) < MIN_STRONG_COLUMNS:
        lo, hi = int(lit[0]), int(lit[-1])
    else:
        runs = []
        start = prev = int(strong[0])
        for column in strong[1:]:
            column = int(column)
            if column - prev > FAR_GAP:
                runs.append((start, prev))
                start = column
            prev = column
        runs.append((start, prev))
        best = None
        for first, last in runs:
            weight = int(cols[first:last + 1].sum())
            if best is None or weight > best[0]:
                best = (weight, first, last)
        lo, hi = _grow(lit, best[1], best[2])
        if anchor is not None:
            # `runs` is in the trimmed frame and `anchor` is absolute, so
            # the threshold has to come back by `dropped`. Comparing them
            # raw picks the wrong run, which is the failure this exists
            # to stop.
            reach = anchor - dropped
            far = None
            for first, last in runs:
                if last >= reach:
                    far = (first, last)
            if far is not None:
                far_lo, far_hi = _grow(lit, far[0], far[1])
                lo, hi = min(lo, far_lo), max(hi, far_hi)
    return (dropped + max(lo - pad, 0),
            dropped + min(hi + pad + 1, mask.shape[1]))


def _grow(lit, lo, hi):
    """Widen [lo, hi] outwards while the next lit column is within reach.

    Strong ink says which run is the subtitle; any ink says where it
    ends. Pulled out of `_ink_columns` because the anchored run has to be
    grown the same way before the two are merged -- growing only one of
    them clipped the strokes off whichever end came from the other.
    """
    while True:
        near = lit[(lit >= lo - NEAR_GAP) & (lit <= hi + NEAR_GAP)]
        grown_lo, grown_hi = int(near.min()), int(near.max())
        if grown_lo == lo and grown_hi == hi:
            return lo, hi
        lo, hi = grown_lo, grown_hi


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


def _cue_blocks(workdir, manifest, spec, row_slots=None,
                compare_cols=None, right_anchor=None):
    """(blocks, undecided, decided, blank) -- one block per cue with a strip.

    Columns are cropped as they always were, to wherever there is ink. Rows
    are cropped to the slot the line is in, when that can be told; the ink
    used to tell is measured only inside `compare_cols`, because over the
    whole width a bright background (dry grass, a newspaper page) levels the
    two slots out and the answer comes back "cannot tell" for strips that
    are perfectly clear -- 186 of 1,188 on one episode, against 79 when
    measured inside the window.
    """
    # 版面ê事實對 preset 來，毋是對 manifest 來——`cues.json` 內底彼
    # 份 mask 是切 cue 彼時寫ê，無 `compare_cols` 嘛無 `right_anchor`。
    # 呼叫ê人有提就用伊ê，無才退轉去問 spec。
    anchor = spec.right_anchor if right_anchor is None else right_anchor
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
            box = _ink_columns(mask, anchor=anchor)
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
            # A strip with no ink at all has nothing to crop to, but it
            # must still take the trim: at full frame width it is the one
            # thing left that can make a page too wide to be delivered
            # whole (25 of 058晨's 1,284 strips are blank).
            left, right = box if box is not None else (
                max(img.width - MAX_TILE, 0), img.width)
            if (left, right) != (0, img.width) or rows is not None:
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


# Claude reads an image in 28x28 patches and is charged
# `ceil(w/28) * ceil(h/28)` visual tokens for it. Opus 5 reads at the high
# resolution tier: 4784 visual tokens. Go past that and the API scales the
# whole page down -- the glyphs with it -- without saying so anywhere.
# The previous budget here was a flat 1.10 megapixels, which was the
# standard tier (1568/1568) and left two thirds of a page unused.
#
# The long edge is 2000 rather than the model's own 2576 because the tool
# that hands a sheet to the reader resizes anything longer: measured
# 2026-09-09, an 818x2484 sheet arrived annotated "displayed at 659x2000".
# Every pixel above 2000 is therefore paid for and then thrown away, and
# what the reader gets is a blurred one -- the two who read those sheets
# went on to crop and enlarge every page to tell `I` from `l`, which cost
# several times what the packing had saved. Capping here costs nothing:
# on 058晨 it is 51 sheets instead of 40 for the same 106k visual tokens.
#
# All three numbers belong to somebody else's service, so changing the
# model, the tier, or the tool that delivers the image means measuring
# them again.
PATCH = 28
LONG_EDGE = 2000
VISUAL_TOKENS = 4784

# The page a strip sits on is `GUTTER + strip + TILE_MARGIN` wide, so a
# strip wider than this makes a page the delivery tool has to shrink. The
# frame is 1920 and the gutter and margin come to 124, which is 2044 --
# over by 44 -- so the widest strips have to give the far left back.
#
# What is being given back is background, not type. Measured on three
# episodes, only 1.2% of strips are wide enough to be trimmed at all, and
# every one of those has its ink starting at column 0, which is a bright
# picture (a graphic card, a newspaper page), never a subtitle: news
# subtitles are anchored at the right, x≈1736, and the longest line in
# these episodes -- 23 characters at 62px -- still starts at x≈310.
# 開會了's lines are centred and start at x=654 (p1: 166); the only strips
# it has with ink further left are blank gradient band with a reflection
# in it, 46-69px wide, no type at all.
#
# **This assumes subtitles are never left-aligned.** A corpus that puts
# them on the left has to be measured again before it comes through here.
#
# SPARE is asked for by the user (2026-09-10): trim a little more than the
# arithmetic needs, so that a change of a few pixels anywhere does not
# silently put a page over the limit.
#
# The widest page is then taken down to a whole number of patch columns.
# A page is charged `ceil(w/28)` columns however far into the last one it
# reaches, so 1990px costs the same 72 columns as 2016 would -- 26px
# bought and thrown away. 1988 is 71 columns exactly. Two pixels of
# background, on the side the subtitle never reaches, for a whole column:
# small (0.2% of an episode's visual tokens, since hardly any strip is
# that wide) but free.
GUTTER = 108
TILE_MARGIN = 16
SPARE = 10
MAX_PAGE = ((LONG_EDGE - SPARE) // PATCH) * PATCH
MAX_TILE = MAX_PAGE - GUTTER - TILE_MARGIN


def _height_bound(page_w):
    """The tallest a page this wide can be and still not be scaled down."""
    patches = -(-page_w // PATCH)
    return min(LONG_EDGE, (VISUAL_TOKENS // max(patches, 1)) * PATCH)


def _sheet_width(widest_tile, gutter):
    """The page width a sheet whose widest strip is `widest_tile` needs.

    One sheet's own strips decide this, not the episode's. Taking the
    widest strip anywhere in the work dir -- what this did before --
    charged every sheet for the worst one: on 058晨 all 327 sheets came
    out 2044 px wide while the median strip was 1230, because 5% of the
    strips catch bright background across the full 1920.
    """
    return gutter + widest_tile + TILE_MARGIN


def _block_size(tiles, gap):
    """(height, width) one cue's block occupies on a sheet."""
    height = gap
    width = 0
    for tile in tiles:
        height += tile.height + 2
        width = max(width, tile.width)
    return height, width


def _by_width(blocks, gap):
    """The cues re-ordered widest-with-widest.

    A sheet is as wide as its widest strip, so one 1900px strip among
    600px ones makes every line on that sheet cost three times what it
    needs to. Sorting empties the penalty out: measured on 058晨 it takes
    the episode from 59.2% of the current visual tokens to 40.4%, and a
    sheet of 14 cues then costs the same per cue as a sheet of 4.

    A sheet then no longer covers one stretch of programme, which nothing
    downstream may depend on: a cue's number and clock travel with its
    strip in the same block, `sheets.json` is the one sheet-to-cue map,
    and `verified.json` is keyed by cue number so a part-finished read
    still resumes.
    """
    order = list(blocks)
    order.sort(key=lambda block: (_block_size(block[2], gap)[1], block[0]))
    return order


def build_sheets(workdir, manifest, row_slots=None,
                 compare_cols=None, right_anchor=None):
    """Tile cue strips into a few big images for a vision model to read.

    Reading 800 separate crops costs 800 round trips; reading 40 sheets costs
    40. So a page is grown until one more strip would push it past what the
    reader can take in at full size -- overshoot and the page gets downscaled
    and the glyphs stop being legible, which defeats the point. See
    `_height_bound` for where that limit comes from.
    """
    sheets_dir = os.path.join(workdir, "sheets")
    os.makedirs(sheets_dir, exist_ok=True)
    spec = cuelib.MaskSpec.from_dict(manifest.get("mask", {}))
    gutter = GUTTER
    gap = 10
    try:
        font = ImageFont.truetype(LABEL_FONT, 34)
    except OSError:
        font = ImageFont.load_default()

    index_map = {}
    blocks, undecided, decided, blank = _cue_blocks(
        workdir, manifest, spec, row_slots, compare_cols, right_anchor)
    if row_slots:
        print("row slots: %d cropped, %d could not be told (%.1f%%), "
              "%d blank" % (decided, undecided,
                            100.0 * undecided_share(undecided, decided,
                                                    blank), blank))
    made = 0
    batch = []
    height = 0
    widest = 0
    for index, clock, tiles, start in _by_width(blocks, gap):
        block_h, block_w = _block_size(tiles, gap)
        grown = max(widest, block_w)
        # The width this cue would give the sheet decides the height it is
        # allowed: a page is charged by area, so a wider page may hold
        # fewer rows. Ask before adding, not after.
        budget_h = _height_bound(_sheet_width(grown, gutter))
        if batch and height + block_h > budget_h:
            name, covered = flush_sheet(sheets_dir, batch,
                                        _sheet_width(widest, gutter),
                                        height, gutter, gap, font)
            index_map[name] = covered
            made += 1
            batch = []
            height = 0
            grown = block_w
        batch.append((index, clock, tiles, block_h, start))
        height += block_h
        widest = grown
    if batch:
        name, covered = flush_sheet(sheets_dir, batch,
                                    _sheet_width(widest, gutter),
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
    # The earliest cue on the sheet, not `batch[0]`: the strips are packed
    # widest-with-widest, so the one that happens to sort first is an
    # arbitrary pick out of the whole episode.
    earliest = None
    for _index, _clock, _tiles, _bh, start in batch:
        if earliest is None or start < earliest:
            earliest = start
    path = os.path.join(sheets_dir, stripname.sheet_of(earliest))
    sheet.save(path)
    covered = []
    for index, _clock, _tiles, _bh, _start in batch:
        covered.append(index)
    return os.path.basename(path), covered
