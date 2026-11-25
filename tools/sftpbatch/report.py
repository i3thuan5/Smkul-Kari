"""A run's log and manifest: never clobbering, written as it goes.

Where the files go and what they are called is the calling tool's
business: mxf2mkv keeps one folder per source folder
(kithann/mxf2mkv/<source>/<MMDD-HHMM>_<source>.*, 使用者裁定
2026-09-06), mkv2mp4wav one per programme
(kithann/mkv2mp4wav/<aiyalaeho|news>/<MMDD-HHMM>.*). What is shared is
how the names are claimed and how the manifest is written.

The manifest is rewritten after every item, through a temporary file and
an atomic rename: a run that dies part-way leaves every finished item on
disk as complete JSON, with `已收尾` false. Before this the manifest was
only written at the end, and kithann/mxf2mkv/ still holds three empty ones
left by runs that were stopped.

Timestamps are CST (see CLAUDE.md); the caller passes them in rather than
this module reading the clock, so tests are not time-dependent.
"""
import json
import os

LOG_EXT = ".log"
MANIFEST_EXT = ".manifest.json"


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

    def __init__(self, header, log_path, manifest_path):
        self.header = dict(header)
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

    def _dump(self, entries, finished, work_dir=None):
        document = dict(self.header)
        document["檔案"] = entries
        document["已收尾"] = finished
        if work_dir:
            document["工作目錄"] = work_dir
        staging = self.manifest_path + ".tmp"
        try:
            with open(staging, "w", encoding="utf-8") as handle:
                json.dump(document, handle, ensure_ascii=False, indent=2,
                          sort_keys=True)
                handle.write("\n")
        except BaseException:
            if os.path.exists(staging):
                os.remove(staging)
            raise
        # os.replace is atomic on one filesystem: a reader sees either the
        # previous complete manifest or this one, never half of either.
        os.replace(staging, self.manifest_path)

    def write(self, entries):
        """Rewrite the manifest mid-run. `entries` is everything so far."""
        self._dump(entries, False)

    def close(self, entries, work_dir=None):
        """The final manifest: `已收尾` true, plus the kept work dir."""
        self._dump(entries, True, work_dir)


def open_run(folder, stem, header):
    """Claim `<folder>/<stem>.log` and `.manifest.json`, never overwriting.

    Two runs starting inside the same minute would want the same names;
    the loser takes a `-2`, `-3` suffix rather than replacing anything.
    `header` is the run-level fields the manifest starts with.
    """
    os.makedirs(folder, exist_ok=True)
    suffix = 1
    while True:
        candidate = stem if suffix == 1 else "%s-%d" % (stem, suffix)
        try:
            log, manifest = _claim(folder, candidate)
        except FileExistsError:
            suffix += 1
            continue
        return Run(header, log, manifest)
