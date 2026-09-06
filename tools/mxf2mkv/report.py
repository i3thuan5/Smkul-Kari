"""Where a run's log and manifest go, and how they avoid clobbering.

Layout (使用者裁定 2026-09-06):

    kithann/mxf2mkv/
    └── 2月原始mxf檔/                            <- the source folder's name
        ├── 0905-2017_2月原始mxf檔.log
        ├── 0905-2017_2月原始mxf檔.manifest.json
        ├── 0906-0930_2月原始mxf檔.log           <- second run, same folder
        └── 0906-0930_2月原始mxf檔.manifest.json

The outer directory carries only the source name, not the time: a batch
gets rerun after failures, and the point of the directory is that those
attempts sit together so you can see how many there were and which one
worked. Putting the time up there would give every run its own directory
and defeat that. The file names still carry the full date and time, and
repeat the source name so a file dragged out of the directory still says
what it is.

Timestamps are CST (see CLAUDE.md); the caller passes one in rather than
this module reading the clock, so tests are not time-dependent.
"""
import json
import os

LOG_EXT = ".log"
MANIFEST_EXT = ".manifest.json"


def folder_for(report_root, src_name):
    """The directory holding every run against this source folder."""
    return os.path.join(report_root, src_name)


def stem(src_name, stamp):
    """The shared file-name stem for one run: time, then source name."""
    return "%s_%s" % (stamp, src_name)


def _claim(folder, base):
    """Create both files for `base`, or fail if either name is taken.

    O_EXCL rather than "check then create": with two runs starting in the
    same second, looking and then creating are two separate moments and
    both can look, see nothing, and create -- the second one silently
    truncating the first one's log. O_EXCL makes the check and the claim
    a single operation, so exactly one caller wins.

    Both names are claimed or neither is. Taking one and failing on the
    other would leave an empty .log behind that reads like a run that
    happened and produced nothing.
    """
    log = os.path.join(folder, base + LOG_EXT)
    manifest = os.path.join(folder, base + MANIFEST_EXT)
    made = []
    try:
        for path in (log, manifest):
            os.close(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            made.append(path)
    except FileExistsError:
        for path in made:
            os.remove(path)
        raise
    return log, manifest


class Run:
    """One execution's two output files."""

    def __init__(self, src_name, stamp, log_path, manifest_path):
        self.src_name = src_name
        self.stamp = stamp
        self.log_path = log_path
        self.manifest_path = manifest_path

    def log(self, text):
        """Append to the run's log. Every external command's stderr goes
        here in full -- that is the only place a failure can be read back
        after the drive has been unplugged."""
        with open(self.log_path, "a", encoding="utf-8") as handle:
            handle.write(text)
            if not text.endswith("\n"):
                handle.write("\n")

    def close(self, entries, work_dir=None):
        """Write the manifest. `entries` is one dict per file processed."""
        document = {
            "來源資料夾": self.src_name,
            "開始時間": self.stamp,
            "檔案": entries,
        }
        if work_dir:
            document["工作目錄"] = work_dir
        with open(self.manifest_path, "w", encoding="utf-8") as handle:
            json.dump(document, handle, ensure_ascii=False, indent=2,
                      sort_keys=True)
            handle.write("\n")


def open_run(report_root, src_name, stamp):
    """Claim this run's log and manifest, never overwriting an older run.

    Two runs starting inside the same minute would want the same names;
    the loser takes a `-2`, `-3` suffix rather than replacing anything.
    """
    folder = folder_for(report_root, src_name)
    os.makedirs(folder, exist_ok=True)
    base = stem(src_name, stamp)
    suffix = 1
    while True:
        candidate = base if suffix == 1 else "%s-%d" % (base, suffix)
        try:
            log, manifest = _claim(folder, candidate)
        except FileExistsError:
            suffix += 1
            continue
        return Run(src_name, stamp, log, manifest)
