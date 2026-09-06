"""Turn every mxf in a local folder into an archival mkv on the SFTP host.

    python3 -m tools.mxf2mkv --src /media/hong/USB/2月原始mxf檔
    python3 -m tools.mxf2mkv --src ... --limit 2 --dry-run

Built for a plugged-in external drive: get the files off it, one at a
time, and sort out which episode each one is afterwards. Nothing here
reads the catalogue, smkul.csv or the inventory, so a master that has
never been registered still transfers.

The remote layout mirrors the source: <--dst-root>/<the source folder's
own name>/<the file's path inside it>, extension swapped for .mkv. Files
already on the server are skipped, so an interrupted run resumes, and a
file that fails is logged and skipped rather than stopping the batch.
"""
import argparse
import datetime
import os
import shutil
import sys
import tempfile

from tools.mxf2mkv import batch
from tools.mxf2mkv import run as runner

DEFAULT_DST_ROOT = "/home/mkv-raw"
DEFAULT_REPORT_DIR = os.path.join("kithann", "mxf2mkv")
WORK_PREFIX = "mxf2mkv-"
CST = datetime.timezone(datetime.timedelta(hours=8))


def stamp_now():
    """CST, per CLAUDE.md -- the container runs UTC and is 8 hours out."""
    return datetime.datetime.now(CST).strftime("%m%d-%H%M")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="python3 -m tools.mxf2mkv",
        description="隨身硬碟資料夾內底ê mxf 逐支轉 mkv，轉一支傳一支")
    parser.add_argument("--src", required=True,
                        help="來源資料夾（會遞迴揣底下所有 .mxf）")
    parser.add_argument("--dst-root", default=DEFAULT_DST_ROOT,
                        help="遠端根目錄（預設 %s）" % DEFAULT_DST_ROOT)
    parser.add_argument("--work", default=None,
                        help="工作目錄（預設 /tmp 底下逐擺各生一个）")
    parser.add_argument("--report-dir", default=DEFAULT_REPORT_DIR,
                        help="紀錄佮對照表囥ê所在（預設 %s）"
                             % DEFAULT_REPORT_DIR)
    parser.add_argument("--crf", type=int, default=23,
                        help="視訊 CRF（預設 23，實測過ê值）")
    parser.add_argument("--pix-fmt", default="yuv420p")
    parser.add_argument("--limit", type=int, default=0,
                        help="干焦做頭 N 支，0 是全部")
    parser.add_argument("--dry-run", action="store_true",
                        help="干焦列會做啥、傳去佗，無振動任何檔案")
    return parser.parse_args(argv)


def _report(jobs):
    for job in jobs:
        print("  %-50s -> %s" % (job.relative, job.remote))


def main(argv=None):
    args = parse_args(argv)
    if not os.path.isdir(args.src):
        print("揣無來源資料夾：%s" % args.src, file=sys.stderr)
        return 2

    if args.dry_run:
        result = batch.run(
            src_root=args.src, dst_root=args.dst_root, work_dir="(試走)",
            report_root=args.report_dir, stamp=stamp_now(),
            one_file=None, limit=args.limit, dry_run=True)
        print("試走：%d 支" % len(result.planned))
        _report(result.planned)
        return 0

    # 逐擺執行各有家己ê工作目錄，按呢會使仝時對幾若个來源資料夾
    # 各起一个（來源佇無仝碟ê時陣）。
    work = args.work or tempfile.mkdtemp(prefix=WORK_PREFIX, dir="/tmp")
    os.makedirs(work, exist_ok=True)
    print("工作目錄：%s" % work)

    def one_file(job, log):
        if runner.already_done(job):
            print("  %s 遠端已經有矣，跳過" % job.relative)
            return {"remote": job.remote, "結果": "已存在"}
        print("  %s" % job.relative)
        return runner.one_file(job, work, crf=args.crf,
                               pix_fmt=args.pix_fmt, log=log)

    result = batch.run(
        src_root=args.src, dst_root=args.dst_root, work_dir=work,
        report_root=args.report_dir, stamp=stamp_now(),
        one_file=one_file, limit=args.limit)

    print("對照表：%s" % result.manifest_path)
    if result.keep_work:
        print("有 %d 支失敗，工作目錄留咧：%s" % (len(result.failed), work),
              file=sys.stderr)
        print("失敗ê明細：%s" % result.log_path, file=sys.stderr)
    elif not args.work:
        shutil.rmtree(work, ignore_errors=True)
    return result.exit_code


if __name__ == "__main__":
    sys.exit(main())
