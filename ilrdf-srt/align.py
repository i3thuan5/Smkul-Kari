#!/usr/bin/env python3
"""Snap noisy OCR cues back onto the 文稿 text they were typeset from.

Tesseract reads this material badly -- `去年底桃園復興巴陵的一場大火` comes back
as `同/和)[人圖復興叫陜病一易大六` -- but it does not read it *randomly*. Enough
characters survive to locate each cue inside the episode's script, and once
located the script supplies the exact wording.

The whole OCR stream is matched against the whole script at once rather than
cue by cue, so the alignment is monotonic by construction: a cue can only be
placed after the cue before it. That is what stops a repeated phrase from
pulling one cue to the wrong story.

Two independent tests must both pass before a cue is rewritten:

  coverage    how much of the cue's own text was found in the script
  compactness how tightly it landed -- a 17 character cue whose matches are
              smeared over 200 characters of script has not been located, it
              has collided with common characters in the wrong story

Coverage alone accepts exactly that kind of collision, which is why both are
required. Anything that fails keeps the recogniser's text and is counted as
unaligned, because a confidently wrong subtitle is worse than a visibly
broken one.
"""
import argparse
import difflib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import wenkao                                            # noqa: E402

# Characters worth matching on: Han, digits and Latin. Punctuation is
# dropped because the subtitler re-punctuates freely and tesseract invents
# it constantly.
KEEP = re.compile(r"[㐀-䶿一-鿿A-Za-z0-9]")


def normalise(text):
    out = []
    for ch in text:
        if KEEP.match(ch):
            out.append(ch)
    return "".join(out)


def build_reference(folder):
    """Character stream for the episode plus a map back to the raw text.

    Two parallel views are kept: `norm` drives the matching, `raw` carries
    the original punctuation so the emitted subtitle reads the way it was
    written. `back[i]` is the index in `raw` of the i-th matched character.
    """
    raw = []
    norm = []
    back = []
    lines = []
    for item in wenkao.episode_text(folder):
        for line in item["lines"]:
            start = len(norm)
            for ch in line:
                raw.append(ch)
                if KEEP.match(ch):
                    norm.append(ch)
                    back.append(len(raw) - 1)
            if len(norm) > start:
                lines.append({"start": start, "end": len(norm),
                              "text": line})
            raw.append("\n")
    return "".join(raw), "".join(norm), back, lines


GRAM = 3
MAX_POSTINGS = 60
CANDIDATES = 4


def candidates(text, index):
    """Where in the script this cue might start, by k-gram vote.

    Each surviving k-gram votes for the offset that would put the cue there,
    so a cue read half-right still concentrates its votes on one offset while
    its wrong characters scatter theirs harmlessly.
    """
    votes = {}
    limit = len(text) - GRAM + 1
    for j in range(limit):
        postings = index.get(text[j:j + GRAM])
        if not postings or len(postings) > MAX_POSTINGS:
            continue                      # too common to be evidence
        for q in postings:
            at = q - j
            if at >= 0:
                votes[at] = votes.get(at, 0) + 1
    ranked = sorted(votes.items(), key=lambda kv: -kv[1])
    return ranked[:CANDIDATES]


def backbone(per_cue):
    """Pick one offset per cue so the sequence runs forwards.

    Cues and script both advance, so the alignment is a longest increasing
    subsequence over the candidate offsets, weighted by how much evidence
    each one has. Solving it globally is what keeps a phrase that recurs in
    two stories from dragging its cue to the wrong one -- the neighbours
    outvote it.
    """
    items = []
    for i, cands in enumerate(per_cue):
        for at, votes in cands:
            items.append((i, at, votes))
    if not items:
        return {}

    best = [0.0] * len(items)
    prev = [-1] * len(items)
    for a in range(len(items)):
        cue_a, at_a, votes_a = items[a]
        best[a] = float(votes_a)
        for b in range(a):
            cue_b, at_b, _ = items[b]
            if cue_b < cue_a and at_b <= at_a and best[b] + votes_a > best[a]:
                best[a] = best[b] + votes_a
                prev[a] = b

    end = max(range(len(items)), key=lambda i: best[i])
    chosen = {}
    while end >= 0:
        cue, at, votes = items[end]
        chosen[cue] = (at, votes)
        end = prev[end]

    # The chain is one path through the candidates, so a cue whose own best
    # guess did not happen to lie on it is dropped even when it fits
    # perfectly well between its neighbours. Give those a second chance
    # against the bracket the chain has now established, which is a much
    # cheaper test than being on the optimal path.
    settled = sorted(chosen)
    for left, right in zip(settled, settled[1:]):
        low = chosen[left][0]
        high = chosen[right][0]
        for cue in range(left + 1, right):
            for at, votes in per_cue[cue]:
                if low <= at <= high:
                    chosen[cue] = (at, votes)
                    low = at
                    break
    return chosen


def align(texts, reference):
    """Map each cue onto a span of the reference stream, monotonically."""
    index = {}
    for i in range(len(reference) - GRAM + 1):
        index.setdefault(reference[i:i + GRAM], []).append(i)

    per_cue = []
    normed = []
    for text in texts:
        piece = normalise(text)
        normed.append(piece)
        per_cue.append(candidates(piece, index) if len(piece) >= GRAM else [])

    chosen = backbone(per_cue)

    out = []
    for i, piece in enumerate(normed):
        if i not in chosen or not piece:
            out.append(None)
            continue
        at, _ = chosen[i]
        window = reference[at:at + len(piece)]
        matcher = difflib.SequenceMatcher(None, piece, window, autojunk=False)
        hits = []
        for a, b, size in matcher.get_matching_blocks():
            for k in range(size):
                hits.append(at + b + k)
        if not hits:
            out.append(None)
            continue
        span = max(hits) - min(hits) + 1
        out.append({
            "lo": min(hits),
            "hi": max(hits) + 1,
            "coverage": len(hits) / float(len(piece)),
            "compactness": len(piece) / float(span),
        })
    return out


PAIRS = {")": "(", "）": "（", "]": "[", "】": "【", "」": "「", "》": "《"}


def tidy(text):
    """Drop bracket halves the slice cut in two.

    A 文稿 wraps each interview in parentheses that open on the speaker's
    name line and close several lines later, so slicing out one subtitle
    routinely takes a lone `)` with it.
    """
    text = " ".join(text.split())
    opens = set(PAIRS.values())
    out = []
    stack = []
    for ch in text:
        if ch in opens:
            stack.append(len(out))
            out.append(ch)
        elif ch in PAIRS:
            if stack and out[stack[-1]] == PAIRS[ch]:
                stack.pop()
                out.append(ch)
        else:
            out.append(ch)
    for at in reversed(stack):
        del out[at]
    return "".join(out).strip()


def slice_raw(raw, back, lo, hi):
    """Original, punctuated text for normalised span [lo, hi)."""
    if lo >= len(back):
        return ""
    start = back[lo]
    end = back[min(hi, len(back)) - 1] + 1
    return tidy(raw[start:end])


# A 文稿 line at or under this many characters is already a subtitle line --
# the interview sections are typed one screen per line. Longer lines are
# narration paragraphs, which the subtitler broke up in a way the script does
# not record, so those can only be sliced by character offset.
SUBTITLE_LINE = 30


def snap(lines, lo, hi, ocr_len):
    """Widen a matched span to the unit the script actually stores.

    Matching stops at the last character tesseract got right, so a span is
    routinely short at both ends -- `沒有把它澈底` for `沒有把它澈底澆熄`.
    Where the overlapped 文稿 lines are already subtitle-sized, taking them
    whole restores the missing tail exactly. Where they are narration
    paragraphs, the span is instead grown to the length of the cue's own
    text, which is the only length evidence available.
    """
    # Only widen a span that is actually short. Where the recogniser read the
    # cue cleanly the span already spells the whole subtitle, and snapping it
    # out to its paragraph would hand two adjacent cues the same sentence.
    if hi - lo >= ocr_len:
        return lo, hi, "exact"

    touched = []
    for line in lines:
        if line["end"] > lo and line["start"] < hi:
            touched.append(line)
    if not touched:
        return lo, hi, "exact"
    if all(x["end"] - x["start"] <= SUBTITLE_LINE for x in touched):
        return touched[0]["start"], touched[-1]["end"], "line"

    grow = max(0, ocr_len - (hi - lo))
    lo = max(touched[0]["start"], lo - grow // 2)
    hi = min(touched[-1]["end"], hi + grow - grow // 2)
    return lo, hi, "slice"


def interpolate(records, slots, lengths, raw, back, lines):
    """Fill cues between two confident anchors.

    Both sequences run forwards, so a cue sitting between two anchored cues
    can only have come from the script between their spans. Where the amount
    of script left over matches the amount of text those cues hold, the
    correspondence is forced and can be shared out in proportion to length.

    Where it does not match -- the script is missing an item, or the cues
    cover something never scripted such as a caption or a station promo --
    the gap is left alone. Filling it anyway is exactly how an alignment
    silently walks off by one story.
    """
    anchors = []
    for i, rec in enumerate(records):
        if rec["aligned"] and slots[i]:
            anchors.append(i)

    filled = 0
    for left, right in zip(anchors, anchors[1:]):
        inner = list(range(left + 1, right))
        if not inner:
            continue
        lo = slots[left]["hi"]
        hi = slots[right]["lo"]
        gap = hi - lo
        need = sum(lengths[i] for i in inner)
        if gap <= 0 or need <= 0:
            continue
        if abs(gap - need) > 0.5 * max(gap, need):
            continue

        speaking = []
        for i in inner:
            if lengths[i] > 0:
                speaking.append(i)
        if not speaking:
            continue

        # The interview sections of a 文稿 are typed one screen per line, so
        # when the gap holds exactly one such line per cue the correspondence
        # is one-to-one and no arithmetic is needed. Slicing those by
        # character proportion instead is what produced lines like
        # `些動作 餘燼沒有完全`, which repeat their neighbours' text.
        inside = []
        for line in lines:
            if line["start"] >= lo and line["end"] <= hi:
                inside.append(line)
        if len(inside) == len(speaking) and all(
                x["end"] - x["start"] <= SUBTITLE_LINE for x in inside):
            for i, line in zip(speaking, inside):
                records[i]["aligned"] = tidy(line["text"])
                records[i]["source"] = "interpolated"
                filled += 1
            continue

        at = lo
        for i in speaking:
            take = int(round(gap * lengths[i] / float(need)))
            end = min(hi, at + max(1, take))
            a, b, _ = snap(lines, at, end, lengths[i])
            text = slice_raw(raw, back, max(lo, a), min(hi, b))
            if text:
                records[i]["aligned"] = text
                records[i]["source"] = "interpolated"
                filled += 1
            at = end
    return filled


def resolve(work, folder, min_coverage=0.5, min_compactness=0.55):
    """Return one record per cue describing what the script says it is."""
    cues = json.load(open(os.path.join(work, "cues.json"),
                          encoding="utf-8"))["cues"]
    path = os.path.join(work, "transcripts.json")
    tr = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}
    name = "han"
    texts = []
    for cue in cues:
        entry = tr.get(str(cue["index"]))
        if isinstance(entry, dict):
            texts.append(entry.get(name, "") or "")
        else:
            texts.append("")

    raw, norm, back, lines = build_reference(folder)
    placed = align(texts, norm)

    records = []
    kept = []
    lengths = []
    for cue, slot, text in zip(cues, placed, texts):
        rec = {
            "index": cue["index"],
            "start": cue["start"],
            "end": cue["end"],
            "ocr": text,
            "aligned": "",
            "source": "",
            "coverage": 0.0,
            "compactness": 0.0,
        }
        lengths.append(len(normalise(text)))
        accepted = None
        if slot is not None:
            rec["coverage"] = slot["coverage"]
            rec["compactness"] = slot["compactness"]
            if (slot["coverage"] >= min_coverage
                    and slot["compactness"] >= min_compactness):
                lo, hi, how = snap(lines, slot["lo"], slot["hi"],
                                   len(normalise(text)))
                # A narration paragraph is one long line in the script, so a
                # cue landing inside one can only be cut by character offset
                # and the cut lands mid-phrase: `000多種的植物種類。在` for
                # `孕育出高達4000多種的植物種類`. Measured 2/4 right, against
                # 17/17 for spans that already spelled the whole subtitle and
                # 6/7 for spans snapped to a subtitle-sized script line. The
                # script simply does not record where the subtitler broke a
                # paragraph, so these are dropped rather than guessed.
                if how != "slice":
                    rec["aligned"] = slice_raw(raw, back, lo, hi)
                    rec["source"] = how
                # Record the span actually consumed, not the one matched.
                # Interpolation works from the leftovers between anchors, and
                # if an anchor under-reports what it emitted the next cue is
                # handed the tail of the line it already used.
                accepted = {"lo": lo, "hi": hi}
        records.append(rec)
        kept.append(accepted)

    # Interpolation between anchors is deliberately not used. Measured
    # against 46 hand-read cues it scored 0/9 -- every filled cue was wrong,
    # while the anchors around them were 25/28 right. Sharing a stretch of
    # script out among the cues that happen to sit between two anchors
    # assumes nothing unscripted lies in the gap, and on a news programme
    # something almost always does: a promo, a headline, an anchor link.
    return records, len(norm), 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work")
    ap.add_argument("--wenkao", required=True)
    ap.add_argument("--min-coverage", type=float, default=0.5)
    ap.add_argument("--min-compactness", type=float, default=0.55)
    ap.add_argument("--show", type=int, default=25)
    args = ap.parse_args()

    records, size, filled = resolve(args.work, args.wenkao,
                                    args.min_coverage, args.min_compactness)
    print("reference: %d matchable chars (%d interpolated)" % (size, filled))
    shown = 0
    good = 0
    for rec in records:
        if not rec["aligned"]:
            continue
        good += 1
        if shown < args.show:
            shown += 1
            print("\ncue %-4d cov=%.2f cmp=%.2f %-13s t=%.1f"
                  % (rec["index"], rec["coverage"], rec["compactness"],
                     rec["source"], rec["start"]))
            print("  ocr : %s" % rec["ocr"])
            print("  ref : %s" % rec["aligned"])
    print("\n%d/%d cues aligned" % (good, len(records)))


if __name__ == "__main__":
    main()
