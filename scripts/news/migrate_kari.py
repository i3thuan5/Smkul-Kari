#!/usr/bin/env python3
"""One-shot migration of the February batch's data into Kari-SRT.

This is the documented mapping from every historical name a piece of data
carried to the one key Kari-SRT uses, `srt_name`. Runs read-only against the
sources and COPIES everything -- the vision TSVs are untracked and have no
git backup until Kari-SRT is committed, so nothing here moves or deletes.

Sources and their naming vintages:

  ilrdf-srt/vision/            first vision pass (the 文稿-gap cues)
      032午_泰雅/bNN.tsv           episode-shorthand dirs
      038_卡那卡那富/bNN.tsv        shorthand without 午/晚 (single episode day)
      truku_042/bNN.tsv            english_episode dirs
      rukai_043_b01-03.tsv         flattened spans, three batches in one file
      kavalan_040_sample.tsv       early spot-check, its own file
  ilrdf-srt/vision-rtf/        C-pass census (the 文稿-covered cues)
      <shorthand>/bNN.tsv
  kithann/out/mxf/<slug>.B.work/
      cues.json  from_rtf.json  verified.json  transcripts.json  sheets.json

Every copied episode is reconciled before anything is written:

  * union of TSV cue numbers == the cue set of verified.json (nothing lost,
    nothing invented), and
  * the text each cue ends up with == transcripts.json (the ingested truth
    the delivered SRTs were built from), with vision-rtf taking precedence
    over vision where both read the same cue -- that is the order ingest
    applied them in.

Flattened spans are split back into per-batch bNN.tsv using the work dir's
sheets.json. The sheets-per-batch size is inferred per file, because it
changed over the project's life: the rukai batches ran 12 sheets each (the
README's "12 張一批時 3,450 tokens" era), later episodes ran 24.
"""
import argparse
import json
import os
import re
import shutil
import sys

from scripts.news import paths

VISION_SRC = os.path.join(paths.ROOT, "ilrdf-srt", "vision")
VISION_RTF_SRC = os.path.join(paths.ROOT, "ilrdf-srt", "vision-rtf")
BATCH_SIZES = (12, 24)     # sheets per batch, by era; inferred per file

FLAT = re.compile(r"^([a-z]+)_(\d+)_b(\d+)-(\d+)\.tsv$")
SAMPLE = re.compile(r"^([a-z]+)_(\d+)_sample\.tsv$")


def episodes():
    """Non-truncated inventory entries, with every alias they ever had."""
    entries = json.load(open(paths.INVENTORY, encoding="utf-8"))
    out = []
    for entry in entries:
        if entry["truncated"]:
            continue
        number = int(entry["集數"])
        half = entry["播出時段"][0]          # 午 or 晚
        zh = entry["族語別(中)"]
        en = entry["族語別(英)"].lower()
        aliases = set()
        aliases.add("%03d%s_%s" % (number, half, zh))   # 032午_泰雅
        aliases.add("%03d_%s" % (number, zh))           # 038_卡那卡那富
        aliases.add("%s_%03d" % (en, number))           # truku_042
        aliases.add(entry["slug"])
        aliases.add(entry["srt_name"])
        out.append({
            "srt_name": entry["srt_name"],
            "slug": entry["slug"],
            "aliases": aliases,
            "eng_no": "%s_%03d" % (en, number),
        })
    return out


def by_alias(eps):
    index = {}
    for ep in eps:
        for alias in ep["aliases"]:
            if alias in index:
                raise SystemExit("alias %r is ambiguous" % alias)
            index[alias] = ep
    return index


def read_tsv(path):
    """{cue: text} for one TSV; blank cues may lack their trailing tab."""
    rows = {}
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) < 2:
                raise SystemExit("unparseable row in %s: %r" % (path, line))
            text = parts[2] if len(parts) > 2 else ""
            rows[int(parts[0])] = text
    return rows


def workdir(ep):
    return os.path.join(paths.WORK, ep["slug"] + ".B.work")


def sheet_of_cue(ep):
    """cue number -> sheet number, from the work dir's sheets.json."""
    path = os.path.join(workdir(ep), "sheets.json")
    mapping = {}
    for name, cues in json.load(open(path, encoding="utf-8")).items():
        number = int(re.search(r"(\d+)", name).group(1))
        for cue in cues:
            mapping[cue] = number
    return mapping


def sizes_fitting(rows, cue_sheet, lo, hi, path):
    """Which batch sizes put every cue of this span inside b<lo>-<hi>."""
    for cue in rows:
        if cue not in cue_sheet:
            raise SystemExit("%s: cue %d is on no sheet" % (path, cue))
    fits = []
    for size in BATCH_SIZES:
        ok = True
        for cue in rows:
            batch = (cue_sheet[cue] - 1) // size + 1
            if not lo <= batch <= hi:
                ok = False
                break
        if ok:
            fits.append(size)
    return fits


def split_flats(specs, ep):
    """Split one episode's flattened spans into {batch_number: rows}.

    One span alone can be ambiguous (a b01-03 file fits any size whose first
    three batches cover its sheets), so the size is decided by what fits
    every span of the episode at once.
    """
    cue_sheet = sheet_of_cue(ep)
    fits = set(BATCH_SIZES)
    for path, rows, lo, hi in specs:
        fits &= set(sizes_fitting(rows, cue_sheet, lo, hi, path))
    if len(fits) != 1:
        raise SystemExit("%s: sheets-per-batch ambiguous or impossible, "
                         "candidates left: %s" % (ep["slug"], sorted(fits)))
    size = fits.pop()

    batches = {}
    for path, rows, lo, hi in specs:
        for cue, text in rows.items():
            batch = (cue_sheet[cue] - 1) // size + 1
            batches.setdefault(batch, {})[cue] = text
    return batches


def gather(src_root, alias_index, kind):
    """Collect {srt_name: {tsv_basename: {cue: text}}} from one source tree."""
    collected = {}
    flat_specs = {}
    if not os.path.isdir(src_root):
        return collected
    for name in sorted(os.listdir(src_root)):
        full = os.path.join(src_root, name)
        if os.path.isdir(full):
            ep = alias_index.get(name)
            if ep is None:
                raise SystemExit("%s: no inventory match for dir %r"
                                 % (kind, name))
            dest = collected.setdefault(ep["srt_name"], {})
            for tsv in sorted(os.listdir(full)):
                if tsv.endswith(".tsv"):
                    dest[tsv] = read_tsv(os.path.join(full, tsv))
            continue
        flat = FLAT.match(name)
        if flat:
            alias = "%s_%03d" % (flat.group(1), int(flat.group(2)))
            ep = alias_index.get(alias)
            if ep is None:
                raise SystemExit("%s: no inventory match for %r"
                                 % (kind, name))
            flat_specs.setdefault(ep["srt_name"], (ep, []))[1].append(
                (full, read_tsv(full),
                 int(flat.group(3)), int(flat.group(4))))
            continue
        sample = SAMPLE.match(name)
        if sample:
            alias = "%s_%03d" % (sample.group(1), int(sample.group(2)))
            ep = alias_index.get(alias)
            if ep is None:
                raise SystemExit("%s: no inventory match for %r"
                                 % (kind, name))
            collected.setdefault(ep["srt_name"], {})["sample.tsv"] = \
                read_tsv(full)
            continue
        raise SystemExit("%s: unrecognised entry %r" % (kind, name))

    for srt_name in sorted(flat_specs):
        ep, specs = flat_specs[srt_name]
        dest = collected.setdefault(srt_name, {})
        for batch, rows in split_flats(specs, ep).items():
            key = "b%02d.tsv" % batch
            if key in dest:
                raise SystemExit("%s: %s exists both flattened and as a dir "
                                 "file" % (srt_name, key))
            dest[key] = rows
    return collected


def reconcile(ep, vision, vision_rtf):
    """Check coverage and text against the work dir before writing anything."""
    work = workdir(ep)
    verified = json.load(open(os.path.join(work, "verified.json"),
                              encoding="utf-8"))
    transcripts = json.load(open(os.path.join(work, "transcripts.json"),
                                 encoding="utf-8"))

    resolved = {}
    for name in sorted(vision):
        for cue, text in vision[name].items():
            resolved[cue] = text
    for name in sorted(vision_rtf):
        for cue, text in vision_rtf[name].items():
            resolved[cue] = text          # C-pass wins, as ingest applied it

    want = set()
    for key in verified:
        want.add(int(key))
    have = set(resolved)
    problems = []
    if have != want:
        missing = sorted(want - have)
        extra = sorted(have - want)
        problems.append("cue sets differ: missing %s extra %s"
                        % (missing[:5], extra[:5]))

    mismatched = 0
    for cue in sorted(have & want):
        got = transcripts.get(str(cue), {})
        final = got.get("han", "") if isinstance(got, dict) else ""
        if resolved[cue] != final:
            mismatched += 1
            if mismatched <= 3:
                problems.append("cue %d text differs: tsv=%r final=%r"
                                % (cue, resolved[cue][:25], final[:25]))
    if mismatched > 3:
        problems.append("...and %d more text mismatches" % (mismatched - 3))
    return problems


def write_tsvs(root, srt_name, files):
    out_dir = os.path.join(root, srt_name)
    os.makedirs(out_dir, exist_ok=True)
    for name in sorted(files):
        rows = files[name]
        with open(os.path.join(out_dir, name), "w", encoding="utf-8") as out:
            for cue in sorted(rows):
                out.write("%d\than\t%s\n" % (cue, rows[cue]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="reconcile and report; write nothing")
    args = ap.parse_args()

    eps = episodes()
    alias_index = by_alias(eps)
    vision_all = gather(VISION_SRC, alias_index, "vision")
    rtf_all = gather(VISION_RTF_SRC, alias_index, "vision-rtf")

    failures = []
    for ep in eps:
        problems = reconcile(ep,
                             vision_all.get(ep["srt_name"], {}),
                             rtf_all.get(ep["srt_name"], {}))
        for problem in problems:
            failures.append("%s: %s" % (ep["srt_name"], problem))

    if failures:
        for line in failures:
            print("FAIL:", line)
        raise SystemExit(1)
    print("reconciled %d episodes: TSV union == verified set, "
          "text == transcripts" % len(eps))
    if args.dry_run:
        return

    os.makedirs(paths.KARI, exist_ok=True)
    for sub in ("srt", "cues", "from_rtf", "report"):
        os.makedirs(os.path.join(paths.KARI, sub), exist_ok=True)

    for ep in eps:
        write_tsvs(os.path.join(paths.KARI, "vision"),
                   ep["srt_name"], vision_all.get(ep["srt_name"], {}))
        if ep["srt_name"] in rtf_all:
            write_tsvs(os.path.join(paths.KARI, "vision-rtf"),
                       ep["srt_name"], rtf_all[ep["srt_name"]])
        work = workdir(ep)
        shutil.copy2(os.path.join(work, "cues.json"),
                     os.path.join(paths.KARI, "cues",
                                  ep["srt_name"] + ".json"))
        shutil.copy2(os.path.join(work, "from_rtf.json"),
                     os.path.join(paths.KARI, "from_rtf",
                                  ep["srt_name"] + ".json"))

    srt_src = os.path.join(paths.ROOT, "kithann", "srt")
    copied = 0
    for name in sorted(os.listdir(srt_src)):
        if name.endswith(".srt") or name == "smkul.csv":
            shutil.copy2(os.path.join(srt_src, name),
                         os.path.join(paths.KARI, "srt", name))
            copied += 1
        elif name.startswith("rtf-vs-vision."):
            # reports live beside the deliverables, not among them
            shutil.copy2(os.path.join(srt_src, name),
                         os.path.join(paths.KARI, "report", name))
            copied += 1
    shutil.copy2(paths.INVENTORY, os.path.join(paths.KARI, "inventory.json"))

    print("wrote Kari-SRT: %d episodes of TSV/cues/from_rtf, %d srt-dir "
          "files, inventory.json" % (len(eps), copied))


if __name__ == "__main__":
    sys.exit(main())
