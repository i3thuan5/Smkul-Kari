"""Put one finished archive on the SFTP server.

Everything goes through `scripts/news/sftp.sh` rather than a Python SFTP
library. Two reasons, and they point the same way: the password rules say
a password may not appear on a command line, and that script already
solves it (SSH_ASKPASS plus a password file it reads itself); and a
library would be a new dependency where an existing tool does the job.
It also refuses paths carrying quotes, backslashes or control characters,
which `sftp -b` would otherwise re-parse into extra commands.
"""
import os
import subprocess

from scripts.news import paths

SFTP_SCRIPT = os.path.join(paths.ROOT, "scripts", "news", "sftp.sh")


class UploadError(Exception):
    """The archive did not make it up intact."""


def dirs_to_make(remote):
    """Every level of the file's parent directory, outermost first.

    sftp's mkdir makes one level at a time; handed a path whose parent is
    missing it just fails, and the first upload into a new source folder
    is exactly that case.
    """
    parts = os.path.dirname(remote).strip("/").split("/")
    out = []
    for index in range(len(parts)):
        out.append("/" + "/".join(parts[:index + 1]))
    return out


def parse_size(listing):
    """The byte count out of `ls -l` output, or None if it names no file.

    Column 5, and only on a line starting with "-": a directory or an
    error message is not a file whose size we can compare against.
    """
    for line in listing.splitlines():
        if not line.startswith("-"):
            continue
        fields = line.split()
        if len(fields) < 5:
            continue
        try:
            return int(fields[4])
        except ValueError:
            continue
    return None


def _sftp(*args):
    return subprocess.run(["bash", SFTP_SCRIPT] + list(args),
                          capture_output=True, text=True)


def remote_size(remote):
    """How many bytes the server has for this path, or None if it has none."""
    done = _sftp("ls", remote)
    return parse_size(done.stdout)


PARTIAL_SUFFIX = ".partial"


def already_there(remote):
    """Whether the server already holds a finished archive at this path.

    Existence is proof of completeness here, which it normally would not
    be -- an interrupted transfer leaves a short file that looks present.
    It works because `put` never writes this name directly: a transfer in
    flight occupies `<name>.partial`, and the final name only appears
    after the byte count has been checked. So the final name existing
    means some run got all the way through.

    The alternative, comparing byte counts, cannot be done here: the size
    of the archive is not known until it has been encoded, and encoding
    is the twenty minutes the skip exists to avoid.
    """
    size = remote_size(remote)
    return size is not None and size > 0


def put(local, remote, local_size):
    """Upload to a partial name, prove it arrived whole, then rename.

    "The transfer returned zero" is not the same as "the file is there
    and complete", so the byte count is read back rather than assumed --
    and it is checked *before* the rename, so a short transfer never
    reaches the name that later runs treat as proof of a finished upload.
    """
    for folder in dirs_to_make(remote):
        # The leading "-" inside sftp.sh makes "already there" survivable,
        # which is the normal case for every file after the first.
        made = _sftp("mkdir", folder)
        if made.returncode:
            raise UploadError("袂使建遠端資料夾：%s\n%s"
                              % (folder, made.stderr))
    staging = remote + PARTIAL_SUFFIX
    sent = _sftp("put", local, staging)
    if sent.returncode:
        raise UploadError("上傳失敗：%s\n%s" % (staging, sent.stderr))
    size = remote_size(staging)
    if size != local_size:
        raise UploadError("上傳了後位元組數無仝：%s（遠端 %s，本機 %s）"
                          % (staging, size, local_size))
    moved = _sftp("rename", staging, remote)
    if moved.returncode:
        raise UploadError("換名失敗：%s -> %s\n%s"
                          % (staging, remote, moved.stderr))
    return size
