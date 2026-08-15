#!/usr/bin/env python3
"""Every deliverable episode through the default speech pipeline.

    python3 -m scripts.news.asrmt_batch [--limit N]

Per episode: fetch the mp3 over SFTP, decode (words), project
(entries), render the raw SRT -- the default endpoint (使用者裁定) --
then delete the audio. Episodes already done, pending or truncated are
skipped; a failing episode is reported and the batch moves on.
"""
import argparse
import csv
import json
import os
import subprocess
import sys

from scripts.news import asrmt_run
from scripts.news import paths


def parse_shard(spec):
    """"i/n" -> (i, n); worker i of n takes positions where pos%n==i."""
    part, _, total = spec.partition("/")
    if not (part.isdigit() and total.isdigit()):
        raise SystemExit("bad --shard %r (want i/n, e.g. 0/3)" % spec)
    i, n = int(part), int(total)
    if not 0 <= i < n:
        raise SystemExit("bad --shard %r: need 0 <= i < n" % spec)
    return i, n


def shard_ok(position, worker, total):
    return position % total == worker


def _fetch(remote, local):
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "sftp.sh")
    command = 'get "%s" "%s"' % (remote, local)
    done = subprocess.run(["bash", script, command])
    if done.returncode or not os.path.exists(local):
        raise SystemExit("sftp fetch failed: %s" % remote)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=0,
                    help="stop after N episodes (0 = all)")
    ap.add_argument("--shard", default="0/1",
                    help="i/n: run only this worker's partition")
    args = ap.parse_args(argv)
    worker, total = parse_shard(args.shard)

    with open(paths.INVENTORY, encoding="utf-8") as handle:
        entries = json.load(handle)
    with open(paths.CATALOGUE, encoding="utf-8-sig", newline="") as handle:
        catalogue = list(csv.DictReader(handle))

    raw_dir = os.path.join(paths.ASR_DIR, "3-srt-raw")
    done = []
    failed = []
    for position, entry in enumerate(entries):
        name = entry["srt_name"]
        if not shard_ok(position, worker, total):
            continue
        if entry.get("pending") or entry.get("truncated"):
            continue
        if os.path.exists(os.path.join(raw_dir, name + ".srt")):
            continue
        if args.limit and len(done) + len(failed) >= args.limit:
            break
        print("==", name, flush=True)
        audio = os.path.join(asrmt_run._workdir(name), "audio.mp3")
        try:
            if not os.path.exists(audio):
                _fetch(asrmt_run.mp3_remote(name, catalogue), audio)
            asrmt_run.step_words(name, entry["族語別(英)"])
            asrmt_run.step_entries(name)
            asrmt_run.step_raw(name)
            if os.path.exists(audio):
                os.remove(audio)
            done.append(name)
        except SystemExit as error:
            failed.append((name, str(error)))
            print("FAILED:", name, "--", error, flush=True)

    print("\n完成 %d 集" % len(done))
    for name, why in failed:
        print("失敗：%s（%s）" % (name, why))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
