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
"""
import csv
import os
import statistics

from scripts.errors import PipelineError

OPENING_SECONDS = 90.0
MIN_WORDS = 5
FIELDS = ["族語別", "開場組數", "辭典命中率中位數"]
DIGITS = 4


def baseline(groups):
    """{tribe: {"rate", "groups"}} from groups carrying tribe, start,
    asr_words and lexicon_rate."""
    rates = {}
    for group in groups:
        if group["start"] >= OPENING_SECONDS:
            continue
        if group["asr_words"] < MIN_WORDS:
            continue
        rates.setdefault(group["tribe"], []).append(group["lexicon_rate"])
    table = {}
    for tribe, values in rates.items():
        table[tribe] = {"rate": statistics.median(values),
                        "groups": len(values)}
    return table


def write(table, path):
    """UTF-8, no BOM, LF, one tribe per row sorted by name."""
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(FIELDS)
        for tribe in sorted(table):
            writer.writerow([tribe, table[tribe]["groups"],
                             "%.*f" % (DIGITS, table[tribe]["rate"])])
    return path


def read(path):
    if not os.path.exists(path):
        raise PipelineError("揣無校正基準表 %s——先跑 "
                            "`python3 -m scripts.news.pairs_run "
                            "--recalibrate`" % path)
    table = {}
    with open(path, encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            table[row["族語別"]] = {
                "rate": float(row["辭典命中率中位數"]),
                "groups": int(row["開場組數"]),
            }
    return table


def rate_of(table, tribe, episode):
    """The tribe's baseline, or a refusal naming the tribe and episode.

    Never a default: the experiment's `opening.get(tribe, 0.5)` would
    have tiered a tribe the table forgot against someone else's line.
    """
    if tribe not in table:
        raise PipelineError("校正基準表查無「%s」（%s）——重跑 "
                            "--recalibrate" % (tribe, episode))
    return table[tribe]["rate"]
