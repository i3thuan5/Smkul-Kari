#!/usr/bin/env python3
"""Each tribe's dictionary baseline, measured once and frozen in a table.

The official dictionaries cover the tribes very unevenly -- over the
anchors' opening 90 s the median hit rate is 卑南 0.17, 魯凱 0.20 but
卡那卡那富 0.67 -- so a group is judged against its own tribe's opening,
not against one shared line. The opening is the anchor reading a script:
the one stretch where the recogniser is reliably hearing the language.

The table is computed only on request. Recomputed on every run, each new
month would move every tribe's baseline and with it the tiers of every
old episode, and the store could no longer be rebuilt byte for byte.
A request only fills rows the table lacks (`fill_missing`): recomputing
魯凱 over 2021-11～2024-12 would move it from 0.27 to 0.44 (measured
2026-11-16). To recompute a row, delete the table first.

Rows are keyed by (族語別, 語言別代號). An ordinary row carries the
family code (`dru`); a variety read with its own supplement (萬山
`dru-x-opnh`) has its own row, measured on its own episodes only.
"""
import csv
import os
import statistics

from scripts import languages
from scripts.errors import PipelineError

OPENING_SECONDS = 90.0
MIN_WORDS = 5
FIELDS = ["族語別", "語言別代號", "開場組數", "辭典命中率中位數"]
DIGITS = 4


def baseline(groups):
    """{(tribe, code): {"rate", "groups"}} from groups carrying tribe,
    code (the row they count towards), start, asr_words and
    lexicon_rate."""
    rates = {}
    for group in groups:
        if group["start"] >= OPENING_SECONDS:
            continue
        if group["asr_words"] < MIN_WORDS:
            continue
        key = (group["tribe"], group["code"])
        rates.setdefault(key, []).append(group["lexicon_rate"])
    table = {}
    for key, values in rates.items():
        table[key] = {"rate": statistics.median(values),
                      "groups": len(values)}
    return table


def fill_missing(old, new):
    """`old` untouched, plus the rows of `new` it does not have."""
    merged = dict(old)
    for key, row in new.items():
        if key not in merged:
            merged[key] = row
    return merged


def write(table, path):
    """UTF-8, no BOM, LF, one row per (tribe, code), sorted."""
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(FIELDS)
        for key in sorted(table):
            tribe, code = key
            writer.writerow([tribe, code, table[key]["groups"],
                             "%.*f" % (DIGITS, table[key]["rate"])])
    return path


def read(path):
    if not os.path.exists(path):
        raise PipelineError("揣無校正基準表 %s——先跑 "
                            "`python3 -m scripts.news.pairs_run "
                            "--recalibrate`" % path)
    table = {}
    with open(path, encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if "語言別代號" not in (reader.fieldnames or []):
            raise PipelineError("校正基準表 %s 是舊格式（沒有語言別代號欄）"
                                % path)
        for row in reader:
            table[(row["族語別"], row["語言別代號"])] = {
                "rate": float(row["辭典命中率中位數"]),
                "groups": int(row["開場組數"]),
            }
    return table


def rate_of(table, tribe, code, episode):
    """The variety's own row, else the family's; else a refusal naming the
    tribe and episode.

    Never a default: the experiment's `opening.get(tribe, 0.5)` would
    have tiered a tribe the table forgot against someone else's line.
    """
    for key in ((tribe, code), (tribe, languages.code_for(tribe, ""))):
        if key in table:
            return table[key]["rate"]
    raise PipelineError("校正基準表查無「%s」（%s）——重跑 "
                        "--recalibrate" % (tribe, episode))
