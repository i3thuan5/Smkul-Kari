#!/usr/bin/env python3
"""The speech side's three renders.

    2-srt-raw       族語：／華語：                       delivered
    3-srt-ai        ＋族語ASR結果翻譯華語-ailabs：       analysis
    4-srt-quality   ＋族華對應品質：                     analysis

Two label sets, on purpose (使用者裁定 2026-09-04). The delivered file
gets the short ones because it is the thing that gets used; the analysis
files get labels that name their source, because reading one of those is
asking which engine said what, and 族語： does not answer that.

All three render off the same chain rows as the delivered subtitle SRT,
so they carry the same entries at the same timestamps -- that is where
coaxiality comes from, rather than from anything checking it afterwards.

The analysis renders take their extra line from a lookup rather than
from the entry. The same render then serves both callers: the step that
fetches translations (its lookup calls the service) and the offline
rebuild check (its lookup only reads the cache, and a miss is an error).
"""
from scripts.asrmt import orthography
from scripts.srtlib import srt
from scripts.errors import PipelineError

FORMOSAN = "族語："
CHINESE = "華語："
ASR = "族語ASR結果："
SUBTITLE = "華語OCR字幕："
TRANSLATED = "族語ASR結果翻譯華語-ailabs："
QUALITY = "族華對應品質："


def _blocks(rows, lines_of):
    blocks = []
    for row in rows:
        blocks.append((row["srt_start"], row["srt_end"],
                       "\n".join(lines_of(row))))
    return srt.render_srt(blocks)


def _asked(row, lookup, value):
    """Run a lookup for one entry, and say which entry if it fails.

    The lookup knows the cache; only the render knows the entry number,
    and the entry number is what someone fixing this needs.
    """
    try:
        return lookup(value)
    except PipelineError as error:
        raise PipelineError("條目 %d：%s" % (row["index"], error))


def raw_body(entries):
    """2-srt-raw: the delivered two lines, source material only.

    Always one entry per delivered-SRT entry, never merged. An entry
    whose true window holds no recognised word keeps its prefix with
    nothing after it -- the silence is part of what the file records.
    """
    def lines_of(row):
        return [FORMOSAN + row["formosan"], CHINESE + row["subtitle"]]
    return _blocks(entries, lines_of)


def ai_body(entries, translate):
    """3-srt-ai: the same two lines plus ai-labs' Formosan->Chinese line.

    `translate(formosan) -> str`. An empty Formosan line is not looked
    up at all: there is nothing to translate, and asking would spend a
    request on the empty string.

    The translation is written in this corpus's character forms (see
    `orthography`): the service mixes Japanese variants and a few
    simplified codepoints into otherwise-traditional output, and the
    delivered file is what a person reads. The cache keeps what the
    service actually said.
    """
    def lines_of(row):
        rendered = ""
        if row["formosan"].strip():
            rendered = orthography.normalise(
                _asked(row, translate, row["formosan"]))
        return [ASR + row["formosan"], SUBTITLE + row["subtitle"],
                TRANSLATED + rendered]
    return _blocks(entries, lines_of)


def quality_body(entries, grade):
    """4-srt-quality: the same two lines plus the correspondence grade.

    `grade(entry) -> 高|中|低`. No translation appears here: the file
    answers one question -- is this pair usable as training data -- and
    the translation was only ever a hint the judge was given.
    """
    def lines_of(row):
        return [ASR + row["formosan"], SUBTITLE + row["subtitle"],
                QUALITY + _asked(row, grade, row)]
    return _blocks(entries, lines_of)


def write(path, body):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(body)
        if body and not body.endswith("\n"):
            handle.write("\n")
