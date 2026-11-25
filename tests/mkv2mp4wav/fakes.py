"""假ê伺服器、編碼器、節目模組，予單集流程佮指令ê測試用。

逐个外部動作攏換掉：下載、ffprobe、量音量、編碼、轉音檔、上傳。會寫
檔ê動作真正寫一个細檔，按呢「做煞本機愛清掉」才測會著。
"""
import os

from tools.sftpbatch import batch
from tools.mkv2mp4wav import encode

FRAMES = 86318
DURATION = 2880.144


class FakeMeter:
    def __init__(self, levels, samples):
        self.levels = levels
        self.samples = {}
        self._samples = samples
        self.asked = []

    def mean(self, source, index):
        self.asked.append(index)
        self.samples[index] = self._samples
        return self.levels[index]


class FakeTools:
    """Everything run.one_episode reaches outside the process for."""

    def __init__(self, existing=(), levels=(-25.0,), pix_fmt="yuv420p",
                 container="mkv", audio_codec="flac", samples=143999856):
        self.existing = set(existing)
        self.levels = list(levels)
        self.pix_fmt = pix_fmt
        self.container = container
        self.audio_codec = audio_codec
        self.source_samples = samples
        self.sftp = object()
        self.fetched = []
        self.encoded = []
        self.converted = []
        self.uploaded = []
        self.local_files_seen = []
        self.encode_error = None
        self.convert_error = None
        self.put_error = None
        self.preview_changes = {}
        self.wav_changes = {}
        self.meters = []

    # -- server
    def already_there(self, remote):
        return remote in self.existing

    def put(self, local, remote, size):
        if self.put_error and remote.endswith(self.put_error[0]):
            raise self.put_error[1]
        self.uploaded.append((os.path.basename(local), remote))
        return size

    def fetch(self, remote, local):
        self.fetched.append((remote, local))
        with open(local, "w") as handle:
            handle.write("source")

    # -- probing
    def probe_source(self, path, count_frames=True):
        audio = []
        for _level in self.levels:
            audio.append({"codec_type": "audio",
                          "codec_name": self.audio_codec,
                          "channels": 1, "start_time": "0.000000"})
        return {"container": self.container, "pix_fmt": self.pix_fmt,
                "frames": FRAMES if count_frames else None,
                "video_start": 0.0, "duration": DURATION, "audio": audio,
                "size": 2500000000}

    def meter(self):
        made = FakeMeter(self.levels, self.source_samples)
        self.meters.append(made)
        return made

    # -- producing
    def encode(self, cmd, timeout, log):
        self.encoded.append(cmd)
        self.local_files_seen.append(sorted(os.listdir(
            os.path.dirname(cmd[-1]))))
        with open(cmd[-1], "w") as handle:
            handle.write("preview")
        if self.encode_error:
            raise self.encode_error

    def probe_preview(self, path):
        video = {"codec_type": "video", "codec_name": "h264",
                 "profile": "High", "pix_fmt": "yuv420p", "width": 1280,
                 "height": 720, "r_frame_rate": "30000/1001",
                 "field_order": "progressive"}
        audio = {"codec_type": "audio", "codec_name": "aac", "channels": 1,
                 "sample_rate": "48000"}
        keys = []
        second = 0.0
        while second < DURATION:
            keys.append(second)
            second += 1.0
        facts = {"frames": FRAMES, "video_start": 0.0, "audio_start": 0.0,
                 "duration": DURATION, "streams": [video, audio],
                 "head": (b"\0\0\0\x10ftyp" + b"\0" * 8
                          + b"\0\0\0\x08moov" + b"\0\0\0\x08mdat"),
                 "keyframes": keys, "size": 600000000}
        facts.update(self.preview_changes)
        return facts

    def convert(self, src, dst, track, log):
        self.converted.append((src, dst, track))
        with open(dst, "w") as handle:
            handle.write("wav")
        if self.convert_error:
            raise self.convert_error

    def probe_wav(self, path):
        stream = {"codec_type": "audio", "codec_name": "pcm_s16le",
                  "sample_rate": "24000", "channels": 1,
                  "duration_ts": self.source_samples // 2}
        stream.update(self.wav_changes)
        return {"streams": [stream]}


class FakeProgram:
    """A programme module: jobs, where each source is, what is there."""

    NAME = "aiyalaeho"
    SOURCE = "Kari-SRT/aiyalaeho/smkul.csv"

    def __init__(self, names, source_ext=".mkv", missing=(), listed=()):
        self.names = list(names)
        self.source_ext = source_ext
        self.missing = set(missing)
        self.listed = set(listed)
        self.listed_calls = 0

    def jobs(self, limit=0):
        out = []
        names = self.names[:limit] if limit else self.names
        for name in names:
            out.append(make_job(name))
        return out

    def locate(self, job, sftp, log):
        if job.label in self.missing:
            raise RuntimeError("揣無來源：/docker/a/%s%s、/home/b/%s%s"
                               % (job.label, self.source_ext, job.label,
                                  self.source_ext))
        return "/docker/src/%s%s" % (job.label, self.source_ext), "原始"

    def listing(self, sftp, jobs):
        self.listed_calls += 1
        return set(self.listed)


def make_job(name):
    return batch.Job(name, "/home/aiyalaeho/mp4/%s.mp4" % name,
                     preview="/home/aiyalaeho/mp4/%s.mp4" % name,
                     wav="/home/aiyalaeho/wav/%s.wav" % name)


def path_of(cmd):
    """Which encode path an ffmpeg command line belongs to."""
    if "-hwaccel" in cmd:
        return encode.HARDWARE
    if "-vaapi_device" in cmd:
        return encode.HYBRID
    return encode.SOFTWARE
