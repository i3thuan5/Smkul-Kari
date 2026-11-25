"""Which masters a run covers, and how mxf2mkv hands them to the loop.

The loop itself -- one at a time, keep going on failure, stop on Ctrl+C,
the manifest rewritten after every file -- lives in tools/sftpbatch/batch.py
and is shared with tools.mkv2mp4wav. What stays here is mxf2mkv's own
part: scanning the source folder into jobs, and where its log and
manifest go.
"""
import os

from tools.sftpbatch import batch
from tools.sftpbatch import report
from tools.mxf2mkv import walk

# Kept for callers that still say batch.Result.
Result = batch.Result


def Job(relative, source, remote):
    """One master and where it is going."""
    return batch.Job(relative, remote, relative=relative, source=source)


def plan(src_root, dst_root, limit=0):
    """Every master under `src_root`, paired with its remote path."""
    out = []
    for relative in walk.apply_limit(walk.scan(src_root), limit):
        out.append(Job(relative,
                       os.path.join(src_root, relative),
                       walk.remote_path(src_root, relative, dst_root)))
    return out


def report_folder(report_root, src_name):
    """The directory holding every run against this source folder.

    Only the source name, not the time: a batch gets rerun after
    failures, and the point of the directory is that those attempts sit
    together so you can see how many there were and which one worked.
    """
    return os.path.join(report_root, src_name)


def report_stem(src_name, stamp):
    """The shared file-name stem for one run: time, then source name --
    repeated so a file dragged out of the directory still says what it
    is."""
    return "%s_%s" % (stamp, src_name)


def run(src_root, dst_root, work_dir, report_root, stamp, one_file,
        limit=0, dry_run=False):
    """Process every master under `src_root`, one at a time.

    Serial on purpose: the source is usually a single external drive, and
    reading two multi-gigabyte files off it at once costs more in seek
    contention than it gains. Several source folders on different drives
    can each have their own run.
    """
    jobs = plan(src_root, dst_root, limit)
    src_name = walk.src_label(src_root)

    def open_report():
        return report.open_run(report_folder(report_root, src_name),
                               report_stem(src_name, stamp),
                               {"來源資料夾": src_name, "開始時間": stamp})

    return batch.run(jobs, open_report, one_file, work_dir=work_dir,
                     key_field="src", dry_run=dry_run)
