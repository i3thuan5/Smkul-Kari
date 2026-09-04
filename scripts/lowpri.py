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


def be_nice(target=NICE):
    """Top this process up to nice `target`; return the level it is at.

    Returns None when the platform or the policy will not allow it -- a
    job that cannot be niced should still run, just less politely.

    **A target, not an increment.** `os.nice` is cumulative, and this
    pipeline nices in two places: the shell wrappers start their heavy
    steps under `nice -n 15`, and the Python entry points call this. Two
    entry points into the speech side (`asrmt_batch` calls into
    `asrmt_run`) add a third way to arrive here twice. Adding 15 each
    time reaches 30, which the kernel clamps to 19 -- the job lands at
    the very bottom instead of the level that was chosen.

    A module flag used to guard that, and it could not: a flag is
    per-process, and the shell's nice happened before this process
    existed. Reading the current value and topping up handles both, and
    is idempotent by nature, so the flag is gone.

    A process already below the target is left alone -- somebody set that
    deliberately, and this is not the place to overrule them.
    """
    try:
        current = os.nice(0)
        if current >= target:
            return current
        return os.nice(target - current)
    except (OSError, AttributeError):
        return None
