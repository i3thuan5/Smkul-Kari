"""The training WAV: 24 kHz, 16-bit, mono, bit-identical every time.

Meeting decision 2026-11-23. Taken from the chosen track (tracks.py).

Which sources may become a WAV, by container:

- mkv: the track must be FLAC. Matroska does not carry the number of
  priming samples an AAC stream starts with, so decoding AAC out of an
  mkv shifts the whole track by a frame.
- mp4: FLAC or AAC. 開會了's 20 mp4 are AAC; mp4 records the priming in
  its edit list and ffmpeg skips it when decoding.

Anything else, more than one channel, or a start time other than 0 fails
the WAV (the preview still goes ahead). A WAV has no start time, so a
track starting at 0.021 s would come out 0.021 s early against the SRT;
and mixing channels down is a decision about the audio this tool does
not make.

How the source's sample count is known (measured 2026-11-23): the
volumedetect pass that picks the track prints `n_samples`, the count
after decoding. mkv's `duration_ts` is useless here -- Matroska's time
base is milliseconds, and ffprobe reports N/A for FLAC in mkv anyway.

  107 (mkv, FLAC 24-bit):  n_samples 143,999,856 -> WAV 71,999,928, exactly
                           half; file 143,999,900 bytes = 44-byte header.
  079 (mp4, AAC):          n_samples 80,637,952 (78,749 frames x 1024 minus
                           the 1024 priming samples) -> WAV 40,318,976,
                           exactly half. The mp4 edit list says 80,637,360:
                           ffmpeg trims the priming at the front but keeps
                           592 samples (12 ms) of encoder padding at the
                           end. Only the end, so nothing shifts.

So acceptance compares the WAV's samples with half of `n_samples`, to
within one sample.
"""
import json
import subprocess

from tools.sftpbatch import batch

RATE = 24000
NICE = ["nice", "-n", "15", "ionice", "-c", "3"]


class AudioError(Exception):
    """This episode's WAV did not come out."""


def container_of(format_name):
    """"mkv", "mp4" or None, from ffprobe's format_name."""
    names = format_name.split(",")
    if "matroska" in names:
        return "mkv"
    if "mp4" in names or "mov" in names:
        return "mp4"
    return None


def precheck(container, stream):
    """None when this track may become a WAV, else the reason it may not."""
    codec = stream.get("codec_name")
    allowed = {"mkv": ("flac",), "mp4": ("flac", "aac")}.get(container, ())
    if codec not in allowed:
        return ("聲音格式 %s 在 %s 裡不能轉 WAV（mkv 只收 FLAC："
                "mkv 不記 AAC 開頭要略過的樣本數，解碼會整段偏移）"
                % (codec, container))
    if stream.get("channels") != 1:
        return "聲音有 %s 個聲道，不是單聲道，不混音" % stream.get("channels")
    try:
        start = float(stream.get("start_time"))
    except (TypeError, ValueError):
        return "讀不到聲音起點：%r" % stream.get("start_time")
    if start != 0:
        return ("聲音起點 %s 秒不是 0：WAV 不記起點，照轉會整段提早、"
                "對不上 SRT" % stream.get("start_time"))
    return None


def command(src, dst, track):
    """The ffmpeg command for one WAV. No dither option is set, so none is
    applied; the three bitexact switches keep ffmpeg's version out of the
    header (98 bytes with it, 44 without)."""
    return NICE + ["ffmpeg", "-nostdin", "-hide_banner", "-v", "error",
                   "-y", "-i", src, "-map", "0:a:%d" % track,
                   "-af", "aresample=%d:resampler=soxr:precision=28" % RATE,
                   "-sample_fmt", "s16", "-c:a", "pcm_s16le",
                   "-map_metadata", "-1",
                   "-fflags", "+bitexact", "-flags:a", "+bitexact",
                   dst]


def convert(src, dst, track, log, run=subprocess.run):
    done = run(command(src, dst, track), capture_output=True, text=True)
    if done.stderr:
        log(done.stderr)
    if done.returncode in batch.INTERRUPTED_CODES:
        raise KeyboardInterrupt("轉音檔被中斷（離開碼 %d）"
                                % done.returncode)
    if done.returncode:
        raise AudioError("轉音檔失敗（離開碼 %d）：%s"
                         % (done.returncode, done.stderr.strip()[-2000:]))


def verify(info, source_samples):
    """Problems with a finished WAV, as notes; empty means it passes."""
    audios = []
    for stream in info.get("streams", []):
        if stream.get("codec_type") == "audio":
            audios.append(stream)
    if len(audios) != 1:
        return ["音檔有 %d 條音軌，應為 1 條" % len(audios)]
    stream = audios[0]
    out = []
    if stream.get("codec_name") != "pcm_s16le":
        out.append("格式 %s，應為 pcm_s16le" % stream.get("codec_name"))
    if str(stream.get("sample_rate")) != str(RATE):
        out.append("取樣率 %s Hz，應為 %d" % (stream.get("sample_rate"), RATE))
    if stream.get("channels") != 1:
        out.append("%s 個聲道，應為 1" % stream.get("channels"))
    samples = stream.get("duration_ts")
    if source_samples is None:
        out.append("量不到來源樣本數，無法比對")
    elif samples is None or abs(int(samples) - source_samples / 2) > 1:
        out.append("樣本數 %s，來源 %d 個的一半是 %.1f"
                   % (samples, source_samples, source_samples / 2))
    return out


def probe(path):
    done = subprocess.run(["ffprobe", "-v", "error", "-show_streams",
                           "-of", "json", path],
                          capture_output=True, text=True)
    if done.returncode:
        raise AudioError("ffprobe 讀音檔失敗：%s" % done.stderr.strip())
    return json.loads(done.stdout)
