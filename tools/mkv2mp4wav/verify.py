"""Acceptance for one preview mp4, before it may be uploaded.

Section 4 of 《字幕編輯預覽檔規格》, with two user rulings (2026-11-23):
the start times must equal the source's rather than be 0, and there must
be no timecode track. Every check is a pure function over already-parsed
ffprobe output (or the file's first bytes) returning (ok, note), so the
tests need no video; `probe()` is the thin layer that runs ffprobe.

`check_all()` runs every item and returns them all: a preview that fails
three ways should say so three times, not stop at the first.
"""
import json
import os
import struct
import subprocess

START_TOLERANCE = 0.001
DURATION_TOLERANCE = 0.1
KEYFRAME_GAP = 1.1
HEAD_BYTES = 4 * 1024 * 1024
# VBR ceiling plus the audio, in bytes per second: 48 minutes is about
# 0.69 GB, matching the document's "under 0.7 GB" for a 48-minute episode,
# but scaled so a 24-minute one cannot hide at 0.5 GB.
MAX_BYTES_PER_SECOND = (1800 + 128) * 1000 / 8

WANT_VIDEO = (("codec_name", "h264"), ("profile", "High"),
              ("pix_fmt", "yuv420p"), ("width", 1280), ("height", 720),
              ("r_frame_rate", "30000/1001"),
              ("field_order", "progressive"))


def frames_equal(src_frames, got_frames):
    if src_frames == got_frames:
        return True, "%d 格" % got_frames
    return False, "影格數不同：來源 %s 格、預覽檔 %s 格" % (src_frames, got_frames)


def starts_equal(src, got):
    notes = []
    for key, label in (("video_start", "影像"), ("audio_start", "聲音")):
        want = src[key]
        have = got[key]
        if want is None or have is None or abs(want - have) > START_TOLERANCE:
            notes.append("%s起點 來源 %s、預覽檔 %s" % (label, want, have))
    if notes:
        return False, "起點不同：" + "；".join(notes)
    return True, "影像 %s、聲音 %s" % (got["video_start"], got["audio_start"])


def duration_close(src_duration, got_duration):
    gap = got_duration - src_duration
    if abs(gap) <= DURATION_TOLERANCE:
        return True, "差 %.3f 秒" % gap
    return False, ("時長差 %.1f 秒：來源 %.3f、預覽檔 %.3f"
                   % (gap, src_duration, got_duration))


def _streams(streams, kind):
    out = []
    for stream in streams:
        if stream.get("codec_type") == kind:
            out.append(stream)
    return out


def video_spec(streams):
    videos = _streams(streams, "video")
    if len(videos) != 1:
        return False, "影像軌有 %d 條，應為 1 條" % len(videos)
    wrong = []
    for key, want in WANT_VIDEO:
        have = videos[0].get(key)
        if have != want:
            wrong.append("%s=%s（應為 %s）" % (key, have, want))
    if wrong:
        return False, "影像規格不符：" + "、".join(wrong)
    return True, "h264 High yuv420p 1280×720 30000/1001 progressive"


def audio_spec(streams):
    audios = _streams(streams, "audio")
    if len(audios) != 1:
        return False, "聲音軌有 %d 條，應為 1 條" % len(audios)
    stream = audios[0]
    wrong = []
    if stream.get("codec_name") != "aac":
        wrong.append("codec=%s" % stream.get("codec_name"))
    if stream.get("channels") != 1:
        wrong.append("%s 聲道" % stream.get("channels"))
    if str(stream.get("sample_rate")) != "48000":
        wrong.append("%s Hz" % stream.get("sample_rate"))
    if wrong:
        return False, "聲音規格不符：" + "、".join(wrong)
    return True, "aac 1 聲道 48000 Hz"


def no_timecode(streams):
    for stream in streams:
        if (stream.get("codec_type") == "data"
                and stream.get("codec_tag_string") == "tmcd"):
            return False, "有 tmcd 時間碼軌"
    return True, "沒有時間碼軌"


def moov_before_mdat(head):
    """Walk the top-level boxes in the first bytes; which comes first."""
    offset = 0
    while offset + 8 <= len(head):
        size, kind = struct.unpack(">I4s", head[offset:offset + 8])
        if size == 1:
            if offset + 16 > len(head):
                break
            size = struct.unpack(">Q", head[offset + 8:offset + 16])[0]
        if kind == b"moov":
            return True, "moov 在 mdat 之前"
        if kind == b"mdat":
            return False, "mdat 在 moov 之前（faststart 沒有生效）"
        if size < 8:
            break
        offset += size
    return False, "前 4 MB 內找不到 moov"


def keyframe_gap(keyframes, duration):
    if len(keyframes) < 2:
        if duration > KEYFRAME_GAP:
            return False, "只有 %d 個關鍵格" % len(keyframes)
        return True, "片長太短"
    widest = 0.0
    for index in range(1, len(keyframes)):
        widest = max(widest, keyframes[index] - keyframes[index - 1])
    if widest > KEYFRAME_GAP:
        return False, "關鍵格最大間距 %.1f 秒（應 ≤ %.1f）" % (
            widest, KEYFRAME_GAP)
    return True, "最大間距 %.3f 秒" % widest


def size_within(size, duration):
    limit = MAX_BYTES_PER_SECOND * duration
    if size <= limit:
        return True, "%d 位元組（上限 %d）" % (size, limit)
    return False, "大小 %d 位元組超過上限 %d（位元率上限沒有生效）" % (size, limit)


def check_all(src, got):
    """Every item as (name, ok, note), in the document's order."""
    out = []
    checks = (
        ("影格數", frames_equal(src["frames"], got["frames"])),
        ("起點", starts_equal(src, got)),
        ("時長", duration_close(src["duration"], got["duration"])),
        ("影像規格", video_spec(got["streams"])),
        ("聲音規格", audio_spec(got["streams"])),
        ("時間碼軌", no_timecode(got["streams"])),
        ("索引在檔頭", moov_before_mdat(got["head"])),
        ("關鍵格間距", keyframe_gap(got["keyframes"], got["duration"])),
        ("大小", size_within(got["size"], got["duration"])),
    )
    for name, (ok, note) in checks:
        out.append((name, ok, note))
    return out


def problems(results):
    """Just the notes of the items that failed."""
    out = []
    for _name, ok, note in results:
        if not ok:
            out.append(note)
    return out


def _ffprobe(args):
    done = subprocess.run(["ffprobe", "-v", "error"] + args,
                          capture_output=True, text=True)
    if done.returncode:
        raise RuntimeError("ffprobe 失敗：%s" % done.stderr.strip())
    return done.stdout


def streams_and_format(path):
    """ffprobe's streams and format sections, parsed."""
    return json.loads(_ffprobe(["-show_streams", "-show_format",
                                "-of", "json", path]))


def video_packets(path):
    """(packet count, keyframe times) of the first video stream.

    One pass over the whole file gives both: counting packets is the
    document's frame count, and the K flags give the keyframe gaps.
    """
    out = _ffprobe(["-select_streams", "v:0", "-show_entries",
                    "packet=pts_time,flags", "-of", "csv=p=0", path])
    count = 0
    keys = []
    for line in out.splitlines():
        fields = line.split(",")
        if len(fields) < 2:
            continue
        count += 1
        if "K" in fields[1]:
            try:
                keys.append(float(fields[0]))
            except ValueError:
                pass
    keys.sort()
    return count, keys


def _start(stream):
    try:
        return float(stream.get("start_time"))
    except (TypeError, ValueError):
        return None


def probe(path):
    """Everything `check_all` needs about a finished preview."""
    info = streams_and_format(path)
    streams = info.get("streams", [])
    videos = _streams(streams, "video")
    audios = _streams(streams, "audio")
    frames, keys = video_packets(path)
    with open(path, "rb") as handle:
        head = handle.read(HEAD_BYTES)
    return {
        "frames": frames,
        "video_start": _start(videos[0]) if videos else None,
        "audio_start": _start(audios[0]) if audios else None,
        "duration": float(info["format"]["duration"]),
        "streams": streams,
        "head": head,
        "keyframes": keys,
        "size": os.path.getsize(path),
    }
