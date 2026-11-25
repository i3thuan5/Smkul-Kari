"""The preview mp4: which of three ffmpeg commands, and running it.

Parameters are copied from 《字幕編輯預覽檔規格》
(kithann/字幕編輯預覽檔規格_20261027.md, 3.1 hardware, 3.2 software);
the ones that look optional are correctness options, see each comment and
tests/mkv2mp4wav/test_encode_cmd.py. Two departures from that document,
both user rulings (2026-11-23): no timecode track (`-write_tmcd 0`), and
the start time follows the source rather than being forced to 0.

Three paths:

  硬體  source is 4:2:0 (news, 開會了 mkv): decode, deinterlace, scale and
        encode all on the GPU -- spec 3.1 unchanged.
  混合  source is anything else, in practice 開會了's H.264 High 4:2:2 mp4,
        which the GPU cannot decode (spec 3.1 fails with "Impossible to
        convert between the formats"): CPU decode, convert to nv12, upload,
        then the same GPU deinterlace/scale/encode. Measured on 079's first
        60 s: 7.3 s, 1799 = 1799 frames. Decoding is single-threaded
        (`-threads 1`): with frame-threaded decoding the flush at the end
        of the file hands over a burst of frames and hwupload fails with
        "Cannot allocate memory" (exit 244) -- a synthetic 300-frame clip
        came out 285 frames; 079's 60 s test never reached the end.
  軟體  only with --software, for the whole batch -- spec 3.2.

A list, not a bash script: there is no per-track loop to build, so the
list itself is what the tests compare.
"""
import os
import subprocess

from tools.sftpbatch import batch

HARDWARE = "硬體"
HYBRID = "混合"
SOFTWARE = "軟體"

DEVICE = "/dev/dri/renderD128"

# A batch runs for days next to other work (使用者裁定 -- CPU 影響到其他
# 工作); the software path alone takes 2888 core-seconds an episode.
NICE = ["nice", "-n", "15", "ionice", "-c", "3"]

# mode=bob: without it the driver's default (motion adaptive) has to read
# ahead before it outputs anything -- measured, the whole episode came out
# 3 frames short and 0.066 s late. rate=frame: one frame out per frame in.
GPU_FILTERS = ("deinterlace_vaapi=mode=bob:rate=frame,"
               "scale_vaapi=w=1280:h=720:format=nv12")
# yadif=0:-1:0 -- one frame out per frame in, field order from the stream,
# every frame processed. deint=1 would skip frames flagged progressive, and
# 開會了's mp4 are flagged progressive while 610 of 618 frames are
# interlaced.
CPU_FILTERS = "yadif=0:-1:0,scale=1280:-2,format=yuv420p"

VAAPI_CODEC = ["-c:v", "h264_vaapi", "-profile:v", "high", "-rc_mode", "VBR"]
X264_CODEC = ["-c:v", "libx264", "-profile:v", "high", "-preset", "veryfast"]


class EncodeError(Exception):
    """This episode's preview did not come out."""


def choose_path(pix_fmt, software):
    """Which command this source gets."""
    if software:
        return SOFTWARE
    if pix_fmt == "yuv420p":
        return HARDWARE
    return HYBRID


def command(src, dst, track, path):
    """The full ffmpeg command line for one preview."""
    head = NICE + ["ffmpeg", "-nostdin", "-hide_banner", "-v", "error"]
    if path == HARDWARE:
        head += ["-threads", "1", "-hwaccel", "vaapi",
                 "-hwaccel_device", DEVICE,
                 "-hwaccel_output_format", "vaapi"]
        filters = GPU_FILTERS
        codec = VAAPI_CODEC
    elif path == HYBRID:
        head += ["-threads", "1", "-vaapi_device", DEVICE]
        filters = "format=nv12,hwupload," + GPU_FILTERS
        codec = VAAPI_CODEC
    elif path == SOFTWARE:
        filters = CPU_FILTERS
        codec = X264_CODEC
    else:
        raise ValueError("沒有這條編碼路徑：%r" % path)
    return (head
            + ["-y", "-i", src,
               "-map", "0:v:0", "-map", "0:a:%d" % track,
               "-vf", filters]
            + codec
            + ["-b:v", "1200k", "-maxrate", "1800k", "-bufsize", "3600k",
               "-g", "30", "-bf", "0",
               # Keep every frame's own time: without it the mp4 muxer
               # duplicates or drops frames 33 ms at a time, cumulatively.
               "-fps_mode", "passthrough",
               "-c:a", "aac", "-b:a", "128k", "-ac", "1",
               # The source's broadcast timecode would otherwise become a
               # tmcd track, and editors count from 01:00:00;00.
               "-write_tmcd", "0",
               "-movflags", "+faststart",
               dst])


def probe_vaapi(device=DEVICE, run=subprocess.run):
    """Whether hardware encoding works on this machine: (ok, reason).

    One synthetic frame through h264_vaapi, so a missing driver shows up
    before a 2.5 GB download rather than after it.
    """
    if not os.access(device, os.R_OK):
        return False, "%s 不存在或無法讀取" % device
    done = run(["ffmpeg", "-nostdin", "-hide_banner", "-v", "error",
                "-vaapi_device", device,
                "-f", "lavfi", "-i", "color=c=black:s=1280x720:d=0.1",
                "-vf", "format=nv12,hwupload", "-frames:v", "1",
                "-c:v", "h264_vaapi", "-f", "null", "-"],
               capture_output=True, text=True)
    if done.returncode:
        return False, "h264_vaapi 試編一格失敗：%s" % done.stderr.strip()
    return True, ""


def encode(cmd, timeout, log, run=subprocess.run):
    """Run one encode, its stderr into the log.

    `timeout` is the source's duration: the GPU runs 7-8x real time, so
    one that has not finished in 1x is stuck. That is an ordinary failure
    of this episode. A signal exit is someone stopping the batch.
    """
    try:
        done = run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise EncodeError("編碼超過來源時長 %.0f 秒還沒結束，已停掉" % timeout)
    if done.stderr:
        log(done.stderr)
    if done.returncode in batch.INTERRUPTED_CODES:
        raise KeyboardInterrupt("編碼被中斷（離開碼 %d）" % done.returncode)
    if done.returncode:
        raise EncodeError("編碼失敗（離開碼 %d）：%s"
                          % (done.returncode, done.stderr.strip()[-2000:]))
