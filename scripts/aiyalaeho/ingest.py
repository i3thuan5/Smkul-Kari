#!/usr/bin/env python3
"""Check a batch of vision TSVs and import them into an episode's work dir.

    python3 -m scripts.aiyalaeho.ingest 開會了_068_Amis_阿美

Two rows per cue, one per subtitle row:

    12<TAB>formosan<TAB>Nga'ay ho^
    12<TAB>han<TAB>大家好
    13<TAB>formosan<TAB>            <- 這條 cue 族語彼逝無字幕，留空

Three things are checked before anything is written, because all three
fail silently otherwise:

  format    a row with no text is written `13<TAB>formosan` once the
            trailing tab is stripped, which the importer would read as a
            missing field rather than as a confirmed blank
  mapping   every cue number must appear on a sheet the reader was given.
            A row outside that set means the reader drifted, and the text
            would land on the wrong subtitle -- far worse than a misread
            character, because nothing downstream looks wrong
  ownership two batches claiming the same cue means one of them was read
            against the wrong sheet list

Only `b*.tsv` is read. The news side learned that one: a stray
`sample.tsv` sorted after the batches and quietly overwrote 72 cues, and
because its content happened to match under the old numbering, four
months of verification stayed green.
"""
import argparse
import glob
import json
import os
import sys

from scripts.aiyalaeho import paths
from scripts.ocr import transcripts
from scripts.errors import PipelineError

BATCH_GLOB = "b*.tsv"


def normalise(path):
    """Restore the empty third field on confirmed-blank rows."""
    rows = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            parts = line.split("\t")
            while len(parts) < 3:
                parts.append("")
            rows.append("\t".join(parts[:3]))
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(rows) + "\n")
    return rows


def _audit(files, on_sheets):
    """(cue -> file, problems) for a whole batch of TSVs."""
    seen = {}
    problems = []
    for path in files:
        for row in normalise(path):
            index = row.split("\t")[0]
            if not index.isdigit():
                problems.append("%s: 編號 %r 毋是數字"
                                % (os.path.basename(path), index))
                continue
            index = int(index)
            if index not in on_sheets:
                problems.append(
                    "%s: cue %d 無佇這批讀者提著ê任何一張 sheet 頂懸"
                    % (os.path.basename(path), index))
            if index in seen and seen[index] != path:
                problems.append(
                    "cue %d 佇 %s 佮 %s 兩个檔攏出現"
                    % (index, os.path.basename(seen[index]),
                       os.path.basename(path)))
            seen[index] = path
    return seen, problems


def _on_sheets(work):
    with open(os.path.join(work, "sheets.json"), encoding="utf-8") as handle:
        sheets = json.load(handle)
    out = set()
    for cues in sheets.values():
        out.update(cues)
    return out


def run(work, tsvdir):
    """Audit then import. Returns what was read; raises if anything is off.

    Nothing is written when a problem is found -- a half-imported batch is
    the worst outcome available, because the rows that landed look no
    different from the rows that did not.
    """
    on_sheets = _on_sheets(work)
    files = sorted(glob.glob(os.path.join(tsvdir, BATCH_GLOB)))
    seen, problems = _audit(files, on_sheets)
    if problems:
        for line in problems[:20]:
            sys.stderr.write("PROBLEM %s\n" % line)
        raise PipelineError("%d 項問題，一字都無匯入" % len(problems))

    # 規集ê cue 數對 manifest 提，莫對匯入ê結果提：一批若一个 TSV 都
    # 無，`import_tsv` 連走都無走，報出來ê「規集 0 條」是假ê。
    total = len(transcripts.read_manifest(work)["cues"])
    covered = 0
    for path in files:
        _rows, covered, _total = transcripts.import_tsv(work, path)

    unread = sorted(on_sheets - set(seen))
    return {"files": len(files), "read": len(seen), "cues": total,
            "covered": covered, "unread": unread}


def _work_and_tsvdir(srt_name, tsvdir):
    work = paths.work_dir(srt_name)
    if not os.path.isdir(work):
        raise PipelineError("揣無 work dir %s——先切 cue" % work)
    if not tsvdir:
        tsvdir = paths.stage_path(paths.KARI_VISION, srt_name)
    return work, paths.check_under(tsvdir, "tsvdir")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("srt_name")
    ap.add_argument("tsvdir", nargs="?", default="",
                    help="TSV 目錄；無寫就是 store ê 2-vision/<srt_name>")
    args = ap.parse_args(argv)

    work, tsvdir = _work_and_tsvdir(paths.check_srt_name(args.srt_name),
                                    args.tsvdir)
    report = run(work, tsvdir)
    print("%d 个 TSV，讀著 %d 條 cue；規集 %d 條，這馬有字ê %d 條"
          % (report["files"], report["read"], report["cues"],
             report["covered"]))
    if report["unread"]:
        print("猶未讀ê %d 條（頭幾條：%s）"
              % (len(report["unread"]), report["unread"][:10]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
