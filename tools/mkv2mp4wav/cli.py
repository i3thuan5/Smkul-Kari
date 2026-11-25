"""What the two commands share: arguments, checks, progress, the batch.

`python3 -m tools.mkv2mp4wav.aiyalaeho` and `python3 -m
tools.mkv2mp4wav.news` each pass their programme module to `main()`.
A programme module provides:

    NAME              "aiyalaeho" / "news" -- also the log folder
    SOURCE            the catalogue it reads, for the manifest header
    jobs(limit)       the episodes, sorted by srt_name, as sftpbatch Jobs
                      carrying .preview and .wav (and .error when the
                      catalogue name breaks the rules)
    locate(job, sftp, log)  -> (remote source path, where it was found)
    listing(sftp, jobs)     -> set of output paths already on the server

Built to be run by hand from the repo root with the system python3: no
tox venv, nothing beyond the standard library, ffmpeg and sftp. Before
anything is listed or downloaded it checks those are there.
"""
import argparse
import datetime
import os
import shutil
import sys
import tempfile

from scripts.news import paths as news_paths
from tools.sftpbatch import batch
from tools.sftpbatch import report
from tools.mkv2mp4wav import encode
from tools.mkv2mp4wav import progress as progress_mod
from tools.mkv2mp4wav import run

ROOT = news_paths.ROOT
WORK_PREFIX = "mkv2mp4wav-"
CST = datetime.timezone(datetime.timedelta(hours=8))
PASS_FILE = os.path.join(ROOT, ".sftp-pass")


def stamp_now():
    """CST, per CLAUDE.md -- the container runs UTC and is 8 hours out."""
    return datetime.datetime.now(CST).strftime("%m%d-%H%M")


def default_report_dir(name):
    """kithann/mkv2mp4wav/<programme>/ -- never mxf2mkv's folder."""
    return os.path.join(ROOT, "kithann", "mkv2mp4wav", name)


def parse_args(program, argv=None):
    parser = argparse.ArgumentParser(
        prog="python3 -m tools.mkv2mp4wav.%s" % program.NAME,
        description=getattr(program, "DESCRIPTION", None))
    parser.add_argument("--limit", type=int, default=0,
                        help="只做照成果檔名排序的前 N 集，0 是全部")
    parser.add_argument("--software", action="store_true",
                        help="整批改用 libx264 軟體編碼（沒有 GPU 的機器）")
    parser.add_argument("--dry-run", action="store_true",
                        help="只列每集兩種產出要做還是跳過，不下載、不建任何檔")
    parser.add_argument("--work", default=None,
                        help="工作目錄（預設 /tmp 底下每次新建一個）")
    parser.add_argument("--report-dir", default=default_report_dir(
        program.NAME), help="紀錄與對照表放哪（預設 %(default)s）")
    return parser.parse_args(argv)


def preflight(software, which=shutil.which, pass_file=None,
              probe=encode.probe_vaapi):
    """What is missing for a run on this machine; empty when nothing is.

    The password file is only checked for existence -- never opened: what
    is read ends up in the conversation (CLAUDE.md, 密碼、憑證處理規定).
    """
    pass_file = pass_file or os.environ.get("SFTP_PASS_FILE", PASS_FILE)
    out = []
    for tool in ("ffmpeg", "ffprobe", "sftp"):
        if which(tool) is None:
            out.append("PATH 裡找不到 %s" % tool)
    if not os.path.exists(pass_file):
        out.append("找不到 SFTP 密碼檔：%s（請自己在終端機建立）" % pass_file)
    if not software:
        ok, reason = probe()
        if not ok:
            out.append("硬體編碼不能用（%s）；沒有 GPU 的機器請加 --software"
                       % reason)
    return out


def _say(text, current=None):
    print(text, flush=True)
    if current is not None:
        current.log(text)


def _dry_run(jobs, existing):
    for job in jobs:
        if job.error:
            print("  %s  失敗：%s" % (job.label, job.error))
            continue
        for remote in (job.preview, job.wav):
            state = "跳過（已存在）" if remote in existing else "要做"
            print("  %s  %s" % (remote, state))
    return 0


def main(program, argv=None, tools=None):
    args = parse_args(program, argv)
    problems = preflight(args.software)
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        return 2

    tools = tools or run.Tools()
    jobs = program.jobs(args.limit)
    existing = program.listing(tools.sftp, jobs)
    labels = []
    remotes = {}
    for job in jobs:
        labels.append(job.label)
        if not job.error:
            remotes[job.label] = (job.preview, job.wav)
    done = progress_mod.done_labels(list(remotes), remotes, existing)
    meter = progress_mod.Progress(labels, done)
    opening = meter.start()
    if args.dry_run:
        print("試跑：" + opening)
        return _dry_run(jobs, existing)

    work = args.work or tempfile.mkdtemp(prefix=WORK_PREFIX, dir="/tmp")
    os.makedirs(work, exist_ok=True)
    stamp = stamp_now()
    holder = {}

    def open_report():
        current = report.open_run(args.report_dir, stamp,
                                  {"來源": program.SOURCE, "開始時間": stamp})
        holder["run"] = current
        _say("工作目錄：%s" % work, current)
        _say(opening, current)
        return current

    def one_file(job, log):
        return run.one_episode(job, program, work, args.software, log, tools)

    def on_done(job, entry, seconds):
        _say(meter.finished(job.label, entry.get("結果"), seconds),
             holder.get("run"))

    try:
        result = batch.run(jobs, open_report, one_file, work_dir=work,
                           key_field="srt_name", on_done=on_done)
    except KeyboardInterrupt:
        print("中斷：已停下，做到一半的這集沒有上傳，後面的沒有做。"
              "再打同一行指令就會接著做。", file=sys.stderr)
        return 130

    _say(meter.summary(), holder.get("run"))
    print("對照表：%s" % result.manifest_path)
    if result.keep_work:
        print("有 %d 集失敗，明細在 %s" % (len(result.failed), result.log_path),
              file=sys.stderr)
    if not args.work:
        shutil.rmtree(work, ignore_errors=True)
    return result.exit_code
