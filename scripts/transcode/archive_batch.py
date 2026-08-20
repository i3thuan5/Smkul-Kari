#!/usr/bin/env python3
"""Archive every delivered episode's master as an mkv (使用者裁定 spec:
.claude/skills/video-subtitle-srt/壓縮率分析.md -- CRF 23, yuv420p, flac,
MKV, verify before delete).

    python3 -m scripts.transcode.archive_batch [--limit N]

Per episode: fetch the master over SFTP into the shared stage dir (reused
if already there with the right byte count), run encode_master.sh into a
*.partial.mkv and rename it into place only once ffmpeg's own audio MD5
check has passed, then delete the staged master. An episode whose archive
mkv already exists is skipped, so an interrupted batch resumes without
redoing finished work; a failing episode is reported and the batch moves
on to the next one.
"""
import argparse
import csv
import os
import subprocess
import sys

from scripts.news import paths

REMOTE_ROOT = "/docker"

# smkul.csv abbreviates the Feb mxf batch's location to "ilrdf-corpus/2月/
# <檔名>" -- a leftover from when those masters were mounted locally at
# that path. On the SFTP host the real directory is one level deeper (see
# scripts/news/refine_fetch.sh's identical note); the short form 404s.
FEB_MXF_SHORTHAND = "ilrdf-corpus/2月/"
FEB_MXF_REAL_DIR = "ilrdf-corpus/族語新聞/110.1-110.10/2月原始mxf檔/"
HERE = os.path.dirname(os.path.abspath(__file__))
ENCODE_SCRIPT = os.path.join(HERE, "encode_master.sh")
SFTP_SCRIPT = os.path.join(paths.ROOT, "scripts", "news", "sftp.sh")


def _cell_path(cell, slot):
    """One catalogue cell -> the path naming this slot, or None.

    Defensive: the master catalogue sometimes packs several paths into
    one cell separated by ";" (see asrmt_run.mp3_remote).
    """
    candidates = []
    for part in cell.split(";"):
        if part.strip():
            candidates.append(part.strip())
    if not candidates:
        return None
    for part in candidates:
        if slot in part:
            return part
    return candidates[0]


def video_remote(srt_name, rows):
    """The episode's master path on the SFTP host, from smkul.csv."""
    date = "%s-%s-%s" % (srt_name[0:4], srt_name[4:6], srt_name[6:8])
    slot = srt_name.split("_")[2]
    for row in rows:
        if row["播出日期"] != date or row["播出時段"] != slot:
            continue
        chosen = _cell_path(row["影片檔案位置"].strip(), slot)
        if chosen is None:
            continue
        if chosen.startswith(FEB_MXF_SHORTHAND):
            chosen = FEB_MXF_REAL_DIR + chosen[len(FEB_MXF_SHORTHAND):]
        return REMOTE_ROOT + "/" + chosen
    raise SystemExit("no video in smkul.csv for %s" % srt_name)


def stage_name(srt_name, remote):
    ext = os.path.splitext(remote)[1]
    return srt_name + ext


def output_path(srt_name, archive_dir=None):
    # 預設值查佇呼叫ê時陣，毋是 import ê時陣：寫做
    # `archive_dir=paths.MKV_ARCHIVE` ê話，模組載入了後 patch
    # paths.MKV_ARCHIVE 就無效，測試改了看起來若像有影，其實無。
    if archive_dir is None:
        archive_dir = paths.MKV_ARCHIVE
    return os.path.join(archive_dir, srt_name + ".mkv")


def already_done(srt_name, archive_dir=None):
    return os.path.exists(output_path(srt_name, archive_dir))


def _remote_size(remote):
    out = subprocess.run(
        ["bash", SFTP_SCRIPT, "ls", remote],
        capture_output=True, text=True)
    size = None
    for line in out.stdout.splitlines():
        if line.startswith("-"):
            size = int(line.split()[4])
            break
    return size


def _fetch(remote, local):
    size = _remote_size(remote)
    if size is None:
        raise SystemExit("not found on SFTP: %s" % remote)
    have = os.path.getsize(local) if os.path.exists(local) else 0
    if have == size:
        print("  已在 stage，重用（%d MB）" % (size // 1_000_000))
        return
    done = subprocess.run(["bash", SFTP_SCRIPT, "get", remote, local])
    got = os.path.getsize(local) if os.path.exists(local) else 0
    if done.returncode or got != size:
        if os.path.exists(local):
            os.remove(local)
        raise SystemExit("sftp fetch incomplete: %s (%s/%s bytes)"
                         % (remote, got, size))


def _encode(src, dst):
    partial = dst + ".partial.mkv"
    if os.path.exists(partial):
        os.remove(partial)
    subprocess.run(["bash", ENCODE_SCRIPT, src, partial], check=True)
    os.rename(partial, dst)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=0,
                    help="stop after N episodes (0 = all)")
    args = ap.parse_args(argv)

    os.makedirs(paths.STAGE, exist_ok=True)
    os.makedirs(paths.MKV_ARCHIVE, exist_ok=True)

    entries = paths.load_inventory()
    with open(paths.TRACKER_STORE, encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    done = []
    failed = []
    for entry in entries:
        name = entry["srt_name"]
        if entry.get("pending") or entry.get("truncated"):
            continue
        if already_done(name):
            continue
        if args.limit and len(done) + len(failed) >= args.limit:
            break
        print("==", name, flush=True)
        remote = video_remote(name, rows)
        local = os.path.join(paths.STAGE, stage_name(name, remote))
        try:
            print("  抓取", remote)
            _fetch(remote, local)
            print("  轉檔 ->", output_path(name))
            _encode(local, output_path(name))
            os.remove(local)
            done.append(name)
        except (SystemExit, subprocess.CalledProcessError) as error:
            failed.append((name, str(error)))
            print("FAILED:", name, "--", error, flush=True)

    print("\n完成 %d 集" % len(done))
    for name, why in failed:
        print("失敗：%s（%s）" % (name, why))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
