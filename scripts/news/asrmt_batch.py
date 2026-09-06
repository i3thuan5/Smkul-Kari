#!/usr/bin/env python3
"""Every deliverable episode through the default speech pipeline.

    python3 -m scripts.news.asrmt_batch [--limit N]

Per episode: fetch the mp3 over SFTP, decode (words), then project and
render the two-line SRT -- the end of the machine-time work -- and
delete the audio. Translation and grading come after, in their own
steps, because they are not CPU work: one talks to a public service,
the other spends model tokens. Episodes already done, pending or truncated are
skipped; a failing episode is reported and the batch moves on.
"""
import argparse
import csv
import os
import subprocess
import sys

from scripts.news import asrmt_run
from scripts.news import paths
from scripts import lowpri
from scripts.errors import PipelineError


def parse_shard(spec):
    """"i/n" -> (i, n); worker i of n takes positions where pos%n==i."""
    part, _, total = spec.partition("/")
    if not (part.isdigit() and total.isdigit()):
        raise PipelineError("bad --shard %r (want i/n, e.g. 0/3)" % spec)
    i, n = int(part), int(total)
    if not 0 <= i < n:
        raise PipelineError("bad --shard %r: need 0 <= i < n" % spec)
    return i, n


def shard_ok(position, worker, total):
    return position % total == worker


def _fetch(remote, local):
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "sftp.sh")
    done = subprocess.run(["bash", script, "get", remote, local])
    if done.returncode or not os.path.exists(local):
        raise PipelineError("sftp fetch failed: %s" % remote)


def _todo(entries, worker, total, raw_dir, only=""):
    """This worker's episodes still without a raw SRT, inventory order.

    `only` names a single episode and takes it even while it is pending.
    Doing an episode end to end runs the speech side *before* `publish`
    -- OCR, then 2-srt-raw, then publish -- so "pending" no longer means
    "not ready"; naming the episode is the caller saying its cues and
    vision transcripts are in. If they are not, `step_entries` fails and
    says which file is missing.
    """
    todo = []
    for position, entry in enumerate(entries):
        name = entry["srt_name"]
        if only:
            if name != only:
                continue
        elif not shard_ok(position, worker, total):
            continue
        elif entry.get("pending"):
            continue
        if entry.get("truncated"):
            continue
        if os.path.exists(paths.stage_path(raw_dir, name, ".srt")):
            continue
        todo.append(entry)
    return todo


def _run_episode(entry, catalogue):
    """Fetch -> decode -> project+render -> delete audio, one episode."""
    name = entry["srt_name"]
    audio = os.path.join(asrmt_run._workdir(name), "audio.mp3")
    if not os.path.exists(audio):
        _fetch(asrmt_run.mp3_remote(name, catalogue), audio)
    asrmt_run.step_words(name, entry["族語別(英)"])
    asrmt_run.step_raw(name)
    if os.path.exists(audio):
        os.remove(audio)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=0,
                    help="stop after N episodes (0 = all)")
    ap.add_argument("--shard", default="0/1",
                    help="i/n: run only this worker's partition")
    ap.add_argument("--only", default="",
                    help="干焦這一集（逐集流程用；pending 嘛做）")
    args = ap.parse_args(argv)
    # vosk 解碼一集愛幾分鐘，一批走幾點鐘；降優先權才袂kā機器食牢，
    # 佮 encode_master.sh 彼支 ffmpeg 仝一套。ffmpeg 是這爿生ê囝，
    # 會 kè-sîng 這个 nice 值。
    lowpri.be_nice()
    worker, total = parse_shard(args.shard)

    entries = paths.load_inventory()
    with open(paths.CATALOGUE, encoding="utf-8-sig", newline="") as handle:
        catalogue = list(csv.DictReader(handle))

    raw_dir = paths.ASR_RAW
    todo = _todo(entries, worker, total, raw_dir, only=args.only)
    if args.limit:
        todo = todo[:args.limit]

    done = []
    failed = []
    for entry in todo:
        name = entry["srt_name"]
        print("==", name, flush=True)
        try:
            _run_episode(entry, catalogue)
            done.append(name)
        except PipelineError as error:
            failed.append((name, str(error)))
            print("FAILED:", name, "--", error, flush=True)

    print("\n完成 %d 集" % len(done))
    for name, why in failed:
        print("失敗：%s（%s）" % (name, why))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
