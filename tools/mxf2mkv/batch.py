"""Walk a source folder, hand each master to a worker, keep going on failure.

Split out from `__main__` so the loop -- which is where the failure policy
lives -- can be tested without going through argument parsing, and from
`run` so the same policy applies whatever the worker does. The worker is
passed in as `one_file(job, log)`, which is also how the tests drive
failures without a real encoder; it is handed the run's log because every
external command's stderr belongs there in full.

Failure policy: a batch runs for hours, so one bad file must not stop the
rest. Each failure is written to the log with its reason, recorded in the
manifest, and the batch moves on; the exit code says at the end whether
anything went wrong.
"""
import os

from tools.mxf2mkv import report
from tools.mxf2mkv import walk


class Job:
    """One master and where it is going."""

    def __init__(self, relative, source, remote):
        self.relative = relative
        self.source = source
        self.remote = remote

    def __repr__(self):
        return "Job(%r -> %r)" % (self.relative, self.remote)


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


def plan(src_root, dst_root, limit=0):
    """Every master under `src_root`, paired with its remote path."""
    out = []
    for relative in walk.apply_limit(walk.scan(src_root), limit):
        out.append(Job(relative,
                       os.path.join(src_root, relative),
                       walk.remote_path(src_root, relative, dst_root)))
    return out


def run(src_root, dst_root, work_dir, report_root, stamp, one_file,
        limit=0, dry_run=False):
    """Process every master under `src_root`, one at a time.

    Serial on purpose: the source is usually a single external drive, and
    reading two multi-gigabyte files off it at once costs more in seek
    contention than it gains. Several source folders on different drives
    can each have their own run.
    """
    jobs = plan(src_root, dst_root, limit)
    if dry_run:
        return Result(jobs, [], [], None, work_dir)

    src_name = walk.src_label(src_root)
    current = report.open_run(report_root, src_name, stamp)
    entries = []
    failed = []
    for job in jobs:
        if not walk.is_safe(job.relative):
            reason = "檔名有引號、反斜線抑是控制字元，拒絕處理"
            current.log("== %s\n%s" % (job.relative, reason))
            entries.append({"src": job.relative, "結果": "失敗",
                            "原因": reason})
            failed.append(job.relative)
            continue
        current.log("== %s" % job.relative)
        try:
            entry = one_file(job, current.log)
        # 掠規類 Exception 是刁工ê：這位ê規矩就是「毋管按怎倒，
        # 記落來、行下一支」。若干焦掠家己知影ê幾种，一个無拍算
        # ê錯誤就會共規批停掉，彼正正是這條愛避免ê代誌。
        except Exception as problem:
            current.log(str(problem))
            entries.append({"src": job.relative, "結果": "失敗",
                            "原因": str(problem)})
            failed.append(job.relative)
            continue
        entry = dict(entry)
        entry["src"] = job.relative
        entries.append(entry)

    result = Result(jobs, entries, failed, current, work_dir)
    if result.keep_work:
        current.log("有 %d 支失敗，工作目錄留咧無刣：%s"
                    % (len(failed), work_dir))
    current.close(entries, work_dir if result.keep_work else None)
    return result
