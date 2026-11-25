"""Hand each job to a worker, one at a time, and keep going on failure.

Moved here from tools/mxf2mkv/batch.py so that tools.mxf2mkv and
tools.mkv2mp4wav run on the same loop: the failure policy took two months
of real batches to get right and should exist once.

The caller builds the job list (mxf2mkv scans a local folder, mkv2mp4wav
reads a catalogue) and passes the worker as `one_file(job, log)`, which is
also how the tests drive failures without a real encoder; it is handed the
run's log because every external command's stderr belongs there in full.

Failure policy: a batch runs for hours -- the news preview run for days --
so one bad file must not stop the rest. Each failure is written to the log
with its reason, recorded in the manifest, and the batch moves on; the
exit code says at the end whether anything went wrong. Ctrl+C is not a
bad file: it stops the whole batch.
"""
import signal
import time

# How a child that was told to stop comes back. ffmpeg catches SIGINT,
# SIGTERM and SIGHUP, closes its outputs properly and exits 255; a shell
# killed outright reads as the negative signal; 130 is a shell's own
# "stopped by Ctrl+C". None of these is a bad file -- someone wants the
# whole run to stop -- so they must not fall into "log it and carry on".
INTERRUPTED_CODES = (255, 130, -signal.SIGINT, -signal.SIGTERM,
                     -signal.SIGHUP)

# sftp -b re-parses every line of its batch file, so a quote inside a path
# can end the argument and a newline can start a whole new command.
# scripts/news/sftp.sh refuses these too; catching them here as well means
# the failure names the offending file instead of surfacing as a broken
# sftp batch. No broadcast master or catalogue name legitimately has one.
UNSAFE = ('"', "\\", "\n", "\r", "\t")


def is_safe(label):
    """Whether this name may be handed to sftp at all."""
    if not label:
        return False
    for bad in UNSAFE:
        if bad in label:
            return False
    return True


class Job:
    """One unit of work.

    `label` names it in the log and the manifest; `remote` is where the
    result goes, interpreted only by the worker. Anything else the caller
    needs travels as keyword attributes. A job built with `error` set is
    already known to be bad (a catalogue name that breaks the naming
    rules): it is recorded as failed without the worker ever seeing it,
    so no remote path is built from it.
    """

    def __init__(self, label, remote, error=None, **extra):
        self.label = label
        self.remote = remote
        self.error = error
        for key in extra:
            setattr(self, key, extra[key])

    def __repr__(self):
        return "Job(%r -> %r)" % (self.label, self.remote)


class Result:
    """What a whole batch did."""

    def __init__(self, planned, entries, failed, run, work_dir):
        self.planned = planned
        self.entries = entries
        self.failed = failed
        self.run = run
        self.work_dir = work_dir

    @property
    def log_path(self):
        return self.run.log_path if self.run else None

    @property
    def manifest_path(self):
        return self.run.manifest_path if self.run else None

    @property
    def keep_work(self):
        """Failures leave the work directory behind.

        It holds the half-finished products, and after the drive is
        unplugged they are the only thing left to look at.
        """
        return bool(self.failed)

    @property
    def exit_code(self):
        return 1 if self.failed else 0


def _record(current, entries, entry, on_done, job, seconds):
    entries.append(entry)
    current.write(entries)
    if on_done is not None:
        on_done(job, entry, seconds)


def run(jobs, open_report, one_file, work_dir, key_field, dry_run=False,
        on_done=None, clock=time.monotonic):
    """Process every job, one at a time.

    Serial on purpose: mxf2mkv reads off a single external drive, and
    mkv2mp4wav keeps at most one episode on the local disk.

    `open_report()` returns a fresh `report.Run`; it is a callable so a
    dry run creates nothing. Each manifest entry is keyed by `key_field`
    ("src" for mxf2mkv, so its manifest format is unchanged; "srt_name"
    for mkv2mp4wav). The manifest is rewritten after every job.

    `on_done(job, entry, seconds)`, when given, is called after each job
    with how long it took -- mkv2mp4wav prints its progress line there.
    """
    if dry_run:
        return Result(jobs, [], [], None, work_dir)

    current = open_report()
    entries = []
    failed = []
    for job in jobs:
        started = clock()
        if job.error or not is_safe(job.label):
            reason = job.error or "檔名有引號、反斜線抑是控制字元，拒絕處理"
            current.log("== %s\n%s" % (job.label, reason))
            failed.append(job.label)
            _record(current, entries,
                    {key_field: job.label, "結果": "失敗", "原因": reason},
                    on_done, job, clock() - started)
            continue
        current.log("== %s" % job.label)
        try:
            entry = one_file(job, current.log)
        # Ctrl+C 毋是檔案歹，是人欲規个停：記落來、收對照表，閣擲出去，
        # 莫予下跤彼條「記落來、行下一支」吞去。
        except KeyboardInterrupt:
            current.log("中斷：%s 做到一半予人喝停，無上傳，後壁ê無做"
                        % job.label)
            entries.append({key_field: job.label, "結果": "中斷"})
            failed.append(job.label)
            current.close(entries, work_dir)
            raise
        # 掠規類 Exception 是刁工ê：這位ê規矩就是「毋管按怎倒，
        # 記落來、行下一支」。若干焦掠家己知影ê幾种，一个無拍算
        # ê錯誤就會共規批停掉，彼正正是這條愛避免ê代誌。
        except Exception as problem:
            current.log(str(problem))
            failed.append(job.label)
            _record(current, entries,
                    {key_field: job.label, "結果": "失敗",
                     "原因": str(problem)},
                    on_done, job, clock() - started)
            continue
        entry = dict(entry)
        entry[key_field] = job.label
        if entry.get("結果") == "失敗":
            failed.append(job.label)
        _record(current, entries, entry, on_done, job, clock() - started)

    result = Result(jobs, entries, failed, current, work_dir)
    if result.keep_work:
        current.log("有 %d 支失敗，工作目錄留咧無刣：%s"
                    % (len(failed), work_dir))
    current.close(entries, work_dir if result.keep_work else None)
    return result
