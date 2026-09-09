"""Which pixels belong to the same glyph, and how deep it reaches.

WHY THIS EXISTS
---------------
Every reader of a batch has to answer the same pixel question -- where do
the formosan row's descenders really end? -- and the environment carries
no scipy, so each of them writes their own connected-component pass.
That is exactly how the corpus has been bitten before: two readers once
reimplemented `band_present` as HSV saturation, got the same wrong number
as each other, and the agreement was mistaken for confirmation. One
implementation, exercised by tests, removes the class of error.

WHAT THE DESCENDER QUESTION ACTUALLY IS
---------------------------------------
The band drifts down the fixed region from episode to episode and inside
one episode too. Where it sits low, the formosan row's descenders cross
the slot floor and land in the `han` strip: the contact sheet then cuts
them, `y` loses its tail and reads as `v`, `q` and `g` become
indistinguishable, and the seam window has to move. So the measurement is
"does the formosan row's ink reach past y948", and `deepest_bottom` is
that measurement.

TWO WAYS TO GET IT WRONG, BOTH MET IN PRACTICE
----------------------------------------------
Counting the last row that holds any ink at all reports a stray
anti-aliasing speck as a descender (123 cue 313 measured 945 on the
strength of one w1/h1/area1 pixel; 547 measured 951 the same way).
Widening the window until it would catch an overflow instead catches the
Chinese row's ascenders coming up. `deepest_bottom` rules out both: a
component counts only if its *top* starts inside the slot, and only if it
is bigger than a speck.

Filter on area, never on width. A real `l` stem is one pixel wide.
"""
import numpy as np


def label(mask):
    """(labels, count) for a boolean mask; 8-connected, 0 is background.

    Diagonal touching joins, because glyph strokes meet at corners and a
    4-connected pass would split one letter into several.
    """
    height, width = mask.shape
    parent = [0]
    labels = np.zeros((height, width), dtype=np.int32)

    def find(node):
        root = node
        while parent[root] != root:
            root = parent[root]
        while parent[node] != root:
            parent[node], node = root, parent[node]
        return root

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    for y in range(height):
        for x in range(width):
            if not mask[y][x]:
                continue
            seen = []
            for dy, dx in ((-1, -1), (-1, 0), (-1, 1), (0, -1)):
                ny, nx = y + dy, x + dx
                if 0 <= ny < height and 0 <= nx < width and labels[ny][nx]:
                    seen.append(int(labels[ny][nx]))
            if not seen:
                parent.append(len(parent))
                labels[y][x] = len(parent) - 1
            else:
                lowest = min(seen)
                labels[y][x] = lowest
                for other in seen:
                    union(lowest, other)

    # 頭一逝行過ê時是「臨時號碼」，相黏ê會有幾若个。遮重號做 1..n，
    # 中間無空喙——按呢 boxes() 才會使直接照號碼行。
    remap = {}
    out = np.zeros_like(labels)
    for y in range(height):
        for x in range(width):
            if labels[y][x]:
                root = find(int(labels[y][x]))
                if root not in remap:
                    remap[root] = len(remap) + 1
                out[y][x] = remap[root]
    return out, len(remap)


def boxes(labels, count):
    """[(x0, y0, width, height, area)] per label, in label order.

    `area` is the ink, not the box: an `L` in a 2x2 box has area 3. The
    descender census filters on area for that reason -- a one-pixel speck
    and a one-pixel-wide stem are the same width but not the same thing.
    """
    out = []
    for i in range(1, count + 1):
        ys, xs = np.nonzero(labels == i)
        out.append((int(xs.min()), int(ys.min()),
                    int(xs.max() - xs.min() + 1),
                    int(ys.max() - ys.min() + 1),
                    int(len(ys))))
    return out


def deepest_bottom(mask, top, floor, min_area=2):
    """Lowest row reached by a glyph that *starts* between top and floor.

    Rows are the mask's own, so add the region's y offset to compare
    against an absolute slot floor. Returns None when nothing starts in
    that band at all -- a cue with no formosan text, most often.

    `top`/`floor` are the slot the glyphs belong to: a component whose
    top row is at or below `floor` is the next row's, not this one's.
    `min_area` is inclusive -- the smallest component still counted.
    2 is the working value: it drops the lone anti-aliasing pixel and
    keeps everything that is a stroke.
    """
    labels, count = label(mask)
    deepest = None
    for (_x0, y0, _w, height, area) in boxes(labels, count):
        if not top <= y0 < floor:
            continue
        if area < min_area:
            continue
        bottom = y0 + height - 1
        if deepest is None or bottom > deepest:
            deepest = bottom
    return deepest
