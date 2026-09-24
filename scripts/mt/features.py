#!/usr/bin/env python3
"""Per-group numbers a filter can threshold on -- all of them available
on the news corpus, where there is no gold: the two sapolita rows, the
subtitle text, the times, and the episode language's dictionary.

  chrf / ngram_f1   sapolita's own Chinese MT against the subtitle text
                    (the Bleualign idea: translate one side, compare in
                    one language)
  lexicon_rate      share of the ASR words in the official dictionary
  suspicious        any flag on any segment, low dictionary rate included
  hallucinated      loops, numeral-run MT or a blank segment only -- a low
                    rate is judged against the tribe's own baseline
  cover_seg         share of the segments' time under a subtitle
  cover_entries     share of the subtitles' time inside a segment
  len_ratio         ASR words per subtitle character
  wps               ASR words per second of segment time
  compression       zlib ratio of the ASR text (loops compress well)
  best_tribe/foreign  with all 16 dictionaries: the language the words
                    actually fit, and whether that is another tribe by
                    a margin (an interviewee from elsewhere)
"""
import zlib

from scripts.mt import hallucination
from scripts.mt import overlap
from scripts.mt import textsim


def compression_ratio(text):
    """Bytes before / after zlib, Whisper's own loop detector (>2.4)."""
    raw = text.encode("utf-8")
    if not raw:
        return 0.0
    return len(raw) / len(zlib.compress(raw))


def group_features(group, segments, entries, lexicon=None, fold=None,
                   lexicons=None, tribe=None):
    segs = []
    for i in group["segs"]:
        segs.append(segments[i])
    ents = []
    for j in group["entries"]:
        ents.append(entries[j])

    formosan = " ".join(s["formosan"] for s in segs)
    mt_han = " ".join(s["han"] for s in segs)
    sub_han = " ".join(e["han"] for e in ents)
    words = textsim.formosan_words(formosan)
    han_chars = textsim.han_chars(sub_han)

    suspicious = False
    repeat = False
    hallucinated = False
    for seg in segs:
        flags = hallucination.flags(seg, lexicon, fold)
        suspicious = suspicious or flags["suspicious"]
        repeat = repeat or flags["repeat"]
        hallucinated = hallucinated or bool(
            flags["repeat"] or flags["number_run"] or flags["empty"])

    seg_time = 0.0
    covered_seg = 0.0
    for seg in segs:
        seg_time += seg["end"] - seg["start"]
        for ent in ents:
            covered_seg += overlap.overlap(seg["start"], seg["end"],
                                           ent["true_start"],
                                           ent["true_end"])
    ent_time = 0.0
    for ent in ents:
        ent_time += ent["true_end"] - ent["true_start"]

    start, end = overlap.span(group, segments, entries)
    out = {
        "n_segs": len(segs), "n_entries": len(ents),
        "duration": end - start,
        "asr_words": len(words), "han_chars": len(han_chars),
        "len_ratio": len(words) / len(han_chars) if han_chars else 0.0,
        "chrf": textsim.chrf(mt_han, sub_han),
        "ngram_f1": textsim.ngram_f1(mt_han, sub_han),
        "suspicious": suspicious, "repeat": repeat,
        "hallucinated": hallucinated,
        "cover_seg": covered_seg / seg_time if seg_time else 0.0,
        "cover_entries": covered_seg / ent_time if ent_time else 0.0,
        "wps": len(words) / seg_time if seg_time else 0.0,
        "compression": compression_ratio(formosan),
    }
    if lexicon is not None:
        out["lexicon_rate"] = hallucination.lexicon_rate(words, lexicon,
                                                         fold)
    if lexicons is not None and tribe is not None:
        check = hallucination.language_check(words, lexicons, tribe)
        out["best_tribe"] = check["best_tribe"]
        out["best_rate"] = check["best_rate"]
        out["foreign"] = check["foreign"]
        out["suspicious"] = bool(out["suspicious"] or check["foreign"])
    return out
