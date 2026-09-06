"""Which masters a source folder holds, and where each one goes.

Pure path arithmetic and one directory scan; no encoding, no network.

The mapping is "照著放": the remote path is the remote root, plus the
**last component of the source folder's own path**, plus the file's path
relative to that folder, with the extension swapped for .mkv. Nothing is
renamed and nothing is reorganised -- the point of this tool is to get the
files off the drive while it is plugged in, and sort out what each episode
is afterwards.
"""
import os

MASTER_EXT = ".mxf"
ARCHIVE_EXT = ".mkv"

# sftp -b re-parses every line of its batch file, so a quote inside a path
# can end the argument and a newline can start a whole new command.
# scripts/news/sftp.sh refuses these too; catching them here as well means
# the failure names the offending file instead of surfacing as a broken
# sftp batch. No broadcast master legitimately has one.
UNSAFE = ('"', "\\", "\n", "\r", "\t")


def is_safe(relative):
    """Whether this path may be handed to sftp at all."""
    if not relative:
        return False
    for bad in UNSAFE:
        if bad in relative:
            return False
    return True


def src_label(src_root):
    """The source folder's own name -- the layer that goes on the server.

    `os.path.basename` on a path ending in a slash returns "", and a
    trailing slash is what tab completion produces, so normalise first.
    Without this the remote path silently loses a level and every file in
    the batch lands one directory too high.
    """
    return os.path.basename(os.path.normpath(src_root))


def remote_path(src_root, relative, dst_root):
    """Where `relative` (a path under `src_root`) belongs on the server."""
    stem = os.path.splitext(relative)[0]
    return "/".join([dst_root.rstrip("/"), src_label(src_root),
                     stem + ARCHIVE_EXT])


def scan(src_root):
    """Every master under `src_root`, as paths relative to it, sorted.

    Sorted because `--limit 2` has to mean the same two files on a rerun;
    `os.walk` order is filesystem order and is not guaranteed stable.
    """
    out = []
    for folder, _dirs, files in os.walk(src_root):
        for name in files:
            if os.path.splitext(name)[1].lower() != MASTER_EXT:
                continue
            full = os.path.join(folder, name)
            out.append(os.path.relpath(full, src_root))
    out.sort()
    return out


def needs_upload(local_size, remote_size):
    """Whether this archive still has to go up.

    Compared by byte count rather than "does it exist": an interrupted
    upload leaves a short file behind, and a shorter file that is present
    would otherwise read as done.
    """
    return remote_size != local_size


def apply_limit(rows, limit):
    """The first `limit` of them, or all of them when limit is 0."""
    if not limit:
        return rows
    return rows[:limit]
