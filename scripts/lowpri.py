#!/usr/bin/env python3
"""Drop a long-running job's priority so it does not take the machine over.

A batch here runs for hours -- vosk decoding a whole episode, ffmpeg
walking a 19 GB master, 25 fps frame classification over every cue
boundary -- on a box somebody is also trying to work on.
`scripts/transcode/encode_master.sh` already runs its ffmpeg under
`nice -n 15 ionice -c 3` (使用者裁定 -- CPU 影響到其他工作); this is the
same decision for the steps that are driven from Python.

Child processes inherit the parent's nice value, so calling this once at
an entry point also covers the ffmpeg it goes on to spawn.

No ionice here: the standard library has no binding for it, and these
steps are CPU-bound rather than disk-bound -- the shell scripts, which do
read whole masters off disk, ask for `ionice -c 3` themselves.
"""
import os

# The same number `encode_master.sh` uses. If one of them moves, both do:
# "跟轉 mkv 一樣" is the whole point.
NICE = 15

_applied = False


def be_nice(step=NICE):
    """Lower this process's priority by `step`; return the new value.

    Returns None when the platform or the policy will not allow it -- a
    job that cannot be niced should still run, just less politely.

    Only the first call does anything. `os.nice` is *cumulative*, and
    there are two entry points into the speech side (`asrmt_batch` calls
    into `asrmt_run`), so without this guard a batch run would land on 30
    instead of 15.
    """
    global _applied
    if _applied:
        return None
    try:
        level = os.nice(step)
    except (OSError, AttributeError):
        return None
    _applied = True
    return level
