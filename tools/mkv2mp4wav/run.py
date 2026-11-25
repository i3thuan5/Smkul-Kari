"""One episode: download once, make what is missing, check it, upload it.

Knows nothing about which programme it is working for: the programme
module supplies `locate(job, sftp, log)`, and the job carries the two
remote paths (`job.preview`, `job.wav`).

The two outputs are independent. Each is skipped if its final name is
already on the server, and each has its own try: a WAV that fails its
check does not stop the preview going up, and the episode is recorded
as failed naming which one. Only Ctrl+C escapes.

Whatever happens, the downloaded source and both local products are
deleted before returning: the disk has filled up twice before when
downloaded episodes were left behind.
"""
import os

from scripts.news import audio as news_audio
from scripts.news import video_names
from tools.sftpbatch import upload
from tools.mkv2mp4wav import audio
from tools.mkv2mp4wav import encode
from tools.mkv2mp4wav import tracks
from tools.mkv2mp4wav import verify

PASSED = "通過"


class Rejected(Exception):
    """The product was made but failed its acceptance check."""


def _start(stream):
    try:
        return float(stream.get("start_time"))
    except (TypeError, ValueError):
        return None


def probe_source(path, count_frames=True):
    """What the episode needs to know about its downloaded source.

    Counting frames reads the whole file (tens of seconds for 2.5 GB), so
    it is skipped when only the WAV is being made.
    """
    info = verify.streams_and_format(path)
    videos = []
    audios = []
    for stream in info.get("streams", []):
        if stream.get("codec_type") == "video":
            videos.append(stream)
        elif stream.get("codec_type") == "audio":
            audios.append(stream)
    frames = None
    if count_frames:
        frames = verify.video_packets(path)[0]
    return {
        "container": audio.container_of(info["format"]["format_name"]),
        "pix_fmt": videos[0].get("pix_fmt") if videos else None,
        "frames": frames,
        "video_start": _start(videos[0]) if videos else None,
        "duration": float(info["format"]["duration"]),
        "audio": audios,
        "size": os.path.getsize(path),
    }


class Tools:
    """Every outside action, as attributes so tests can swap them."""

    def __init__(self):
        self.sftp = video_names.Sftp()
        self.already_there = upload.already_there
        self.put = upload.put
        self.probe_source = probe_source
        self.meter = tracks.Meter
        self.encode = encode.encode
        self.probe_preview = verify.probe
        self.convert = audio.convert
        self.probe_wav = audio.probe

    def fetch(self, remote, local):
        news_audio.fetch_video(remote, local, sftp=self.sftp)


def _make_preview(tools, src, facts, choice, local, remote, software, log,
                  part):
    path = encode.choose_path(facts["pix_fmt"], software)
    part["編碼路徑"] = path
    tools.encode(encode.command(src, local, choice.index, path),
                 facts["duration"], log)
    got = tools.probe_preview(local)
    part["影格數"] = {"來源": facts["frames"], "預覽檔": got["frames"]}
    wanted = {"frames": facts["frames"], "video_start": facts["video_start"],
              "audio_start": _start(facts["audio"][choice.index]),
              "duration": facts["duration"]}
    problems = verify.problems(verify.check_all(wanted, got))
    if problems:
        part["驗收"] = problems
        raise Rejected("；".join(problems))
    part["驗收"] = PASSED
    size = os.path.getsize(local)
    part["位元組數"] = tools.put(local, remote, size)


def _make_wav(tools, src, facts, choice, samples, local, remote, log, part):
    if choice.problem:
        raise Rejected(choice.problem)
    reason = audio.precheck(facts["container"], facts["audio"][choice.index])
    if reason:
        raise Rejected(reason)
    tools.convert(src, local, choice.index, log)
    problems = audio.verify(tools.probe_wav(local), samples)
    if problems:
        part["驗收"] = problems
        raise Rejected("；".join(problems))
    part["驗收"] = PASSED
    size = os.path.getsize(local)
    part["位元組數"] = tools.put(local, remote, size)


def _attempt(label, make, part, problems, log):
    """Run one output's steps; any failure but Ctrl+C is recorded."""
    try:
        make()
        part["結果"] = "成功"
    except KeyboardInterrupt:
        raise
    # 刁工掠規類：一種產出毋管按怎倒，攏袂使牽連另一種。
    except Exception as problem:
        part["結果"] = "失敗"
        part["原因"] = str(problem)
        problems.append("%s：%s" % (label, problem))
        log("%s失敗：%s" % (label, problem))


def one_episode(job, program, work_dir, software, log, tools=None):
    """Both outputs of one episode. Returns its manifest entry."""
    tools = tools or Tools()
    preview = {"遠端": job.preview, "位元組數": None, "驗收": None}
    wav = {"遠端": job.wav, "位元組數": None, "驗收": None}
    entry = {"預覽檔": preview, "音檔": wav}
    need_preview = not tools.already_there(job.preview)
    need_wav = not tools.already_there(job.wav)
    if not need_preview:
        preview["結果"] = "已存在"
    if not need_wav:
        wav["結果"] = "已存在"
    if not need_preview and not need_wav:
        entry["結果"] = "已存在"
        return entry

    remote, where = program.locate(job, tools.sftp, log)
    extension = os.path.splitext(remote)[1].lower()
    # The source keeps its own extension (an mp4 stays .mp4) and the
    # preview gets ".preview.mp4", so an mp4 source and its preview can
    # never be the same file.
    local_src = os.path.join(work_dir, job.label + extension)
    local_preview = os.path.join(work_dir, job.label + ".preview.mp4")
    local_wav = os.path.join(work_dir, job.label + ".wav")
    entry["來源"] = {"遠端": remote, "位置": where}
    problems = []
    try:
        tools.fetch(remote, local_src)
        facts = tools.probe_source(local_src, count_frames=need_preview)
        entry["來源"]["位元組數"] = facts["size"]
        entry["來源"]["影格數"] = facts["frames"]
        meter = tools.meter()
        choice = tracks.pick(local_src, len(facts["audio"]), meter.mean)
        entry["音軌"] = {"第幾條": choice.index + 1,
                       "平均音量": choice.mean_db}
        if need_preview:
            _attempt("預覽檔", lambda: _make_preview(
                tools, local_src, facts, choice, local_preview, job.preview,
                software, log, preview), preview, problems, log)
        if need_wav:
            samples = meter.samples.get(choice.index)
            _attempt("音檔", lambda: _make_wav(
                tools, local_src, facts, choice, samples, local_wav,
                job.wav, log, wav), wav, problems, log)
    finally:
        for path in (local_src, local_preview, local_wav):
            if os.path.exists(path):
                os.remove(path)
    if problems:
        entry["結果"] = "失敗"
        entry["原因"] = "；".join(problems)
    else:
        entry["結果"] = "成功"
    return entry
