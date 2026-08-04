#!/usr/bin/env python3
"""Score the 文稿 alignment against hand-read truth.

The aligner rewrites a cue only when it believes it has located that cue in
the episode's script. Believing wrongly is the failure that matters: it
replaces visibly broken OCR with fluent, plausible, wrong text, which no
later reader would think to question.

So the number worth knowing is not how many cues were aligned but how many
aligned cues are *right*. Feed this a TSV of cues read off the contact sheets
and it reports precision on exactly those cues, plus what tesseract alone
scored on the same ones for comparison.
"""
import argparse

from scripts.news import align as aligner


def load_truth(path):
    truth = {}
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            index = int(parts[0])
            text = parts[2] if len(parts) > 2 else ""
            truth[index] = text.strip()
    return truth


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work")
    ap.add_argument("--rtf", required=True)
    ap.add_argument("--truth", required=True)
    ap.add_argument("--show", type=int, default=15)
    args = ap.parse_args()

    truth = load_truth(args.truth)
    records, _, _ = aligner.resolve(args.work, args.rtf)
    by_index = {r["index"]: r for r in records}

    aligned_right = aligned_wrong = 0
    ocr_right = 0
    considered = 0
    misses = []
    by_source = {}
    for index in sorted(truth):
        want = aligner.normalise(truth[index])
        rec = by_index.get(index)
        if rec is None or not want:
            continue                      # blank cues carry no evidence
        considered += 1
        if aligner.normalise(rec["ocr"]) == want:
            ocr_right += 1
        got = aligner.normalise(rec["aligned"])
        if not got:
            continue
        tally = by_source.setdefault(rec["source"] or "?", [0, 0])
        if got == want:
            aligned_right += 1
            tally[0] += 1
        else:
            aligned_wrong += 1
            tally[1] += 1
            misses.append((index, truth[index], rec["aligned"]))

    total_aligned = aligned_right + aligned_wrong
    print("cues with text in the sample : %d" % considered)
    print("tesseract exactly right      : %d (%.0f%%)"
          % (ocr_right, 100.0 * ocr_right / considered if considered else 0))
    print("文稿-aligned                  : %d" % total_aligned)
    if total_aligned:
        print("  of those, exactly right    : %d (%.0f%%)"
              % (aligned_right, 100.0 * aligned_right / total_aligned))
        print("  of those, wrong            : %d" % aligned_wrong)
    for source in sorted(by_source):
        right, wrong = by_source[source]
        total = right + wrong
        print("  source=%-13s %d/%d right (%.0f%%)"
              % (source, right, total, 100.0 * right / total))
    for index, want, got in misses[:args.show]:
        print("\ncue %d" % index)
        print("  truth : %s" % want)
        print("  文稿   : %s" % got)


if __name__ == "__main__":
    main()
